# checklists/views.py
import logging
from django.db import transaction, models # Added models import
from django.forms import HiddenInput
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, View
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.db.models import Count, Q, Prefetch
from django.http import JsonResponse

# Import forms and models from current app
from .models import (
    ChecklistTemplate, ChecklistTemplateItem, Checklist, ChecklistResult,
    ChecklistItemStatus, Location, ChecklistPoint
)
from .forms import (
    ChecklistTemplateForm, ChecklistTemplateItemFormSet, ChecklistResultFormSet
)
# Import filters and API views/serializers if they exist
# from .filters import ChecklistHistoryFilter
from .serializers import ChecklistPointSerializer # Assuming serializers.py exists
from rest_framework import generics, permissions # For API view
from django_filters.rest_framework import DjangoFilterBackend # For API view filtering


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
        queryset = ChecklistTemplate.objects.all() # Show all by default
        # Optionally filter active: queryset = queryset.filter(is_active=True)
        return queryset.select_related('category', 'target_location', 'target_point') \
                       .annotate(item_count_agg=Count('items')) \
                       .order_by('category__name', 'name')

class ChecklistTemplateDetailView(LoginRequiredMixin, DetailView):
    model = ChecklistTemplate
    template_name = 'checklists/template_detail.html'
    context_object_name = 'template'

    def get_queryset(self):
        return super().get_queryset().select_related(
            'category', 'target_location', 'target_point'
            ).prefetch_related(
                models.Prefetch('items', queryset=ChecklistTemplateItem.objects.select_related('target_point').order_by('order'))
            )

class ChecklistTemplateCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = ChecklistTemplate
    form_class = ChecklistTemplateForm
    template_name = 'checklists/template_form.html'
    success_message = _("Шаблон чеклиста '%(name)s' успешно создан.")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Создать шаблон чеклиста")
        if self.request.POST:
            # Pass the (unsaved) instance to the formset if the main form is bound
            # Pass parent_instance kwargs to the forms within the formset
            context['item_formset'] = ChecklistTemplateItemFormSet(
                self.request.POST, prefix='items',
                form_kwargs={'parent_instance': self.object} # Pass parent instance here
            )
        else:
            context['item_formset'] = ChecklistTemplateItemFormSet(
                prefix='items', queryset=ChecklistTemplateItem.objects.none()
            )
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        # Re-initialize formset with instance=unsaved_object for validation context
        self.object = form.instance # Get unsaved object from main form
        item_formset = ChecklistTemplateItemFormSet(
            self.request.POST, prefix='items', instance=self.object,
            form_kwargs={'parent_instance': self.object} # Pass parent instance again
        )

        if item_formset.is_valid():
            with transaction.atomic():
                # Save the main template form first
                self.object = form.save()
                # Set the instance for the formset and save
                item_formset.instance = self.object
                item_formset.save()
                logger.info(f"Checklist Template '{self.object.name}' created by {self.request.user.username}")
                messages.success(self.request, self.get_success_message(form.cleaned_data))
                return redirect(self.get_success_url())
        else:
            # Formset invalid. form_invalid will handle rendering response.
            logger.warning(f"Item formset invalid during create: {item_formset.errors}")
            return self.form_invalid(form) # Pass the main form to form_invalid

    def form_invalid(self, form):
        logger.warning(f"Checklist Template form invalid: {form.errors}")
        # Re-render with errors in both main form and formset
        context = self.get_context_data(form=form) # This re-initializes item_formset with POST data
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
            context['item_formset'] = ChecklistTemplateItemFormSet(
                self.request.POST, instance=self.object, prefix='items',
                form_kwargs={'parent_instance': self.object} # Pass parent instance
            )
        else:
            context['item_formset'] = ChecklistTemplateItemFormSet(
                instance=self.object, prefix='items',
                form_kwargs={'parent_instance': self.object} # Pass parent instance
            )
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        item_formset = context['item_formset']
        if item_formset.is_valid():
            with transaction.atomic():
                self.object = form.save()
                item_formset.instance = self.object
                item_formset.save()
                logger.info(f"Checklist Template '{self.object.name}' updated by {self.request.user.username}")
                messages.success(self.request, self.get_success_message(form.cleaned_data))
                return redirect(self.get_success_url())
        else:
            logger.warning(f"Item formset invalid during update for template {self.object.id}: {item_formset.errors}")
            return self.form_invalid(form) # Pass main form to form_invalid

    def form_invalid(self, form):
        logger.warning(f"Template update form invalid for template {self.object.id}: {form.errors}")
        context = self.get_context_data(form=form) # Re-initializes formset with POST data
        return self.render_to_response(context)

    def get_success_url(self):
        return reverse('checklists:template_detail', kwargs={'pk': self.object.pk})

