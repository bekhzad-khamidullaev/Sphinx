# tasks/forms.py
import logging
import re
from datetime import timedelta
from django.utils import timezone
from django import forms
from django.urls import reverse_lazy
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.db import transaction
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Fieldset, Row, Column, Field, HTML, Submit
from django_select2.forms import (
    Select2Widget, Select2MultipleWidget,
    ModelSelect2Widget, ModelSelect2MultipleWidget
)

from .models import Task, TaskPhoto, Project, TaskCategory, TaskSubcategory, TaskComment, TaskAssignment, PriorityDeadline
from django.contrib.auth import get_user_model
User = get_user_model()

logger = logging.getLogger(__name__)

# --- Base CSS Classes for Form Widgets ---
BASE_INPUT_CLASSES = (
    "block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm "
    "focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm transition duration-150 ease-in-out"
)
TEXT_INPUT_CLASSES = f"form-input {BASE_INPUT_CLASSES}"
TEXTAREA_CLASSES = f"form-textarea {BASE_INPUT_CLASSES}"
SELECT_CLASSES = f"form-select {BASE_INPUT_CLASSES}" # For native selects if not using Select2
DATE_INPUT_CLASSES = f"form-input {BASE_INPUT_CLASSES} flatpickr-date" # For Flatpickr
DATETIME_INPUT_CLASSES = f"form-input {BASE_INPUT_CLASSES} flatpickr-datetime" # For Flatpickr
FILE_INPUT_CLASSES = (
    "form-control block w-full text-sm text-gray-900 border border-gray-300 rounded-lg "
    "cursor-pointer bg-gray-50 focus:outline-none file:mr-4 file:py-2 file:px-4 file:rounded-lg "
    "file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 transition duration-150 ease-in-out"
)
CHECKBOX_CLASSES = "form-checkbox h-5 w-5 text-indigo-600 rounded border-gray-300 focus:ring-indigo-500"

# URL name for user autocomplete, used by django-select2
USER_AUTOCOMPLETE_URL_NAME = 'tasks:user_autocomplete' # Make sure this matches your urls.py

