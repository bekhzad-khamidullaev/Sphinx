# room/views.py
import json
import logging
import uuid # Needed for slug fallback
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden, JsonResponse, Http404
from django.views.decorators.http import require_POST, require_GET
from django.db.models import Q, Max, OuterRef, Subquery
from django.utils.text import slugify
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.db import transaction # Import transaction
from .models import Room, Message, MessageReadStatus

from .models import Room, Message, MessageReadStatus # Removed Reaction import, not used here
from .forms import RoomForm # Import the form

User = get_user_model()
logger = logging.getLogger(__name__)

@login_required
def rooms(request):
    """Displays a list of accessible, non-archived chat rooms with unread status."""

    # Subquery for the ID of the last message in each room
    last_message_id_subquery = Message.objects.filter(
        room=OuterRef('pk'), is_deleted=False
    ).order_by('-date_added').values('id')[:1]

    # Subquery for the ID of the last message READ BY THE CURRENT USER in each room
    user_last_read_id_subquery = MessageReadStatus.objects.filter(
        user=request.user,
        room=OuterRef('pk')
    ).values('last_read_message_id')[:1] #[:1] handles potential None

    # Filter rooms and annotate
    rooms_list = Room.objects.filter(
        Q(is_archived=False) &
        (Q(private=False) | Q(participants=request.user))
    ).annotate(
        # Get the ID of the very last message
        room_last_message_id=Subquery(last_message_id_subquery),
        # Get the ID of the last message read by the user (can be NULL)
        user_last_read_message_id=Subquery(user_last_read_id_subquery),
        # Optimize by getting last message time too for ordering
        last_message_time=Subquery(last_message_id_subquery.values('date_added'))
    ).select_related().distinct().order_by('-last_message_time', '-updated_at')

    # Calculate unread status based on annotations directly (more efficient)
    # We don't need the exact count here, just whether unread exist
    processed_rooms = []
    for room in rooms_list:
        # Determine if unread:
        # 1. User has never read (user_last_read_message_id is None) AND room has messages (room_last_message_id exists)
        # 2. User has read, but the room's last message ID is different from the user's last read ID
        #    (Note: Assumes IDs are sequential like UUIDv1 or auto-increment int. If not, compare timestamps)
        has_unread = (room.room_last_message_id is not None) and \
                     (room.user_last_read_message_id is None or \
                      room.room_last_message_id != room.user_last_read_message_id)

        room.has_unread = has_unread # Add the flag directly to the room object for template use
        processed_rooms.append(room)

    return render(request, 'room/rooms.html', {'rooms': processed_rooms}) # Pass processed list

@login_required
def room(request, slug):
    """Displays a specific chat room and its messages."""
    room_obj = get_object_or_404(Room.objects.prefetch_related('participants'), slug=slug, is_archived=False)
    if room_obj.private and request.user not in room_obj.participants.all():
        messages.error(request, _("У вас нет доступа к этой приватной комнате."))
        return redirect('room:rooms')

    # Fetch initial messages
    message_queryset = Message.objects.filter(room=room_obj) \
                                      .select_related('user', 'reply_to__user') \
                                      .prefetch_related('reactions__user') \
                                      .order_by('date_added')
    messages_list = list(message_queryset[:100])

    # Get other rooms for sidebar (with unread status)
    last_message_id_subquery = Message.objects.filter(room=OuterRef('pk'), is_deleted=False).order_by('-date_added').values('id')[:1]
    user_last_read_id_subquery = MessageReadStatus.objects.filter(user=request.user,room=OuterRef('pk')).values('last_read_message_id')[:1]
    rooms_for_sidebar_qs = Room.objects.filter(
        Q(is_archived=False) & (Q(private=False) | Q(participants=request.user))
    ).exclude(pk=room_obj.pk).annotate(
        room_last_message_id=Subquery(last_message_id_subquery),
        user_last_read_message_id=Subquery(user_last_read_id_subquery),
        last_message_time=Subquery(last_message_id_subquery.values('date_added'))
    ).distinct().order_by('-last_message_time', '-updated_at')[:20] # Limit sidebar rooms

    rooms_for_sidebar_processed = []
    for r in rooms_for_sidebar_qs:
         r.has_unread = (r.room_last_message_id is not None) and \
                        (r.user_last_read_message_id is None or \
                         r.room_last_message_id != r.user_last_read_message_id)
         rooms_for_sidebar_processed.append(r)


    # Mark messages as read
    if messages_list:
        # ... (mark as read logic as before) ...
        last_message = messages_list[-1]
        try:
            MessageReadStatus.objects.update_or_create(
                user=request.user, room=room_obj,
                defaults={'last_read_message': last_message}
            )
        except Exception as e: logger.error(f"Error updating read status: {e}")


    context = {
        'room': room_obj,
        'messages': messages_list,
        'rooms_for_sidebar': rooms_for_sidebar_processed, # Pass processed list
    }
    return render(request, 'room/room.html', context)

