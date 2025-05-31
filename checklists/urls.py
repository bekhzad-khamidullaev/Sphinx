# checklists/urls.py
from django.urls import path, include
from . import views
from rest_framework.routers import DefaultRouter

router = DefaultRouter()

app_name = 'checklists'

api_urlpatterns = [
    path('points/', views.ChecklistPointListView.as_view(), name='api_checklist_point_list'),
]


urlpatterns = [
    path('templates/', views.ChecklistTemplateListView.as_view(), name='template_list'),
    path('templates/new/', views.ChecklistTemplateCreateView.as_view(), name='template_create'),
    path('templates/<uuid:pk>/', views.ChecklistTemplateDetailView.as_view(), name='template_detail'),
    path('templates/<uuid:pk>/edit/', views.ChecklistTemplateUpdateView.as_view(), name='template_update'),
    path('templates/<uuid:pk>/delete/', views.ChecklistTemplateDeleteView.as_view(), name='template_delete'),

    path('perform/<uuid:template_pk>/', views.PerformChecklistView.as_view(), name='checklist_perform'),

    path('history/', views.ChecklistHistoryListView.as_view(), name='history_list'),
    path('history/<uuid:pk>/', views.ChecklistDetailView.as_view(), name='checklist_detail'),
    path('history/<uuid:pk>/status/', views.ChecklistStatusUpdateView.as_view(), name='checklist_status_change'),      

    path('reports/summary/', views.ChecklistReportView.as_view(), name='report_summary'),
    path('reports/issues/', views.ChecklistIssuesReportView.as_view(), name='report_issues'),

    path('api/', include((api_urlpatterns, 'checklists'), namespace='api')),
]