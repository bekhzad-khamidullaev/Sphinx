# room/routing.py
from django.urls import path
from .consumers import ChatConsumer#, UserSearchConsumer

websocket_urlpatterns = [
    path('ws/chat/<str:room_name>/', ChatConsumer.as_asgi()),
    #path("ws/user_search/", UserSearchConsumer.as_asgi()), # Если используется
]