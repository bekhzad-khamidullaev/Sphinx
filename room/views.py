from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from user_profiles.models import User  # Make sure this import is correct
from django.http import HttpResponseForbidden
from django.db.models import Q

from .models import Room, Message

@login_required
def rooms(request):
    rooms = Room.objects.all()  # Or filter based on user access, etc.
    return render(request, 'room/rooms.html', {'rooms': rooms}) # A separate template for listing all rooms (optional)


@login_required
def room(request, slug):
    room = Room.objects.get(slug=slug)
    # Check if the room is private and if the user has access
    if room.private and request.user not in room.participants.all():
        return HttpResponseForbidden("You don't have permission to access this room.")


    rooms = Room.objects.filter(Q(private=False) | Q(participants=request.user)).distinct() # Fetch rooms for the sidebar
    messages = Message.objects.filter(room=room).order_by('date_added') # Get *all* messages, ordered by date
    return render(request, 'room/room.html', {'room': room, 'messages': messages, 'rooms': rooms})