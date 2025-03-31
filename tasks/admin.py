# tasks/admin.py
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.db import models # <--- ДОБАВЬТЕ ЭТОТ ИМПОРТ
from django.urls import reverse
from django.utils.html import format_html

from .models import (
    Project, TaskCategory, TaskSubcategory,
    Task, TaskPhoto
)
# Импортируем TaskUserRole из user_profiles, т.к. инлайн используется здесь
from user_profiles.models import TaskUserRole

# --- Inlines ---

class TaskPhotoInline(admin.TabularInline):
    """Inline for managing Task Photos directly within the Task admin."""
    model = TaskPhoto
    extra = 1
    fields = ('photo', 'thumbnail', 'description', 'uploaded_by', 'created_at') # Добавлен thumbnail
    readonly_fields = ('created_at', 'uploaded_by', 'thumbnail') # Добавлен thumbnail
    verbose_name = _("Фотография")
    verbose_name_plural = _("Фотографии")
    autocomplete_fields = ('uploaded_by',) # Автокомплит для пользователя

    def save_model(self, request, obj, form, change):
        # Этот метод не нужен для Inline, используется save_formset
        pass

    def save_formset(self, request, form, formset, change):
        """Присваивает uploaded_by при сохранении формсета."""
        instances = formset.save(commit=False)
        for instance in instances:
            if not instance.pk and not instance.uploaded_by: # Если новый объект и нет загрузчика
                instance.uploaded_by = request.user
            instance.save()
        formset.save_m2m()

    def thumbnail(self, obj):
        """Display image thumbnail."""
        if obj.photo:
            return format_html('<img src="{}" style="max-height: 40px; max-width: 70px;" />', obj.photo.url)
        return "-"
    thumbnail.short_description = _("Миниатюра")

class TaskUserRoleInline(admin.TabularInline):
    """Inline for managing user roles directly within the Task admin."""
    model = TaskUserRole
    extra = 1
    fields = ('user', 'role', 'created_at')
    readonly_fields = ('created_at',)
    autocomplete_fields = ('user',) # Use autocomplete for user selection
    verbose_name = _("Роль пользователя")
    verbose_name_plural = _("Роли пользователей")
    # fk_name = "task" # Not needed if model has only one FK to Task


