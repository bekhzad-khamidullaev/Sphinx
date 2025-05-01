import logging
from django.db import transaction, models
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
from django.core.exceptions import PermissionDenied

# Import models, forms, filters, and utils from current app
from .models import (
    ChecklistTemplate, ChecklistTemplateItem, Checklist, ChecklistResult,
    ChecklistItemStatus, Location, ChecklistPoint, ChecklistRunStatus, AnswerType
)
from .forms import (
    ChecklistTemplateForm, ChecklistTemplateItemFormSet, PerformChecklistResultFormSet,
    ChecklistStatusUpdateForm
)
from .filters import ChecklistHistoryFilter
from .utils import calculate_checklist_score # Use the utility function

# Import serializers and DRF components if needed for API views
from .serializers import ChecklistPointSerializer
from rest_framework import generics, permissions
from django_filters.rest_framework import DjangoFilterBackend


logger = logging.getLogger(__name__)

# ==================================
# Permission Mixins (Optional, but good practice)
# ==================================
# You might define mixins like this for role-based access
class CanPerformChecklistMixin(UserPassesTestMixin):
    def test_func(self):
        # Example: Only active users can perform checklists
        return self.request.user.is_authenticated and self.request.user.is_active
    def handle_no_permission(self):
        messages.error(self.request, _("У вас нет прав для выполнения чеклистов."))
        return redirect(reverse_lazy('login')) # Redirect to login or a permission denied page

class CanReviewChecklistMixin(UserPassesTestMixin):
     def test_func(self):
         # Example: Only staff users can review/approve checklists
         return self.request.user.is_authenticated and self.request.user.is_staff
     def handle_no_permission(self):
         messages.error(self.request, _("У вас нет прав для просмотра отчетов или изменения статуса чеклистов."))
         return redirect(reverse_lazy('checklists:history_list')) # Redirect to history list


# ==================================
# Checklist Template Views (CRUD)
# ==================================
class ChecklistTemplateListView(LoginRequiredMixin, ListView):
    model = ChecklistTemplate
    template_name = 'checklists/template_list.html'
    context_object_name = 'templates'
    paginate_by = 20

    def get_queryset(self):
        queryset = ChecklistTemplate.objects.filter(is_archived=False) # Show non-archived by default
        # Optional: Filter by active, or apply user permissions/location access
        # if not self.request.user.is_staff:
        #      queryset = queryset.filter(is_active=True)

        return queryset.select_related('category', 'target_location', 'target_point') \
                       .annotate(item_count_agg=Count('items'), run_count_agg=Count('runs')) \
                       .order_by('category__name' if ChecklistTemplate._meta.get_field('category').remote_field.model else 'name', 'name') # Handle dummy category ordering

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Список шаблонов чеклистов")
        # Add options for creating new templates (if user has permission)
        # context['can_create_template'] = self.request.user.has_perm('checklists.add_checklisttemplate')
        return context


class ChecklistTemplateDetailView(LoginRequiredMixin, DetailView):
    model = ChecklistTemplate
    template_name = 'checklists/template_detail.html'
    context_object_name = 'template'

    def get_queryset(self):
        # Prefetch sections and items, ensuring correct order
        return super().get_queryset().select_related(
            'category', 'target_location', 'target_point'
            ).prefetch_related(
                models.Prefetch('sections', queryset=ChecklistSection.objects.order_by('order')),
                models.Prefetch('items', queryset=ChecklistTemplateItem.objects.select_related('target_point', 'section').order_by('section__order', 'order'))
            )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Шаблон чеклиста: %s") % self.object.name
        # Filter items not linked to any section (already prefetched)
        context['unsectioned_items'] = [item for item in self.object.items.all() if item.section is None]
        # Items within sections are available via template.sections.all() loop in template

        # Check permissions for editing/deleting
        # context['can_edit'] = self.request.user.has_perm('checklists.change_checklisttemplate')
        # context['can_delete'] = self.request.user.has_perm('checklists.delete_checklisttemplate')
        return context


