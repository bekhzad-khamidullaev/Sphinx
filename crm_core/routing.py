from django.urls import re_path, path
from . import consumers

websocket_urlpatterns = [
    path("ws/tasks/", consumers.TaskConsumer.as_asgi()),
    path("ws/campaigns/", consumers.CampaignConsumer.as_asgi()),
    path("ws/teams/", consumers.TeamConsumer.as_asgi()),
    path("ws/users/", consumers.UserConsumer.as_asgi()),
    path("ws/generic/<str:group>/", consumers.GenericConsumer.as_asgi()),
]