# --- ModelAdmins ---

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "start_date", "end_date", "created_at", "task_count")
    search_fields = ("name", "description")
    list_filter = ("start_date", "end_date", "created_at")
    date_hierarchy = "created_at"
    fieldsets = (
        (None, {"fields": ("name", "description")}),
        (_("Даты"), {"fields": ("start_date", "end_date")}),
        # Add fields like owner, status if they exist
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # --- ИСПРАВЛЕНИЕ ЗДЕСЬ: Используем импортированный models ---
        qs = qs.annotate(models.Count('tasks'))
        # --- КОНЕЦ ИСПРАВЛЕНИЯ ---
        return qs

    def task_count(self, obj):
        # Проверяем, есть ли аннотированное поле
        count = getattr(obj, 'tasks__count', None)
        if count is None:
             # Если нет (например, при просмотре отдельного объекта), считаем напрямую
             # Это может быть неэффективно для списка, но для деталей - нормально
             return obj.tasks.count()
        return count

    task_count.short_description = _("Кол-во задач")
    task_count.admin_order_field = 'tasks__count' # Сортировка по аннотированному полю


@admin.register(TaskCategory)
class TaskCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at", "updated_at")
    search_fields = ("name", "description")


@admin.register(TaskSubcategory)
class TaskSubcategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "created_at", "updated_at")
    list_filter = ("category",)
    search_fields = ("name", "description", "category__name")
    autocomplete_fields = ('category',) # Autocomplete for category selection


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    inlines = [TaskUserRoleInline, TaskPhotoInline] # Manage roles and photos inline
    list_display = (
        "task_number", "title", "project_link", "status_display", "priority_display",
        "deadline", "get_assigned_users_display", "created_by_link", "created_at"
    )
    list_filter = (
        "status", "priority", "project", "category", "subcategory",
        "deadline", "created_at", "user_roles__user", "user_roles__role" # Filter by assigned user/role
    )
    search_fields = (
        "task_number", "title", "description", "project__name",
        "user_roles__user__username", "user_roles__user__first_name", "user_roles__user__last_name", # Search by assigned user
        "created_by__username"
    )
    ordering = ("-created_at", "priority", "deadline") # Default ordering
    date_hierarchy = "created_at" # Date drilldown navigation
    readonly_fields = ("task_number", "created_at", "updated_at", "created_by_link", "completion_date") # Заменяем created_by на ссылку
    list_select_related = ('project', 'category', 'subcategory', 'created_by') # Optimize list view queries
    # Autocomplete fields for better FK selection performance
    autocomplete_fields = ('project', 'category', 'subcategory', 'created_by')

    fieldsets = (
        (None, {"fields": ("task_number", "project", "title", "description")}),
        (_("Классификация и Статус"), {"fields": ("category", "subcategory", "status", "priority")}),
        # Assignee/Team fields removed, managed via TaskUserRoleInline now
        (_("Сроки и Оценка"), {"fields": ("start_date", "deadline", "completion_date", "estimated_time"), "classes": ("collapse",)}),
        (_("Системная информация"), {
            "fields": ("created_by_link", "created_at", "updated_at"), # Используем ссылку
            "classes": ("collapse",),
        }),
    )

    # Custom Actions
    actions = ['mark_completed', 'mark_in_progress']

    def save_model(self, request, obj, form, change):
        """Assign creator on first save."""
        if not change and not obj.created_by_id: # Проверяем _id для оптимизации
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        # Prefetch related users for assigned users display
        return super().get_queryset(request).prefetch_related(
            'user_roles__user' # Prefetch users related through roles
        )

    def get_assigned_users_display(self, obj):
        """Display assigned users (e.g., Responsible, Executors) in list view."""
        # Оптимизация: используем prefetched данные
        users_roles = obj.user_roles.all() # Получаем prefetched роли
        if not users_roles:
            return "---"

        display_parts = []
        # Сортируем роли для консистентности отображения
        role_order = {
            TaskUserRole.RoleChoices.RESPONSIBLE: 1,
            TaskUserRole.RoleChoices.EXECUTOR: 2,
            TaskUserRole.RoleChoices.WATCHER: 3
        }
        sorted_roles = sorted(users_roles, key=lambda r: role_order.get(r.role, 99))

        for role_assignment in sorted_roles:
            role_abbr = role_assignment.get_role_display()[:3] # Аббревиатура роли
            # Проверяем, есть ли уже загруженный пользователь
            user_display = getattr(role_assignment.user, 'display_name', _('Неизвестный пользователь'))
            display_parts.append(f"{user_display} ({role_abbr}.)")
        return ", ".join(display_parts)
    get_assigned_users_display.short_description = _("Участники")

    # --- Методы для ссылок в list_display и readonly_fields ---
    def project_link(self, obj):
        if obj.project:
            link = reverse("admin:tasks_project_change", args=[obj.project.id])
            return format_html('<a href="{}">{}</a>', link, obj.project.name)
        return "-"
    project_link.short_description = _("Проект")
    project_link.admin_order_field = 'project__name' # Сортировка по имени проекта

    def created_by_link(self, obj):
        if obj.created_by:
            link = reverse("admin:user_profiles_user_change", args=[obj.created_by.id])
            return format_html('<a href="{}">{}</a>', link, obj.created_by.display_name)
        return "-"
    created_by_link.short_description = _("Создатель")
    created_by_link.admin_order_field = 'created_by__username' # Сортировка по username создателя

    # --- Admin Actions ---
    @admin.action(description=_("Отметить выбранные задачи как 'Выполнена'"))
    def mark_completed(self, request, queryset):
        updated_count = 0
        from django.utils import timezone # Импорт внутри метода
        for task in queryset:
             if task.status != Task.StatusChoices.COMPLETED:
                 task.status = Task.StatusChoices.COMPLETED
                 task.completion_date = timezone.now() # Устанавливаем явно здесь для действия
                 try:
                     # Важно сохранить completion_date
                     task.save(update_fields=['status', 'completion_date', 'updated_at'])
                     updated_count += 1
                 except Exception as e:
                     self.message_user(request, f"Ошибка при обновлении задачи {task.task_number}: {e}", level='error')

        self.message_user(request, _(f"{updated_count} задач успешно отмечены как выполненные."), level='success')

    @admin.action(description=_("Отметить выбранные задачи как 'В работе'"))
    def mark_in_progress(self, request, queryset):
        updated_count = 0
        for task in queryset.exclude(status=Task.StatusChoices.COMPLETED): # Не трогаем выполненные
             if task.status != Task.StatusChoices.IN_PROGRESS:
                 task.status = Task.StatusChoices.IN_PROGRESS
                 task.completion_date = None # Сбрасываем дату завершения
                 try:
                     # Важно сохранить completion_date
                     task.save(update_fields=['status', 'completion_date', 'updated_at'])
                     updated_count += 1
                 except Exception as e:
                      self.message_user(request, f"Ошибка при обновлении задачи {task.task_number}: {e}", level='error')
        self.message_user(request, _(f"{updated_count} задач успешно переведены в статус 'В работе'."), level='success')


@admin.register(TaskPhoto)
class TaskPhotoAdmin(admin.ModelAdmin):
    list_display = ("id", "task_link", "thumbnail", "description", "uploaded_by_link", "created_at")
    list_filter = ("created_at", "task__project", "uploaded_by") # Filter by project via task
    search_fields = ("description", "task__task_number", "task__title", "uploaded_by__username")
    list_select_related = ('task', 'uploaded_by', 'task__project') # Optimize queries
    readonly_fields = ("created_at", "uploaded_by_link", "thumbnail") # Используем ссылку
    autocomplete_fields = ('task', 'uploaded_by')

    fieldsets = (
        (None, {"fields": ("task", "photo", "thumbnail", "description")}),
        (_("Системная информация"), {
            "fields": ("uploaded_by_link", "created_at", "updated_at"), # Используем ссылку
            "classes": ("collapse",)
        }),
    )

    def task_link(self, obj):
        """Link to the task in the admin."""
        if obj.task:
            link = reverse("admin:tasks_task_change", args=[obj.task.id])
            # Отображаем номер задачи и её название для понятности
            return format_html('<a href="{}">[{}] {}</a>', link, obj.task.task_number, obj.task.title[:30])
        return "-"
    task_link.short_description = _("Задача")
    task_link.admin_order_field = 'task__task_number' # Сортировка по номеру задачи

    def thumbnail(self, obj):
        """Display image thumbnail."""
        if obj.photo:
            return format_html('<img src="{}" style="max-height: 50px; max-width: 100px;" />', obj.photo.url)
        return "-"
    thumbnail.short_description = _("Миниатюра")

    def uploaded_by_link(self, obj):
        """Link to the user who uploaded the photo."""
        if obj.uploaded_by:
            link = reverse("admin:user_profiles_user_change", args=[obj.uploaded_by.id])
            return format_html('<a href="{}">{}</a>', link, obj.uploaded_by.display_name)
        return "-"
    uploaded_by_link.short_description = _("Загрузил")
    uploaded_by_link.admin_order_field = 'uploaded_by__username'