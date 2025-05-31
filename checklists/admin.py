# checklists/admin.py
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.db.models import Count # Для аннотации

from .models import (
    Location, ChecklistPoint, ChecklistTemplate, ChecklistSection,
    ChecklistTemplateItem, Checklist, ChecklistResult
)

@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent', 'created_at', 'updated_at')
    list_filter = ('parent',)
    search_fields = ('name', 'description')
    ordering = ('name',)
    autocomplete_fields = ['parent']


@admin.register(ChecklistPoint)
class ChecklistPointAdmin(admin.ModelAdmin):
    list_display = ('name', 'location', 'created_at', 'updated_at')
    list_filter = ('location',)
    search_fields = ('name', 'description', 'location__name')
    ordering = ('location__name', 'name')
    raw_id_fields = ('location',) # Можно оставить raw_id или использовать autocomplete_fields
    autocomplete_fields = ['location'] # Если у LocationAdmin есть search_fields


# ---- НОВЫЕ РЕГИСТРАЦИИ ДЛЯ AUTOCOMPLETE ----
@admin.register(ChecklistSection)
class ChecklistSectionAdmin(admin.ModelAdmin):
    list_display = ('title', 'template', 'order', 'item_count')
    list_filter = ('template',)
    search_fields = ('title', 'template__name') # Обязательно для autocomplete_fields в других моделях
    ordering = ('template__name', 'order', 'title')
    list_select_related = ('template',)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(item_count_annotation=Count('items'))

    @admin.display(description=_("Пунктов"), ordering='item_count_annotation')
    def item_count(self, obj):
        return obj.item_count_annotation
    # item_count.admin_order_field = 'item_count_annotation' # Уже указано в display


@admin.register(ChecklistTemplateItem)
class ChecklistTemplateItemAdmin(admin.ModelAdmin):
    list_display = ('item_text_short', 'template', 'section', 'order', 'answer_type')
    list_filter = ('template', 'section', 'answer_type')
    search_fields = ('item_text', 'template__name', 'section__title') # Обязательно для autocomplete_fields
    ordering = ('template__name', 'section__order', 'order')
    list_select_related = ('template', 'section', 'target_point', 'parent_item')
    raw_id_fields = ('template', 'section', 'target_point', 'parent_item') # Можно оставить или заменить на autocomplete
    autocomplete_fields = ['template', 'section', 'target_point', 'parent_item'] # Для удобства

    @admin.display(description=_("Текст пункта (коротко)"))
    def item_text_short(self, obj):
        return obj.item_text[:75] + '...' if len(obj.item_text) > 75 else obj.item_text
# ---- КОНЕЦ НОВЫХ РЕГИСТРАЦИЙ ----


class ChecklistSectionInline(admin.StackedInline):
    model = ChecklistSection
    extra = 1
    fields = ('title', 'order',)
    verbose_name = _("Секция")
    verbose_name_plural = _("Секции")
    ordering = ('order', 'title')
    classes = ['collapse']
    # autocomplete_fields не нужны здесь, т.к. это создание новых секций


class ChecklistTemplateItemInline(admin.StackedInline):
    model = ChecklistTemplateItem
    extra = 1
    fields = ('section', 'order', 'item_text', 'answer_type', 'target_point', 'help_text', 'default_value', 'parent_item',)
    raw_id_fields = ('target_point',) # section и parent_item теперь могут быть autocomplete
    autocomplete_fields = ['section', 'target_point', 'parent_item'] # Убедитесь, что для этих моделей есть Admin с search_fields
    verbose_name = _("Пункт шаблона")
    verbose_name_plural = _("Пункты шаблона")
    ordering = ('section__order', 'order',)
    classes = ['collapse']
    fk_name = 'template'

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        template_id = request.resolver_match.kwargs.get('object_id')
        current_template = None
        if template_id:
            try:
                current_template = ChecklistTemplate.objects.get(pk=template_id)
            except ChecklistTemplate.DoesNotExist:
                pass

        if db_field.name == "section":
            if current_template:
                kwargs["queryset"] = ChecklistSection.objects.filter(template=current_template).order_by('order', 'title')
            else:
                kwargs["queryset"] = ChecklistSection.objects.none()
        
        if db_field.name == "parent_item":
            if current_template:
                # Исключаем текущий редактируемый элемент, если форма привязана к экземпляру
                # Это сложнее сделать для нового, еще не сохраненного инлайна.
                # Модель должна сама проверять на самореференс.
                qs = ChecklistTemplateItem.objects.filter(template=current_template)
                # if self.instance and self.instance.pk: # self.instance здесь это ChecklistTemplateItem
                #    qs = qs.exclude(pk=self.instance.pk)
                kwargs["queryset"] = qs.select_related('section').order_by('section__order', 'order', 'item_text')
            else:
                kwargs["queryset"] = ChecklistTemplateItem.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(ChecklistTemplate)
class ChecklistTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'version', 'is_active', 'is_archived', 'target_location_name', 'category_name_display', 'frequency', 'item_count_display', 'created_at') # item_count -> item_count_display
    list_filter = ('is_active', 'is_archived', 'category', 'target_location', 'frequency')
    search_fields = ('name', 'description', 'tags__name', 'category__name')
    raw_id_fields = ('target_point',) # category и target_location могут быть autocomplete
    autocomplete_fields = ['category', 'target_location', 'target_point']
    inlines = [ChecklistSectionInline, ChecklistTemplateItemInline]
    fieldsets = (
        (None, {
            'fields': ('name', 'description', 'uuid', 'version', 'is_active', 'is_archived', 'tags')
        }),
        (_('Целевые объекты и категоризация'), {
            'fields': ('category', 'target_location', 'target_point',)
        }),
        (_('Планирование'), {
            'fields': ('frequency', 'next_due_date')
        }),
        (_('Метаданные'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    readonly_fields = ('uuid', 'created_at', 'updated_at')
    save_on_top = True
    list_select_related = ('category', 'target_location')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.annotate(item_count_annotation=Count('items')) # Аннотация для сортировки
        return qs.select_related('category', 'target_location', 'target_point').prefetch_related('tags')

    @admin.display(description=_("Категория"), ordering='category__name')
    def category_name_display(self, obj):
        return obj.category.name if obj.category and hasattr(obj.category, 'name') else '-'

    @admin.display(description=_("Целевое местоположение"), ordering='target_location__name')
    def target_location_name(self, obj):
        return obj.target_location.name if obj.target_location else '-'

    @admin.display(description=_("Пунктов"), ordering='item_count_annotation')
    def item_count_display(self, obj): # Переименовано для ясности
        return obj.item_count_annotation


class ChecklistResultInline(admin.StackedInline):
    model = ChecklistResult
    extra = 0
    exclude = ('value', 'numeric_value', 'boolean_value', 'date_value', 'datetime_value', 'time_value', 'file_attachment', 'media_url')
    fields = ('template_item_link', 'display_value_admin', 'status', 'is_corrected', 'comments', 'recorded_at', 'created_by_link', 'updated_by_link')
    readonly_fields = ('template_item_link', 'display_value_admin', 'recorded_at', 'created_by_link', 'updated_by_link')
    raw_id_fields = ('created_by', 'updated_by') # template_item теперь autocomplete
    autocomplete_fields = ['template_item', 'created_by', 'updated_by'] # Добавлен template_item
    verbose_name = _("Результат пункта")
    verbose_name_plural = _("Результаты пунктов")
    ordering = ('template_item__section__order', 'template_item__order',)
    classes = ['collapse']
    fk_name = 'checklist_run'


    def template_item_link(self, obj):
        if obj.template_item:
            link = reverse("admin:checklists_checklisttemplateitem_change", args=[obj.template_item.pk])
            return format_html('<a href="{}">{}</a>', link, str(obj.template_item))
        return "-"
    template_item_link.short_description = _("Пункт шаблона")


    def created_by_link(self, obj):
        if obj.created_by:
            link = reverse("admin:user_profiles_user_change", args=[obj.created_by.id])
            return format_html('<a href="{}">{}</a>', link, obj.created_by.username)
        return "-"
    created_by_link.short_description = _("Создано кем")

    def updated_by_link(self, obj):
        if obj.updated_by:
            link = reverse("admin:user_profiles_user_change", args=[obj.updated_by.id])
            return format_html('<a href="{}">{}</a>', link, obj.updated_by.username)
        return "-"
    updated_by_link.short_description = _("Обновлено кем")


    @admin.display(description=_("Ответ"))
    def display_value_admin(self, obj):
        return obj.display_value

    def get_queryset(self, request):
         qs = super().get_queryset(request)
         return qs.select_related(
             'template_item',
             'template_item__section',
             'template_item__target_point',
             'created_by',
             'updated_by'
         )


@admin.register(Checklist)
class ChecklistAdmin(admin.ModelAdmin):
    list_display = ('checklist_name_display', 'template_name_admin', 'status_display_admin', 'performed_at', 'performed_by_username', 'location_name_admin', 'score_display', 'view_link')
    list_filter = ('status', 'is_complete', ('template', admin.RelatedOnlyFieldListFilter), ('location', admin.RelatedOnlyFieldListFilter), ('performed_by', admin.RelatedOnlyFieldListFilter), ('template__category', admin.RelatedOnlyFieldListFilter))
    search_fields = ('id__iexact','template__name', 'notes', 'performed_by__username', 'location__name', 'point__name', 'external_reference')
    raw_id_fields = ('related_task', 'approved_by') # template, performed_by, location, point могут быть autocomplete
    autocomplete_fields = ['template', 'performed_by', 'related_task', 'location', 'point', 'approved_by']
    inlines = [ChecklistResultInline]
    readonly_fields = ('id', 'created_at', 'updated_at', 'completion_time', 'approved_at', 'score')
    fieldsets = (
        (None, {
            'fields': ('template', 'performed_by', 'performed_at', 'status', 'is_complete', 'completion_time', 'score')
        }),
        (_('Связанные объекты'), {
            'fields': ('related_task', 'location', 'point', 'external_reference'),
             'classes': ('collapse',),
        }),
        (_('Примечания'), {
            'fields': ('notes',),
            'classes': ('collapse',),
        }),
        (_('Одобрение/Проверка'), {
            'fields': ('approved_by', 'approved_at',),
            'classes': ('collapse',)
        }),
        (_('Метаданные'), {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    ordering = ('-performed_at',)
    save_on_top = True
    date_hierarchy = 'performed_at'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related(
            'template', 'performed_by', 'location', 'point',
            'approved_by', 'template__category', 'related_task'
        )

    @admin.display(description=_("Чеклист"), ordering='template__name') # или id, если __str__ включает id
    def checklist_name_display(self, obj):
        return str(obj)

    @admin.display(description=_("Шаблон"), ordering='template__name')
    def template_name_admin(self,obj):
        if obj.template:
            link = reverse("admin:checklists_checklisttemplate_change", args=[obj.template.pk])
            return format_html('<a href="{}">{}</a>', link, obj.template.name)
        return '-'

    @admin.display(description=_("Статус"), ordering='status')
    def status_display_admin(self, obj): # Переименовано, чтобы не конфликтовать с полем status
        return obj.get_status_display()


    @admin.display(description=_("Кем выполнен"), ordering='performed_by__username')
    def performed_by_username(self,obj):
        if obj.performed_by:
            link = reverse("admin:user_profiles_user_change", args=[obj.performed_by.id])
            return format_html('<a href="{}">{}</a>', link, obj.performed_by.username)
        return '-'

    @admin.display(description=_("Местоположение"), ordering='location__name')
    def location_name_admin(self,obj):
        if obj.location:
            link = reverse("admin:checklists_location_change", args=[obj.location.id])
            return format_html('<a href="{}">{}</a>', link, obj.location.name)
        return '-'

    @admin.display(description=_("Точка"), ordering='point__name')
    def point_name_admin(self,obj):
        if obj.point:
            link = reverse("admin:checklists_checklistpoint_change", args=[obj.point.id])
            return format_html('<a href="{}">{}</a>', link, obj.point.name)
        return '-'

    @admin.display(description=_("Оценка"), ordering='score')
    def score_display(self, obj):
        return obj.score if obj.score is not None else "-"


    @admin.display(description=_("Ссылка на просмотр"))
    def view_link(self, obj):
        if obj.pk:
            url = reverse('checklists:checklist_detail', kwargs={'pk': obj.pk})
            return format_html('<a href="{}" target="_blank"><i class="fas fa-external-link-alt"></i> {}</a>', url, _('Просмотр'))
        return "-"