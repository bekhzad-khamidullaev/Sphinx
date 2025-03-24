from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/tasks/', consumers.TaskConsumer.as_asgi()),
    # Task update WebSocket connection
    re_path(r'ws/task_updates/', consumers.TaskConsumer.as_asgi()),  # Removed the extra $ at the end

    # Generic WebSocket connection (e.g., for receiving updates)
    re_path(r'ws/generic/(?P<group>\w+)/$', consumers.GenericConsumer.as_asgi()),

    # Project WebSocket connection
    re_path(r'ws/projects/$', consumers.ProjectConsumer.as_asgi()),

    # Team WebSocket connection
    re_path(r'ws/teams/$', consumers.TeamConsumer.as_asgi()),

    # User WebSocket connection
    re_path(r'ws/users/$', consumers.UserConsumer.as_asgi()),
]