# --- Crispy Forms Mixin ---
class CrispyFormMixin(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_method = 'post'
        self.helper.form_tag = False # We'll add <form> tags in the template
        self.helper.disable_csrf = True # We'll add {% csrf_token %} in the template

# --- Project Form ---
class ProjectForm(CrispyFormMixin, forms.ModelForm):
    class Meta:
        model = Project
        fields = ["name", "description", "owner", "start_date", "end_date", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _('Введите название проекта')}),
            "description": forms.Textarea(attrs={'rows': 4, 'class': TEXTAREA_CLASSES, 'placeholder': _('Добавьте описание проекта')}),
            "owner": Select2Widget(
                attrs={'class': SELECT_CLASSES, 'data-placeholder': _("Выберите владельца (необязательно)")}
            ), # Assuming owner is a standard ForeignKey, Select2Widget can be used.
               # If you need AJAX autocomplete for owner, use ModelSelect2Widget.
            "start_date": forms.DateInput(format='%Y-%m-%d', attrs={"type": "date", 'class': DATE_INPUT_CLASSES}),
            "end_date": forms.DateInput(format='%Y-%m-%d', attrs={"type": "date", 'class': DATE_INPUT_CLASSES}),
            "is_active": forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
        }
        labels = {
            "name": _("Название проекта"),
            "description": _("Описание"),
            "start_date": _("Дата начала"),
            "end_date": _("Дата завершения"),
            "is_active": _("Проект активен"),
            "owner": _("Владелец проекта")
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Customize Crispy Forms layout
        self.helper.layout = Layout(
            Fieldset(
                _("Основная информация"),
                'name',
                'description',
                'owner',
                'is_active',
                css_class="mb-4 p-4 border rounded-lg border-gray-200 "
            ),
            Fieldset(
                _("Сроки проекта"),
                Row(
                    Column('start_date', css_class='md:w-1/2 pr-2'), # Added pr-2 for spacing
                    Column('end_date', css_class='md:w-1/2 pl-2')   # Added pl-2 for spacing
                ),
                css_class="mb-4 p-4 border rounded-lg border-gray-200 "
            ),
        )

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")

        # Default start_date to today for new projects if not provided
        if not start_date and not (self.instance and self.instance.pk): # If new instance and no start_date
            cleaned_data['start_date'] = timezone.now().date()
            start_date = cleaned_data['start_date'] # update for subsequent checks

        if start_date and end_date and end_date < start_date:
            self.add_error('end_date', ValidationError(_("Дата завершения не может быть раньше даты начала.")))
        return cleaned_data

# --- TaskCategory Form ---
class TaskCategoryForm(CrispyFormMixin, forms.ModelForm):
    class Meta:
        model = TaskCategory
        fields = ["name", "description"]
        widgets = {
            "name": forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES}),
            "description": forms.Textarea(attrs={'rows': 2, 'class': TEXTAREA_CLASSES})
        }
        labels = { # Explicit labels
            "name": _("Название категории"),
            "description": _("Описание категории")
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper.layout = Layout('name', 'description')

# --- TaskSubcategory Form ---
class TaskSubcategoryForm(CrispyFormMixin, forms.ModelForm):
    category = forms.ModelChoiceField(
        queryset=TaskCategory.objects.all().order_by("name"),
        label=_("Родительская категория"),
        widget=Select2Widget(attrs={'class': SELECT_CLASSES, 'data-placeholder': _("Выберите категорию...")})
    )

    class Meta:
        model = TaskSubcategory
        fields = ["category", "name", "description"]
        widgets = {
            "name": forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES}),
            "description": forms.Textarea(attrs={'rows': 2, 'class': TEXTAREA_CLASSES})
        }
        labels = { # Explicit labels
            "name": _("Название подкатегории"),
            "description": _("Описание подкатегории")
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper.layout = Layout('category', 'name', 'description')

    def clean(self):
        cleaned_data = super().clean()
        category = cleaned_data.get('category')
        name = cleaned_data.get('name')
        if category and name:
            query = TaskSubcategory.objects.filter(category=category, name__iexact=name)
            if self.instance and self.instance.pk: # Exclude self if updating
                query = query.exclude(pk=self.instance.pk)
            if query.exists():
                self.add_error('name', ValidationError(_("Подкатегория с таким названием уже существует в этой категории.")))
        return cleaned_data

# --- Task Form ---
class TaskForm(CrispyFormMixin, forms.ModelForm):
    project = forms.ModelChoiceField(
        label=_('Проект'),
        queryset=Project.objects.filter(is_active=True).order_by("name"),
        required=True,
        widget=Select2Widget(attrs={'class': SELECT_CLASSES, 'data-placeholder': _('Выберите проект...')})
    )
    category = forms.ModelChoiceField(
        label=_('Категория'),
        queryset=TaskCategory.objects.all().order_by("name"),
        required=False,
        widget=Select2Widget(attrs={'class': SELECT_CLASSES, 'id': 'id_category', 'data-placeholder': _('Выберите категорию (необязательно)')})
    )
    subcategory = forms.ModelChoiceField(
        label=_('Подкатегория'),
        queryset=TaskSubcategory.objects.none(), # Populated by JS
        required=False,
        widget=Select2Widget(attrs={'class': SELECT_CLASSES, 'id': 'id_subcategory', 'disabled': True, 'data-placeholder': _('Сначала выберите категорию')})
    )
    estimated_time = forms.CharField(
        label=_('Оценка времени'),
        required=False,
        help_text=_("Формат: 1d 2h 30m (d-дни, h-часы, m-минуты)"),
        widget=forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _('Напр., 1d 4h')})
    )

    # Common attributes for AJAX-powered Select2 user fields
    _user_select_widget_common_attrs = {
        'data-ajax--url': reverse_lazy(USER_AUTOCOMPLETE_URL_NAME),
        'data-ajax--cache': 'true',
        'data-ajax--delay': 250,
        'data-minimum-input-length': 1, # Start searching after 1 char
        'class': SELECT_CLASSES, # Apply base styling
    }

    responsible_user = forms.ModelChoiceField(
        label=_('Ответственный'),
        queryset=User.objects.filter(is_active=True),
        required=False, # Adjust as per your business logic
        widget=ModelSelect2Widget(
            model=User,
            search_fields=['username__icontains', 'first_name__icontains', 'last_name__icontains', 'email__icontains'],
            attrs={**_user_select_widget_common_attrs, 'id': 'id_responsible_user', 'data-placeholder': _('Выберите ответственного...')}
        )
    )
    executors = forms.ModelMultipleChoiceField(
        label=_('Исполнители'),
        queryset=User.objects.filter(is_active=True),
        required=False,
        widget=ModelSelect2MultipleWidget(
            model=User,
            search_fields=['username__icontains', 'first_name__icontains', 'last_name__icontains', 'email__icontains'],
            attrs={**_user_select_widget_common_attrs, 'id': 'id_executors', 'data-placeholder': _('Добавьте исполнителей...')}
        )
    )
    watchers = forms.ModelMultipleChoiceField(
        label=_('Наблюдатели'),
        queryset=User.objects.filter(is_active=True),
        required=False,
        widget=ModelSelect2MultipleWidget(
            model=User,
            search_fields=['username__icontains', 'first_name__icontains', 'last_name__icontains', 'email__icontains'],
            attrs={**_user_select_widget_common_attrs, 'id': 'id_watchers', 'data-placeholder': _('Добавьте наблюдателей...')}
        )
    )

    class Meta:
        model = Task
        fields = [
            "project", "title", "description", "category", "subcategory",
            "status", "priority", "start_date", "due_date", "estimated_time"
        ]
        widgets = {
            "title": forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _('Краткое и информативное название задачи')}),
            "description": forms.Textarea(attrs={'rows': 5, 'class': TEXTAREA_CLASSES, 'placeholder': _('Подробное описание...')}),
            "status": forms.Select(attrs={'class': SELECT_CLASSES}), # Native select, can be styled
            "priority": forms.Select(attrs={'class': SELECT_CLASSES}), # Native select
            "start_date": forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': DATE_INPUT_CLASSES}),
            "due_date": forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': DATE_INPUT_CLASSES}),
        }
        # Labels can be defined here too if needed, or rely on model verbose_name

    def __init__(self, *args, **kwargs):
        self.request_user = kwargs.pop('user', None) # Pop user from kwargs for use in save
        instance = kwargs.get("instance")
        initial_data = kwargs.get("initial", {})

        if instance and instance.pk: # Pre-fill assignment fields if updating an existing task
            assignments = TaskAssignment.objects.filter(task=instance).select_related('user')
            initial_data.setdefault("responsible_user", next((a.user for a in assignments if a.role == TaskAssignment.RoleChoices.RESPONSIBLE), None))
            initial_data.setdefault("executors", [a.user.pk for a in assignments if a.role == TaskAssignment.RoleChoices.EXECUTOR])
            initial_data.setdefault("watchers", [a.user.pk for a in assignments if a.role == TaskAssignment.RoleChoices.WATCHER])
        kwargs["initial"] = initial_data

        super().__init__(*args, **kwargs)

        # Set initial values for new tasks
        if not (instance and instance.pk): # If this is a new task form
            if not self.initial.get('priority'):
                self.fields['priority'].initial = Task.TaskPriority.MEDIUM
            if not self.initial.get('start_date'):
                self.fields['start_date'].initial = timezone.now().date()
            if not self.initial.get('status'):
                self.fields['status'].initial = Task.StatusChoices.BACKLOG # Or NEW

        # Logic for dependent subcategory field based on category
        category_id_from_data = self.data.get(self.add_prefix('category')) if self.is_bound else None
        category_id_from_initial = self.initial.get('category')
        category_id_from_instance = instance.category_id if instance and instance.category_id else None

        # Determine the final category ID to use for querying subcategories
        final_category_id = category_id_from_data or \
                            (category_id_from_initial.id if hasattr(category_id_from_initial, 'id') else category_id_from_initial) or \
                            category_id_from_instance

        if final_category_id:
            try:
                # Ensure final_category_id is an integer if it's a string from POST data
                final_category_id_int = int(final_category_id)
                self.fields['subcategory'].queryset = TaskSubcategory.objects.filter(category_id=final_category_id_int).order_by('name')
                self.fields['subcategory'].widget.attrs.pop('disabled', None) # Enable if disabled
            except (ValueError, TypeError):
                logger.warning(f"Could not determine valid category ID for subcategories: {final_category_id}")
                self.fields['subcategory'].queryset = TaskSubcategory.objects.none()
                self.fields['subcategory'].widget.attrs['disabled'] = True
        else:
            self.fields['subcategory'].queryset = TaskSubcategory.objects.none()
            self.fields['subcategory'].widget.attrs['disabled'] = True

        self.priority_deadlines = {pd.priority: pd.days for pd in PriorityDeadline.objects.all()}

        # Crispy Forms Layout
        self.helper.layout = Layout(
            Fieldset(
                _('Основная информация'),
                Field('project'), Field('title'), Field('description'),
                css_class="mb-4 p-4 border rounded-lg border-gray-200 "
            ),
            Fieldset(
                _('Классификация и Детализация'),
                Row(
                    Column(Field('category', wrapper_class="flex-grow"), css_class='md:w-1/2 pr-2 mb-4 md:mb-0'), # Added mb for mobile
                    Column(Field('subcategory', wrapper_class="flex-grow"), css_class='md:w-1/2 pl-2')
                , css_class="flex flex-col md:flex-row mb-4"), # flex-col for mobile stacking
                Row(
                    Column(Field('status', wrapper_class="flex-grow"), css_class='md:w-1/2 pr-2 mb-4 md:mb-0'),
                    Column(Field('priority', wrapper_class="flex-grow"), css_class='md:w-1/2 pl-2')
                , css_class="flex flex-col md:flex-row mb-4"),
                css_class="mb-4 p-4 border rounded-lg border-gray-200 "
            ),
            Fieldset(
                _('Сроки и Оценка'),
                Row(
                    Column(Field('start_date', wrapper_class="flex-grow"), css_class='md:w-1/3 pr-2 mb-4 md:mb-0'),
                    Column(Field('due_date', wrapper_class="flex-grow"), css_class='md:w-1/3 px-1 mb-4 md:mb-0'), # px-1 for spacing
                    Column(Field('estimated_time', wrapper_class="flex-grow"), css_class='md:w-1/3 pl-2')
                , css_class="flex flex-col md:flex-row mb-4"),
                css_class="mb-4 p-4 border rounded-lg border-gray-200 "
            ),
            Fieldset(
                _('Участники'),
                Field('responsible_user', css_class="mb-4"),
                Field('executors', css_class="mb-4"),
                Field('watchers', css_class="mb-4"),
                css_class="p-4 border rounded-lg border-gray-200 "
            )
        )

    def clean_estimated_time(self):
        duration_string = self.cleaned_data.get("estimated_time", "")
        if not duration_string or not duration_string.strip():
            return None # Allow empty

        normalized_duration = duration_string.lower().replace(' ', '')
        days, hours, minutes = 0, 0, 0

        days_match = re.search(r"(\d+)d", normalized_duration)
        hours_match = re.search(r"(\d+)h", normalized_duration)
        minutes_match = re.search(r"(\d+)m", normalized_duration)

        if days_match:
            days = int(days_match.group(1))
            normalized_duration = normalized_duration.replace(days_match.group(0), "")
        if hours_match:
            hours = int(hours_match.group(1))
            normalized_duration = normalized_duration.replace(hours_match.group(0), "")
        if minutes_match:
            minutes = int(minutes_match.group(1))
            normalized_duration = normalized_duration.replace(minutes_match.group(0), "")

        # If any non-numeric, non-d/h/m characters remain after parsing
        if re.search(r"[^\d]", normalized_duration): # Check for anything not a digit
             raise ValidationError(
                _("Неверный формат времени. Используйте только цифры и 'd', 'h', 'm'. Например: 1d 2h 30m."),
                code='invalid_timedelta_format'
            )


        if not (days_match or hours_match or minutes_match): # If no valid units were found but string was not empty
             if duration_string.strip(): # And the original string was not just whitespace
                raise ValidationError(
                    _("Неверный формат времени. Укажите d (дни), h (часы), или m (минуты)."),
                    code='invalid_timedelta_units'
                )
             return None # Treat as empty if only whitespace was entered

        if days == 0 and hours == 0 and minutes == 0 and (days_match or hours_match or minutes_match): # e.g. "0d 0h 0m"
            return timedelta(0) # Return zero timedelta

        return timedelta(days=days, hours=hours, minutes=minutes)

    def clean(self):
        cleaned_data = super().clean()
        category = cleaned_data.get("category")
        subcategory = cleaned_data.get("subcategory")
        start_date = cleaned_data.get("start_date")
        due_date = cleaned_data.get("due_date")

        if subcategory and not category:
            self.add_error('category', _("Необходимо выбрать категорию, если указана подкатегория."))
        elif subcategory and category and subcategory.category != category:
            self.add_error('subcategory', _("Выбранная подкатегория не принадлежит указанной категории."))

        if start_date and due_date and due_date < start_date:
            self.add_error('due_date', _("Срок выполнения не может быть раньше даты начала."))

        responsible = cleaned_data.get("responsible_user")
        executors = cleaned_data.get("executors") or User.objects.none() # Ensure it's a queryset
        watchers = cleaned_data.get("watchers") or User.objects.none()   # Ensure it's a queryset

        if responsible and hasattr(executors, '__iter__') and responsible in executors:
            self.add_error('executors', _("Ответственный пользователь не может быть одновременно исполнителем."))
        if responsible and hasattr(watchers, '__iter__') and responsible in watchers:
            self.add_error('watchers', _("Ответственный пользователь не может быть одновременно наблюдателем."))

        if hasattr(executors, '__iter__') and hasattr(watchers, '__iter__'):
            common_users = set(executors) & set(watchers)
            if common_users:
                self.add_error(None, ValidationError(
                    _("Пользователи %(users)s не могут быть одновременно исполнителями и наблюдателями.") %
                    {'users': ", ".join(u.get_username() for u in common_users)}
                ))
        return cleaned_data

    @transaction.atomic
    def save(self, commit=True):
        task_instance = super().save(commit=False)

        # Set created_by for new tasks if not already set and request_user is available
        if not task_instance.pk and self.request_user and self.request_user.is_authenticated and not task_instance.created_by_id:
            task_instance.created_by = self.request_user

        # Set initiator for signals/auditing if request_user is available
        if self.request_user and self.request_user.is_authenticated:
            setattr(task_instance, '_initiator_user_id', self.request_user.id)
        setattr(task_instance, '_called_from_form_save', True) # Flag for model's save method

        if commit:
            task_instance.save() # Save the Task instance first to get a PK
            # self.save_m2m() # Call if Task model had direct M2M fields managed by this form (not assignments)

            # Handle TaskAssignments
            responsible_user = self.cleaned_data.get('responsible_user')
            executor_users = self.cleaned_data.get('executors', User.objects.none())
            watcher_users = self.cleaned_data.get('watchers', User.objects.none())

            # Fetch current assignments for this task
            current_assignments = TaskAssignment.objects.filter(task=task_instance)
            target_assignment_tuples = set() # Store (user_id, role)

            # Add responsible user
            if responsible_user:
                target_assignment_tuples.add((responsible_user.id, TaskAssignment.RoleChoices.RESPONSIBLE))

            # Add executors
            for user in executor_users:
                if user != responsible_user: # Cannot be both
                    target_assignment_tuples.add((user.id, TaskAssignment.RoleChoices.EXECUTOR))

            # Add watchers
            for user in watcher_users:
                # Watcher cannot be responsible or executor (as per earlier clean method logic)
                if user != responsible_user and user not in executor_users:
                    target_assignment_tuples.add((user.id, TaskAssignment.RoleChoices.WATCHER))

            # Add creator as reporter if not already a primary participant
            if self.request_user and self.request_user.is_authenticated:
                creator_is_primary_assigned = (responsible_user == self.request_user) or \
                                              (self.request_user in executor_users)
                if not creator_is_primary_assigned:
                    target_assignment_tuples.add((self.request_user.id, TaskAssignment.RoleChoices.REPORTER))


            current_db_tuples = set((ca.user_id, ca.role) for ca in current_assignments)

            # Assignments to delete
            to_delete_pks = [ca.pk for ca in current_assignments if (ca.user_id, ca.role) not in target_assignment_tuples]
            if to_delete_pks:
                TaskAssignment.objects.filter(pk__in=to_delete_pks).delete()

            # Assignments to create
            assigned_by_user = self.request_user if self.request_user and self.request_user.is_authenticated else None
            assignments_to_create = []
            for user_id, role in target_assignment_tuples:
                if (user_id, role) not in current_db_tuples:
                    assignments_to_create.append(
                        TaskAssignment(task=task_instance, user_id=user_id, role=role, assigned_by=assigned_by_user)
                    )
            if assignments_to_create:
                TaskAssignment.objects.bulk_create(assignments_to_create, ignore_conflicts=True) # ignore_conflicts for safety

        # Clean up temporary attributes
        if hasattr(task_instance, '_initiator_user_id'):
            delattr(task_instance, '_initiator_user_id')
        if hasattr(task_instance, '_called_from_form_save'):
            delattr(task_instance, '_called_from_form_save')

        return task_instance