class ChecklistTemplateCreateView(LoginRequiredMixin, UserPassesTestMixin, SuccessMessageMixin, CreateView):
    model = ChecklistTemplate
    form_class = ChecklistTemplateForm
    template_name = 'checklists/template_form.html'
    success_message = _("Шаблон чеклиста '%(name)s' успешно создан.")

    def test_func(self):
        # Example: Only staff can create templates
        return self.request.user.is_authenticated and self.request.user.is_staff
        # Or use permissions: return self.request.user.has_perm('checklists.add_checklisttemplate')


    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Создать шаблон чеклиста")
        if self.request.POST:
            # Pass the (unsaved) instance to the formset if the main form is bound
            # Pass parent_instance kwargs to the forms within the formset
            context['item_formset'] = ChecklistTemplateItemFormSet(
                self.request.POST, self.request.FILES, prefix='items',
                instance=self.object, # Use self.object even if unsaved to link formset
                form_kwargs={'parent_instance': self.object} # Pass parent instance here
            )
             # Include section formset if you implement inline sections
             # context['section_formset'] = ChecklistSectionFormSet(self.request.POST, prefix='sections', instance=self.object)

        else:
            context['item_formset'] = ChecklistTemplateItemFormSet(
                prefix='items', queryset=ChecklistTemplateItem.objects.none(),
                form_kwargs={'parent_instance': self.object} # Pass dummy instance for initial form
            )
             # context['section_formset'] = ChecklistSectionFormSet(prefix='sections', queryset=ChecklistSection.objects.none())

        return context

    def form_valid(self, form):
        context = self.get_context_data()
        # Get formsets from context (already initialized with POST data if it's a POST request)
        item_formset = context['item_formset']
        # section_formset = context['section_formset']

        # Link the formsets to the main object instance before checking validity
        self.object = form.instance # Get unsaved object from main form
        item_formset.instance = self.object
        # section_formset.instance = self.object

        # Check formset validity
        if item_formset.is_valid(): # and section_formset.is_valid():
            with transaction.atomic():
                # Save the main template form first
                self.object = form.save()
                # Set the instance for the formsets again and save
                item_formset.instance = self.object
                item_formset.save()
                # section_formset.instance = self.object
                # section_formset.save()

                logger.info(f"Checklist Template '{self.object.name}' created by {self.request.user.username}")
                messages.success(self.request, self.get_success_message(form.cleaned_data))
                return redirect(self.get_success_url())
        else:
            # Formset invalid. form_invalid will handle rendering response.
            logger.warning(f"Item formset invalid during template create: {item_formset.errors}")
            # logger.warning(f"Section formset invalid during template create: {section_formset.errors}")
            return self.form_invalid(form) # Pass the main form to form_invalid

    def form_invalid(self, form):
        logger.warning(f"Checklist Template form invalid on create: {form.errors}")
        # Re-render with errors in both main form and formsets
        context = self.get_context_data(form=form) # This re-initializes formsets with POST data and errors
        return self.render_to_response(context)

    def get_success_url(self):
        return reverse('checklists:template_detail', kwargs={'pk': self.object.pk})


class ChecklistTemplateUpdateView(LoginRequiredMixin, UserPassesTestMixin, SuccessMessageMixin, UpdateView):
    model = ChecklistTemplate
    form_class = ChecklistTemplateForm
    template_name = 'checklists/template_form.html'
    success_message = _("Шаблон чеклиста '%(name)s' успешно обновлен.")

    def test_func(self):
        # Example: Only staff can edit templates
        return self.request.user.is_authenticated and self.request.user.is_staff
        # Or use permissions: return self.request.user.has_perm('checklists.change_checklisttemplate')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Редактировать шаблон: ") + self.object.name
        if self.request.POST:
            context['item_formset'] = ChecklistTemplateItemFormSet(
                self.request.POST, self.request.FILES, instance=self.object, prefix='items',
                form_kwargs={'parent_instance': self.object} # Pass parent instance
            )
            # context['section_formset'] = ChecklistSectionFormSet(self.request.POST, instance=self.object, prefix='sections')
        else:
            context['item_formset'] = ChecklistTemplateItemFormSet(
                instance=self.object, prefix='items',
                form_kwargs={'parent_instance': self.object} # Pass parent instance
            )
            # context['section_formset'] = ChecklistSectionFormSet(instance=self.object, prefix='sections')

        return context

    def form_valid(self, form):
        context = self.get_context_data()
        item_formset = context['item_formset']
        # section_formset = context['section_formset']

        # Check formset validity
        if item_formset.is_valid(): # and section_formset.is_valid():
            with transaction.atomic():
                self.object = form.save()
                item_formset.instance = self.object
                item_formset.save()
                # section_formset.instance = self.object
                # section_formset.save()

                logger.info(f"Checklist Template '{self.object.name}' updated by {self.request.user.username}")
                messages.success(self.request, self.get_success_message(form.cleaned_data))
                return redirect(self.get_success_url())
        else:
            logger.warning(f"Item formset invalid during template update for template {self.object.id}: {item_formset.errors}")
            # logger.warning(f"Section formset invalid during template update for template {self.object.id}: {section_formset.errors}")
            return self.form_invalid(form) # Pass main form to form_invalid

    def form_invalid(self, form):
        logger.warning(f"Template update form invalid for template {self.object.id}: {form.errors}")
        context = self.get_context_data(form=form) # Re-initializes formsets with POST data
        return self.render_to_response(context)

    def get_success_url(self, **kwargs):
        # Redirect back to the template detail view after successful update
        return reverse('checklists:template_detail', kwargs={'pk': self.object.pk})