class ChecklistTemplateDeleteView(LoginRequiredMixin, SuccessMessageMixin, DeleteView):
    model = ChecklistTemplate
    template_name = 'checklists/template_confirm_delete.html'
    success_url = reverse_lazy('checklists:template_list')
    success_message = _("Шаблон чеклиста '%(name)s' успешно удален.")

    def form_valid(self, form):
        object_name = self.object.name
        try:
            # Use super().form_valid() for standard deletion process handled by DeleteView
            response = super().form_valid(form)
            messages.success(self.request, self.get_success_message({'name': object_name}))
            logger.info(f"Checklist Template '{object_name}' deleted by {self.request.user.username}")
            return response
        except models.ProtectedError as e:
            logger.error(f"Cannot delete template '{object_name}' due to protected checklist runs: {e}")
            messages.error(self.request, _("Невозможно удалить шаблон, так как существуют связанные выполненные чеклисты."))
            return redirect(self.object.get_absolute_url())
        except Exception as e:
             logger.exception(f"Error deleting template '{object_name}': {e}")
             messages.error(self.request, _("Произошла ошибка при удалении шаблона."))
             return redirect(self.object.get_absolute_url())


# ==================================
# Perform Checklist View
# ==================================
class PerformChecklistView(LoginRequiredMixin, View):
    template_name = 'checklists/perform_checklist.html'

    def get_checklist_run(self, request, template):
        """Gets or creates the checklist run for today for the given template."""
        today = timezone.now().date()
        checklist_run, created = Checklist.objects.get_or_create(
            template=template,
            performed_by=request.user,
            performed_at__date=today,
            is_complete=False,
            defaults={
                'performed_by': request.user,
                'location': template.target_location,
                'point': template.target_point,
            }
        )
        if created:
            logger.info(f"Created Checklist run {checklist_run.id} for template {template.id}")
            # Pre-populate results
            results_to_create = []
            items_queryset = template.items.order_by('order')
            # Filter items by run's point only if the run has a point specified
            if checklist_run.point:
                 items_queryset = items_queryset.filter(
                     Q(target_point__isnull=True) | Q(target_point=checklist_run.point)
                 )
                 logger.debug(f"Filtering items for run {checklist_run.id} based on point {checklist_run.point.id}")
            elif checklist_run.location:
                  # Optional: Filter by location if point is not set
                  items_queryset = items_queryset.filter(
                     Q(target_point__isnull=True) | Q(target_point__location=checklist_run.location)
                 )
                  logger.debug(f"Filtering items for run {checklist_run.id} based on location {checklist_run.location.id}")

            for item in items_queryset:
                results_to_create.append(ChecklistResult(checklist_run=checklist_run, template_item=item))
            if results_to_create:
                ChecklistResult.objects.bulk_create(results_to_create)
                logger.debug(f"Created {len(results_to_create)} initial results for run {checklist_run.id}")
        return checklist_run

    def get_formset(self, checklist_run, data=None):
         """ Helper to initialize the result formset, ordered correctly. """
         # Fetch results linked to the specific run, ordered by the template item order
         queryset = ChecklistResult.objects.filter(checklist_run=checklist_run) \
                                          .select_related('template_item', 'template_item__target_point') \
                                          .order_by('template_item__order')
         # Pass POST data if available, otherwise create unbound formset
         return ChecklistResultFormSet(data, instance=checklist_run, prefix='results', queryset=queryset)

    def get(self, request, *args, **kwargs):
        template_pk = kwargs['template_pk']
        template = get_object_or_404(ChecklistTemplate, pk=template_pk, is_active=True)
        checklist_run = self.get_checklist_run(request, template)
        formset = self.get_formset(checklist_run)
        context = {
            'page_title': _("Выполнение: %s") % template.name,
            'template': template,
            'checklist_run': checklist_run,
            'formset': formset,
            'location': checklist_run.location,
            'point': checklist_run.point,
        }
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        template_pk = kwargs['template_pk']
        template = get_object_or_404(ChecklistTemplate, pk=template_pk, is_active=True)
        # Get the run based on ID potentially passed in POST or find existing one
        run_id = request.POST.get('checklist_run_id') # Ensure hidden input in template
        if run_id:
             checklist_run = get_object_or_404(Checklist, pk=run_id, template=template, performed_by=request.user, is_complete=False)
        else:
             # Fallback to finding/creating if ID not passed (less ideal)
             checklist_run = self.get_checklist_run(request, template)

        formset = self.get_formset(checklist_run, data=request.POST)

        if formset.is_valid():
            try:
                with transaction.atomic():
                    formset.save()
                    checklist_run.mark_complete()
                    messages.success(request, _("Чеклист '%(name)s' успешно завершен.") % {'name': template.name})
                    return redirect(reverse('checklists:history_list'))
            except Exception as e:
                logger.exception(f"Error saving completed checklist run {checklist_run.id}: {e}")
                messages.error(request, _("Произошла ошибка при сохранении чеклиста."))
        else:
            logger.warning(f"Invalid ChecklistResultFormSet for run {checklist_run.id}: {formset.errors}")
            messages.error(request, _("Пожалуйста, исправьте ошибки в пунктах чеклиста."))

        # Re-render form if invalid or save error occurred
        context = {
            'page_title': _("Выполнение: %s") % template.name,
            'template': template,
            'checklist_run': checklist_run,
            'formset': formset, # Pass back formset with errors
            'location': checklist_run.location,
            'point': checklist_run.point,
        }
        return render(request, self.template_name, context)

