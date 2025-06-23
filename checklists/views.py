# checklists/views.py
import logging
from django.db import transaction, models as django_db_models
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.views.generic import (
    ListView,
    DetailView,
    CreateView,
    UpdateView,
    DeleteView,
    View,
)
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.db.models import Count, Q, Prefetch, Avg
from django.http import JsonResponse, HttpResponseRedirect
from django.core.exceptions import PermissionDenied

from .models import (
    ChecklistTemplate,
    ChecklistTemplateItem,
    Checklist,
    ChecklistResult,
    ChecklistItemStatus,
    Location,
    ChecklistPoint,
    ChecklistRunStatus,
    ChecklistSection,
)
from .forms import (
    ChecklistTemplateForm,
    ChecklistTemplateItemFormSet,
    PerformChecklistResultFormSet,
    ChecklistStatusUpdateForm,
)
from .filters import ChecklistHistoryFilter, ChecklistTemplateFilter
from .utils import calculate_checklist_score

from .serializers import ChecklistPointSerializer
from rest_framework import generics, permissions as drf_permissions
from django_filters.rest_framework import DjangoFilterBackend


logger = logging.getLogger(__name__)


class CanPerformChecklistMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_active

    def handle_no_permission(self):
        messages.error(self.request, _("У вас нет прав для выполнения чеклистов."))
        return redirect(reverse_lazy("profiles:base_login"))


class CanManageTemplatesMixin(UserPassesTestMixin):
    permission_denied_message = _("У вас нет прав для управления шаблонами чеклистов.")
    raise_exception = True # Будет вызываться PermissionDenied, обрабатываемый стандартным механизмом Django

    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_staff


class CanReviewChecklistMixin(UserPassesTestMixin):
    permission_denied_message = _("У вас нет прав для просмотра отчетов или изменения статуса чеклистов.")
    raise_exception = True

    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_staff


class CanConfirmChecklistMixin(UserPassesTestMixin):
    """Mixin requiring the confirm_checklist permission."""

    permission_denied_message = _("У вас нет прав подтверждать чеклисты.")
    raise_exception = True

    def test_func(self):
        user = self.request.user
        return user.is_authenticated and user.has_perm("checklists.confirm_checklist")


