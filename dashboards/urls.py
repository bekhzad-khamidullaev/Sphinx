from django.urls import path
from . import views

app_name = 'dashboards'

urlpatterns = [
    path('tasks/', views.TaskDashboardView.as_view(), name='task_dashboard'),
]
