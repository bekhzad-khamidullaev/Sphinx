# tasks/routing.py
# -*- coding: utf-8 -*-

from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # Обновления для списков моделей
    re_path(r'^ws/tasks_list/$', consumers.TaskConsumer.as_asgi()), # Для общего списка задач
    re_path(r'^ws/projects_list/$', consumers.ProjectConsumer.as_asgi()),
    re_path(r'^ws/categories_list/$', consumers.CategoryConsumer.as_asgi()),
    re_path(r'^ws/subcategories_list/$', consumers.SubcategoryConsumer.as_asgi()),

    # Обновления для конкретных экземпляров моделей (например, для детальных страниц)
    re_path(r'^ws/tasks/(?P<task_id>\d+)/updates/$', consumers.TaskConsumer.as_asgi()),
    re_path(r'^ws/projects/(?P<project_id>\d+)/updates/$', consumers.ProjectConsumer.as_asgi()),
    re_path(r'^ws/categories/(?P<category_id>\d+)/updates/$', consumers.CategoryConsumer.as_asgi()),
    re_path(r'^ws/subcategories/(?P<subcategory_id>\d+)/updates/$', consumers.SubcategoryConsumer.as_asgi()),

    # Комментарии для конкретной задачи
    re_path(r'^ws/tasks/(?P<task_id>\d+)/comments/$', consumers.TaskCommentConsumer.as_asgi()),

    # Общий потребитель, если используется (менее предпочтительно для типизированных обновлений)
    # re_path(r'^ws/updates/(?P<group_name_prefix>\w+)/$', consumers.ModelUpdateConsumerBase.as_asgi()),
    # re_path(r'^ws/updates/(?P<group_name_prefix>\w+)/(?P<group_identifier>\w+)/$', consumers.ModelUpdateConsumerBase.as_asgi()),
]