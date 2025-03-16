from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from user_profiles.models import User
from django.http import HttpResponseForbidden

from .models import Room, Message

@login_required
def rooms(request):
    rooms = Room.objects.all()

    return render(request, 'room/room.html', {'rooms': rooms})

@login_required
def room(request, slug):
    rooms = Room.objects.all()
    room = Room.objects.get(slug=slug)
    messages = Message.objects.filter(room=room)[0:25]

    return render(request, 'room/room.html', {'room': room, 'messages': messages, 'rooms': rooms})
