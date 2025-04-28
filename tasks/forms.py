# tasks/forms.py

import logging
import re
from datetime import timedelta

from django import forms
from django.urls import reverse_lazy # Used for generating API URLs dynamically
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.db import transaction # For atomic database operations
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Fieldset, Row, Field, HTML
# Import specific Select2 widgets including ModelSelect2 for AJAX loading
from django_select2.forms import (
    Select2Widget, Select2MultipleWidget,
    ModelSelect2Widget, ModelSelect2MultipleWidget
)


# Get the logger instance for this module
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Import Models
# --------------------------------------------------------------------------
# Import models from the current application (.models)
# Important: Import only the models themselves, not attributes at the class level yet
from .models import Task, TaskPhoto, Project, TaskCategory, TaskSubcategory, TaskComment

# Import User and TaskUserRole models from user_profiles app safely
# This allows the tasks app to function (with limitations) even if user_profiles is not installed
try:
    from user_profiles.models import User, TaskUserRole
except ImportError:
    # Log an error if the import fails and set models to None
    logger.error("Could not import User or TaskUserRole from user_profiles.models. User selection features will be disabled.")
    User = None
    TaskUserRole = None
except Exception as e:
    # Catch other potential import errors
    logger.exception(f"An unexpected error occurred while importing from user_profiles.models: {e}")
    User = None
    TaskUserRole = None


# --------------------------------------------------------------------------
# Define Reusable CSS Classes (Tailwind CSS with Dark Mode)
# --------------------------------------------------------------------------
# Ensure these class strings match your Tailwind configuration and conventions
BASE_INPUT_CLASSES = "block w-full px-4 py-2 border border-gray-300 rounded-lg shadow-sm focus:ring focus:ring-blue-500 focus:border-blue-500 focus:outline-none dark:bg-dark-700 dark:border-dark-600 dark:text-gray-200 dark:placeholder-gray-500 transition duration-150 ease-in-out"
TEXT_INPUT_CLASSES = f"form-input {BASE_INPUT_CLASSES}"
TEXTAREA_CLASSES = f"form-textarea {BASE_INPUT_CLASSES}"
# Base styling for standard select elements (often replaced visually by JS widgets like Select2)
SELECT_CLASSES = f"form-select {BASE_INPUT_CLASSES}"
# Class for date/datetime inputs, assuming flatpickr or similar JS picker is used and handles styling
DATE_INPUT_CLASSES = f"form-input {BASE_INPUT_CLASSES} flatpickr"
DATETIME_INPUT_CLASSES = DATE_INPUT_CLASSES
# Styling for file input fields
FILE_INPUT_CLASSES = "form-control block w-full text-sm text-gray-900 border border-gray-300 rounded-lg cursor-pointer bg-gray-50 dark:text-gray-400 focus:outline-none dark:bg-dark-600 dark:border-dark-500 dark:placeholder-gray-400 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 dark:file:bg-dark-500 dark:file:text-gray-300 dark:hover:file:bg-dark-400 transition duration-150 ease-in-out"

# Optional CSS classes specifically for targeting Select2 widgets via JavaScript initialization
# (Note: django-select2 typically handles initialization automatically via form media)
SELECT2_SINGLE_CLASS = "select2-single-widget"
SELECT2_MULTIPLE_CLASS = "select2-multiple-widget"


# --------------------------------------------------------------------------
# Define API Endpoint URL Name
# --------------------------------------------------------------------------
# This should match the 'name' argument in the path() definition in your api/urls.py
# Using reverse_lazy allows the URL lookup to happen when needed, not at import time.
USER_AUTOCOMPLETE_URL_NAME = 'api:user_autocomplete'


