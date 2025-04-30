# room/urls.py
from django.urls import path
from . import views

app_name = 'room'

urlpatterns = [
    path('', views.rooms, name='rooms'),
    path('create/', views.create_room, name='create_room'), # Add create room URL
    path('<slug:slug>/', views.room, name='room'),
    # API-like endpoints
    path('<slug:slug>/archive/', views.archive_room, name='archive_room'),
    path('<slug:slug>/search/', views.search_messages, name='search_messages'),
]