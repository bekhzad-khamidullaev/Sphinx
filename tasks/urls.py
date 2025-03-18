from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = "tasks"

# API router
router = DefaultRouter()
router.register(r'campaigns', views.CampaignViewSet)
router.register(r'task-categories', views.TaskCategoryViewSet)
router.register(r'task-subcategories', views.TaskSubcategoryViewSet)
router.register(r'tasks', views.TaskViewSet)
router.register(r'task-photos', views.TaskPhotoViewSet)

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
    path("tasks/update_status/<int:task_id>/", views.update_task_status, name="update_task_status"),

    # Campaign management URLs
    path('campaigns/', views.campaign_list, name='campaign_list'),
    path('campaigns/create/', views.modal_create_campaign, name='modal_create_campaign'),
    path('campaigns/<int:pk>/update/', views.modal_update_campaign, name='modal_update_campaign'),
    path('campaigns/<int:pk>/delete/', views.modal_delete_campaign, name='modal_delete_campaign'),
    path('campaigns/create/', views.create_campaign, name='create_campaign'),
    path('campaigns/<int:pk>/delete/', views.delete_campaign, name='delete_campaign'),

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

    # Report URLs
    path('tasks/export/excel/', views.export_tasks_to_excel, name='export_tasks_to_excel'),

    # API URLs
    path('api/', include(router.urls)),
]