# ============================================================================== #
# Project Form
# ============================================================================== #
class ProjectForm(forms.ModelForm):
    """
    Form for creating and editing Project instances.
    Uses standard Django form widgets styled with Tailwind CSS classes.
    """
    class Meta:
        model = Project
        fields = ["name", "description", "start_date", "end_date", "is_active"] # Added is_active if applicable
        widgets = {
            "name": forms.TextInput(attrs={
                'class': TEXT_INPUT_CLASSES,
                'placeholder': _('Введите название проекта')
            }),
            "description": forms.Textarea(attrs={
                'rows': 4,
                'class': TEXTAREA_CLASSES,
                'placeholder': _('Добавьте описание целей и задач проекта (необязательно)')
            }),
            "start_date": forms.DateInput(format='%Y-%m-%d', attrs={
                "type": "date", # Use HTML5 date picker as fallback
                'class': DATE_INPUT_CLASSES,
                'placeholder': _('ГГГГ-ММ-ДД')
            }),
            "end_date": forms.DateInput(format='%Y-%m-%d', attrs={
                "type": "date",
                'class': DATE_INPUT_CLASSES,
                'placeholder': _('ГГГГ-ММ-ДД')
            }),
             "is_active": forms.CheckboxInput(attrs={
                'class': 'form-checkbox h-5 w-5 text-blue-600 border-gray-300 rounded focus:ring-blue-500 dark:border-dark-600 dark:bg-dark-700 dark:checked:bg-blue-500 dark:focus:ring-offset-dark-800'
            }),
        }
        labels = {
            "name": _("Название проекта"),
            "description": _("Описание"),
            "start_date": _("Дата начала"),
            "end_date": _("Дата завершения"),
            "is_active": _("Активен"),
        }
        help_texts = {
            "name": _("Укажите уникальное и понятное название для этого проекта."),
            "start_date": _("Дата, когда планируется или фактически начались работы по проекту."),
            "end_date": _("Планируемая или фактическая дата завершения всех работ по проекту."),
            "is_active": _("Отметьте, если проект активен и должен отображаться в списках."),
        }

    def __init__(self, *args, **kwargs):
        """Initialize the form and configure Crispy Forms helper."""
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_method = 'post'
        # form_tag=False prevents Crispy from rendering <form> tags itself,
        # as it's expected to be rendered inside a parent <form> in the template.
        self.helper.form_tag = False
        self.helper.disable_csrf = True # CSRF token should be handled by the template's <form> tag

    def clean(self):
        """Add cross-field validation."""
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")

        if start_date and end_date and end_date < start_date:
            self.add_error('end_date', ValidationError(_("Дата завершения не может быть раньше даты начала.")))
            self.add_error('start_date', ValidationError(_("Дата начала не может быть позже даты завершения.")))

        return cleaned_data

# ============================================================================== #
# Task Category Form
# ============================================================================== #
class TaskCategoryForm(forms.ModelForm):
    """
    Form for creating and editing TaskCategory instances.
    """
    class Meta:
        model = TaskCategory
        fields = ["name", "description"]
        widgets = {
            "name": forms.TextInput(attrs={
                'class': TEXT_INPUT_CLASSES,
                'placeholder': _('Название категории задач')
            }),
            "description": forms.Textarea(attrs={
                "rows": 3,
                'class': TEXTAREA_CLASSES,
                'placeholder': _('Краткое описание назначения категории (необязательно)')
            }),
        }
        labels = {
            "name": _("Название категории"),
            "description": _("Описание"),
        }


# ============================================================================== #
# Task Subcategory Form
# ============================================================================== #
class TaskSubcategoryForm(forms.ModelForm):
    """
    Form for creating and editing TaskSubcategory instances.
    Includes a Select2 widget for choosing the parent category.
    """
    # Use ModelChoiceField with Select2Widget for parent category selection
    category = forms.ModelChoiceField(
        queryset=TaskCategory.objects.all().order_by("name"),
        label=_("Родительская категория"),
        widget=Select2Widget(attrs={
            'data-placeholder': _("Выберите родительскую категорию..."),
            'class': f'{SELECT_CLASSES} {SELECT2_SINGLE_CLASS}' # Apply base styles and optional JS target class
            }),
        help_text=_("Выберите категорию, к которой относится эта подкатегория.")
    )

    class Meta:
        model = TaskSubcategory
        fields = ["category", "name", "description"]
        widgets = {
            "name": forms.TextInput(attrs={
                'class': TEXT_INPUT_CLASSES,
                'placeholder': _('Название подкатегории')
            }),
            "description": forms.Textarea(attrs={
                "rows": 3,
                'class': TEXTAREA_CLASSES,
                'placeholder': _('Краткое описание назначения подкатегории (необязательно)')
            }),
        }
        labels = {
            "name": _("Название подкатегории"),
            "description": _("Описание"),
        }


