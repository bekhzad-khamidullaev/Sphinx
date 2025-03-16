from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = "crm_core"

# API router
router = DefaultRouter()
router.register(r'campaigns', views.CampaignViewSet)
router.register(r'teams', views.TeamViewSet)
router.register(r'task-categories', views.TaskCategoryViewSet)
router.register(r'task-subcategories', views.TaskSubcategoryViewSet)
router.register(r'tasks', views.TaskViewSet)
router.register(r'task-photos', views.TaskPhotoViewSet)
router.register(r'roles', views.RoleViewSet)
router.register(r'users', views.UserViewSet)

urlpatterns = [
    # Auth URLs
    # path('login/', views.LoginView.as_view(), name='login'),
    # path('logout/', views.LogoutView.as_view(), name='logout'),
    # path('clear-messages/', views.clear_messages, name='clear_messages'),

    # Task management URLs
    path('tasks/', views.TaskListView.as_view(), name='task_list'),
    path('tasks/summary/', views.TaskSummaryReportView.as_view(), name='task_summary_report'),
    path('tasks/create/', views.TaskCreateView.as_view(), name='task_create'),
    path('tasks/<int:pk>/', views.TaskDetailView.as_view(), name='task_detail'),
    path('tasks/<int:pk>/update/', views.TaskUpdateView.as_view(), name='task_update'),
    path('tasks/<int:pk>/delete/', views.TaskDeleteView.as_view(), name='task_delete'),
    path('tasks/<int:pk>/perform/', views.TaskPerformView.as_view(), name='task_perform'),

    # Campaign management URLs
    path('campaigns/', views.campaign_list, name='campaign_list'),
    path('campaigns/create/', views.modal_create_campaign, name='modal_create_campaign'),
    path('campaigns/<int:pk>/update/', views.modal_update_campaign, name='modal_update_campaign'),
    path('campaigns/<int:pk>/delete/', views.modal_delete_campaign, name='modal_delete_campaign'),
    path('campaigns/create/', views.create_campaign, name='create_campaign'),
    path('campaigns/<int:pk>/delete/', views.delete_campaign, name='delete_campaign'),

    # Team management URLs
    path('teams/', views.team_list, name='team_list'),
    path('teams/create/', views.modal_create_team, name='modal_create_team'),
    path('teams/<int:pk>/update/', views.modal_update_team, name='modal_update_team'),
    path('teams/<int:pk>/delete/', views.modal_delete_team, name='modal_delete_team'),
    path('teams/create/', views.create_team, name='create_team'),
    path('teams/<int:pk>/delete/', views.delete_team, name='delete_team'),

    # Category management URLs
    path('categories/', views.category_list, name='category_list'),
    path('categories/create/', views.modal_create_category, name='modal_create_category'),
    path('categories/create/', views.create_category, name='create_category'),
    path('categories/<int:pk>/update/', views.modal_update_category, name='modal_update_category'),
    path('categories/<int:pk>/update/', views.update_category, name='update_category'),
    path('categories/<int:pk>/delete/', views.modal_delete_category, name='modal_delete_category'),
    path('categories/<int:pk>/delete/', views.delete_category, name='delete_category'),

    # Subcategory management URLs
    path('subcategories/', views.subcategory_list, name='subcategory_list'),
    path('subcategories/create/', views.modal_create_subcategory, name='modal_create_subcategory'),
    path('subcategories/create/', views.create_subcategory, name='create_subcategory'),
    path('subcategories/<int:pk>/update/', views.modal_update_subcategory, name='modal_update_subcategory'),
    path('subcategories/<int:pk>/update/', views.update_subcategory, name='update_subcategory'),
    path('subcategories/<int:pk>/delete/', views.modal_delete_subcategory, name='modal_delete_subcategory'),
    path('subcategories/<int:pk>/delete/', views.delete_subcategory, name='delete_subcategory'),

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

    # Report URLs
    path('tasks/export/excel/', views.export_tasks_to_excel, name='export_tasks_to_excel'),

    # API URLs
    path('api/', include(router.urls)),
]
