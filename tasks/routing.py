# tasks/routing.py
# -*- coding: utf-8 -*-

from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # Task list and individual task updates (can be combined or separate)
    re_path(r'^ws/tasks/$', consumers.TaskConsumer.as_asgi()), # For general task list updates
    re_path(r'^ws/tasks/(?P<task_id>\d+)/$', consumers.TaskConsumer.as_asgi()), # For specific task updates

    # Generic consumer for various model updates if a single group is used per model type
    # Example: /ws/updates/projects/ or /ws/updates/projects/project_123/
    re_path(r'^ws/updates/(?P<group_name_prefix>\w+)/$', consumers.ModelUpdateConsumerBase.as_asgi()),
    re_path(r'^ws/updates/(?P<group_name_prefix>\w+)/(?P<group_identifier>\w+)/$', consumers.ModelUpdateConsumerBase.as_asgi()),

    # Specific model consumers (can use ModelUpdateConsumerBase or be custom)
    re_path(r'^ws/projects/$', consumers.ProjectConsumer.as_asgi()), # List updates
    # re_path(r'^ws/project/(?P<group_identifier>\d+)/$', consumers.ProjectConsumer.as_asgi()), # Specific project

    re_path(r'^ws/categories/$', consumers.CategoryConsumer.as_asgi()),
    re_path(r'^ws/subcategories/$', consumers.SubcategoryConsumer.as_asgi()),
    re_path(r'^ws/teams/$', consumers.TeamConsumer.as_asgi()),
    re_path(r'^ws/users/$', consumers.UserConsumer.as_asgi()), # General user list or specific user updates

    # Comments for a specific task
    re_path(r'^ws/tasks/(?P<task_id>\d+)/comments/$', consumers.TaskCommentConsumer.as_asgi()),
]