# ============================================================================== #
# Task Form
# ============================================================================== #
class TaskForm(forms.ModelForm):
    """
    Comprehensive form for creating and editing Task instances.
    Features include:
    - Standard input fields styled with Tailwind CSS.
    - Select2 widgets for Project and Category/Subcategory selection.
    - AJAX-powered ModelSelect2 widgets for selecting Responsible User, Executors, and Watchers.
    - Dynamic population of Subcategory choices based on selected Category via JavaScript.
    - Custom validation for estimated time format.
    - Cross-field validation for Category/Subcategory and User Roles.
    - Atomic save method to update Task and associated TaskUserRole records safely.
    - Crispy Forms integration for layout rendering in templates.
    - Graceful degradation if User/TaskUserRole models are unavailable.
    """

    # --- Core Task Fields ---
    title = forms.CharField(
        label=_('Название задачи'),
        max_length=255, # Define max length consistent with model
        widget=forms.TextInput(attrs={
            'class': TEXT_INPUT_CLASSES,
            'placeholder': _('Введите краткое и понятное название задачи')
        }),
        help_text=_("Основное название, которое будет отображаться в списках задач.")
    )
    description = forms.CharField(
        label=_('Описание задачи'),
        required=False, # Description is optional
        widget=forms.Textarea(attrs={
            'class': TEXTAREA_CLASSES,
            'rows': 5,
            'placeholder': _('Добавьте подробное описание задачи: что нужно сделать, шаги выполнения, критерии приемки, полезные ссылки и т.д.')
        }),
        help_text=_("Предоставьте всю необходимую информацию для выполнения задачи.")
    )
    deadline = forms.DateTimeField(
        label=_('Срок выполнения'),
        required=False, # Deadline is optional
        # Use HTML5 datetime-local input type as a fallback or primary input method
        widget=forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={
            'type': 'datetime-local',
            'class': DATETIME_INPUT_CLASSES # Apply styling and potentially JS picker class
        }),
        help_text=_("Укажите дату и время, к которому задача должна быть завершена.")
    )
    estimated_time = forms.CharField(
        label=_('Планируемое время'),
        required=False, # Estimated time is optional
        help_text=_("Оценка времени в формате 'Xd Yh Zm' (или 'Xд Yч Zм'). Например: 1d 2h 30m, 2ч 15м, 45m."),
        widget=forms.TextInput(attrs={
            'class': TEXT_INPUT_CLASSES,
            'placeholder': _('Напр., 2h 30m')
        })
    )
    priority = forms.ChoiceField(
        label=_('Приоритет'),
        choices=[], # Choices are dynamically set in __init__ based on model definition
        widget=forms.Select(attrs={
            'class': SELECT_CLASSES # Use standard select, styled by Tailwind/CSS
        }),
        help_text=_("Укажите важность задачи.")
    )

    # --- Relational Fields (Project, Category, Subcategory) ---
    project = forms.ModelChoiceField(
        label=_('Проект'),
        # Optimize queryset by filtering active projects if applicable
        queryset=Project.objects.filter(is_active=True).order_by("name") if hasattr(Project, 'is_active') else Project.objects.all().order_by("name"),
        required=False, # Task may not belong to a project
        widget=Select2Widget(attrs={
            'data-placeholder': _('Выберите проект (необязательно)...'),
            'class': f'{SELECT_CLASSES} {SELECT2_SINGLE_CLASS}' # Base style + JS target class
        }),
        help_text=_("Свяжите задачу с конкретным проектом, если применимо.")
    )
    category = forms.ModelChoiceField(
        label=_('Категория'),
        queryset=TaskCategory.objects.all().order_by("name"),
        required=False, # Category is optional
        widget=Select2Widget(attrs={
            'id': 'id_category', # Specific ID needed for JavaScript interaction (dependent dropdown)
            'data-placeholder': _('Выберите категорию (необязательно)...'),
            'class': f'{SELECT_CLASSES} {SELECT2_SINGLE_CLASS}'
        }),
        help_text=_("Выберите основную категорию для классификации задачи.")
    )
    subcategory = forms.ModelChoiceField(
        label=_('Подкатегория'),
        queryset=TaskSubcategory.objects.none(), # Initially empty, populated by JavaScript based on Category selection
        required=False, # Subcategory is optional
        widget=Select2Widget(attrs={
            'id': 'id_subcategory', # Specific ID needed for JavaScript interaction
            'disabled': True, # Initially disabled until a category is chosen
            'data-placeholder': _('Сначала выберите категорию...'),
            'class': f'{SELECT_CLASSES} {SELECT2_SINGLE_CLASS}'
        }),
        help_text=_("Выберите подкатегорию для более точной классификации (доступно после выбора категории).")
    )

    # --- User Role Fields (Responsible, Executors, Watchers) ---
    # These fields are defined conditionally based on whether the User model was imported
    if User:
        # Define common attributes for all AJAX user selection widgets
        # Reduces repetition and ensures consistency
        user_select_widget_attrs = {
            'data-placeholder': _('Начните вводить имя, фамилию или email...'), # General placeholder
            'data-ajax--url': reverse_lazy(USER_AUTOCOMPLETE_URL_NAME), # URL for AJAX lookups
            'data-ajax--cache': 'true', # Enable client-side caching of results
            'data-ajax--delay': 250, # Delay in milliseconds before sending request
            'data-minimum-input-length': 1, # Minimum characters needed to trigger search
            'class': f'{SELECT_CLASSES}' # Apply base styling (Select2 overrides visuals)
            # 'theme': 'bootstrap-5' # Optional: Uncomment if using a specific theme like Bootstrap 5
        }

        # Responsible User (Single Selection, Required)
        responsible_user = forms.ModelChoiceField(
            label=_('Ответственный'),
            # Queryset used primarily for backend validation
            queryset=User.objects.filter(is_active=True),
            required=True, # A task must have a responsible user
            # Use ModelSelect2Widget for AJAX single selection
            widget=ModelSelect2Widget(
                model=User,
                # Define fields the widget's default view searches (should align with API view logic)
                search_fields=[
                    'username__icontains',
                    'first_name__icontains',
                    'last_name__icontains',
                    'email__icontains'
                ],
                # Merge common attributes with specific ones for this field
                attrs={
                    **user_select_widget_attrs,
                    'data-placeholder': _('Выберите ответственного (обязательно)...'), # More specific placeholder
                    'class': f'{SELECT_CLASSES} {SELECT2_SINGLE_CLASS}' # Add JS target class
                },
            ),
            help_text=_("Выберите пользователя, который несет основную ответственность за выполнение задачи.")
        )

        # Executors (Multiple Selection, Optional)
        executors = forms.ModelMultipleChoiceField(
            label=_('Исполнители'),
            queryset=User.objects.filter(is_active=True),
            required=False, # Executors are optional
            # Use ModelSelect2MultipleWidget for AJAX multiple selection
            widget=ModelSelect2MultipleWidget(
                model=User,
                search_fields=[
                    'username__icontains',
                    'first_name__icontains',
                    'last_name__icontains',
                    'email__icontains'
                ],
                # Merge common attributes with specific ones
                attrs={
                    **user_select_widget_attrs,
                    'data-placeholder': _('Выберите одного или нескольких исполнителей...'),
                    'class': f'{SELECT_CLASSES} {SELECT2_MULTIPLE_CLASS}' # Add JS target class
                },
            ),
            help_text=_("Выберите пользователей, которые будут непосредственно выполнять работу по задаче.")
        )

        # Watchers (Multiple Selection, Optional)
        watchers = forms.ModelMultipleChoiceField(
            label=_('Наблюдатели'),
            queryset=User.objects.filter(is_active=True),
            required=False, # Watchers are optional
            # Use ModelSelect2MultipleWidget
            widget=ModelSelect2MultipleWidget(
                model=User,
                search_fields=[
                    'username__icontains',
                    'first_name__icontains',
                    'last_name__icontains',
                    'email__icontains'
                ],
                 # Merge common attributes with specific ones
                 attrs={
                    **user_select_widget_attrs,
                    'data-placeholder': _('Выберите наблюдателей (необязательно)...'),
                    'class': f'{SELECT_CLASSES} {SELECT2_MULTIPLE_CLASS}' # Add JS target class
                },
            ),
            help_text=_("Выберите пользователей, которые будут получать уведомления об изменениях в этой задаче.")
        )
    else:
        # --- Fallback Fields if User Model is Unavailable ---
        # Provide disabled text fields as placeholders to indicate the feature is missing
        responsible_user = forms.CharField(
            label=_('Ответственный'),
            required=True, # Still conceptually required
            disabled=True, # Disable the field
            widget=forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES + ' bg-gray-100 dark:bg-dark-800 cursor-not-allowed'}), # Add disabled styling
            help_text=_("Функционал выбора пользователя недоступен (модуль user_profiles не найден).")
        )
        executors = forms.CharField(
            label=_('Исполнители'),
            required=False,
            disabled=True,
             widget=forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES + ' bg-gray-100 dark:bg-dark-800 cursor-not-allowed'}),
            help_text=_("Функционал выбора пользователей недоступен.")
        )
        watchers = forms.CharField(
            label=_('Наблюдатели'),
            required=False,
            disabled=True,
             widget=forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES + ' bg-gray-100 dark:bg-dark-800 cursor-not-allowed'}),
             help_text=_("Функционал выбора пользователей недоступен.")
        )


    class Meta:
        """Meta options for the TaskForm."""
        model = Task
        # Define the fields from the Task model that this form directly manages.
        # User roles (responsible_user, executors, watchers) are handled by the
        # manually defined fields above, so they are NOT listed here.
        fields = [
            "title", "description", "priority",
            "category", "subcategory", "project",
            "deadline", "estimated_time",
            # Do not include fields like 'created_by', 'created_at', 'updated_at'
            # unless you intend for the user to edit them directly via the form.
        ]

    def __init__(self, *args, **kwargs):
        """
        Initialize the TaskForm.
        - Sets up initial data for user roles when editing.
        - Populates priority choices.
        - Sets initial subcategory queryset.
        - Configures the Crispy Forms helper for layout.
        """
        # Extract the 'user' kwarg if provided (e.g., from the view)
        self.request_user = kwargs.pop('user', None)
        # Get the Task instance if provided (for editing)
        instance = kwargs.get("instance")
        # Get or initialize the 'initial' data dictionary
        initial_data = kwargs.get("initial", {})

        # --- Pre-populate User Role Fields for Editing ---
        # Only attempt if editing an existing task (instance has pk) and User/Role models are available
        if instance and instance.pk and TaskUserRole and User:
            try:
                # Fetch all roles associated with this task instance in one query
                roles_data = TaskUserRole.objects.filter(task=instance).values_list("user_id", "role")
                # Extract user IDs for each role type
                executors_ids = [user_id for user_id, role in roles_data if role == TaskUserRole.RoleChoices.EXECUTOR]
                watchers_ids = [user_id for user_id, role in roles_data if role == TaskUserRole.RoleChoices.WATCHER]
                # Find the responsible user's ID (should be only one, but handle potential missing case)
                responsible_id = next((user_id for user_id, role in roles_data if role == TaskUserRole.RoleChoices.RESPONSIBLE), None)

                # Set initial data for the form fields, only if not already provided in kwargs['initial']
                initial_data.setdefault("responsible_user", responsible_id)
                initial_data.setdefault("executors", executors_ids)
                initial_data.setdefault("watchers", watchers_ids)
            except Exception as error:
                 # Log any error during role pre-population
                 logger.error(f"Error pre-populating user roles for task ID {instance.pk}: {error}")

        # Update kwargs with potentially modified initial data before calling parent init
        kwargs["initial"] = initial_data
        # Call the parent ModelForm's __init__ method
        super().__init__(*args, **kwargs)

        # --- Set Priority Choices and Initial Value ---
        try:
            # Check if the Task model has the necessary TaskPriority enum/choices defined
            if hasattr(Task, 'TaskPriority') and hasattr(Task.TaskPriority, 'choices'):
                self.fields['priority'].choices = Task.TaskPriority.choices
                # Set a default priority (e.g., Medium) only if creating a new task
                # and no initial priority was provided.
                if 'priority' not in self.initial and not (instance and instance.priority):
                     # Ensure Task.TaskPriority.MEDIUM actually exists
                     if hasattr(Task.TaskPriority, 'MEDIUM'):
                        self.fields['priority'].initial = Task.TaskPriority.MEDIUM
                     else:
                         logger.warning("Task.TaskPriority.MEDIUM not found, cannot set default priority.")
            else:
                # Log error if priority setup fails
                logger.error("Model Task has no attribute 'TaskPriority' or it lacks 'choices'. Priority field cannot be populated.")
                self.fields['priority'].choices = [('', '-------')] # Provide a default empty choice
                self.fields['priority'].widget.attrs['disabled'] = True # Disable the field
        except Exception as error:
             # Catch any unexpected errors during priority setup
             logger.exception(f"Unexpected error setting choices for priority field: {error}")
             self.fields['priority'].choices = [('', '-------')]
             self.fields['priority'].widget.attrs['disabled'] = True

        # --- Set Initial Subcategory Queryset Based on Category ---
        # Determine the initial category ID from initial data or the instance
        category_field_value = self.initial.get('category') or (instance and instance.category_id)
        if category_field_value:
             try:
                 # If a category is selected, populate the subcategory choices accordingly
                 self.fields['subcategory'].queryset = TaskSubcategory.objects.filter(category_id=category_field_value).order_by('name')
                 # Enable the subcategory field (remove 'disabled' attribute if present)
                 self.fields['subcategory'].widget.attrs.pop('disabled', None)
             except Exception as error:
                  # Handle potential errors (e.g., invalid category ID, DB issues)
                  logger.error(f"Error setting initial subcategory queryset for category ID {category_field_value}: {error}")
                  self.fields['subcategory'].queryset = TaskSubcategory.objects.none() # Reset to empty queryset
                  self.fields['subcategory'].widget.attrs['disabled'] = True # Ensure it remains disabled
        else:
             # If no category is selected initially, keep subcategory empty and disabled
             self.fields['subcategory'].queryset = TaskSubcategory.objects.none()
             self.fields['subcategory'].widget.attrs['disabled'] = True


        # --- Configure Crispy Forms Helper for Layout Rendering ---
        self.helper = FormHelper(self)
        self.helper.form_method = 'post' # Specify form submission method
        self.helper.form_tag = False # Template will render the <form> tag
        self.helper.disable_csrf = True # Template will render the {% csrf_token %}

        # Define the visual layout of the form using Crispy Forms syntax
        # This structure uses Fieldsets for grouping and Rows with Tailwind CSS classes for columns
        self.helper.layout = Layout(
            # --- Section 1: Basic Info ---
            Fieldset(
                '', # No legend text for the first group
                Field('title', css_class='mb-4'), # Add bottom margin for spacing
                Field('description', css_class='mb-4'),
                # Add a visual separator (horizontal rule)
                css_class='border-b border-gray-200 dark:border-dark-600 pb-6 mb-6'
            ),
            # --- Section 2: Details & Classification ---
            Fieldset(
                _('Детали и классификация'), # Legend for this group
                 # Use a Row with Tailwind flexbox classes for side-by-side fields
                 Row(
                    # Field wrapped in a div taking half width on medium screens and full width on small
                    Field('priority', wrapper_class='w-full md:w-1/2 px-2 mb-4'),
                    Field('project', wrapper_class='w-full md:w-1/2 px-2 mb-4'),
                    # Apply flexbox classes to the Row container
                    css_class='flex flex-wrap -mx-2' # Negative margin compensates for padding on Fields
                 ),
                Row(
                    Field('category', wrapper_class='w-full md:w-1/2 px-2 mb-4'),
                    Field('subcategory', wrapper_class='w-full md:w-1/2 px-2 mb-4'),
                    css_class='flex flex-wrap -mx-2'
                 ),
                 # Add a visual separator
                css_class='border-b border-gray-200 dark:border-dark-600 pb-6 mb-6'
            ),
            # --- Section 3: Dates & Estimates ---
            Fieldset(
                 _('Сроки и оценка'),
                 Row(
                    Field('deadline', wrapper_class='w-full md:w-1/2 px-2 mb-4'),
                    Field('estimated_time', wrapper_class='w-full md:w-1/2 px-2 mb-4'),
                    css_class='flex flex-wrap -mx-2'
                 ),
                 # Add a visual separator
                 css_class='border-b border-gray-200 dark:border-dark-600 pb-6 mb-6'
            ),
            # --- Section 4: Participants ---
            Fieldset(
                 _('Участники'),
                 # Render each user selection field with bottom margin for vertical spacing
                 Field('responsible_user', css_class='mb-4'),
                 Field('executors', css_class='mb-4'),
                 Field('watchers', css_class='mb-4'),
                 # No bottom border needed for the last fieldset
            )
        ) # End of Layout definition

    def clean_estimated_time(self):
        """
        Validates the 'estimated_time' field and converts a human-readable
        time string (e.g., '1d 2h 30m', '2ч', '45м') into a Python timedelta object.
        Returns None if the field is empty, raises ValidationError if the format is invalid.
        """
        duration_string = self.cleaned_data.get("estimated_time")
        # If the field is optional and empty, return None
        if not duration_string:
            return None

        # Normalize the input: convert to lowercase and remove all whitespace
        normalized_duration = duration_string.lower().replace(' ', '')

        # Define the regular expression to capture days (d/д), hours (h/ч), and minutes (m/м)
        # Each part is optional (?:...)?
        # Named capture groups (?P<name>...) are used for easy extraction
        pattern = re.compile(
            r"^(?:(?P<days>\d+)(?:d|д))?"      # Optional days part (e.g., 1d, 10д)
            r"(?:(?P<hours>\d+)(?:h|ч))?"     # Optional hours part (e.g., 2h, 5ч)
            r"(?:(?P<minutes>\d+)(?:m|м))?$"  # Optional minutes part (e.g., 30m, 15м)
        )
        # Attempt to match the pattern against the normalized string from the beginning (^) to the end ($)
        match = pattern.match(normalized_duration)

        # Check if the pattern matched the entire string and captured at least one group
        if match and match.group(0): # match.group(0) contains the entire matched string
            # Extract captured values into a dictionary, converting non-None values to integers
            time_parameters = {
                key: int(value) for key, value in match.groupdict().items() if value is not None
            }
            # If the dictionary is not empty (at least one time component was found)
            if time_parameters:
                # Create and return a timedelta object using the extracted parameters
                return timedelta(**time_parameters)

        # If the pattern did not match, or matched but captured no values, raise a validation error
        raise ValidationError(
            _("Неверный формат времени. Используйте комбинацию 'Xd Yh Zm' (или 'Xд Yч Zм'). Примеры: '1d 2h 30m', '2ч', '45м'."),
            code='invalid_timedelta_format' # Provide an error code for potential frontend use
        )

    def clean(self):
        """
        Performs cross-field validation after individual field cleaning.
        - Validates the relationship between Category and Subcategory.
        - Validates User Roles (e.g., Responsible cannot be Executor or Watcher).
        """
        # Get the dictionary of cleaned data from the parent class's clean method
        cleaned_data = super().clean()

        # --- Validate Category/Subcategory Relationship ---
        category = cleaned_data.get("category")
        subcategory = cleaned_data.get("subcategory")

        if subcategory and not category:
            # Raise an error if a subcategory is selected but no parent category is chosen
            self.add_error('subcategory', ValidationError(_("Нельзя выбрать подкатегорию без выбора родительской категории.")))
            # Optionally add error to category field as well for clarity
            # self.add_error('category', ValidationError(_("Необходимо выбрать категорию для выбранной подкатегории.")))
        elif subcategory and category and subcategory.category != category:
            # Raise an error if the selected subcategory does not belong to the selected category
            # This prevents data inconsistency if the JS logic fails or is bypassed
            self.add_error('subcategory', ValidationError(_("Выбранная подкатегория не принадлежит выбранной категории.")))

        # --- Validate User Roles (Only if User Model is Available) ---
        if User:
            responsible = cleaned_data.get("responsible_user")
            # Get QuerySets for executors/watchers, default to empty QuerySet if None/empty
            executors = cleaned_data.get("executors") or User.objects.none()
            watchers = cleaned_data.get("watchers") or User.objects.none()

            # Check if a responsible user was selected
            if responsible:
                # Check if the responsible user is also listed as an executor
                # Ensure 'executors' is iterable (it should be a QuerySet here)
                if hasattr(executors, '__iter__') and responsible in executors:
                    self.add_error('executors', ValidationError(_("Ответственный пользователь не может быть одновременно исполнителем.")))
                    # Add error to responsible_user field as well for better feedback
                    self.add_error('responsible_user', ValidationError(_("Этот пользователь не может быть одновременно исполнителем.")))

                # Check if the responsible user is also listed as a watcher
                if hasattr(watchers, '__iter__') and responsible in watchers:
                    self.add_error('watchers', ValidationError(_("Ответственный пользователь не может быть одновременно наблюдателем.")))
                    self.add_error('responsible_user', ValidationError(_("Этот пользователь не может быть одновременно наблюдателем.")))

        # Always return the full cleaned_data dictionary
        return cleaned_data

    @transaction.atomic # Decorator ensures all database operations within save() are atomic
    def save(self, commit=True):
        """
        Saves the Task instance and synchronizes the associated TaskUserRole records.
        Uses bulk operations for efficiency when updating roles.
        """
        # Call the parent save method with commit=False to get the model instance
        # without saving it to the database immediately.
        task_instance = super().save(commit=False)

        # --- Assign Creator ---
        # If this is a new task (no primary key yet) and a request user was provided
        if not task_instance.pk and self.request_user:
             # Check if the task instance has a 'created_by' field
            if hasattr(task_instance, 'created_by'):
                # Assign the request user as the creator only if 'created_by' is not already set
                # (e.g., avoids overriding values set by signals or other pre-save logic)
                if not task_instance.created_by_id: # Check _id field to avoid unnecessary user object fetch
                    task_instance.created_by = self.request_user
            else:
                logger.warning(f"Task model does not have a 'created_by' attribute. Cannot assign creator.")


        # --- Commit Changes (if commit=True) ---
        if commit:
            # Save the Task instance itself to the database
            task_instance.save()
            self.save_m2m() # Important for ModelForms with M2M fields if defined in Meta

            # --- Update User Roles (Conditional on Model Availability) ---
            # Proceed only if TaskUserRole and User models were successfully imported
            if TaskUserRole and User:
                # Get the selected users/QuerySets from the validated form data
                responsible_user_instance = self.cleaned_data.get('responsible_user')
                executor_queryset = self.cleaned_data.get('executors') or User.objects.none()
                watcher_queryset = self.cleaned_data.get('watchers') or User.objects.none()

                # --- Efficient Role Synchronization Logic ---
                # 1. Get current roles for this task as a dictionary: {user_id: TaskUserRole_instance}
                current_user_role_map = {
                    user_role.user_id: user_role
                    for user_role in TaskUserRole.objects.filter(task=task_instance)
                }

                # 2. Prepare lists for bulk database operations
                new_roles_to_create = [] # Roles to be created
                roles_to_update = []     # Roles whose 'role' needs updating
                # Keep track of users whose roles have been determined in this save operation
                processed_user_ids = set()

                # 3. Process the selected Responsible User
                if responsible_user_instance:
                    user_id = responsible_user_instance.id
                    processed_user_ids.add(user_id) # Mark this user as processed
                    # Check if this user already has a role in the task
                    if user_id in current_user_role_map:
                        # Yes, get the existing role instance and remove it from the map
                        # (so it won't be deleted later)
                        existing_role = current_user_role_map.pop(user_id)
                        # If the existing role is not 'RESPONSIBLE', update it
                        if existing_role.role != TaskUserRole.RoleChoices.RESPONSIBLE:
                            existing_role.role = TaskUserRole.RoleChoices.RESPONSIBLE
                            roles_to_update.append(existing_role) # Add to bulk update list
                    else:
                        # No existing role, create a new 'RESPONSIBLE' role
                        new_roles_to_create.append(
                            TaskUserRole(task=task_instance, user=responsible_user_instance, role=TaskUserRole.RoleChoices.RESPONSIBLE)
                        )

                # 4. Process selected Executors (excluding the responsible user)
                executor_ids = set(executor_queryset.values_list('id', flat=True))
                # Remove the responsible user's ID if they were accidentally included
                if responsible_user_instance:
                     executor_ids.discard(responsible_user_instance.id)

                for user_id in executor_ids:
                     # Process only if not already handled (e.g., as responsible)
                     if user_id not in processed_user_ids:
                        processed_user_ids.add(user_id)
                        if user_id in current_user_role_map:
                            # Existing role found, update if necessary
                            existing_role = current_user_role_map.pop(user_id)
                            if existing_role.role != TaskUserRole.RoleChoices.EXECUTOR:
                                existing_role.role = TaskUserRole.RoleChoices.EXECUTOR
                                roles_to_update.append(existing_role)
                        else:
                            # New executor role needed, fetch User instance safely
                            try:
                                executor_user_instance = User.objects.get(pk=user_id)
                                new_roles_to_create.append(
                                    TaskUserRole(task=task_instance, user=executor_user_instance, role=TaskUserRole.RoleChoices.EXECUTOR)
                                )
                            except User.DoesNotExist:
                                logger.warning(f"User ID {user_id} selected as executor for task '{task_instance.title}' (ID: {task_instance.id}) not found.")

                # 5. Process selected Watchers (excluding Responsible and Executors)
                watcher_ids = set(watcher_queryset.values_list('id', flat=True))
                # Remove responsible user and anyone already assigned as an executor
                if responsible_user_instance:
                    watcher_ids.discard(responsible_user_instance.id)
                watcher_ids -= executor_ids # Set difference removes executor IDs

                for user_id in watcher_ids:
                    # Process only if not already handled
                    if user_id not in processed_user_ids:
                        processed_user_ids.add(user_id)
                        if user_id in current_user_role_map:
                            # Existing role found, update if necessary
                            existing_role = current_user_role_map.pop(user_id)
                            if existing_role.role != TaskUserRole.RoleChoices.WATCHER:
                                existing_role.role = TaskUserRole.RoleChoices.WATCHER
                                roles_to_update.append(existing_role)
                        else:
                            # New watcher role needed, fetch User instance safely
                            try:
                                watcher_user_instance = User.objects.get(pk=user_id)
                                new_roles_to_create.append(
                                    TaskUserRole(task=task_instance, user=watcher_user_instance, role=TaskUserRole.RoleChoices.WATCHER)
                                )
                            except User.DoesNotExist:
                                logger.warning(f"User ID {user_id} selected as watcher for task '{task_instance.title}' (ID: {task_instance.id}) not found.")

                # --- Perform Bulk Database Operations ---
                # Bulk Create: Efficiently insert all new roles
                if new_roles_to_create:
                    # ignore_conflicts=True prevents errors if a role somehow already exists (unlikely with this logic but safe)
                    TaskUserRole.objects.bulk_create(new_roles_to_create, ignore_conflicts=True)
                    logger.info(f"Bulk created/ignored {len(new_roles_to_create)} roles for Task ID {task_instance.id}")

                # Bulk Update: Efficiently update roles that changed type
                if roles_to_update:
                    # Specify the fields to update ('role' in this case)
                    TaskUserRole.objects.bulk_update(roles_to_update, ['role'])
                    logger.info(f"Bulk updated {len(roles_to_update)} roles for Task ID {task_instance.id}")

                # Delete Obsolete Roles: Remove roles for users no longer associated in any capacity
                # Any roles remaining in 'current_user_role_map' at this point are obsolete
                roles_to_delete_pks = [role.pk for role in current_user_role_map.values()]
                if roles_to_delete_pks:
                    # Delete roles by their primary keys
                    deleted_count, deleted_details = TaskUserRole.objects.filter(pk__in=roles_to_delete_pks).delete()
                    logger.info(f"Deleted {deleted_count} obsolete roles for Task ID {task_instance.id}. Details: {deleted_details}")

            else:
                 # Log a warning if roles couldn't be updated due to missing models
                 logger.warning("TaskUserRole or User model not available. Skipping user role synchronization during task save.")

        # Return the saved Task instance
        return task_instance


