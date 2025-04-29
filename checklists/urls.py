# checklists/urls.py
from django.urls import path
from . import views

app_name = 'checklists'

urlpatterns = [
    # Template CRUD
    path('templates/', views.ChecklistTemplateListView.as_view(), name='template_list'),
    path('templates/new/', views.ChecklistTemplateCreateView.as_view(), name='template_create'),
    path('templates/<int:pk>/', views.ChecklistTemplateDetailView.as_view(), name='template_detail'),
    path('templates/<int:pk>/edit/', views.ChecklistTemplateUpdateView.as_view(), name='template_update'),
    path('templates/<int:pk>/delete/', views.ChecklistTemplateDeleteView.as_view(), name='template_delete'),

    # Perform Checklist
    # Maybe a view to select template first? Or link directly from template list/detail
    path('perform/<int:template_pk>/', views.PerformChecklistView.as_view(), name='checklist_perform'),

    # History / Results
    path('history/', views.ChecklistHistoryListView.as_view(), name='history_list'),
    path('history/<int:pk>/', views.ChecklistDetailView.as_view(), name='checklist_detail'),

    # Reports
    path('reports/summary/', views.ChecklistReportView.as_view(), name='report_summary'),
    path('reports/issues/', views.ChecklistIssuesReportView.as_view(), name='report_issues'),
]