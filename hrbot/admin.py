# hrbot/admin.py
from django.contrib import admin
from .models import TelegramUser, Questionnaire, Question, Evaluation
# Импортируем User, Role, чтобы проверить регистрацию админок
# (хотя сами ModelAdmin для них лучше держать в user_profiles.admin)
from user_profiles.models import User, Role

# --- Проверка регистрации админок для autocomplete_fields ---
# Django сам проверит наличие админок при запуске, но можно добавить явные проверки для надежности
# if not admin.site.is_registered(User):
#     logger.warning("ModelAdmin for User is not registered. Autocomplete for 'employee' might fail.")
# if not admin.site.is_registered(Role):
#     logger.warning("ModelAdmin for Role is not registered. Autocomplete for 'role' might fail.")
# -------------------------------------------------------------

@admin.register(Questionnaire)
class QuestionnaireAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'is_active', 'question_count', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'description')
    readonly_fields = ('created_at', 'updated_at')

    @admin.display(description='Кол-во вопросов')
    def question_count(self, obj):
        return obj.questions.count()

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('text', 'questionnaire', 'order')
    list_filter = ('questionnaire',)
    search_fields = ('text', 'questionnaire__name')
    list_editable = ('order',)
    ordering = ('questionnaire', 'order',)
    autocomplete_fields = ['questionnaire'] # Добавим автокомплит

@admin.register(Evaluation)
class EvaluationAdmin(admin.ModelAdmin):
    list_display = ('employee_name', 'get_evaluator_display', 'questionnaire', 'role', 'timestamp')
    list_filter = ('questionnaire', 'role', 'timestamp', 'evaluator__user__username')
    search_fields = ('employee_name', 'evaluator__user__username', 'evaluator__telegram_id', 'questionnaire__name', 'role__name')
    readonly_fields = ('timestamp', 'responses_formatted') # Показываем форматированные ответы
    list_select_related = ('evaluator', 'evaluator__user', 'questionnaire', 'role', 'employee')
    # Убедимся, что админки для ВСЕХ этих моделей зарегистрированы
    autocomplete_fields = ['employee', 'role', 'questionnaire', 'evaluator']
    date_hierarchy = 'timestamp' # Удобная навигация по дате

    @admin.display(description='Оценщик', ordering='evaluator__user__username')
    def get_evaluator_display(self, obj):
        return obj.get_evaluator_name() or f"TG ID: {obj.get_evaluator_telegram_id()}"

    @admin.display(description='Ответы')
    def responses_formatted(self, obj):
        # Безопасное отображение JSON
        import json
        from django.utils.html import format_html
        try:
            # Пытаемся получить форматированные ответы (если реализован get_formatted_responses)
            if hasattr(obj, 'get_formatted_responses'):
                formatted = obj.get_formatted_responses()
                if formatted:
                     # Отображаем красиво, экранируя HTML
                     items = "".join([f"<li><b>{admin.display.html.escape(q)}:</b> {admin.display.html.escape(str(a))}</li>" for q, a in formatted.items()])
                     return format_html("<ul>{}</ul>", format_html(items))
            # Если форматирование не удалось или не реализовано, показываем сырой JSON
            return format_html('<pre>{}</pre>', json.dumps(obj.responses, indent=2, ensure_ascii=False))
        except Exception:
            return "Error displaying responses"


@admin.register(TelegramUser)
class TelegramUserAdmin(admin.ModelAdmin):
    list_display = ('telegram_id', 'get_user_display', 'approved', 'notified_on_approval')
    list_filter = ('approved', 'notified_on_approval')
    search_fields = ('telegram_id', 'user__username', 'user__first_name', 'user__last_name')
    actions = ['approve_users', 'disapprove_users']
    list_select_related = ('user',)
    autocomplete_fields = ['user'] # Добавим автокомплит

    @admin.display(description='Пользователь Django', ordering='user__username')
    def get_user_display(self, obj):
        if obj.user:
            return f"{obj.user.get_full_name()} ({obj.user.username})"
        return "N/A"

    @admin.action(description='Подтвердить выбранных пользователей')
    def approve_users(self, request, queryset):
        # Сначала обновляем без вызова сигналов
        updated_count = queryset.filter(approved=False).update(approved=True)
        # Затем для тех, кого обновили и кто не был уведомлен, вызываем save для сигнала
        users_to_notify = queryset.filter(approved=True, notified_on_approval=False)
        notified_count = 0
        for user in users_to_notify:
            try:
                user.save(update_fields=['approved']) # Вызовет сигнал, который проверит флаг notified_on_approval
                notified_count +=1 # Считаем тех, для кого потенциально вызван сигнал
            except Exception as e:
                 self.message_user(request, f"Ошибка при сохранении пользователя {user.id} для уведомления: {e}", level='ERROR')

        self.message_user(request, f'{updated_count} пользователей было подтверждено. Попытка уведомления для {notified_count}.')


    @admin.action(description='Снять подтверждение у выбранных пользователей')
    def disapprove_users(self, request, queryset):
        updated = queryset.update(approved=False, notified_on_approval=False)
        self.message_user(request, f'Подтверждение снято у {updated} пользователей.')