class ChecklistTemplateListView(LoginRequiredMixin, ListView):
    model = ChecklistTemplate
    template_name = "checklists/template_list.html"
    context_object_name = "templates"
    paginate_by = 20

    def get_queryset(self):
        queryset = ChecklistTemplate.objects.filter(is_archived=False)
        related_fields = ["target_location", "target_point"]
        order_by_fields = ["name"]
        if (
            ChecklistTemplate._meta.get_field("category").remote_field.model is not None
            and not isinstance(ChecklistTemplate._meta.get_field("category").remote_field.model, str)
            and hasattr(ChecklistTemplate._meta.get_field("category").remote_field.model, '_meta') # Доп. проверка
            and ChecklistTemplate._meta.get_field("category").remote_field.model._meta.concrete_model
        ):
            related_fields.append("category")
            order_by_fields.insert(0, "category__name")

        self.filterset = ChecklistTemplateFilter(self.request.GET, queryset=queryset)

        return (
            self.filterset.qs.select_related(*related_fields)
            .annotate(item_count_agg=Count("items"), run_count_agg=Count("runs"))
            .order_by(*order_by_fields)
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = _("Шаблоны чеклистов")
        context['can_create_template'] = self.request.user.is_staff
        context["filterset"] = getattr(self, "filterset", None)
        return context


class ChecklistTemplateDetailView(LoginRequiredMixin, DetailView):
    model = ChecklistTemplate
    template_name = "checklists/template_detail.html"
    context_object_name = "template"

    def get_queryset(self):
        related_fields = ["target_location", "target_point"]
        if (
            ChecklistTemplate._meta.get_field("category").remote_field.model is not None
            and not isinstance(ChecklistTemplate._meta.get_field("category").remote_field.model, str)
            and hasattr(ChecklistTemplate._meta.get_field("category").remote_field.model, '_meta')
            and ChecklistTemplate._meta.get_field("category").remote_field.model._meta.concrete_model
        ):
            related_fields.append("category")

        return (
            super()
            .get_queryset()
            .select_related(*related_fields)
            .prefetch_related(
                Prefetch(
                    "sections", queryset=ChecklistSection.objects.order_by("order")
                ),
                Prefetch(
                    "items",
                    queryset=ChecklistTemplateItem.objects.select_related(
                        "target_point", "section"
                    ).order_by("section__order", "order"),
                ),
                Prefetch('tags') # Предзагрузка тегов
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        template_obj = self.object # Уже загруженный объект
        context["page_title"] = _("Шаблон чеклиста: %s") % template_obj.name
        # Группируем пункты по секциям и отдельно те, что без секции
        items_by_section = {}
        unsectioned_items = []
        for item in template_obj.items.all(): # items.all() будет использовать prefetch
            if item.section:
                if item.section not in items_by_section:
                    items_by_section[item.section] = []
                items_by_section[item.section].append(item)
            else:
                unsectioned_items.append(item)

        # Сортируем секции по их order
        sorted_sections = sorted(items_by_section.keys(), key=lambda s: s.order)
        context["grouped_items"] = [(section, items_by_section[section]) for section in sorted_sections]
        context["unsectioned_items"] = unsectioned_items

        context['can_edit'] = self.request.user.is_staff
        context['can_delete'] = self.request.user.is_staff
        return context


class ChecklistTemplateCreateView(
    LoginRequiredMixin, CanManageTemplatesMixin, SuccessMessageMixin, CreateView
):
    model = ChecklistTemplate
    form_class = ChecklistTemplateForm
    template_name = "checklists/template_form.html"
    success_message = _("Шаблон чеклиста '%(name)s' успешно создан.")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = _("Создать шаблон чеклиста")
        context["form_action_text"] = _("Создать шаблон") # Более точный текст кнопки
        
        # self.object здесь None, так как это CreateView
        # Для item_formset instance должен быть ChecklistTemplate(), если это новый объект
        # или self.object, если форма была невалидна и перерисовывается
        template_instance = self.object if self.object and self.object.pk else ChecklistTemplate()

        if self.request.POST:
            context["item_formset"] = ChecklistTemplateItemFormSet(
                self.request.POST,
                self.request.FILES,
                prefix="items",
                instance=template_instance, # Передаем текущий объект (может быть несохраненным)
                form_kwargs={"parent_instance": template_instance},
            )
        else:
            context["item_formset"] = ChecklistTemplateItemFormSet(
                prefix="items",
                queryset=ChecklistTemplateItem.objects.none(), # Пустой queryset для новой формы
                instance=template_instance, # Для связи
                form_kwargs={"parent_instance": template_instance},
            )
        return context

    def form_valid(self, form):
        # self.object устанавливается в form.instance после form.is_valid() в базовом CreateView,
        # но до вызова form.save(). Мы сохраняем его явно, чтобы получить PK для formset.
        self.object = form.save(commit=False) # Пока не сохраняем в базу

        item_formset = ChecklistTemplateItemFormSet(
            self.request.POST,
            self.request.FILES,
            prefix="items",
            instance=self.object, # self.object здесь еще не имеет PK, если это новая запись
            form_kwargs={"parent_instance": self.object},
        )

        if item_formset.is_valid():
            with transaction.atomic():
                self.object.save() # Сохраняем основной объект, чтобы получить PK
                form.save_m2m()    # Сохраняем M2M поля основной формы (например, tags)
                
                # Теперь, когда self.object сохранен и имеет PK, связываем и сохраняем формсет
                item_formset.instance = self.object
                item_formset.save()

                logger.info(
                    f"Checklist Template '{self.object.name}' created by {self.request.user.username}"
                )
                messages.success(
                    self.request, self.get_success_message(form.cleaned_data)
                )
                return HttpResponseRedirect(self.get_success_url()) # Redirect после успешного сохранения
        else:
            logger.warning(
                f"Item formset invalid during template create: {item_formset.errors}"
            )
            # Если формсет невалиден, перерисовываем страницу с ошибками
            # form_invalid из CreateView должен быть вызван автоматически, если основная форма невалидна
            # Если основная валидна, а формсет нет, нужно вызвать form_invalid явно.
            return self.form_invalid(form, item_formset=item_formset)


    def form_invalid(self, form, item_formset=None): # Добавили item_formset как параметр
        logger.warning(f"Checklist Template form invalid on create: {form.errors}")
        context = self.get_context_data(form=form) # Получаем контекст с основной формой
        # Если item_formset был передан (т.е. он был невалиден), используем его
        # иначе, если он не был обработан в form_valid, инициализируем его с POST данными
        if item_formset:
            context["item_formset"] = item_formset
        elif self.request.POST: # Только если был POST запрос
             template_instance = self.object if self.object and self.object.pk else form.instance # form.instance может быть несохраненным
             context["item_formset"] = ChecklistTemplateItemFormSet(
                self.request.POST,
                self.request.FILES,
                prefix="items",
                instance=template_instance,
                form_kwargs={"parent_instance": template_instance},
            )
        # Если это GET запрос и item_formset не передан, он уже инициализирован в get_context_data
        return self.render_to_response(context)

    def get_success_url(self):
        # Перенаправляем на страницу деталей созданного шаблона
        return reverse("checklists:template_detail", kwargs={"pk": self.object.pk})


class ChecklistTemplateUpdateView(
    LoginRequiredMixin, CanManageTemplatesMixin, SuccessMessageMixin, UpdateView
):
    model = ChecklistTemplate
    form_class = ChecklistTemplateForm
    template_name = "checklists/template_form.html"
    success_message = _("Шаблон чеклиста '%(name)s' успешно обновлен.")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = _("Редактировать шаблон: %s") % self.object.name
        context["form_action_text"] = _("Сохранить изменения")
        if self.request.POST:
            context["item_formset"] = ChecklistTemplateItemFormSet(
                self.request.POST,
                self.request.FILES,
                instance=self.object, # self.object здесь - это существующий экземпляр
                prefix="items",
                form_kwargs={"parent_instance": self.object},
            )
        else:
            context["item_formset"] = ChecklistTemplateItemFormSet(
                instance=self.object,
                prefix="items",
                form_kwargs={"parent_instance": self.object},
            )
        return context

    def form_valid(self, form):
        # self.object уже установлен UpdateView
        item_formset = ChecklistTemplateItemFormSet( # Важно пересоздать с POST данными
            self.request.POST,
            self.request.FILES,
            instance=self.object,
            prefix="items",
            form_kwargs={"parent_instance": self.object}
        )

        if item_formset.is_valid():
            with transaction.atomic():
                self.object = form.save() # Сохраняет основную форму и ее M2M
                item_formset.instance = self.object # Убедимся, что instance правильный
                item_formset.save() # Сохраняет изменения в формсете

                logger.info(
                    f"Checklist Template '{self.object.name}' updated by {self.request.user.username}"
                )
                messages.success(
                    self.request, self.get_success_message(form.cleaned_data)
                )
                return HttpResponseRedirect(self.get_success_url())
        else:
            logger.warning(
                f"Item formset invalid during template update for template {self.object.id}: {item_formset.errors}"
            )
            return self.form_invalid(form, item_formset=item_formset) # Передаем невалидный формсет

    def form_invalid(self, form, item_formset=None):
        logger.warning(
            f"Template update form invalid for template {self.object.id}: {form.errors}"
        )
        context = self.get_context_data(form=form) # Получаем контекст с основной формой
        if item_formset: # Если формсет был передан из form_valid
            context["item_formset"] = item_formset
        # Иначе get_context_data уже должен был инициализировать его с POST данными, если это был POST
        return self.render_to_response(context)

    def get_success_url(self):
        return reverse("checklists:template_detail", kwargs={"pk": self.object.pk})


class ChecklistTemplateDeleteView(
    LoginRequiredMixin, CanManageTemplatesMixin, DeleteView
):
    model = ChecklistTemplate
    template_name = "checklists/template_confirm_delete.html"
    success_url = reverse_lazy("checklists:template_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = _("Удалить шаблон: %s") % self.object.name
        return context

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        object_name = self.object.name
        try:
            if self.object.runs.exists():
                messages.error(
                    self.request,
                    _(
                        "Невозможно удалить шаблон '%(name)s', так как существуют связанные выполненные чеклисты. Архивируйте шаблон вместо удаления."
                    ) % {"name": object_name},
                )
                return redirect(self.object.get_absolute_url())

            response = super().delete(request, *args, **kwargs)
            messages.success(
                self.request, _("Шаблон чеклиста '%s' успешно удален.") % object_name
            )
            logger.info(
                f"Checklist Template '{object_name}' deleted by {self.request.user.username}"
            )
            return response

        except django_db_models.ProtectedError:
            logger.warning(
                f"Attempted to delete protected template '{object_name}' due to ProtectedError."
            )
            messages.error(
                self.request,
                 _(
                        "Невозможно удалить шаблон '%(name)s', так как существуют связанные выполненные чеклисты (ProtectedError). Архивируйте шаблон вместо удаления."
                    ) % {"name": object_name},
            )
            return redirect(self.object.get_absolute_url())
        except Exception as e:
            logger.exception(f"Error deleting template '{object_name}': {e}")
            messages.error(self.request, _("Произошла ошибка при удалении шаблона."))
            return redirect(self.object.get_absolute_url())


class PerformChecklistView(LoginRequiredMixin, CanPerformChecklistMixin, View):
    template_name = "checklists/perform_checklist.html"

    def get_checklist_run(self, request, template):
        today = timezone.now().date()
        checklist_run = Checklist.objects.filter(
            template=template,
            performed_by=request.user,
            performed_at__date=today, # Ищем только за сегодня
            status__in=[ChecklistRunStatus.DRAFT, ChecklistRunStatus.IN_PROGRESS],
        ).order_by('-created_at').first()

        if not checklist_run:
            checklist_run = Checklist.objects.create(
                template=template,
                performed_by=request.user,
                performed_at=timezone.now(),
                location=template.target_location,
                point=template.target_point,
                status=ChecklistRunStatus.IN_PROGRESS,
            )
            logger.info(
                f"Created new Checklist run {checklist_run.id} for template {template.id} by {request.user.username}"
            )
        elif checklist_run.status == ChecklistRunStatus.DRAFT:
            checklist_run.status = ChecklistRunStatus.IN_PROGRESS
            checklist_run.save(update_fields=['status'])
            logger.info(f"Resumed DRAFT checklist run {checklist_run.id}, now IN_PROGRESS.")
        return checklist_run

    def get_formset(self, checklist_run, data=None, files=None):
        queryset = (
            ChecklistResult.objects.filter(checklist_run=checklist_run)
            .select_related(
                "template_item", "template_item__section", "template_item__target_point"
            )
            .order_by("template_item__section__order", "template_item__order")
        )
        return PerformChecklistResultFormSet(
            data, files, instance=checklist_run, prefix="results", queryset=queryset
        )

    def get(self, request, template_pk):
        template = get_object_or_404(ChecklistTemplate, pk=template_pk, is_active=True, is_archived=False)
        checklist_run = self.get_checklist_run(request, template)

        if checklist_run.status not in [ChecklistRunStatus.DRAFT, ChecklistRunStatus.IN_PROGRESS]:
            messages.info(request, _("Этот чеклист уже обработан и не может быть изменен здесь."))
            return redirect(checklist_run.get_absolute_url())

        formset = self.get_formset(checklist_run)
        context = {
            "page_title": _("Выполнение: %s") % template.name,
            "template": template,
            "checklist_run": checklist_run,
            "formset": formset,
            "location": checklist_run.location, # Передаем для отображения
            "point": checklist_run.point,       # Передаем для отображения
        }
        return render(request, self.template_name, context)

    def post(self, request, template_pk):
        template = get_object_or_404(ChecklistTemplate, pk=template_pk, is_active=True, is_archived=False)
        run_id = request.POST.get("checklist_run_id")
        if not run_id:
            messages.error(request, _("Идентификатор чеклиста не найден."))
            return redirect(reverse("checklists:template_list"))

        checklist_run = get_object_or_404(Checklist, pk=run_id, template=template)

        if checklist_run.status not in [ChecklistRunStatus.DRAFT, ChecklistRunStatus.IN_PROGRESS]:
            messages.error(request, _("Этот чеклист уже обработан и не может быть изменен."))
            return redirect(checklist_run.get_absolute_url())

        if checklist_run.performed_by != request.user and not request.user.is_staff:
            messages.error(self.request, _("У вас нет прав на изменение этого чеклиста."))
            return redirect(checklist_run.get_absolute_url())


        formset = self.get_formset(checklist_run, data=request.POST, files=request.FILES)
        action = request.POST.get("action")

        if formset.is_valid():
            try:
                with transaction.atomic():
                    results_saved = formset.save(commit=False)
                    for result_form_instance in results_saved: # result_form_instance это ChecklistResult
                        if not result_form_instance.created_by: result_form_instance.created_by = request.user
                        result_form_instance.updated_by = request.user
                        result_form_instance.save()
                    
                    # formset.save_m2m() # Если бы в формах формсета были M2M

                    if action == "submit_final":
                        if not request.user.has_perm("checklists.confirm_checklist"):
                            messages.error(request, _("У вас нет прав подтверждать чеклисты."))
                            return redirect(checklist_run.get_absolute_url())
                        pending_items_count = checklist_run.results.filter(status=ChecklistItemStatus.PENDING).count()
                        if pending_items_count > 0:
                            messages.error(request, _("Не все пункты чеклиста заполнены. Пожалуйста, ответьте на все ожидающие пункты (%s) перед отправкой.") % pending_items_count)
                            context = {"page_title": _("Выполнение: %s") % template.name, "template": template, "checklist_run": checklist_run, "formset": formset, "location": checklist_run.location, "point": checklist_run.point}
                            return render(request, self.template_name, context)

                        checklist_run.mark_complete()
                        score = calculate_checklist_score(checklist_run)
                        checklist_run.score = score if score is not None else None
                        checklist_run.save(update_fields=["score"]) # Сохраняем только обновленный score
                        logger.info(f"Calculated score {score} for submitted run {checklist_run.id}")
                        messages.success(request, _("Чеклист '%(name)s' успешно завершен и отправлен.") % {"name": template.name})
                        return redirect(reverse("checklists:history_list"))

                    elif action == "save_draft":
                        if checklist_run.status != ChecklistRunStatus.DRAFT:
                            checklist_run.status = ChecklistRunStatus.DRAFT
                            checklist_run.save(update_fields=['status'])
                        messages.success(request, _("Чеклист '%(name)s' сохранен как черновик.") % {"name": template.name})
                        return redirect(request.path)
                    else:
                        messages.error(request, _("Неизвестное действие."))
            except PermissionDenied:
                raise
            except Exception as e:
                logger.exception(f"Error saving checklist run {checklist_run.id}: {e}")
                messages.error(request, _("Произошла ошибка при сохранении чеклиста."))
        else:
            logger.warning(f"Invalid ChecklistResultFormSet for run {checklist_run.id}: {formset.errors}")
            messages.error(request, _("Пожалуйста, исправьте ошибки в пунктах чеклиста."))

        context = {"page_title": _("Выполнение: %s") % template.name, "template": template, "checklist_run": checklist_run, "formset": formset, "location": checklist_run.location, "point": checklist_run.point }
        return render(request, self.template_name, context)


class ChecklistHistoryListView(LoginRequiredMixin, ListView):
    model = Checklist
    template_name = "checklists/history_list.html"
    context_object_name = "checklist_runs"
    paginate_by = 20

    def get_queryset(self):
        base_queryset = (
            Checklist.objects
            .select_related("template", "performed_by", "template__category", "related_task", "location", "point")
        )
        if not self.request.user.is_staff:
            base_queryset = base_queryset.filter(performed_by=self.request.user)
        
        base_queryset = base_queryset.order_by(self.request.GET.get("sort", "-performed_at"))

        self.filterset = ChecklistHistoryFilter(self.request.GET, queryset=base_queryset)
        return self.filterset.qs.distinct() # distinct() может быть нужен из-за JOIN'ов в фильтрах

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filterset"] = self.filterset
        context["page_title"] = _("История выполнения чеклистов")
        context["current_sort"] = self.request.GET.get("sort", "-performed_at")
        # Добавляем параметры фильтрации для сохранения их в URL пагинации и сортировки
        # context['filter_params'] = self.request.GET.urlencode() # Это сделано в шаблоне через request.GET.urlencode
        return context


class ChecklistDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = Checklist
    template_name = "checklists/checklist_detail.html"
    context_object_name = "checklist_run"
    pk_url_kwarg = "pk"

    def test_func(self):
        run = self.get_object()
        return run.performed_by == self.request.user or self.request.user.is_staff

    def handle_no_permission(self):
        messages.error(self.request, _("У вас нет прав для просмотра этого результата чеклиста."))
        return redirect(reverse_lazy("checklists:history_list"))

    def get_queryset(self):
        related_fields = ["template", "performed_by", "related_task", "location", "point", "approved_by"]
        if (
            ChecklistTemplate._meta.get_field("category").remote_field.model is not None
            and not isinstance(ChecklistTemplate._meta.get_field("category").remote_field.model, str)
            and hasattr(ChecklistTemplate._meta.get_field("category").remote_field.model, '_meta')
            and ChecklistTemplate._meta.get_field("category").remote_field.model._meta.concrete_model
        ):
            related_fields.append("template__category")

        return (
            super()
            .get_queryset()
            .select_related(*related_fields)
            .prefetch_related(
                Prefetch(
                    "results",
                    queryset=ChecklistResult.objects.select_related(
                        "template_item", "template_item__section", "template_item__target_point",
                        "created_by", "updated_by"
                    ).order_by("template_item__section__order", "template_item__order"),
                )
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        run = self.object
        context["page_title"] = _("Результаты чеклиста") # Убран str(self.object) для краткости
        context["page_subtitle"] = str(run) # Используем __str__ для подзаголовка
        context["results"] = run.results.all()

        can_change_status = (
            self.request.user.is_staff and
            run.status in [ChecklistRunStatus.SUBMITTED, ChecklistRunStatus.REJECTED]
        )
        if can_change_status:
            context["status_form"] = ChecklistStatusUpdateForm(instance=run)

        can_edit_results = (
            (run.performed_by == self.request.user or self.request.user.is_staff) and
            run.status in [ChecklistRunStatus.DRAFT, ChecklistRunStatus.IN_PROGRESS]
        )
        context["can_edit_results"] = can_edit_results
        if can_edit_results:
            context["edit_url"] = reverse('checklists:checklist_perform', kwargs={'template_pk': run.template.pk})
        return context


class ChecklistStatusUpdateView(LoginRequiredMixin, CanConfirmChecklistMixin, UpdateView):
    model = Checklist
    form_class = ChecklistStatusUpdateForm
    template_name = "checklists/checklist_status_form.html"
    pk_url_kwarg = "pk"
    context_object_name = "checklist_run"

    def get_queryset(self):
        return super().get_queryset().filter(status__in=[ChecklistRunStatus.SUBMITTED, ChecklistRunStatus.REJECTED])

    def get_object(self, queryset=None):
        obj = super().get_object(queryset=queryset)
        if hasattr(obj, 'status'): # Проверяем, что у объекта есть статус (на случай пустого queryset)
            obj._original_status = obj.status
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = _("Изменить статус чеклиста")
        context["page_subtitle"] = str(self.object)
        return context

    def form_valid(self, form):
        # Устанавливаем approved_by перед сохранением, если статус меняется на APPROVED или REJECTED
        if form.cleaned_data.get('status') in [ChecklistRunStatus.APPROVED, ChecklistRunStatus.REJECTED]:
            if not form.cleaned_data.get('approved_by'): # Если не выбрано, ставим текущего юзера
                form.instance.approved_by = self.request.user

        response = super().form_valid(form)

        if self.object.status in [ChecklistRunStatus.APPROVED, ChecklistRunStatus.REJECTED]:
            score = calculate_checklist_score(self.object)
            if self.object.score != score: # Обновляем только если изменилось
                self.object.score = score
                self.object.save(update_fields=["score"])
                logger.info(f"Updated score to {score} for run {self.object.id} after status change.")

        messages.success(self.request, _("Статус чеклиста '%s' успешно обновлен.") % str(self.object))
        return response

    def form_invalid(self, form):
        logger.warning(f"Checklist status update form invalid for run {self.object.id}: {form.errors}")
        messages.error(self.request, _("Ошибка при обновлении статуса. Пожалуйста, исправьте ошибки."))
        return super().form_invalid(form)

    def get_success_url(self):
        return reverse_lazy("checklists:checklist_detail", kwargs={"pk": self.object.pk})


class ChecklistReportView(LoginRequiredMixin, CanReviewChecklistMixin, ListView):
    template_name = "checklists/report_summary.html"
    context_object_name = "report_data" # Это будет queryset шаблонов с аннотациями

    def get_queryset(self):
        # Берем только завершенные или одобренные/отклоненные для отчета
        finalized_runs_qs = Checklist.objects.filter(status__in=[ChecklistRunStatus.SUBMITTED, ChecklistRunStatus.APPROVED, ChecklistRunStatus.REJECTED])

        start_date_str = self.request.GET.get("start_date")
        end_date_str = self.request.GET.get("end_date")

        if start_date_str:
            try:
                start_date = timezone.datetime.strptime(start_date_str, "%Y-%m-%d").date()
                finalized_runs_qs = finalized_runs_qs.filter(performed_at__date__gte=start_date)
            except ValueError: messages.warning(self.request, _("Неверный формат начальной даты."))
        if end_date_str:
            try:
                end_date = timezone.datetime.strptime(end_date_str, "%Y-%m-%d").date()
                finalized_runs_qs = finalized_runs_qs.filter(performed_at__date__lte=end_date)
            except ValueError: messages.warning(self.request, _("Неверный формат конечной даты."))

        order_by_fields = ["name"]
        related_fields = []
        if (
            ChecklistTemplate._meta.get_field("category").remote_field.model is not None
            and not isinstance(ChecklistTemplate._meta.get_field("category").remote_field.model, str)
            and hasattr(ChecklistTemplate._meta.get_field("category").remote_field.model, '_meta')
            and ChecklistTemplate._meta.get_field("category").remote_field.model._meta.concrete_model
        ):
            order_by_fields.insert(0, "category__name")
            related_fields.append("category")

        report = (
            ChecklistTemplate.objects.filter(runs__in=finalized_runs_qs, is_archived=False)
            .annotate(
                total_runs=Count("runs", filter=Q(runs__in=finalized_runs_qs)),
                runs_with_issues=Count("runs", filter=Q(runs__in=finalized_runs_qs, runs__results__status=ChecklistItemStatus.NOT_OK), distinct=True),
                avg_score=Avg('runs__score', filter=Q(runs__in=finalized_runs_qs, runs__score__isnull=False)) # Средний балл
            )
            .filter(total_runs__gt=0)
            .select_related(*related_fields)
            .order_by(*order_by_fields)
        )
        return report

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = _("Сводный отчет по чеклистам")

        finalized_runs_in_period = Checklist.objects.filter(status__in=[ChecklistRunStatus.SUBMITTED, ChecklistRunStatus.APPROVED, ChecklistRunStatus.REJECTED])
        start_date_str = self.request.GET.get("start_date")
        end_date_str = self.request.GET.get("end_date")

        if start_date_str:
            try:
                start_date = timezone.datetime.strptime(start_date_str, "%Y-%m-%d").date()
                finalized_runs_in_period = finalized_runs_in_period.filter(performed_at__date__gte=start_date)
            except ValueError: pass
        if end_date_str:
            try:
                end_date = timezone.datetime.strptime(end_date_str, "%Y-%m-%d").date()
                finalized_runs_in_period = finalized_runs_in_period.filter(performed_at__date__lte=end_date)
            except ValueError: pass

        total_completed = finalized_runs_in_period.count()
        total_with_issues = finalized_runs_in_period.filter(results__status=ChecklistItemStatus.NOT_OK).distinct().count()
        
        context["total_completed_runs"] = total_completed
        context["total_runs_with_issues"] = total_with_issues
        if total_completed > 0:
            context["overall_percentage_ok"] = ((total_completed - total_with_issues) / total_completed) * 100
        else:
            context["overall_percentage_ok"] = None

        context["start_date"] = start_date_str
        context["end_date"] = end_date_str
        return context


class ChecklistIssuesReportView(LoginRequiredMixin, CanReviewChecklistMixin, ListView):
    template_name = "checklists/report_issues.html"
    context_object_name = "issue_results"
    paginate_by = 50

    def get_queryset(self):
        queryset = ChecklistResult.objects.filter(status=ChecklistItemStatus.NOT_OK)

        start_date_str = self.request.GET.get("start_date")
        end_date_str = self.request.GET.get("end_date")

        if start_date_str:
            try:
                start_date = timezone.datetime.strptime(start_date_str, "%Y-%m-%d").date()
                queryset = queryset.filter(checklist_run__performed_at__date__gte=start_date)
            except ValueError:
                messages.warning(self.request, _("Неверный формат начальной даты."))
        if end_date_str:
            try:
                end_date = timezone.datetime.strptime(end_date_str, "%Y-%m-%d").date()
                queryset = queryset.filter(checklist_run__performed_at__date__lte=end_date)
            except ValueError:
                messages.warning(self.request, _("Неверный формат конечной даты."))

        queryset = queryset.select_related(
            "checklist_run__template",
            "checklist_run__performed_by",
            "template_item",
            "template_item__section",
            "checklist_run__location",
            "checklist_run__point",
            "created_by",
            "updated_by",
        ).order_by("-checklist_run__performed_at", "template_item__section__order", "template_item__order")
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = _("Отчет по пунктам с проблемами")
        context["start_date"] = self.request.GET.get("start_date")
        context["end_date"] = self.request.GET.get("end_date")
        return context


class ChecklistPointListView(generics.ListAPIView):
    serializer_class = ChecklistPointSerializer
    permission_classes = [drf_permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["location"]

    def get_queryset(self):
        return (
            ChecklistPoint.objects.all()
            .select_related("location")
            .order_by("location__name", "name")
        )
