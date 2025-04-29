# checklists/views.py
import logging
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, View
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.db.models import Count, Q # Import Q for filtering issues

from django.db import models
from django.db.models import Prefetch
from .models import (
    ChecklistTemplate, ChecklistTemplateItem, Checklist, ChecklistResult, ChecklistItemStatus
)
from .forms import (
    ChecklistTemplateForm, ChecklistTemplateItemFormSet, ChecklistResultFormSet
)

logger = logging.getLogger(__name__)

# ==================================
# Checklist Template Views
# ==================================
class ChecklistTemplateListView(LoginRequiredMixin, ListView):
    model = ChecklistTemplate
    template_name = 'checklists/template_list.html'
    context_object_name = 'templates'
    paginate_by = 20

    def get_queryset(self):
        # Show active by default, allow filter via GET param?
        # queryset = ChecklistTemplate.objects.filter(is_active=True)
        queryset = ChecklistTemplate.objects.all() # Show all for now
        return queryset.select_related('category').annotate(item_count_agg=Count('items')).order_by('category__name', 'name')

class ChecklistTemplateDetailView(LoginRequiredMixin, DetailView):
    model = ChecklistTemplate
    template_name = 'checklists/template_detail.html'
    context_object_name = 'template'

    def get_queryset(self):
        # Order items by the 'order' field
        return super().get_queryset().prefetch_related(models.Prefetch('items', queryset=ChecklistTemplateItem.objects.order_by('order')))

class ChecklistTemplateCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = ChecklistTemplate
    form_class = ChecklistTemplateForm
    template_name = 'checklists/template_form.html'
    success_message = _("Шаблон чеклиста '%(name)s' успешно создан.")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Создать шаблон чеклиста")
        if self.request.POST:
            context['item_formset'] = ChecklistTemplateItemFormSet(self.request.POST, prefix='items')
        else:
            context['item_formset'] = ChecklistTemplateItemFormSet(prefix='items', queryset=ChecklistTemplateItem.objects.none())
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        item_formset = context['item_formset']
        with transaction.atomic():
            # Save the main template form
            self.object = form.save()
            # Check if the item formset is also valid
            if item_formset.is_valid():
                # Set the instance for the formset and save
                item_formset.instance = self.object
                item_formset.save()
                logger.info(f"Checklist Template '{self.object.name}' created by {self.request.user.username}")
                messages.success(self.request, self.get_success_message(form.cleaned_data))
                return redirect(self.get_success_url())
            else:
                # Formset invalid, transaction rolls back. Re-render with errors.
                logger.warning(f"Checklist Template item formset invalid during create: {item_formset.errors}")
                # Add formset errors to context for display
                context['item_formset'] = item_formset
                return self.render_to_response(context)

    def form_invalid(self, form):
        logger.warning(f"Checklist Template form invalid: {form.errors}")
        # Pass back the main form with errors AND the item formset (re-initialized with POST data)
        context = self.get_context_data(form=form)
        return self.render_to_response(context)

    def get_success_url(self):
        return reverse('checklists:template_detail', kwargs={'pk': self.object.pk})

class ChecklistTemplateUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = ChecklistTemplate
    form_class = ChecklistTemplateForm
    template_name = 'checklists/template_form.html'
    success_message = _("Шаблон чеклиста '%(name)s' успешно обновлен.")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Редактировать шаблон: ") + self.object.name
        if self.request.POST:
            context['item_formset'] = ChecklistTemplateItemFormSet(self.request.POST, instance=self.object, prefix='items')
        else:
            context['item_formset'] = ChecklistTemplateItemFormSet(instance=self.object, prefix='items')
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        item_formset = context['item_formset']
        with transaction.atomic():
            self.object = form.save()
            if item_formset.is_valid():
                item_formset.instance = self.object
                item_formset.save()
                logger.info(f"Checklist Template '{self.object.name}' updated by {self.request.user.username}")
                messages.success(self.request, self.get_success_message(form.cleaned_data))
                return redirect(self.get_success_url())
            else:
                logger.warning(f"Checklist Template update item formset invalid for template {self.object.id}: {item_formset.errors}")
                context['item_formset'] = item_formset # Pass back invalid formset
                return self.render_to_response(context) # Rerender with errors

    def form_invalid(self, form):
        logger.warning(f"Checklist Template update form invalid for template {self.object.id}: {form.errors}")
        context = self.get_context_data(form=form) # Re-initializes item_formset with POST data
        return self.render_to_response(context)

    def get_success_url(self):
        return reverse('checklists:template_detail', kwargs={'pk': self.object.pk})

