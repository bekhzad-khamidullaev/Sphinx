# filename: room/views.py
import json
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden, JsonResponse, Http404
from django.views.decorators.http import require_POST, require_GET
from django.db.models import Q, Max, OuterRef, Subquery
from django.utils.text import slugify
from django.conf import settings
from django.contrib.auth import get_user_model
# from user_profiles.models import User # Keep if correct
User = get_user_model()
from .models import Room, Message, MessageReadStatus, Reaction # Import new models

@login_required
def rooms(request):
    # Show non-archived rooms the user can access
    # Also annotate with last message timestamp for ordering (optional but nice)
    # Annotate with unread status
    user_read_status = MessageReadStatus.objects.filter(
        user=request.user,
        room=OuterRef('pk')
    ).select_related('last_read_message')

    last_message_subquery = Message.objects.filter(
        room=OuterRef('pk')
    ).order_by('-date_added').values('date_added')[:1]

    rooms_list = Room.objects.filter(
        Q(is_archived=False) &
        (Q(private=False) | Q(participants=request.user))
    ).annotate(
        last_message_time=Subquery(last_message_subquery),
        # last_read_id=Subquery(user_read_status.values('last_read_message_id')), # Needs refinement
    ).select_related().distinct().order_by('-last_message_time') # Order by most recent activity

    # Further refine unread logic here or in template based on last_read_id vs max message id
    # For simplicity, passing the raw list for now.

    return render(request, 'room/rooms.html', {'rooms': rooms_list})

@login_required
def room(request, slug):
    room_obj = get_object_or_404(Room, slug=slug, is_archived=False) # Don't show archived rooms directly

    # Check permissions
    if room_obj.private and not room_obj.participants.filter(pk=request.user.pk).exists():
        raise Http404("You don't have permission to access this private room.") # Use 404 for private rooms

    # Fetch messages with related data
    messages = Message.objects.filter(room=room_obj).select_related('user', 'reply_to__user').prefetch_related('reactions__user').order_by('date_added')[:100] # Limit initial load

    # Get other rooms for sidebar (consider performance for many rooms)
    rooms_for_sidebar = Room.objects.filter(
        Q(is_archived=False) & (Q(private=False) | Q(participants=request.user))
    ).distinct().order_by('-updated_at')[:20] # Limit sidebar rooms

    # Mark messages as read up to the latest one shown (can be refined)
    if messages:
        last_message = messages.last()
        MessageReadStatus.objects.update_or_create(
            user=request.user,
            room=room_obj,
            defaults={'last_read_message': last_message}
        )

    # Get initial online users (can also be fetched via WebSocket on connect)
    # online_users = room_obj.get_online_users() # Placeholder - implement using Redis check

    return render(request, 'room/room.html', {
        'room': room_obj,
        'messages': messages,
        'rooms_for_sidebar': rooms_for_sidebar,
        # 'online_users': online_users, # Pass if fetched here
    })

@login_required
def create_room(request):
    users = User.objects.exclude(pk=request.user.pk) # Exclude self from participant list

    if request.method == 'POST':
        # Use Django forms for proper validation
        name = request.POST.get('name', '').strip()
        private = request.POST.get('private') == 'on'
        participants_ids = request.POST.getlist('participants')

        if not name:
             # Handle error - return form with error message
             return render(request, 'room/create_room.html', {'users': users, 'error': 'Room name is required.'})

        slug = slugify(name)
        # Check if slug exists, append counter if needed
        counter = 1
        original_slug = slug
        while Room.objects.filter(slug=slug).exists():
            slug = f"{original_slug}-{counter}"
            counter += 1

        room = Room.objects.create(name=name, slug=slug, private=private)

        # Add creator and selected participants
        participants_to_add = [request.user.pk]
        if private:
            # Validate participant IDs
            valid_participants = User.objects.filter(pk__in=participants_ids)
            participants_to_add.extend([p.pk for p in valid_participants])

        room.participants.add(*participants_to_add)
        room.save()

        return redirect('room:room', slug=room.slug)

    # GET request
    return render(request, 'room/create_room.html', {'users': users})


# --- API-like views (could be moved to a dedicated API app) ---

@require_POST
@login_required
def archive_room(request, slug):
    room_obj = get_object_or_404(Room, slug=slug)
    # Permission check: maybe only participants or specific roles can archive?
    if request.user not in room_obj.participants.all() and not request.user.is_staff:
         return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    # Simple archive: hides for everyone. Per-user needs different logic.
    room_obj.is_archived = True
    room_obj.save(update_fields=['is_archived'])
    return JsonResponse({'success': True, 'message': 'Room archived'})

@require_GET
@login_required
def search_messages(request, slug):
    room_obj = get_object_or_404(Room, slug=slug)
    # Permission check
    if room_obj.private and not room_obj.participants.filter(pk=request.user.pk).exists():
         return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    query = request.GET.get('q', '').strip()
    if not query:
        return JsonResponse({'success': False, 'error': 'Query parameter "q" is required.'}, status=400)

    # Basic search (replace with FTS later if using PostgreSQL)
    results = Message.objects.filter(
        room=room_obj,
        content__icontains=query,
        is_deleted=False # Exclude deleted
    ).select_related('user').order_by('-date_added')[:20] # Limit results

    # Serialize results (consider a serializer function/class)
    messages_data = [
        {
            'id': str(msg.id),
            'user': msg.user.username,
            'content': msg.content,
            'timestamp': msg.date_added.isoformat(),
         } for msg in results
    ]

    return JsonResponse({'success': True, 'messages': messages_data})

# Add URL patterns for these new views in urls.py