# --- TaskPhoto Form (for ModelFormSet) ---
class TaskPhotoForm(CrispyFormMixin, forms.ModelForm):
    class Meta:
        model = TaskPhoto
        fields = ["photo", "description"]
        widgets = {
            "photo": forms.ClearableFileInput(attrs={"class": FILE_INPUT_CLASSES, 'accept': 'image/*'}),
            "description": forms.Textarea(attrs={"rows": 2, 'class': TEXTAREA_CLASSES, 'placeholder': _('Описание фото (необязательно)')})
        }
        labels = {
            "photo": _("Файл фото"),
            "description": _("Описание")
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper.form_tag = False # Part of a formset, main form has the tag
        # Minimal layout for formset rows
        self.helper.layout = Layout(
            Field('photo'),
            Field('description')
        )

# --- TaskComment Form ---
class TaskCommentForm(CrispyFormMixin, forms.ModelForm):
    class Meta:
        model = TaskComment
        fields = ["text"]
        widgets = {
            "text": forms.Textarea(attrs={"rows": 3, "placeholder": _("Напишите комментарий..."), "class": TEXTAREA_CLASSES})
        }
        labels = {
            "text": "" # Hide label as placeholder is sufficient
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper.form_show_labels = False
        self.helper.layout = Layout(Field('text'))