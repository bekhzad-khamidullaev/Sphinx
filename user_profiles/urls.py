# user_profiles/urls.py
from django.urls import path, include # Добавлен include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
# --- Удаляем регистрацию RoleViewSet ---
# router.register(r'roles', views.RoleViewSet)
# ---
router.register(r'users', views.UserViewSet)
router.register(r'teams', views.TeamViewSet)
# Add DepartmentViewSet if needed
# from .serializers import DepartmentSerializer
# class DepartmentViewSet(viewsets.ReadOnlyModelViewSet): # ReadOnly example
#     queryset = Department.objects.all()
#     serializer_class = DepartmentSerializer
# router.register(r'departments', DepartmentViewSet)

app_name = "user_profiles"

urlpatterns = [
    # Authentication URLs
    path('', views.base, name='base'), # Assuming base handles login form display
    path('login/', views.user_login, name='login'), # Or directly render login form here
    path('logout/', views.user_logout, name='logout'),

    # API URLs from DRF Router
    path('api/', include(router.urls)),

    # Team management URLs (assuming modals trigger action views via POST)
    path('teams/', views.team_list, name='team_list'),
    path('teams/modal/create/', views.modal_create_team, name='modal_create_team'),
    path('teams/modal/update/<int:pk>/', views.modal_update_team, name='modal_update_team'),
    path('teams/modal/delete/<int:pk>/', views.modal_delete_team, name='modal_delete_team'),
    # Action URLs (POST requests)
    path('teams/action/create/', views.create_team, name='create_team'),
    # path('teams/action/update/<int:pk>/', views.update_team, name='update_team'), # Add update view if needed
    path('teams/action/delete/<int:pk>/', views.delete_team, name='delete_team'),

    # --- Удаляем URL-шаблоны для Role ---
    # path('roles/', views.role_list, name='role_list'),
    # path('roles/create/', views.role_create, name='role_create'), # Might be modal or action
    # path('roles/<int:pk>/delete/', views.role_delete, name='role_delete'), # Might be modal or action
    # ---

    # User management URLs (assuming modals trigger action views via POST)
    path('users/', views.user_list, name='user_list'), # Added user list URL
    path('users/modal/create/', views.modal_create_user, name='modal_create_user'),
    path('users/modal/update/<int:pk>/', views.modal_update_user, name='modal_update_user'),
    path('users/modal/delete/<int:pk>/', views.modal_delete_user, name='modal_delete_user'),
    # Action URLs (POST requests)
    path('users/action/create/', views.create_user, name='create_user'),
    # path('users/action/update/<int:pk>/', views.update_user, name='update_user'), # Add update view if needed
    path('users/action/delete/<int:pk>/', views.delete_user, name='delete_user'),

    # Add Department URLs if needed
    # path('departments/', views.department_list, name='department_list'),

]