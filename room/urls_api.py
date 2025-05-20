# room/urls_api.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views_api import RoomViewSet, MessageViewSet, UserSearchViewSet

app_name = 'room-api' # Для использования с reverse в тестах и т.д.

router = DefaultRouter()
router.register(r'rooms', RoomViewSet, basename='room')
router.register(r'messages', MessageViewSet, basename='message') # Для отдельных сообщений (если нужно)
router.register(r'users/search', UserSearchViewSet, basename='user-search') # Для поиска пользователей

urlpatterns = [
    path('', include(router.urls)),
]