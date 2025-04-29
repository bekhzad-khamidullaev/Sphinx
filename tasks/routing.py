from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # Задачи — без параметров
    re_path(r'^ws/tasks/$', consumers.TaskConsumer.as_asgi()),

    # Обновления задач — без параметров
    re_path(r'^ws/task_updates/$', consumers.TaskConsumer.as_asgi()),

    # Generic обновления по группе — обязательно с именем группы
    re_path(r'^ws/generic/(?P<group>\w+)/$', consumers.GenericConsumer.as_asgi()),

    # Проекты — без параметров
    re_path(r'^ws/projects/$', consumers.ProjectConsumer.as_asgi()),

    # Команды — без параметров
    re_path(r'^ws/teams/$', consumers.TeamConsumer.as_asgi()),

    # Пользователи — без параметров
    re_path(r'^ws/users/$', consumers.UserConsumer.as_asgi()),

    # Комментарии к задачам — с ID задачи
    re_path(r'^ws/tasks/(?P<task_id>\d+)/comments/$', consumers.TaskCommentConsumer.as_asgi()),
]