# ============================================================================== #
# Task Photo Form
# ============================================================================== #
class TaskPhotoForm(forms.ModelForm):
    """
    Form for uploading and describing photos associated with a Task.
    Designed to be used within a formset.
    """
    class Meta:
        model = TaskPhoto
        fields = ["photo", "description"] # Fields included in the form
        widgets = {
            # Use ClearableFileInput for easy replacement/clearing of the photo
            "photo": forms.ClearableFileInput(attrs={
                "class": FILE_INPUT_CLASSES, # Apply file input styling
                'accept': 'image/jpeg, image/png, image/gif, image/webp, image/avif' # Specify accepted image types
            }),
            "description": forms.Textarea(attrs={
                "rows": 2, # Suggest a smaller text area
                'class': TEXTAREA_CLASSES,
                'placeholder': _('Краткое описание фото (необязательно)')
            }),
        }
        labels = {
            "photo": _("Файл фото"), # User-friendly label
            "description": _("Описание фото")
        }
        help_texts = {
            "photo": _("Загрузите изображение (форматы: JPG, PNG, GIF, WebP, AVIF).")
        }


# ============================================================================== #
# Task Comment Form
# ============================================================================== #
class TaskCommentForm(forms.ModelForm):
    """
    Simple form for adding text comments to a Task.
    """
    class Meta:
        model = TaskComment
        fields = ["text"] # Only include the text field
        widgets = {
            "text": forms.Textarea(attrs={
                "rows": 3, # Suggest 3 rows for the comment box
                "placeholder": _("Введите ваш комментарий здесь..."),
                "class": TEXTAREA_CLASSES, # Apply standard textarea styling
                "aria-label": _("Текст комментария") # Enhance accessibility
            }),
        }
        # Hide the label visually if the placeholder provides enough context,
        # but keep it for screen readers unless an aria-label is used.
        labels = { "text": "" } # Empty label string hides it