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
    path('points/', views.ChecklistPointListView.as_view(), name='api_checklist_point_list'),
    # Example: path('templates/<uuid:pk>/', views.ChecklistTemplateDetailAPIView.as_view(), name='api_template_detail'), # Change int to uuid
    # Example: path('runs/<uuid:pk>/', views.ChecklistRunDetailAPIView.as_view(), name='api_run_detail'), # Change int to uuid
    # Example: path('results/<uuid:pk>/', views.ChecklistResultUpdateAPIView.as_view(), name='api_result_update'), # Change int to uuid
]


urlpatterns = [
    # Template CRUD
    path('templates/', views.ChecklistTemplateListView.as_view(), name='template_list'),
    path('templates/new/', views.ChecklistTemplateCreateView.as_view(), name='template_create'),
    # --- CHANGE HERE ---
    path('templates/<uuid:pk>/', views.ChecklistTemplateDetailView.as_view(), name='template_detail'),
    # --- CHANGE HERE ---
    path('templates/<uuid:pk>/edit/', views.ChecklistTemplateUpdateView.as_view(), name='template_update'),
    # --- CHANGE HERE ---
    path('templates/<uuid:pk>/delete/', views.ChecklistTemplateDeleteView.as_view(), name='template_delete'),

    # Perform Checklist (template_pk is likely int or slug, leave as is unless template uses UUID for lookup here too)
    # Assuming template_pk here refers to the UUID primary key:
    # --- CHANGE HERE (if template_pk is the UUID) ---
    path('perform/<uuid:template_pk>/', views.PerformChecklistView.as_view(), name='checklist_perform'),

    # History / Results List (Checklist model uses UUID pk)
    path('history/', views.ChecklistHistoryListView.as_view(), name='history_list'),
    # --- CHANGE HERE ---
    path('history/<uuid:pk>/', views.ChecklistDetailView.as_view(), name='checklist_detail'),
    # --- CHANGE HERE ---
    path('history/<uuid:pk>/status/', views.ChecklistStatusUpdateView.as_view(), name='checklist_status_change'),

    # Reports (No PKs usually)
    path('reports/summary/', views.ChecklistReportView.as_view(), name='report_summary'),
    path('reports/issues/', views.ChecklistIssuesReportView.as_view(), name='report_issues'),

    # API Endpoints
    path('api/', include((api_urlpatterns, 'checklists'), namespace='api')),

    # Check API URLs as well if they use PKs for templates or checklists
]