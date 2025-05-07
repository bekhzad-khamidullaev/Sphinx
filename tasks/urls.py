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

urlpatterns = [
    # API URLs
    path('api/', include(router.urls)),
    path('api/search-suggestions/', api.SearchSuggestionsView.as_view(), name='search-suggestions-api'),
    path('api/user-autocomplete/', api.UserAutocompleteView.as_view(), name='user_autocomplete'),

    # Project URLs
    path('projects/', project.ProjectListView.as_view(), name='project_list'),
    path('projects/create/', project.ProjectCreateView.as_view(), name='project_create'),
    path('projects/<int:pk>/', project.ProjectDetailView.as_view(), name='project_detail'),
    path('projects/<int:pk>/update/', project.ProjectUpdateView.as_view(), name='project_update'),
    path('projects/<int:pk>/delete/', project.ProjectDeleteView.as_view(), name='project_delete'),

    # TaskCategory URLs
    path('categories/', category.TaskCategoryListView.as_view(), name='category_list'),
    path('categories/create/', category.TaskCategoryCreateView.as_view(), name='category_create'),
    path('categories/<int:pk>/', category.TaskCategoryDetailView.as_view(), name='category_detail'),
    path('categories/<int:pk>/update/', category.TaskCategoryUpdateView.as_view(), name='category_update'),
    path('categories/<int:pk>/delete/', category.TaskCategoryDeleteView.as_view(), name='category_delete'),

    # TaskSubcategory URLs
    path('subcategories/', subcategory.TaskSubcategoryListView.as_view(), name='subcategory_list'),
    path('subcategories/create/', subcategory.TaskSubcategoryCreateView.as_view(), name='subcategory_create'),
    path('subcategories/<int:pk>/', subcategory.TaskSubcategoryDetailView.as_view(), name='subcategory_detail'),
    path('subcategories/<int:pk>/update/', subcategory.TaskSubcategoryUpdateView.as_view(), name='subcategory_update'),
    path('subcategories/<int:pk>/delete/', subcategory.TaskSubcategoryDeleteView.as_view(), name='subcategory_delete'),
    path('ajax/load-subcategories/', ajax.load_subcategories, name='ajax_load_subcategories'), # For dependent dropdown

    # Task URLs
    path('', task.TaskListView.as_view(), name='task_list'), # Список задач как главная страница приложения tasks
    path('tasks/create/', task.TaskCreateView.as_view(), name='task_create'),
    path('tasks/<int:pk>/', task.TaskDetailView.as_view(), name='task_detail'),
    path('tasks/<int:pk>/update/', task.TaskUpdateView.as_view(), name='task_update'),
    path('tasks/<int:pk>/delete/', task.TaskDeleteView.as_view(), name='task_delete'),
    path('tasks/<int:pk>/perform/', task.TaskPerformView.as_view(), name='task_perform'),
    path('tasks/<int:task_id>/add_comment/', task.add_comment_to_task, name='add_comment_to_task'),
    path('ajax/tasks/<int:task_id>/update-status/', ajax.update_task_status, name='ajax_update_task_status'),


    # Report URLs (группируем для ясности)
    # Префикс 'reports/' добавлен к report.ReportIndexView для консистентности, если он используется как входная точка для отчетов
    path('reports/', report.ReportIndexView.as_view(template_name="reports/report_index_public.html"), name='report_index_public'), # Отчеты для фронтенда
    # Примечание: report.ReportIndexView используется и для admin, но с другим шаблоном (определяется в admin.py)

    # Пути к конкретным отчетам для фронтенда (если нужны)
    # path('reports/my-completed-tasks/', report.UserCompletedTasksReportView.as_view(), name='report_user_completed_tasks'),
    # ... другие публичные отчеты

    # AJAX URLs
    # path('ajax/some-action/', ajax.some_action_view, name='ajax_some_action'),
]

# URL-пути для отчетов, доступных через админ-панель, обычно регистрируются в методе get_urls() в TaskAdmin.
# Если же нужны отдельные URL для отчетов вне админки (например, для пользователей с определенными правами),
# их можно добавить сюда. Пример ниже.

report_urlpatterns = [
    path('export/excel/', report.export_tasks_to_excel, name='export_tasks_excel'),
    path('completed/', report.CompletedTasksReportView.as_view(), name='report_completed_tasks'), # Используем CBV
    path('overdue/', report.OverdueTasksReportView.as_view(), name='report_overdue_tasks'),
    path('active/', report.ActiveTasksReportView.as_view(), name='report_active_tasks'),
    path('performance/', report.TeamPerformanceReportView.as_view(), name='report_team_performance'),
    path('workload/', report.EmployeeWorkloadReportView.as_view(), name='report_employee_workload'),
    path('abc/', report.AbcAnalysisReportView.as_view(), name='report_abc_analysis'),
    path('sla/', report.SlaReportView.as_view(), name='report_sla'),
    path('duration/', report.TaskDurationReportView.as_view(), name='report_task_duration'),
    path('issues/', report.IssuesReportView.as_view(), name='report_issues'),
    path('delay-reasons/', report.DelayReasonsReportView.as_view(), name='report_delay_reasons'),
    path('cancelled/', report.CancelledTasksReportView.as_view(), name='report_cancelled_tasks'),
    path('charts/progress/', report.TaskProgressChartView.as_view(), name='chart_task_progress'),
    path('charts/gantt/', report.GanttChartView.as_view(), name='chart_gantt'),
    path('summary/', report.TaskSummaryReportView.as_view(), name='report_task_summary'),
]

# Добавляем пути отчетов с префиксом 'reports/' к основным urlpatterns, если они публичные
# urlpatterns.append(path('reports/', include((report_urlpatterns, 'reports'), namespace='reports')))
# Если отчеты только через админку, то этот блок не нужен, т.к. они регистрируются в admin.py