# checklists/views.py
import logging
from django.db import transaction
from django.forms import modelformset_factory, inlineformset_factory
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, FormView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django import forms
from django.db import models

from .models import (
    ChecklistTemplate, ChecklistTemplateItem, Checklist, ChecklistResult, ChecklistItemStatus
)
from .forms import (
    ChecklistTemplateForm, ChecklistTemplateItemFormSet, ChecklistResultFormSet
)

logger = logging.getLogger(__name__)

# --- Template Views ---
class ChecklistTemplateListView(LoginRequiredMixin, ListView):
    model = ChecklistTemplate
    template_name = 'checklists/template_list.html'
    context_object_name = 'templates'
    paginate_by = 15

    def get_queryset(self):
        # Show only active templates by default, maybe allow filter for inactive?
        return ChecklistTemplate.objects.filter(is_active=True).select_related('category').prefetch_related('items')

class ChecklistTemplateDetailView(LoginRequiredMixin, DetailView):
    model = ChecklistTemplate
    template_name = 'checklists/template_detail.html'
    context_object_name = 'template'

    def get_queryset(self):
        return super().get_queryset().prefetch_related('items')


class ChecklistTemplateCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = ChecklistTemplate
    form_class = ChecklistTemplateForm
    template_name = 'checklists/template_form.html'
    success_message = _("Шаблон чеклиста '%(name)s' успешно создан.")
    success_url = reverse_lazy('checklists:template_list') # Default, overridden below

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Создать шаблон чеклиста")
        if self.request.POST:
            context['item_formset'] = ChecklistTemplateItemFormSet(self.request.POST, prefix='items')
        else:
            context['item_formset'] = ChecklistTemplateItemFormSet(prefix='items')
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        item_formset = context['item_formset']
        with transaction.atomic():
            self.object = form.save()
            if item_formset.is_valid():
                item_formset.instance = self.object
                item_formset.save()
                logger.info(f"Checklist Template '{self.object.name}' created by {self.request.user.username}")
                messages.success(self.request, self.get_success_message(form.cleaned_data))
                return redirect(self.get_success_url()) # Redirect to detail after save
            else:
                # If item formset is invalid, the transaction will roll back.
                # Render the form again with errors (handled by form_invalid).
                logger.warning(f"Checklist Template item formset invalid for user {self.request.user.username}: {item_formset.errors}")
                # We shouldn't really get here if the main form was valid due to transaction rollback
                # but handle defensively.
                return self.form_invalid(form)

    def form_invalid(self, form):
        logger.warning(f"Checklist Template form invalid for user {self.request.user.username}: {form.errors}")
        # Need to pass the item formset back with potential errors too
        context = self.get_context_data(form=form) # This re-initializes item_formset with POST data
        return self.render_to_response(context)

    def get_success_url(self):
        # Redirect to the detail view of the created template
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
                return self.form_invalid(form)

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
        success_message = self.get_success_message({'name': self.object.name})
        response = super().form_valid(form)
        messages.success(self.request, success_message)
        logger.info(f"Checklist Template '{self.object.name}' deleted by {self.request.user.username}")
        return response


