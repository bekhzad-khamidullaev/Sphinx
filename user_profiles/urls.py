# user_profiles/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views # Импортируем views

# DRF Router для API
router = DefaultRouter()
router.register(r'users', views.UserViewSet)
router.register(r'teams', views.TeamViewSet)
# router.register(r'departments', views.DepartmentViewSet) # Если есть DepartmentViewSet

app_name = "user_profiles"

urlpatterns = [
    # --- Authentication ---
    path('', views.base, name='base'), # Представление входа
    path('login/', views.user_login, name='login'), # Может быть редиректом на base
    path('logout/', views.user_logout, name='logout'),

    # --- API ---
    path('api/', include(router.urls)),

    # --- Users (CBV) ---
    path('users/', views.UserListView.as_view(), name='user_list'),
    path('users/create/', views.UserCreateView.as_view(), name='user_create'),
    path('users/<int:pk>/update/', views.UserUpdateView.as_view(), name='user_update'),
    path('users/<int:pk>/delete/', views.UserDeleteView.as_view(), name='user_delete'),

    # --- Teams (CBV) ---
    path('teams/', views.TeamListView.as_view(), name='team_list'),
    path('teams/create/', views.TeamCreateView.as_view(), name='team_create'),
    path('teams/<int:pk>/update/', views.TeamUpdateView.as_view(), name='team_update'),
    path('teams/<int:pk>/delete/', views.TeamDeleteView.as_view(), name='team_delete'),

    path('profile/', views.UserProfileView.as_view(), name='profile_view'),
    path('password_change/', views.UserPasswordChangeView.as_view(), name='password_change'),
    path('password_change/done/', views.UserPasswordChangeDoneView.as_view(), name='password_change_done'),
]