class ChecklistTemplateDeleteView(LoginRequiredMixin, SuccessMessageMixin, DeleteView):
    model = ChecklistTemplate
    template_name = 'checklists/template_confirm_delete.html'
    success_url = reverse_lazy('checklists:template_list')
    success_message = _("Шаблон чеклиста '%(name)s' успешно удален.")

    def form_valid(self, form):
        # Messages need to be displayed before the object is deleted
        # Using delete() method instead of super().form_valid() to ensure message display
        object_name = self.object.name
        try:
            self.object.delete()
            messages.success(self.request, self.get_success_message({'name': object_name}))
            logger.info(f"Checklist Template '{object_name}' deleted by {self.request.user.username}")
        except models.ProtectedError as e:
            logger.error(f"Cannot delete template '{object_name}' due to protected checklist runs: {e}")
            messages.error(self.request, _("Невозможно удалить шаблон, так как существуют связанные выполненные чеклисты."))
            return redirect(self.object.get_absolute_url()) # Redirect back on protection error
        except Exception as e:
             logger.exception(f"Error deleting template '{object_name}': {e}")
             messages.error(self.request, _("Произошла ошибка при удалении шаблона."))
             return redirect(self.object.get_absolute_url())

        return redirect(self.success_url)


# ==================================
# Perform Checklist View
# ==================================
class PerformChecklistView(LoginRequiredMixin, View): # Use generic View for more control
    template_name = 'checklists/perform_checklist.html'

    def get_checklist_run(self, request, template_pk):
        """Gets or creates the checklist run for today."""
        template = get_object_or_404(ChecklistTemplate, pk=template_pk, is_active=True)
        today = timezone.now().date()
        checklist_run, created = Checklist.objects.get_or_create(
            template=template,
            performed_by=request.user,
            performed_at__date=today,
            is_complete=False,
            defaults={'performed_by': request.user} # Ensure user is set on create
        )
        if created:
            logger.info(f"Created new Checklist run {checklist_run.id} for template {template.id} by {request.user.username}")
            # Pre-populate results for a new run
            results_to_create = []
            for item in template.items.order_by('order'):
                results_to_create.append(ChecklistResult(checklist_run=checklist_run, template_item=item))
            if results_to_create:
                ChecklistResult.objects.bulk_create(results_to_create)
                logger.debug(f"Created {len(results_to_create)} initial results for new run {checklist_run.id}")
        return checklist_run, template

    def get(self, request, *args, **kwargs):
        """Handles GET request: displays the formset."""
        template_pk = kwargs['template_pk']
        checklist_run, template = self.get_checklist_run(request, template_pk)

        # Get results ordered correctly for the formset
        queryset = checklist_run.results.select_related('template_item').order_by('template_item__order')
        formset = ChecklistResultFormSet(instance=checklist_run, prefix='results', queryset=queryset)

        context = {
            'page_title': _("Выполнение: %s") % template.name,
            'template': template,
            'checklist_run': checklist_run,
            'formset': formset,
        }
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        """Handles POST request: saves the formset."""
        template_pk = kwargs['template_pk']
        # Find the specific run being submitted (should exist from GET)
        checklist_run, template = self.get_checklist_run(request, template_pk)

        formset = ChecklistResultFormSet(request.POST, instance=checklist_run, prefix='results')

        if formset.is_valid():
            try:
                with transaction.atomic():
                    formset.save()
                    checklist_run.mark_complete()
                    logger.info(f"Checklist run {checklist_run.id} completed by {request.user.username}")
                    messages.success(request, _("Чеклист '%(name)s' успешно завершен.") % {'name': template.name})
                    return redirect(reverse('checklists:history_list')) # Redirect after success
            except Exception as e:
                logger.exception(f"Error saving completed checklist run {checklist_run.id}: {e}")
                messages.error(request, _("Произошла ошибка при сохранении чеклиста."))
                # Fall through to re-render form with error message
        else:
            logger.warning(f"Invalid ChecklistResultFormSet for run {checklist_run.id}: {formset.errors}")
            messages.error(request, _("Пожалуйста, исправьте ошибки в пунктах чеклиста."))

        # Re-render form if invalid or save error occurred
        context = {
            'page_title': _("Выполнение: %s") % template.name,
            'template': template,
            'checklist_run': checklist_run,
            'formset': formset, # Pass back formset with errors
        }
        return render(request, self.template_name, context)

