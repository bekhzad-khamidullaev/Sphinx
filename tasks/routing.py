# tasks/routing.py
# -*- coding: utf-8 -*-

from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # Task list and individual task updates
    re_path(r'^ws/tasks/$', consumers.TaskConsumer.as_asgi()), # Общий список задач (группа tasks_list)
    re_path(r'^ws/tasks/(?P<task_id>\d+)/$', consumers.TaskConsumer.as_asgi()), # Детали конкретной задачи (группа task_<task_id>)

    # Comments for a specific task
    re_path(r'^ws/tasks/(?P<task_id>\d+)/comments/$', consumers.TaskCommentConsumer.as_asgi()), # Комментарии к задаче (группа task_comments_<task_id>)

    # Specific model consumers for task-related entities
    # Эти консьюмеры (ProjectConsumer, CategoryConsumer, SubcategoryConsumer) должны быть определены в tasks/consumers.py
    # и могут наследовать ModelUpdateConsumerBase, если он там есть.
    re_path(r'^ws/projects/$', consumers.ProjectConsumer.as_asgi()),         # Обновления списка проектов (группа projects_list)
    re_path(r'^ws/categories/$', consumers.CategoryConsumer.as_asgi()),       # Обновления списка категорий (группа categories_list)
    re_path(r'^ws/subcategories/$', consumers.SubcategoryConsumer.as_asgi()), # Обновления списка подкатегорий (группа subcategories_list)

    # Если нужен общий consumer для моделей tasks с динамическим префиксом (менее предпочтительно, если есть специфичные)
    # re_path(r'^ws/updates/tasks/(?P<group_name_prefix>\w+)/$', consumers.ModelUpdateConsumerBase.as_asgi()),
    # re_path(r'^ws/updates/tasks/(?P<group_name_prefix>\w+)/(?P<group_identifier>\w+)/$', consumers.ModelUpdateConsumerBase.as_asgi()),
]