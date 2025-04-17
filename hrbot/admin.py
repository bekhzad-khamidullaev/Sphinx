from django.contrib import admin
from .models import TelegramUser, Question, Evaluation
from user_profiles.models import Role
from django.utils.translation import gettext_lazy as _


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(TelegramUser)
class TelegramUserAdmin(admin.ModelAdmin):
    list_display = ("user", "telegram_id", "approved")
    list_editable = ("approved",)
    search_fields = ("user__username", "telegram_id")
    list_filter = ("approved",)


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("text", "role", "order")
    list_filter = ("role",)
    search_fields = ("text", "role__name")
    ordering = ("role", "order")


@admin.register(Evaluation)
class EvaluationAdmin(admin.ModelAdmin):
    list_display = ("employee_name", "get_role_name", "get_evaluator_username", "timestamp")
    readonly_fields = ("employee_name", "role", "get_evaluator_username", "responses", "timestamp")
    list_filter = ("role", "timestamp")
    search_fields = ("employee_name", "role__name", "evaluator__user__username")
    ordering = ("-timestamp",)
    list_per_page = 25

    def get_evaluator_username(self, obj):
        return obj.evaluator.user.username

    get_evaluator_username.short_description = _("Evaluator")
    get_evaluator_username.admin_order_field = "evaluator__user__username"

    def get_role_name(self, obj):
        return obj.role.name

    get_role_name.short_description = _("Role")
    get_role_name.admin_order_field = "role__name"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(evaluator__user=request.user)

    def get_list_display(self, request):
        fields = list(self.list_display)
        if not request.user.is_superuser:
            fields.remove("get_evaluator_username")
        return fields

    def get_list_filter(self, request):
        if request.user.is_superuser:
            return self.list_filter + ("evaluator",)
        return self.list_filter
