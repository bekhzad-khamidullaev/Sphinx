from django.urls import path, include
from . import views
from rest_framework.routers import DefaultRouter # For API endpoints

# Create a router for REST API views
router = DefaultRouter()
# Register your ViewSets or list views here
# router.register(r'templates', views.ChecklistTemplateViewSet) # Example if using ViewSets
# router.register(r'runs', views.ChecklistRunViewSet) # Example if using ViewSets

app_name = 'checklists'

# API URL patterns (using Django REST framework)
api_urlpatterns = [
    # API for ChecklistPoint (e.g., for dynamic filtering in JS)
    path('points/', views.ChecklistPointListView.as_view(), name='api_checklist_point_list'),
    # Add other API endpoints here, e.g., for templates, runs, results
    # path('templates/', views.ChecklistTemplateListAPIView.as_view(), name='api_template_list'),
    # path('templates/<int:pk>/', views.ChecklistTemplateDetailAPIView.as_view(), name='api_template_detail'),
    # path('runs/', views.ChecklistRunListCreateAPIView.as_view(), name='api_run_list_create'),
    # path('runs/<uuid:pk>/', views.ChecklistRunDetailAPIView.as_view(), name='api_run_detail'),
    # Endpoint to update a single result (useful for formset-like API interaction)
    # path('results/<uuid:pk>/', views.ChecklistResultUpdateAPIView.as_view(), name='api_result_update'),
    # path('', include(router.urls)), # Include router URLs if using ViewSets
]


urlpatterns = [
    # Template CRUD
    path('templates/', views.ChecklistTemplateListView.as_view(), name='template_list'),
    path('templates/new/', views.ChecklistTemplateCreateView.as_view(), name='template_create'),
    path('templates/<int:pk>/', views.ChecklistTemplateDetailView.as_view(), name='template_detail'),
    path('templates/<int:pk>/edit/', views.ChecklistTemplateUpdateView.as_view(), name='template_update'),
    path('templates/<int:pk>/delete/', views.ChecklistTemplateDeleteView.as_view(), name='template_delete'),

    # Perform Checklist (start a new run or continue today's)
    # Use template_pk to identify which template to perform
    path('perform/<int:template_pk>/', views.PerformChecklistView.as_view(), name='checklist_perform'),
     # Save answers while performing (AJAX endpoint?) - Optional, handled by formset POST for now
     # path('perform/<uuid:pk>/save-item/<uuid:result_pk>/', views.save_checklist_item_api, name='checklist_save_item'),


    # History / Results List
    # This view uses the filterset
    path('history/', views.ChecklistHistoryListView.as_view(), name='history_list'),
    # Detail view for a completed checklist run (history item)
    path('history/<uuid:pk>/', views.ChecklistDetailView.as_view(), name='checklist_detail'),

    # Status Change View (for review/approval)
    path('history/<uuid:pk>/status/', views.ChecklistStatusUpdateView.as_view(), name='checklist_status_change'),

    # Reports
    path('reports/summary/', views.ChecklistReportView.as_view(), name='report_summary'),
    path('reports/issues/', views.ChecklistIssuesReportView.as_view(), name='report_issues'),

    # API Endpoints (include them under a /api/ prefix)
    path('api/', include((api_urlpatterns, 'checklists'), namespace='api')),
]