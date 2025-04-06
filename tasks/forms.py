import logging
import re
from datetime import timedelta

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Fieldset, Row, Field, HTML
from django_select2.forms import Select2Widget, Select2MultipleWidget

from .models import Task, TaskPhoto, Project, TaskCategory, TaskSubcategory, TaskComment
from user_profiles.models import User, TaskUserRole

logger = logging.getLogger(__name__)

# --- Utility function ---
def add_common_attrs(field, placeholder=None, input_class="form-control"):
    """Adds classes and placeholder to form fields."""
    attrs = field.widget.attrs
    current_classes = attrs.get('class', '')
    if input_class not in current_classes.split():
        attrs['class'] = f'{current_classes} {input_class}'.strip()
    if placeholder:
        attrs.setdefault("placeholder", placeholder)
    field.widget.attrs.update(attrs)


# ============================================================================== #
# Project Form
# ============================================================================== #
class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ["name", "description", "start_date", "end_date"]
        widgets = {
            "name": forms.TextInput(),
            "description": forms.Textarea(attrs={'rows': 4}),
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            add_common_attrs(field)

        self.helper = FormHelper(self)
        self.helper.form_method = 'post'
        self.helper.form_tag = False
        self.helper.disable_csrf = True
        self.helper.layout = Layout(
            Field("name", css_class="mb-3"),
            Field("description", css_class="mb-3"),
            Row(
                Field("start_date", wrapper_class="col-md-6"),
                Field("end_date", wrapper_class="col-md-6"),
                css_class="mb-3"
            ),
        )


# ============================================================================== #
# Task Category Form
# ============================================================================== #
class TaskCategoryForm(forms.ModelForm):
    class Meta:
        model = TaskCategory
        fields = ["name", "description"]
        widgets = {
            "name": forms.TextInput(),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            add_common_attrs(field)


# ============================================================================== #
# Task Subcategory Form
# ============================================================================== #
class TaskSubcategoryForm(forms.ModelForm):
    category = forms.ModelChoiceField(
        queryset=TaskCategory.objects.all().order_by("name"),
        widget=Select2Widget(attrs={'data-placeholder': _("Выберите категорию...")})
    )

    class Meta:
        model = TaskSubcategory
        fields = ["category", "name", "description"]
        widgets = {
            "name": forms.TextInput(),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            add_common_attrs(field)


# ============================================================================== #
# Task Form
# ============================================================================== #
class TaskForm(forms.ModelForm):
    title = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'block w-full px-4 py-2 border border-gray-300 rounded-lg shadow-sm focus:ring focus:ring-blue-500 focus:outline-none',
            'placeholder': 'Введите название задачи'
        })
    )
    description = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'block w-full px-4 py-2 border border-gray-300 rounded-lg shadow-sm focus:ring focus:ring-blue-500 focus:outline-none',
            'placeholder': 'Введите описание'
        })
    )
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'block w-full px-4 py-2 border border-gray-300 rounded-lg shadow-sm focus:ring focus:ring-blue-500 focus:outline-none flatpickr',
            'placeholder': 'Выберите дату'
        })
    )
    deadline = forms.DateTimeField(
        widget=forms.TextInput(attrs={
            'class': 'flatpickr block w-full px-4 py-2 border border-gray-300 rounded-lg shadow-sm focus:ring focus:ring-blue-500 focus:outline-none',
            'placeholder': 'Выберите дату и время'
        })
    )
    project = forms.ModelChoiceField(queryset=Project.objects.all().order_by("name"), widget=Select2Widget())
    category = forms.ModelChoiceField(
        queryset=TaskCategory.objects.all().order_by("name"),
        required=False,
        widget=Select2Widget(attrs={'id': 'id_task_category'})
    )
    subcategory = forms.ModelChoiceField(
        queryset=TaskSubcategory.objects.none(),
        required=False,
        widget=Select2Widget(attrs={'id': 'id_task_subcategory', 'disabled': True})
    )

    priority = forms.ChoiceField(
        choices=[('low', 'Низкий'), ('medium', 'Средний'), ('high', 'Высокий')],
        widget=forms.Select(attrs={
            'class': 'block w-full px-4 py-2 border border-gray-300 rounded-lg shadow-sm focus:ring focus:ring-blue-500 focus:outline-none'
        })
    )
    responsible_user = forms.ModelChoiceField(queryset=User.objects.filter(is_active=True), widget=Select2Widget())
    executors = forms.ModelMultipleChoiceField(queryset=User.objects.filter(is_active=True), widget=Select2MultipleWidget())
    watchers = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(is_active=True),
        required=False,
        widget=Select2MultipleWidget()
    )

    class Meta:
        model = Task
        fields = ["title", "description", "deadline", "start_date", "estimated_time"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "estimated_time": forms.TextInput(attrs={'placeholder': _('Напр., 1d 2h 30m или 45m')}),
        }

    def __init__(self, *args, **kwargs):
        instance = kwargs.get("instance")
        initial_data = kwargs.get("initial", {})

        if instance:
            roles_data = TaskUserRole.objects.filter(task=instance).values_list("user_id", "role")
            role_dict = {role: user_id for user_id, role in roles_data}

            initial_data.update({
                "responsible_user": role_dict.get(TaskUserRole.RoleChoices.RESPONSIBLE),
                "executors": [uid for uid, role in roles_data if role == TaskUserRole.RoleChoices.EXECUTOR],
                "watchers": [uid for uid, role in roles_data if role == TaskUserRole.RoleChoices.WATCHER],
            })
            kwargs["initial"] = initial_data

        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            add_common_attrs(field)

    def clean_estimated_time(self):
        """Handles and validates the time input by the user."""
        duration_str = self.cleaned_data.get("estimated_time")

        if not duration_str:
            return None

        pattern = re.compile(r"((?P<days>\d+)d)?\s*((?P<hours>\d+)h)?\s*((?P<minutes>\d+)m)?")
        match = pattern.fullmatch(duration_str.lower().strip())

        if match:
            time_params = {k: int(v) for k, v in match.groupdict().items() if v}
            return timedelta(**time_params)

        raise ValidationError(_("Формат: '1d 2h 30m', '2h', '45m'."))


# ============================================================================== #
# Task Photo Form
# ============================================================================== #
class TaskPhotoForm(forms.ModelForm):
    class Meta:
        model = TaskPhoto
        fields = ["photo", "description"]
        widgets = {
            "photo": forms.ClearableFileInput(attrs={"class": "dropzone"}),
            "description": forms.Textarea(attrs={"rows": 2}),
        }


# ============================================================================== #
# Task Comment Form
# ============================================================================== #
class TaskCommentForm(forms.ModelForm):
    class Meta:
        model = TaskComment
        fields = ["text"]
        widgets = {
            "text": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": _("Введите ваш комментарий..."),
            }),
        }