# ==================================
# Checklist History/Results Views
# ==================================
class ChecklistHistoryListView(LoginRequiredMixin, ListView):
    model = Checklist
    template_name = 'checklists/history_list.html'
    context_object_name = 'checklist_runs'
<<<<<<< HEAD
    paginate_by = 25

    def get_queryset(self):
        # Base queryset: completed runs
        base_queryset = Checklist.objects.filter(is_complete=True).select_related(
            'template', 'performed_by', 'template__category', 'related_task',
            'location', 'point'
        )
        # Apply filtering using FilterSet if defined and imported
        # self.filterset = ChecklistHistoryFilter(self.request.GET, queryset=base_queryset)
        # return self.filterset.qs.distinct().order_by('-performed_at')

        # Return base queryset if no FilterSet class
        return base_queryset.order_by('-performed_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Pass filterset to template if using filters.py
        # context['filterset'] = getattr(self, 'filterset', None)
        context['page_title'] = _('История выполнения чеклистов')
        context['current_sort'] = self.request.GET.get('sort', '-performed_at')
        return context

=======
    paginate_by = 20 # Or your preferred number

    def get_queryset(self):
        # Base queryset: completed runs, optimized with related fields
        base_queryset = Checklist.objects.filter(is_complete=True).select_related(
            'template', 'performed_by', 'template__category', 'related_task'
        ).order_by('-performed_at') # Default ordering

        # Apply filtering using the FilterSet
        self.filterset = ChecklistHistoryFilter(self.request.GET, queryset=base_queryset)

        # Return the filtered queryset
        # distinct() might be needed depending on filter complexity (e.g., has_issues)
        return self.filterset.qs.distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filterset'] = self.filterset # Pass filterset to template
        context['page_title'] = _('История выполнения чеклистов')
        # Pass current sort parameter for sortable headers
        context['current_sort'] = self.request.GET.get('sort', '-performed_at') # Default sort
        return context



>>>>>>> 29f70277ec8ecd071d7cb509df403b43bbb02843
class ChecklistDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = Checklist
    template_name = 'checklists/checklist_detail.html'
    context_object_name = 'checklist_run'

    def test_func(self):
        run = self.get_object()
        return run.performed_by == self.request.user or self.request.user.is_staff

    def handle_no_permission(self):
        messages.error(self.request, _("У вас нет прав для просмотра этого результата чеклиста."))
        return redirect(reverse_lazy('checklists:history_list'))

    def get_queryset(self):
        return super().get_queryset().select_related(
            'template', 'performed_by', 'related_task', 'template__category',
            'location', 'point'
        ).prefetch_related(
            models.Prefetch('results', queryset=ChecklistResult.objects.select_related(
                 'template_item', 'template_item__target_point' # Include point info for item
                 ).order_by('template_item__order'))
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Результаты чеклиста: %s") % str(self.object)
        context['results'] = self.object.results.all() # Already prefetched and ordered
        return context

# ==================================
# Reporting Views
# ==================================
class ChecklistReportView(LoginRequiredMixin, ListView):
    template_name = 'checklists/report_summary.html'
    context_object_name = 'report_data'

    def get_queryset(self):
        # Aggregate data: count total runs and runs with issues per template
<<<<<<< HEAD
        report = ChecklistTemplate.objects.filter(runs__is_complete=True).annotate(
            total_runs=Count('runs', filter=Q(runs__is_complete=True)),
            runs_with_issues=Count('runs', filter=Q(runs__is_complete=True, runs__results__status=ChecklistItemStatus.NOT_OK))
        ).annotate( # Separate annotation for clarity
            runs_without_issues=Count('runs', filter=Q(runs__is_complete=True) & (Q(runs__results__status=ChecklistItemStatus.OK) | Q(runs__results__status=ChecklistItemStatus.NOT_APPLICABLE)))
        ).filter(total_runs__gt=0).order_by('category__name', 'name')
=======
        report = (
            ChecklistTemplate.objects.filter(runs__is_complete=True)
            .annotate(
                total_runs=Count("runs", filter=Q(runs__is_complete=True)),
                runs_with_issues=Count(
                    "runs",
                    filter=Q(
                        runs__is_complete=True,
                        runs__results__status=ChecklistItemStatus.NOT_OK,
                    ),
                ),
            )
            .annotate(
                runs_without_issues=Count(
                    "runs",
                    filter=Q(
                        runs__is_complete=True,
                        runs__results__status=ChecklistItemStatus.OK,
                    ),
                )
                + Count(
                    "runs",
                    filter=Q(
                        runs__is_complete=True,
                        runs__results__status=ChecklistItemStatus.NOT_APPLICABLE,
                    ),
                )
            )
            .filter(total_runs__gt=0)
            .order_by("category__name", "name")
        )  # Only show templates with completed runs
>>>>>>> 29f70277ec8ecd071d7cb509df403b43bbb02843
        return report

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Сводный отчет по чеклистам")
        # Add overall totals
        context['total_completed_runs'] = Checklist.objects.filter(is_complete=True).count()
        context['total_runs_with_issues'] = Checklist.objects.filter(is_complete=True, results__status=ChecklistItemStatus.NOT_OK).distinct().count()
        # TODO: Add date range filters
        return context

class ChecklistIssuesReportView(LoginRequiredMixin, ListView):
    template_name = 'checklists/report_issues.html'
    context_object_name = 'issue_results'
    paginate_by = 50

    def get_queryset(self):
        # Filter results directly for 'Not OK' status
        # TODO: Add date range filtering
        return ChecklistResult.objects.filter(status=ChecklistItemStatus.NOT_OK) \
            .select_related(
                'checklist_run__template', 'checklist_run__performed_by',
                'template_item', 'checklist_run__location', 'checklist_run__point'
            ).order_by('-checklist_run__performed_at', 'template_item__order')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Отчет по пунктам с проблемами")
        # TODO: Add date range filters
        return context

# ==================================
# API Views
# ==================================
class ChecklistPointListView(generics.ListAPIView):
    """ API view to list ChecklistPoints, filterable by location. """
    serializer_class = ChecklistPointSerializer
    permission_classes = [permissions.IsAuthenticated] # Adjust as needed
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['location'] # Allows ?location=<id> filtering

    def get_queryset(self):
        """ Returns ChecklistPoints ordered by name. """
        return ChecklistPoint.objects.select_related('location').order_by('name')