class ChecklistTemplateDeleteView(LoginRequiredMixin, UserPassesTestMixin, SuccessMessageMixin, DeleteView):
    model = ChecklistTemplate
    template_name = 'checklists/template_confirm_delete.html'
    success_url = reverse_lazy('checklists:template_list')
    success_message = _("Шаблон чеклиста '%(name)s' успешно удален.")

    def test_func(self):
        # Example: Only staff can delete templates
        return self.request.user.is_authenticated and self.request.user.is_staff
         # Or use permissions: return self.request.user.has_perm('checklists.delete_checklisttemplate')


    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Удалить шаблон: ") + self.object.name
        return context

    # Add deletion protection logic
    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        object_name = self.object.name
        try:
            # Check if there are any related checklist runs
            if self.object.runs.exists():
                 raise models.ProtectedError(
                     _("Невозможно удалить шаблон, так как существуют связанные выполненные чеклисты."),
                     self.object.runs.all()
                 )

            # If no related runs, proceed with standard deletion
            response = super().delete(request, *args, **kwargs)
            messages.success(self.request, self.get_success_message({'name': object_name}))
            logger.info(f"Checklist Template '{object_name}' deleted by {self.request.user.username}")
            return response

        except models.ProtectedError as e:
            logger.warning(f"Attempted to delete protected template '{object_name}': {e}")
            messages.error(self.request, _("Невозможно удалить шаблон, так как существуют связанные выполненные чеклисты."))
            # Redirect back to the template detail page or list
            return redirect(self.object.get_absolute_url())
        except Exception as e:
             logger.exception(f"Error deleting template '{object_name}': {e}")
             messages.error(self.request, _("Произошла ошибка при удалении шаблона."))
             return redirect(self.object.get_absolute_url())