@login_required
def create_room(request):
    """Handles creation of new chat rooms using a form."""
    if request.method == 'POST':
        form = RoomForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                # Create instance in memory
                room_instance = form.save(commit=False)
                # Note: creator isn't set on the model, user is passed to form init for queryset filtering

                # --- Generate unique slug ---
                base_slug = slugify(room_instance.name) or f"room-{uuid.uuid4().hex[:8]}" # Ensure non-empty base
                slug = base_slug
                counter = 1
                while Room.objects.filter(slug=slug).exists():
                     slug = f"{base_slug}-{counter}"
                     counter += 1
                room_instance.slug = slug
                logger.info(f"Generated unique slug '{slug}' for room '{room_instance.name}'")
                # --- End slug generation ---

                # Now save the instance with the unique slug
                room_instance.save()
                # Save ManyToMany participants *after* instance is saved
                form.save_m2m()

                # Add creator to participants explicitly after saving M2M
                if request.user not in room_instance.participants.all():
                    room_instance.participants.add(request.user)
                    logger.info(f"Added creator {request.user.username} to participants of room {room_instance.slug}")

                logger.info(f"Room '{room_instance.name}' (slug: {room_instance.slug}) created successfully by {request.user.username}")
                messages.success(request, _("Комната '%(name)s' успешно создана.") % {'name': room_instance.name})
                return redirect('room:room', slug=room_instance.slug) # Redirect to the new room

            except Exception as e:
                 logger.exception(f"Error creating room by user {request.user.username}: {e}")
                 messages.error(request, _("Произошла ошибка при создании комнаты."))
                 # Re-render the form with the original (failed) form object containing errors
                 # Users list for template needs to be fetched again
                 users_for_template = User.objects.filter(is_active=True).exclude(pk=request.user.pk).order_by('username')
                 return render(request, 'room/create_room.html', {'form': form, 'users': users_for_template})
        else:
            # Form is invalid, re-render with errors
            logger.warning(f"Invalid RoomForm submission by {request.user.username}: {form.errors.as_json()}")
            # Fall through to render GET part with the invalid form
    else: # GET request
        form = RoomForm(user=request.user) # Pass user to exclude self from choices

    # Exclude self from user list shown in template (form queryset handles actual exclusion)
    users_for_template = User.objects.filter(is_active=True).exclude(pk=request.user.pk).order_by('username')
    context = {
        'form': form,
        'users': users_for_template # For potential display if not using form rendering
    }
    return render(request, 'room/create_room.html', context)


# --- API-like views ---
@require_POST # Use POST for state changes
@login_required
def archive_room(request, slug):
    room_obj = get_object_or_404(Room, slug=slug)
    # Permission check
    if not request.user.is_staff and request.user not in room_obj.participants.all():
         logger.warning(f"User {request.user.username} attempted archive room '{slug}' without permission.")
         return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    if room_obj.is_archived:
        return JsonResponse({'success': True, 'message': 'Room already archived'})

    room_obj.is_archived = True
    room_obj.save(update_fields=['is_archived'])
    logger.info(f"Room '{slug}' archived by user {request.user.username}.")
    # Return success, JS should remove the room from the list
    return JsonResponse({'success': True, 'message': 'Room archived'})


@require_GET
@login_required
def search_messages(request, slug):
    room_obj = get_object_or_404(Room, slug=slug)
    if room_obj.private and request.user not in room_obj.participants.all():
         logger.warning(f"User {request.user.username} attempted to search private room '{slug}' without permission.")
         return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return JsonResponse({'success': False, 'error': 'Query must be at least 2 characters.'}, status=400)

    # Basic search fallback
    results = Message.objects.filter(
        room=room_obj,
        content__icontains=query,
        is_deleted=False
    ).select_related('user').order_by('-date_added')[:20] # Limit results

    messages_data = [
        {
            'id': str(msg.id),
            'user': msg.user.username if msg.user else 'System',
            'content': msg.content,
            'timestamp': msg.date_added.isoformat(),
            'reply_to_id': str(msg.reply_to.id) if msg.reply_to else None,
            'file_url': msg.file.url if msg.file else None,
         } for msg in results
    ]
    return JsonResponse({'success': True, 'messages': messages_data})