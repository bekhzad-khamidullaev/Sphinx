# user_profiles/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = "user_profiles"

# DRF Router for API
router = DefaultRouter()
router.register(r'users', views.UserViewSet, basename='user-api') # Use basename
router.register(r'teams', views.TeamViewSet, basename='team-api')
router.register(r'departments', views.DepartmentViewSet, basename='department-api')
router.register(r'jobtitles', views.JobTitleViewSet, basename='jobtitle-api') # Add JobTitle ViewSet if created

urlpatterns = [
    # --- Authentication ---
    path('', views.base_login_view, name='base_login'), # Main login/redirect page
    path('login/', views.user_login_redirect, name='login_redirect'), # Simple redirect
    path('logout/', views.user_logout_view, name='logout'),

    # --- API ---
    path('api/v1/', include(router.urls)), # Prefix API urls with v1

    # --- User Profile ---
    path('profile/', views.UserProfileView.as_view(), name='profile_view'),
    path('profile/password_change/', views.UserPasswordChangeView.as_view(), name='password_change'),
    path('profile/password_change/done/', views.UserPasswordChangeDoneView.as_view(), name='password_change_done'),

    # --- User Management (Staff) ---
    path('manage/users/', views.UserListView.as_view(), name='user_list'),
    path('manage/users/create/', views.UserCreateView.as_view(), name='user_create'),
    path('manage/users/<int:pk>/update/', views.UserUpdateView.as_view(), name='user_update'),
    path('manage/users/<int:pk>/delete/', views.UserDeleteView.as_view(), name='user_delete'),
    # path('manage/users/<int:pk>/', views.UserDetailView.as_view(), name='user_detail'), # Optional detail view

    # --- Team Management (Staff) ---
    path('manage/teams/', views.TeamListView.as_view(), name='team_list'),
    path('manage/teams/create/', views.TeamCreateView.as_view(), name='team_create'),
    path('manage/teams/<int:pk>/', views.TeamDetailView.as_view(), name='team_detail'),
    path('manage/teams/<int:pk>/update/', views.TeamUpdateView.as_view(), name='team_update'),
    path('manage/teams/<int:pk>/delete/', views.TeamDeleteView.as_view(), name='team_delete'),

    # --- Department Management (Staff) ---
    path('manage/departments/', views.DepartmentListView.as_view(), name='department_list'),
    path('manage/departments/create/', views.DepartmentCreateView.as_view(), name='department_create'),
    path('manage/departments/<int:pk>/', views.DepartmentDetailView.as_view(), name='department_detail'),
    path('manage/departments/<int:pk>/update/', views.DepartmentUpdateView.as_view(), name='department_update'),
    path('manage/departments/<int:pk>/delete/', views.DepartmentDeleteView.as_view(), name='department_delete'),

    # --- JobTitle Management (Staff) ---
    path('manage/jobtitles/', views.JobTitleListView.as_view(), name='jobtitle_list'),
    path('manage/jobtitles/create/', views.JobTitleCreateView.as_view(), name='jobtitle_create'),
    # path('manage/jobtitles/<int:pk>/', views.JobTitleDetailView.as_view(), name='jobtitle_detail'), # If needed
    path('manage/jobtitles/<int:pk>/update/', views.JobTitleUpdateView.as_view(), name='jobtitle_update'),
    path('manage/jobtitles/<int:pk>/delete/', views.JobTitleDeleteView.as_view(), name='jobtitle_delete'),
]