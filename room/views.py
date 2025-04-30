# room/views.py
import json
import logging
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden, JsonResponse, Http404
from django.views.decorators.http import require_POST, require_GET
from django.db.models import Q, Max, OuterRef, Subquery
from django.utils.text import slugify
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib import messages # For displaying messages
from django.utils.translation import gettext_lazy as _

from .models import Room, Message, MessageReadStatus # Removed Reaction import, not used here
from .forms import RoomForm # Import the form

User = get_user_model()
logger = logging.getLogger(__name__)

@login_required
def rooms(request):
    """Displays a list of accessible, non-archived chat rooms."""
    # Subquery to get the timestamp of the last message in each room
    last_message_subquery = Message.objects.filter(
        room=OuterRef('pk')
    ).order_by('-date_added').values('date_added')[:1]

    # Filter rooms: not archived AND (public OR user is a participant)
    rooms_list = Room.objects.filter(
        Q(is_archived=False) &
        (Q(private=False) | Q(participants=request.user))
    ).annotate(
        last_message_time=Subquery(last_message_subquery) # Annotate with last message time
    ).select_related().distinct().order_by('-last_message_time', '-updated_at') # Order by activity

    # TODO: Implement efficient unread count calculation here if needed

    return render(request, 'room/rooms.html', {'rooms': rooms_list})

@login_required
def room(request, slug):
    """Displays a specific chat room and its messages."""
    room_obj = get_object_or_404(Room, slug=slug, is_archived=False)

    # Permission Check
    if room_obj.private and not request.user in room_obj.participants.all():
        # Use HttpResponseForbidden or redirect for better UX than 404
        logger.warning(f"User {request.user.username} denied access to private room '{slug}'.")
        messages.error(request, _("У вас нет доступа к этой приватной комнате."))
        return redirect('room:rooms')
        # raise Http404("Permission Denied.") # Or keep 404 if preferred

    # Fetch initial messages (limit the load)
    message_queryset = Message.objects.filter(room=room_obj) \
                                      .select_related('user', 'reply_to__user') \
                                      .prefetch_related('reactions__user') \
                                      .order_by('date_added')
    messages_list = list(message_queryset[:100]) # Load latest 100 initially

    # Get other rooms for sidebar (limit for performance)
    rooms_for_sidebar = Room.objects.filter(
        Q(is_archived=False) & (Q(private=False) | Q(participants=request.user))
    ).exclude(pk=room_obj.pk).distinct().order_by('-updated_at')[:20]

    # Mark messages as read up to the latest one shown
    if messages_list:
        last_message = messages_list[-1]
        try:
            MessageReadStatus.objects.update_or_create(
                user=request.user,
                room=room_obj,
                defaults={'last_read_message': last_message}
            )
            logger.debug(f"Updated read status for user {request.user.id} in room {room_obj.id} to message {last_message.id}")
        except Exception as e:
             logger.error(f"Error updating read status for user {request.user.id} in room {room_obj.id}: {e}")


    context = {
        'room': room_obj,
        'messages': messages_list,
        'rooms_for_sidebar': rooms_for_sidebar,
    }
    return render(request, 'room/room.html', context)

@login_required
def create_room(request):
    """Handles creation of new chat rooms using a form."""
    if request.method == 'POST':
        form = RoomForm(request.POST, user=request.user) # Pass user to exclude from choices
        if form.is_valid():
            try:
                # Form's save method handles slug generation and adding creator
                room_instance = form.save(commit=False)
                room_instance.save() # Save instance first to get PK
                form.save_m2m() # Save M2M participants

                # Manually add creator if not added by form logic (form's save should handle this now)
                if request.user not in room_instance.participants.all():
                     room_instance.participants.add(request.user)

                logger.info(f"Room '{room_instance.name}' (slug: {room_instance.slug}) created by {request.user.username}")
                messages.success(request, _("Комната '%(name)s' успешно создана.") % {'name': room_instance.name})
                return redirect('room:room', slug=room_instance.slug)
            except Exception as e:
                 logger.exception(f"Error creating room by user {request.user.username}: {e}")
                 messages.error(request, _("Произошла ошибка при создании комнаты."))
        else:
            logger.warning(f"Invalid RoomForm submission by {request.user.username}: {form.errors.as_json()}")
            # Fall through to render form with errors
    else: # GET request
        form = RoomForm(user=request.user)

    # Exclude self from user list shown in template (form queryset handles actual exclusion)
    users_for_template = User.objects.filter(is_active=True).exclude(pk=request.user.pk).order_by('username')
    context = {
        'form': form,
        'users': users_for_template # For potential JS or display if needed
    }
    return render(request, 'room/create_room.html', context)


# --- API-like views ---

@require_POST # Use POST for actions that change state
@login_required
def archive_room(request, slug):
    room_obj = get_object_or_404(Room, slug=slug)
    # More robust permission check (e.g., only participants or staff)
    if not request.user.is_staff and request.user not in room_obj.participants.all():
         logger.warning(f"User {request.user.username} attempted to archive room '{slug}' without permission.")
         return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    if room_obj.is_archived:
        return JsonResponse({'success': True, 'message': 'Room already archived'})

    room_obj.is_archived = True
    room_obj.save(update_fields=['is_archived'])
    logger.info(f"Room '{slug}' archived by user {request.user.username}.")
    return JsonResponse({'success': True, 'message': 'Room archived'})

# Consider adding unarchive view as well

@require_GET # Search is generally a GET request
@login_required
def search_messages(request, slug):
    room_obj = get_object_or_404(Room, slug=slug)
    # Permission check
    if room_obj.private and request.user not in room_obj.participants.all():
         logger.warning(f"User {request.user.username} attempted to search private room '{slug}' without permission.")
         return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    query = request.GET.get('q', '').strip()
    if len(query) < 2: # Require minimum query length
        return JsonResponse({'success': False, 'error': 'Query parameter "q" must be at least 2 characters.'}, status=400)

    # TODO: Implement Full-Text Search using search_vector if using PostgreSQL
    # from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
    # vector = SearchVector('content', config='russian' if settings.LANGUAGE_CODE.startswith('ru') else 'english')
    # search_query = SearchQuery(query, config='russian' if settings.LANGUAGE_CODE.startswith('ru') else 'english')
    # results = Message.objects.annotate(rank=SearchRank(vector, search_query)) \
    #                          .filter(room=room_obj, is_deleted=False, rank__gte=0.1) \
    #                          .order_by('-rank', '-date_added') \
    #                          .select_related('user')[:20]

    # Basic search fallback
    results = Message.objects.filter(
        room=room_obj,
        content__icontains=query,
        is_deleted=False
    ).select_related('user').order_by('-date_added')[:20] # Limit results

    # Simple serialization
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