from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import project, category, subcategory, task, report, api, ajax

app_name = 'tasks'

router = DefaultRouter()
router.register(r'projects', api.ProjectViewSet, basename='project-api')
router.register(r'categories', api.TaskCategoryViewSet, basename='category-api')
router.register(r'subcategories', api.TaskSubcategoryViewSet, basename='subcategory-api')
router.register(r'tasks', api.TaskViewSet, basename='task-api')
router.register(r'photos', api.TaskPhotoViewSet, basename='photo-api')
router.register(r'assignments', api.TaskAssignmentViewSet, basename='assignment-api')


urlpatterns = [
    path('api/', include(router.urls)),
    path('api/search-suggestions/', api.SearchSuggestionsView.as_view(), name='search-suggestions-api'),
    path('api/user-autocomplete/', api.UserAutocompleteView.as_view(), name='user_autocomplete'),

    path('projects/', project.ProjectListView.as_view(), name='project_list'),
    path('projects/create/', project.ProjectCreateView.as_view(), name='project_create'),
    path('projects/<int:pk>/', project.ProjectDetailView.as_view(), name='project_detail'),
    path('projects/<int:pk>/update/', project.ProjectUpdateView.as_view(), name='project_update'),
    path('projects/<int:pk>/delete/', project.ProjectDeleteView.as_view(), name='project_delete'),

    path('categories/', category.TaskCategoryListView.as_view(), name='category_list'),
    path('categories/create/', category.TaskCategoryCreateView.as_view(), name='category_create'),
    path('categories/<int:pk>/', category.TaskCategoryDetailView.as_view(), name='category_detail'),
    path('categories/<int:pk>/update/', category.TaskCategoryUpdateView.as_view(), name='category_update'),
    path('categories/<int:pk>/delete/', category.TaskCategoryDeleteView.as_view(), name='category_delete'),

    path('subcategories/', subcategory.TaskSubcategoryListView.as_view(), name='subcategory_list'),
    path('subcategories/create/', subcategory.TaskSubcategoryCreateView.as_view(), name='subcategory_create'),
    path('subcategories/<int:pk>/', subcategory.TaskSubcategoryDetailView.as_view(), name='subcategory_detail'),
    path('subcategories/<int:pk>/update/', subcategory.TaskSubcategoryUpdateView.as_view(), name='subcategory_update'),
    path('subcategories/<int:pk>/delete/', subcategory.TaskSubcategoryDeleteView.as_view(), name='subcategory_delete'),
    path('ajax/load-subcategories/', ajax.load_subcategories, name='ajax_load_subcategories'),

    path('', task.TaskListView.as_view(), name='task_list_default'),
    path('tasks/', task.TaskListView.as_view(), name='task_list'),
    path('tasks/create/', task.TaskCreateView.as_view(), name='task_create'),
    path('tasks/<int:pk>/', task.TaskDetailView.as_view(), name='task_detail'),
    path('tasks/<int:pk>/update/', task.TaskUpdateView.as_view(), name='task_update'),
    path('tasks/<int:pk>/delete/', task.TaskDeleteView.as_view(), name='task_delete'),
    path('tasks/<int:pk>/perform/', task.TaskPerformView.as_view(), name='task_perform'),
    path('ajax/tasks/<int:task_id>/update-status/', ajax.update_task_status, name='ajax_update_task_status'),
    path('ajax/tasks/<int:task_id>/delete/', ajax.delete_task_ajax, name='ajax_delete_task'),
    path('tasks/<int:task_id>/add_comment/', task.add_comment_to_task, name='add_comment_to_task'),

    path('reports/', report.ReportIndexView.as_view(), name='report_index'),
    path('reports/export/excel/', report.export_tasks_to_excel, name='export_tasks_excel'),
    path('reports/completed/', report.CompletedTasksReportView.as_view(), name='report_completed_tasks'), # Use CBV directly
    path('reports/overdue/', report.OverdueTasksReportView.as_view(), name='report_overdue_tasks'),
    path('reports/active/', report.ActiveTasksReportView.as_view(), name='report_active_tasks'),
    path('reports/performance/', report.TeamPerformanceReportView.as_view(), name='report_team_performance'),
    path('reports/workload/', report.EmployeeWorkloadReportView.as_view(), name='report_employee_workload'),
    path('reports/abc/', report.AbcAnalysisReportView.as_view(), name='report_abc_analysis'),
    path('reports/sla/', report.SlaReportView.as_view(), name='report_sla'),
    path('reports/duration/', report.TaskDurationReportView.as_view(), name='report_task_duration'),
    path('reports/issues/', report.IssuesReportView.as_view(), name='report_issues'),
    path('reports/delay-reasons/', report.DelayReasonsReportView.as_view(), name='report_delay_reasons'),
    path('reports/cancelled/', report.CancelledTasksReportView.as_view(), name='report_cancelled_tasks'),
    path('reports/charts/progress/', report.TaskProgressChartView.as_view(), name='chart_task_progress'),
    path('reports/charts/gantt/', report.GanttChartView.as_view(), name='chart_gantt'),
    path('reports/summary/', report.TaskSummaryReportView.as_view(), name='report_task_summary'),
]