# ==================================
# Perform Checklist View
# Handles creating/getting the run and displaying/saving results
# ==================================
class PerformChecklistView(LoginRequiredMixin, CanPerformChecklistMixin, View):
    template_name = 'checklists/perform_checklist.html'

    def get_checklist_run(self, request, template):
        """
        Gets the current checklist run for the logged-in user for the given template for today,
        or creates a new one if none exists and template allows it.
        """
        today = timezone.now().date()
        # Look for an incomplete run for this user, template, and date
        checklist_run = Checklist.objects.filter(
            template=template,
            performed_by=request.user,
            performed_at__date=today,
            is_complete=False, # Only find incomplete runs
        ).first()

        if not checklist_run:
            # If no incomplete run found, create a new one
            checklist_run = Checklist.objects.create(
                template=template,
                performed_by=request.user,
                performed_at=timezone.now(), # Set performed_at to now on creation
                location=template.target_location, # Inherit from template
                point=template.target_point,       # Inherit from template
                status=ChecklistRunStatus.DRAFT, # Start as draft
            )
            logger.info(f"Created new Checklist run {checklist_run.id} for template {template.id} by {request.user.username}")
            # Initial results are created by the post_save signal on Checklist

        return checklist_run


    def get_formset(self, checklist_run, data=None, files=None):
         """ Helper to initialize the result formset, ordered correctly. """
         # Fetch results linked to the specific run, ordered by the template item order
         # Select related template_item to access answer_type in the form
         queryset = ChecklistResult.objects.filter(checklist_run=checklist_run) \
                                          .select_related('template_item', 'template_item__section', 'template_item__target_point') \
                                          .order_by('template_item__section__order', 'template_item__order')
         # Pass POST data and FILES if available, otherwise create unbound formset
         return PerformChecklistResultFormSet(data, files, instance=checklist_run, prefix='results', queryset=queryset)

    def get(self, request, template_pk):
        template = get_object_or_404(ChecklistTemplate, pk=template_pk, is_active=True)
        # Permission check based on template? E.g., user's branch/location matches template's target?
        # if template.target_location and not request.user.profile.location == template.target_location:
        #      messages.warning(request, _("У вас нет доступа к чеклистам для этого местоположения."))
        #      return redirect(reverse_lazy('checklists:template_list')) # Or a different view

        checklist_run = self.get_checklist_run(request, template)

        # If the run is already complete, redirect to its detail view
        if checklist_run.is_complete or checklist_run.status in [ChecklistRunStatus.SUBMITTED, ChecklistRunStatus.APPROVED, ChecklistRunStatus.REJECTED]:
             messages.info(request, _("Этот чеклист уже завершен."))
             return redirect(checklist_run.get_absolute_url())


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

    def post(self, request, template_pk):
        template = get_object_or_404(ChecklistTemplate, pk=template_pk, is_active=True)
        # Retrieve the existing checklist run using its ID from a hidden input
        run_id = request.POST.get('checklist_run_id')
        if not run_id:
             messages.error(request, _("Идентификатор чеклиста не найден."))
             return redirect(reverse('checklists:template_list')) # Or handle appropriately

        # Ensure the user performing the post is the same as the run's performer (or staff)
        checklist_run = get_object_or_404(Checklist, pk=run_id, template=template, is_complete=False)
        if checklist_run.performed_by != request.user and not request.user.is_staff:
             raise PermissionDenied(_("У вас нет прав на изменение этого чеклиста."))


        formset = self.get_formset(checklist_run, data=request.POST, files=request.FILES)

        if formset.is_valid():
            try:
                with transaction.atomic():
                    # Update results using the formset
                    # Need to manually set updated_by for each result form
                    for form in formset:
                         if form.has_changed():
                              # Ensure created_by is set on initial save if not already
                              if not form.instance.created_by:
                                   form.instance.created_by = request.user
                              # Always set updated_by on change
                              form.instance.updated_by = request.user
                              # Ensure recorded_at is updated (auto_now=True handles this on model)
                              # form.instance.recorded_at = timezone.now() # Redundant due to auto_now

                    formset.save() # Save the result changes

                    # Check if a "Complete" button was pressed (e.g., using a hidden input or button name)
                    # Or always mark complete on successful POST to this view?
                    # Let's assume successful POST means "Save and Complete" for simplicity here.
                    # If you need separate "Save Draft" and "Submit", add logic here
                    # (e.g., check for 'save_draft' in request.POST).
                    # For now, always mark complete on successful POST.

                    if checklist_run.status in [ChecklistRunStatus.DRAFT, ChecklistRunStatus.IN_PROGRESS]:
                         checklist_run.mark_complete() # Sets status to SUBMITTED

                    # Optional: Calculate score upon completion/submission
                    score = calculate_checklist_score(checklist_run)
                    if score is not None:
                         checklist_run.score = score
                         checklist_run.save(update_fields=['score'])
                         logger.info(f"Calculated score {score} for completed run {checklist_run.id}")
                    else:
                         logger.debug(f"Could not calculate score for run {checklist_run.id}")


                    messages.success(request, _("Чеклист '%(name)s' успешно завершен.") % {'name': template.name})
                    return redirect(reverse('checklists:history_list'))

            except PermissionDenied:
                 raise # Re-raise if permission check failed earlier
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
    paginate_by = 20

    def get_queryset(self):
        # Base queryset: completed runs, optimized with related fields
        # Only show completed runs in history? Or show all? Let's show all non-draft runs.
        base_queryset = Checklist.objects.exclude(status=ChecklistRunStatus.DRAFT).select_related(
            'template', 'performed_by', 'template__category', 'related_task',
            'location', 'point'
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
        # context['current_sort'] = self.request.GET.get('sort', '-performed_at') # Default sort
        return context



class ChecklistDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = Checklist
    template_name = 'checklists/checklist_detail.html'
    context_object_name = 'checklist_run'
    pk_url_kwarg = 'pk' # Ensure PK is expected as 'pk'

    def test_func(self):
        """Permission check: User can view if they performed it or are staff."""
        run = self.get_object()
        return run.performed_by == self.request.user or self.request.user.is_staff
        # Or use permissions: return self.request.user.has_perm('checklists.view_checklist', run)

    def handle_no_permission(self):
        messages.error(self.request, _("У вас нет прав для просмотра этого результата чеклиста."))
        return redirect(reverse_lazy('checklists:history_list'))

    def get_queryset(self):
        # Optimize by selecting/prefetching related data
        return super().get_queryset().select_related(
            'template', 'performed_by', 'related_task', 'template__category',
            'location', 'point', 'approved_by'
        ).prefetch_related(
            models.Prefetch(
                'results',
                queryset=ChecklistResult.objects.select_related(
                 'template_item', 'template_item__section', 'template_item__target_point', # Include item, section, point info
                 'created_by', 'updated_by' # Include user info for results
                 ).order_by('template_item__section__order', 'template_item__order') # Order results
             )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Результаты чеклиста: %s") % str(self.object)
        # Results are already prefetched and ordered
        context['results'] = self.object.results.all()
        # You might group results by section in the template for better display

        # Add forms for actions like changing status if user has permission
        # context['can_change_status'] = self.request.user.has_perm('checklists.change_checklist') # General perm or custom?
        if self.request.user.is_staff: # Example: Only staff can change status
             context['status_form'] = ChecklistStatusUpdateForm(instance=self.object)
        # Add form/link for editing if status allows (e.g., is_complete=False or status IN_PROGRESS/DRAFT)
        if self.object.status in [ChecklistRunStatus.DRAFT, ChecklistRunStatus.IN_PROGRESS]:
             # Link to the perform view which handles editing incomplete runs
             context['can_edit_results'] = True


        return context

# View to handle changing Checklist Run status (e.g., Approve/Reject)
class ChecklistStatusUpdateView(LoginRequiredMixin, CanReviewChecklistMixin, UpdateView):
     model = Checklist
     form_class = ChecklistStatusUpdateForm
     template_name = 'checklists/checklist_status_form.html' # Simple form template
     pk_url_kwarg = 'pk'
     context_object_name = 'checklist_run'

     def get_queryset(self):
          # Ensure only certain statuses can be changed via this view?
          # e.g., only allow changing from SUBMITTED
          return super().get_queryset().filter(status=ChecklistRunStatus.SUBMITTED)

     def get_object(self, queryset=None):
          obj = super().get_object(queryset)
          # Store the original status before form processing starts
          obj._original_status = obj.status
          return obj

     def get_context_data(self, **kwargs):
         context = super().get_context_data(**kwargs)
         context['page_title'] = _("Изменить статус чеклиста")
         return context

     def form_valid(self, form):
          # The form's save method handles setting approved_at and is_complete/completion_time
          # It also clears approval fields if status changes away from APPROVED
          response = super().form_valid(form) # This saves the form instance

          # Optional: Recalculate score if status becomes APPROVED (handled in form.save now)
          # if self.object.status == ChecklistRunStatus.APPROVED and self.object.score is None:
          #      score = calculate_checklist_score(self.object)
          #      if score is not None:
          #           self.object.score = score
          #           self.object.save(update_fields=['score'])
          #           logger.info(f"Calculated score {score} for approved run {self.object.id}")


          messages.success(self.request, _("Статус чеклиста обновлен."))
          return response # Redirects to get_success_url()

     def form_invalid(self, form):
          logger.warning(f"Checklist status update form invalid for run {self.object.id}: {form.errors}")
          messages.error(self.request, _("Ошибка при обновлении статуса. Пожалуйста, исправьте ошибки."))
          return super().form_invalid(form) # Re-render form with errors

     def get_success_url(self):
          return reverse_lazy('checklists:checklist_detail', kwargs={'pk': self.object.pk})


# ==================================
# Reporting Views
# ==================================
class ChecklistReportView(LoginRequiredMixin, CanReviewChecklistMixin, ListView):
    template_name = 'checklists/report_summary.html'
    context_object_name = 'report_data'
    # No pagination for a summary report usually

    def get_queryset(self):
        # Aggregate data: count total completed runs and runs with issues per template
        # Consider date range filtering here based on request.GET
        queryset = Checklist.objects.filter(is_complete=True)

        self.start_date_str = self.request.GET.get('start_date') # Store for context
        self.end_date_str = self.request.GET.get('end_date') # Store for context

        if self.start_date_str:
             try:
                  start_date = timezone.datetime.strptime(self.start_date_str, '%Y-%m-%d').date()
                  queryset = queryset.filter(performed_at__date__gte=start_date)
             except (ValueError, TypeError):
                  messages.warning(self.request, _("Неверный формат начальной даты."))
                  self.start_date_str = None # Clear invalid date

        if self.end_date_str:
             try:
                  end_date = timezone.datetime.strptime(self.end_date_str, '%Y-%m-%d').date()
                  queryset = queryset.filter(performed_at__date__lte=end_date)
             except (ValueError, TypeError):
                  messages.warning(self.request, _("Неверный формат конечной даты."))
                  self.end_date_str = None # Clear invalid date

        # Group by template and annotate counts
        report = (
            ChecklistTemplate.objects.filter(runs__in=queryset) # Only include templates with runs in the filtered set
            .annotate(
                total_runs=Count("runs", filter=Q(runs__in=queryset)), # Count runs within the filtered set
                 # Count runs from the filtered set that have ANY 'not_ok' result
                runs_with_issues=Count(
                    "runs",
                    filter=Q(
                        runs__in=queryset,
                        runs__results__status=ChecklistItemStatus.NOT_OK,
                    ),
                    distinct=True # Count distinct runs
                ),
            )
            .filter(total_runs__gt=0) # Only show templates with completed runs in the period
            .select_related('category')
            .order_by("category__name" if ChecklistTemplate._meta.get_field('category').remote_field.model else 'name', "name")
        )
        return report

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Сводный отчет по чеклистам")

        # Calculate overall totals (apply same date filter logic as in get_queryset)
        all_completed_runs_in_period = Checklist.objects.filter(is_complete=True)
        if self.start_date_str:
             try:
                  start_date = timezone.datetime.strptime(self.start_date_str, '%Y-%m-%d').date()
                  all_completed_runs_in_period = all_completed_runs_in_period.filter(performed_at__date__gte=start_date)
             except (ValueError, TypeError): pass
        if self.end_date_str:
             try:
                  end_date = timezone.datetime.strptime(self.end_date_str, '%Y-%m-%d').date()
                  all_completed_runs_in_period = all_completed_runs_in_period.filter(performed_at__date__lte=end_date)
             except (ValueError, TypeError): pass

        total_completed_runs = all_completed_runs_in_period.count()
        total_runs_with_issues = all_completed_runs_in_period.filter(results__status=ChecklistItemStatus.NOT_OK).distinct().count()

        context['total_completed_runs'] = total_completed_runs
        context['total_runs_with_issues'] = total_runs_with_issues

        # Calculate overall percentage ok
        if total_completed_runs > 0:
            runs_without_issues = total_completed_runs - total_runs_with_issues
            context['overall_percentage_ok'] = (runs_without_issues / total_completed_runs) * 100
        else:
            context['overall_percentage_ok'] = None # Or 100, or 0, depending on preference

        # Calculate percentage for each template stat
        report_data_with_perc = []
        for stat in context['report_data']:
             if stat.total_runs > 0:
                  stat.percentage_ok = ((stat.total_runs - stat.runs_with_issues) / stat.total_runs) * 100
             else:
                  stat.percentage_ok = None # Or 100/0
             report_data_with_perc.append(stat) # This modifies the objects already in context['report_data']

        # Pass dates back to template for filter persistence
        context['start_date'] = self.start_date_str
        context['end_date'] = self.end_date_str

        return context

class ChecklistIssuesReportView(LoginRequiredMixin, CanReviewChecklistMixin, ListView):
    template_name = 'checklists/report_issues.html'
    context_object_name = 'issue_results'
    paginate_by = 50

    def get_queryset(self):
        # Filter results directly for 'Not OK' status
        # Apply date range filtering based on the run's performed_at
        queryset = ChecklistResult.objects.filter(status=ChecklistItemStatus.NOT_OK)

        start_date_str = self.request.GET.get('start_date')
        end_date_str = self.request.GET.get('end_date')

        if start_date_str:
             try:
                  start_date = timezone.datetime.strptime(start_date_str, '%Y-%m-%d').date()
                  queryset = queryset.filter(checklist_run__performed_at__date__gte=start_date)
             except ValueError:
                  messages.warning(self.request, _("Неверный формат начальной даты."))

        if end_date_str:
             try:
                  end_date = timezone.datetime.strptime(end_date_str, '%Y-%m-%d').date()
                  queryset = queryset.filter(checklist_run__performed_at__date__lte=end_date)
             except ValueError:
                  messages.warning(self.request, _("Неверный формат конечной даты."))

        # Optimize with related selects/prefetches for display
        queryset = queryset.select_related(
                'checklist_run__template', 'checklist_run__performed_by',
                'template_item', 'template_item__section', 'checklist_run__location', 'checklist_run__point',
                'created_by', 'updated_by'
            ).order_by('-checklist_run__performed_at', 'template_item__section__order', 'template_item__order')


        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Отчет по пунктам с проблемами")
        # Pass dates back to template for filter persistence
        context['start_date'] = self.request.GET.get('start_date')
        context['end_date'] = self.request.GET.get('end_date')
        return context

# ==================================
# API Views (Requires Django REST framework)
# ==================================
class ChecklistPointListView(generics.ListAPIView):
    """ API view to list ChecklistPoints, filterable by location. """
    serializer_class = ChecklistPointSerializer
    permission_classes = [permissions.IsAuthenticated] # Adjust permission as needed
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['location'] # Allows ?location=<id> filtering

    def get_queryset(self):
        """ Returns ChecklistPoints ordered by name. """
        # Filter points that belong to locations the user has access to?
        # For now, return all points ordered by location and name
        return ChecklistPoint.objects.all().select_related('location').order_by('location__name', 'name')

# Add other API views here following DRF patterns (ListCreateAPIView, RetrieveUpdateDestroyAPIView, etc.)
# For example:
# class ChecklistTemplateListAPIView(generics.ListAPIView):
#      serializer_class = ChecklistTemplateSerializer
#      permission_classes = [permissions.IsAuthenticated]
#      queryset = ChecklistTemplate.objects.filter(is_active=True, is_archived=False).order_by('name')
#      filter_backends = [DjangoFilterBackend]
#      filterset_fields = ['category', 'target_location'] # Add filters


# class ChecklistRunListCreateAPIView(generics.ListCreateAPIView):
#     serializer_class = ChecklistRunSerializer # Or ChecklistRunCreateUpdateSerializer for create
#     permission_classes = [permissions.IsAuthenticated]
#
#     def get_queryset(self):
#         # Show runs performed by the current user or accessible ones
#         return Checklist.objects.filter(performed_by=self.request.user).order_by('-performed_at')
#         # Or if user has access to all: return Checklist.objects.all().order_by('-performed_at')
#
#     def perform_create(self, serializer):
#          # Set performed_by to the current user automatically
#          serializer.save(performed_by=self.request.user)

# class ChecklistRunDetailAPIView(generics.RetrieveAPIView):
#      serializer_class = ChecklistRunSerializer
#      permission_classes = [permissions.IsAuthenticated]
#      queryset = Checklist.objects.all() # Add filtering/permissions as needed

# class ChecklistResultUpdateAPIView(generics.UpdateAPIView):
#      serializer_class = ChecklistResultUpdateSerializer
#      permission_classes = [permissions.IsAuthenticated]
#      queryset = ChecklistResult.objects.all()

# Example API endpoint for saving a single item result (AJAX from Perform view)
# @api_view(['POST']) # Requires rest_framework.decorators.api_view
# @permission_classes([IsAuthenticated]) # Requires rest_framework.decorators.permission_classes, rest_framework.permissions.IsAuthenticated
# def save_checklist_item_api(request, pk, result_pk):
#     checklist_run = get_object_or_404(Checklist, pk=pk, performed_by=request.user)
#     result = get_object_or_404(ChecklistResult, pk=result_pk, checklist_run=checklist_run)
#
#     serializer = ChecklistResultUpdateSerializer(result, data=request.data, partial=True, context={'request': request}) # Use partial=True for partial updates
#     if serializer.is_valid():
#         serializer.save()
#         return Response(serializer.data)
#     return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)