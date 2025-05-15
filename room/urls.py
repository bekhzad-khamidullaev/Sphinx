# room/urls.py
from django.urls import path
from . import views

app_name = 'room'

urlpatterns = [
    path('', views.room_list_view, name='rooms'),
    path('create/', views.room_create_view, name='create_room'),
    path('<slug:slug>/', views.room_detail_view, name='room'),
    path('<slug:slug>/archive/', views.room_archive_view, name='archive_room'), # AJAX
    path('<slug:slug>/search-messages/', views.message_search_view, name='search_messages'), # AJAX/HTTP
]