# --- Perform Checklist View ---
class PerformChecklistView(LoginRequiredMixin, FormView): # Use FormView as base
    template_name = 'checklists/perform_checklist.html'
    form_class = forms.Form # We don't have a main form, only the formset

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        # Get template based on URL pk
        self.template = get_object_or_404(ChecklistTemplate, pk=self.kwargs['template_pk'], is_active=True)
        # Try to find an existing incomplete run for this user and template today, or create new
        today = timezone.now().date()
        self.checklist_run = Checklist.objects.filter(
            template=self.template,
            performed_by=request.user,
            performed_at__date=today,
            is_complete=False
        ).first()

        if not self.checklist_run:
            self.checklist_run = Checklist.objects.create(
                template=self.template,
                performed_by=request.user
            )
            logger.info(f"Created new Checklist run {self.checklist_run.id} for template {self.template.id} by {request.user.username}")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['template'] = self.template
        context['checklist_run'] = self.checklist_run
        if 'formset' not in context: # Initialize formset if not already done by POST handling
            context['formset'] = self.get_formset()
        context['page_title'] = _("Выполнение чеклиста: ") + self.template.name
        return context

    def get_formset(self, data=None):
        """ Helper to initialize the result formset. """
        # Pre-populate formset with existing results for this run, if any
        queryset = ChecklistResult.objects.filter(checklist_run=self.checklist_run)

        # If it's a new run, create initial result objects (PENDING) for each template item
        if not queryset.exists() and not data: # Don't create if handling POST or results exist
            initial_results = []
            for item in self.template.items.all():
                 # Create initial result linked to the run and template item
                 result, created = ChecklistResult.objects.get_or_create(
                     checklist_run=self.checklist_run,
                     template_item=item,
                     defaults={'status': ChecklistItemStatus.PENDING} # Default status
                 )
                 if created:
                      initial_results.append(result)
            if initial_results:
                 logger.debug(f"Created {len(initial_results)} initial ChecklistResult objects for run {self.checklist_run.id}")
                 # Re-query after creation
                 queryset = ChecklistResult.objects.filter(checklist_run=self.checklist_run)


        if data: # If POST request
            return ChecklistResultFormSet(data, instance=self.checklist_run, prefix='results', queryset=queryset)
        else: # If GET request
            return ChecklistResultFormSet(instance=self.checklist_run, prefix='results', queryset=queryset)

    def post(self, request, *args, **kwargs):
        formset = self.get_formset(data=request.POST)
        if formset.is_valid():
            return self.formset_valid(formset)
        else:
            return self.formset_invalid(formset)

    def formset_valid(self, formset):
        try:
            with transaction.atomic():
                # Save results
                formset.save()
                # Mark the main checklist run as complete
                self.checklist_run.mark_complete()
                logger.info(f"Checklist run {self.checklist_run.id} completed by {self.request.user.username}")
                messages.success(self.request, _("Чеклист '%(name)s' успешно завершен.") % {'name': self.template.name})
                return redirect(self.get_success_url())
        except Exception as e:
             logger.exception(f"Error saving completed checklist run {self.checklist_run.id}: {e}")
             messages.error(self.request, _("Произошла ошибка при сохранении чеклиста."))
             # Re-render the form with the valid formset but show an error
             return self.render_to_response(self.get_context_data(formset=formset))

    def formset_invalid(self, formset):
        logger.warning(f"Invalid ChecklistResultFormSet for run {self.checklist_run.id}: {formset.errors}")
        messages.error(self.request, _("Пожалуйста, исправьте ошибки в пунктах чеклиста."))
        return self.render_to_response(self.get_context_data(formset=formset))

    def get_success_url(self):
        # Redirect to checklist history or maybe template list
        return reverse('checklists:history_list')


# --- Checklist History/Results Views ---
class ChecklistHistoryListView(LoginRequiredMixin, ListView):
    model = Checklist
    template_name = 'checklists/history_list.html'
    context_object_name = 'checklist_runs'
    paginate_by = 20

    def get_queryset(self):
        # Show only completed checklists, maybe filter by user/date range later
        return Checklist.objects.filter(is_complete=True).select_related(
            'template', 'performed_by', 'template__category', 'related_task'
        ).order_by('-performed_at')


class ChecklistDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = Checklist
    template_name = 'checklists/checklist_detail.html'
    context_object_name = 'checklist_run'

    def test_func(self):
        # Example permission: Allow viewing if user performed it or is staff
        run = self.get_object()
        return run.performed_by == self.request.user or self.request.user.is_staff

    def get_queryset(self):
        return super().get_queryset().select_related(
            'template', 'performed_by', 'related_task', 'template__category'
        ).prefetch_related(
            'results__template_item' # Prefetch results and their linked item
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Результаты чеклиста: ") + str(self.object)
        # Results are prefetched, order them if needed
        context['results'] = self.object.results.order_by('template_item__order')
        return context

# --- Reporting Views (Basic Examples) ---

class ChecklistReportView(LoginRequiredMixin, ListView):
     """ Basic report showing counts """
     template_name = 'checklists/report_summary.html'
     context_object_name = 'report_data'

     def get_queryset(self):
        # Aggregate data - e.g., count checklists by template and status
        # This needs refinement based on actual reporting needs
        report = Checklist.objects.filter(is_complete=True) \
            .values('template__name') \
            .annotate(
                total_runs=models.Count('id'),
                runs_with_issues=models.Count('id', filter=models.Q(results__status=ChecklistItemStatus.NOT_OK))
            ).order_by('template__name')
        return report

     def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Сводный отчет по чеклистам")
        # Add date range filters here if needed
        return context


class ChecklistIssuesReportView(LoginRequiredMixin, ListView):
    """ Report showing only items marked 'Not OK' """
    template_name = 'checklists/report_issues.html'
    context_object_name = 'issue_results'
    paginate_by = 30

    def get_queryset(self):
        # Filter results directly
        return ChecklistResult.objects.filter(status=ChecklistItemStatus.NOT_OK) \
            .select_related(
                'checklist_run__template',
                'checklist_run__performed_by',
                'template_item'
            ).order_by('-checklist_run__performed_at', 'template_item__order')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Отчет по пунктам с проблемами")
        # Add date range filters here if needed
        return context