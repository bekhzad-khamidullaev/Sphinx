from . import views
from django.urls import path
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r'roles', views.RoleViewSet)
router.register(r'users', views.UserViewSet)
router.register(r'teams', views.TeamViewSet)

app_name = "user_profiles"

urlpatterns = [
    path('', views.base, name='base'),
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),
    # Team management URLs
    path('teams/', views.team_list, name='team_list'),
    path('teams/create/', views.modal_create_team, name='modal_create_team'),
    path('teams/<int:pk>/update/', views.modal_update_team, name='modal_update_team'),
    path('teams/<int:pk>/delete/', views.modal_delete_team, name='modal_delete_team'),
    path('teams/create/', views.create_team, name='create_team'),
    path('teams/<int:pk>/delete/', views.delete_team, name='delete_team'),
    # Role management URLs
    path('roles/', views.role_list, name='role_list'),
    path('roles/create/', views.role_create, name='role_create'),
    path('roles/<int:pk>/delete/', views.role_delete, name='role_delete'),
    # User management URLs
    path('users/create/', views.modal_create_user, name='modal_create_user'),
    path('users/<int:pk>/update/', views.modal_update_user, name='modal_update_user'),
    path('users/<int:pk>/delete/', views.modal_delete_user, name='modal_delete_user'),
    path('users/create/', views.create_user, name='create_user'),
    path('users/<int:pk>/delete/', views.delete_user, name='delete_user'),


]
