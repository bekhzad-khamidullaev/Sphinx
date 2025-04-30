from django.urls import path
from .consumers import ChatConsumer, UserSearchConsumer


websocket_urlpatterns = [
    # Path for the main chat room connection
    path('ws/chat/<str:room_name>/', ChatConsumer.as_asgi()),
    # Path for the user search functionality
    path("ws/user_search/", UserSearchConsumer.as_asgi()),
]