# ==================================
# Checklist History/Results Views
# ==================================
class ChecklistHistoryListView(LoginRequiredMixin, ListView):
    model = Checklist
    template_name = 'checklists/history_list.html'
    context_object_name = 'checklist_runs'
    paginate_by = 25

    def get_queryset(self):
        # Show only completed checklists, allow filtering by user?
        qs = Checklist.objects.filter(is_complete=True)
        # Optionally filter for current user if not staff:
        # if not self.request.user.is_staff:
        #    qs = qs.filter(performed_by=self.request.user)
        return qs.select_related(
            'template', 'performed_by', 'template__category', 'related_task'
        ).order_by('-performed_at')

class ChecklistDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = Checklist
    template_name = 'checklists/checklist_detail.html'
    context_object_name = 'checklist_run'

    def test_func(self):
        # Allow viewing if user performed it or is staff/superuser
        run = self.get_object()
        return run.performed_by == self.request.user or self.request.user.is_staff

    def handle_no_permission(self):
        messages.error(self.request, _("У вас нет прав для просмотра этого результата чеклиста."))
        return redirect(reverse_lazy('checklists:history_list'))

    def get_queryset(self):
        # Optimize query by prefetching results and related items
        return super().get_queryset().select_related(
            'template', 'performed_by', 'related_task', 'template__category'
        ).prefetch_related(
            # Prefetch results and their corresponding template item, ordered correctly
            models.Prefetch('results', queryset=ChecklistResult.objects.select_related('template_item').order_by('template_item__order'))
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Результаты чеклиста: %s") % str(self.object)
        # Results are already prefetched and ordered in get_queryset
        context['results'] = self.object.results.all()
        return context

# ==================================
# Reporting Views
# ==================================
class ChecklistReportView(LoginRequiredMixin, ListView):
    """ Basic summary report showing counts per template. """
    template_name = 'checklists/report_summary.html'
    context_object_name = 'report_data'

    def get_queryset(self):
        # Aggregate data: count total runs and runs with issues per template
        report = ChecklistTemplate.objects.filter(runs__is_complete=True).annotate(
            total_runs=Count('runs', filter=Q(runs__is_complete=True)),
            runs_with_issues=Count('runs', filter=Q(runs__is_complete=True, runs__results__status=ChecklistItemStatus.NOT_OK))
        ).annotate(
            runs_without_issues=Count('runs', filter=Q(runs__is_complete=True, runs__results__status=ChecklistItemStatus.OK)) + Count('runs', filter=Q(runs__is_complete=True, runs__results__status=ChecklistItemStatus.NA))
        ).filter(total_runs__gt=0).order_by('category__name', 'name') # Only show templates with completed runs
        return report

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Сводный отчет по чеклистам")
        context['total_checklists'] = Checklist.objects.filter(is_complete=True).count()
        context['total_templates'] = ChecklistTemplate.objects.filter(runs__is_complete=True).distinct().count()
        context['total_users'] = Checklist.objects.filter(is_complete=True).values('performed_by').distinct().count()
        context['total_tasks'] = Checklist.objects.filter(is_complete=True).values('related_task').distinct().count()
        context['total_issues'] = ChecklistResult.objects.filter(status=ChecklistItemStatus.NOT_OK).count()
        context['total_results'] = ChecklistResult.objects.count()
        context['total_runs'] = Checklist.objects.filter(is_complete=True).count()
        context['total_runs_with_issues'] = ChecklistResult.objects.filter(status=ChecklistItemStatus.NOT_OK).count()
        context['total_runs_without_issues'] = context['total_runs'] - context['total_runs_with_issues']
        # TODO: Add date range filters
        return context

class ChecklistIssuesReportView(LoginRequiredMixin, ListView):
    """ Report showing only items marked 'Not OK'. """
    template_name = 'checklists/report_issues.html'
    context_object_name = 'issue_results'
    paginate_by = 50

    def get_queryset(self):
        """ Filter results to show only 'Not OK' items. """
        # Filter results directly for 'Not OK' status
        # TODO: Add date range filtering
        return ChecklistResult.objects.filter(status=ChecklistItemStatus.NOT_OK) \
            .select_related(
                'checklist_run__template',
                'checklist_run__performed_by',
                'template_item',
                'template_item__template',
                'template_item__template__category'
            ).order_by('-checklist_run__performed_at', 'template_item__order')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Отчет по пунктам с проблемами")
        context['total_issues'] = self.get_queryset().count()
        context['total_checklists'] = Checklist.objects.filter(is_complete=True).count()
        context['total_templates'] = ChecklistTemplate.objects.filter(runs__is_complete=True).distinct().count()
        context['total_users'] = Checklist.objects.filter(is_complete=True).values('performed_by').distinct().count()
        context['total_tasks'] = Checklist.objects.filter(is_complete=True).values('related_task').distinct().count()

        # TODO: Add date range filters
        return context