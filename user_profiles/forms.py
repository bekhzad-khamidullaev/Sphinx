# user_profiles/forms.py
import logging
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Fieldset, Row, Field, Div, Column # Added Column
from django import forms
from django.contrib.auth.models import Group
from django.contrib.auth.forms import (
    AuthenticationForm, UserCreationForm as BaseUserCreationForm, PasswordChangeForm as BasePasswordChangeForm
)
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django_select2.forms import Select2Widget, Select2MultipleWidget # For Select2

from .models import User, Team, Department, JobTitle

logger = logging.getLogger(__name__)

# --- Tailwind CSS classes ---
BASE_INPUT_CLASSES = "block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm dark:bg-dark-700 dark:border-dark-600 dark:text-gray-200 dark:placeholder-gray-500 transition duration-150 ease-in-out"
TEXT_INPUT_CLASSES = f"form-input {BASE_INPUT_CLASSES}"
TEXTAREA_CLASSES = f"form-textarea {BASE_INPUT_CLASSES}"
SELECT_CLASSES = f"form-select {BASE_INPUT_CLASSES}" # Base for non-Select2 selects
CHECKBOX_CLASSES = "form-checkbox h-5 w-5 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500 dark:bg-dark-600 dark:border-dark-500 dark:checked:bg-indigo-500 dark:focus:ring-offset-dark-800"
FILE_INPUT_CLASSES = "form-control block w-full text-sm text-gray-900 border border-gray-300 rounded-lg cursor-pointer bg-gray-50 dark:text-gray-400 focus:outline-none dark:bg-dark-600 dark:border-dark-500 dark:placeholder-gray-400 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 dark:file:bg-dark-500 dark:file:text-gray-300 dark:hover:file:bg-dark-400 transition"


class TeamForm(forms.ModelForm):
    members = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        widget=Select2MultipleWidget(attrs={'data-placeholder': _("Выберите участников...")}),
        required=False, label=_("Участники")
    )
    team_leader = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        required=False,
        widget=Select2Widget(attrs={'data-placeholder': _("Выберите лидера...")}),
        label=_("Лидер команды")
    )
    department = forms.ModelChoiceField(
        queryset=Department.objects.all().order_by('name'),
        required=False,
        widget=Select2Widget(attrs={'data-placeholder': _("Выберите отдел...")}),
        label=_("Отдел")
    )

    class Meta:
        model = Team
        fields = ["name", "description", "team_leader", "department", "members"]
        widgets = {
            'name': forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _("Название команды")}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': TEXTAREA_CLASSES, 'placeholder': _("Описание команды (опционально)")}),
        }
        labels = {
            "name": _("Название команды"),
            "description": _("Описание"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_method = 'post'
        self.helper.form_tag = False
        self.helper.disable_csrf = True
        self.helper.layout = Layout(
            Field('name', css_class="mb-4"),
            Field('description', css_class="mb-4"),
            Field('team_leader', css_class="mb-4"),
            Field('department', css_class="mb-4"),
            Field('members', css_class="mb-4"),
        )

class DepartmentForm(forms.ModelForm):
    head = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        required=False,
        widget=Select2Widget(attrs={'data-placeholder': _("Выберите руководителя...")}),
        label=_("Руководитель отдела")
    )
    parent = forms.ModelChoiceField(
        queryset=Department.objects.all().order_by('name'), # Exclude self if editing
        required=False,
        widget=Select2Widget(attrs={'data-placeholder': _("Выберите вышестоящий отдел...")}),
        label=_("Вышестоящий отдел")
    )
    class Meta:
        model = Department
        fields = ['name', 'description', 'parent', 'head']
        widgets = {
            'name': forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _("Название отдела")}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': TEXTAREA_CLASSES, 'placeholder': _("Описание (опционально)")}),
        }
        labels = {
            "name": _("Название отдела"),
            "description": _("Описание"),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk: # For editing, exclude self from parent choices
            self.fields['parent'].queryset = Department.objects.exclude(pk=self.instance.pk).order_by('name')
        
        self.helper = FormHelper(self)
        self.helper.form_method = 'post'; self.helper.form_tag = False; self.helper.disable_csrf = True
        self.helper.layout = Layout(
            Field('name', css_class="mb-4"),
            Field('description', css_class="mb-4"),
            Field('parent', css_class="mb-4"),
            Field('head', css_class="mb-4"),
        )

class JobTitleForm(forms.ModelForm):
    class Meta:
        model = JobTitle
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _("Название должности")}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': TEXTAREA_CLASSES, 'placeholder': _("Описание (опционально)")}),
        }
        labels = {
            "name": _("Название должности"),
            "description": _("Описание"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_method = 'post'; self.helper.form_tag = False; self.helper.disable_csrf = True
        self.helper.layout = Layout(
            Field('name', css_class="mb-4"),
            Field('description', css_class="mb-4"),
        )


class UserCreateForm(BaseUserCreationForm):
    email = forms.EmailField(required=True, label=_("Email"), widget=forms.EmailInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': 'your@email.com'}))
    first_name = forms.CharField(max_length=150, required=False, label=_("Имя"), widget=forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES}))
    last_name = forms.CharField(max_length=150, required=False, label=_("Фамилия"), widget=forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES}))
    phone_number = forms.CharField(max_length=25, required=False, label=_("Номер телефона"), widget=forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES}))
    job_title = forms.ModelChoiceField(
        queryset=JobTitle.objects.all().order_by('name'), required=False, label=_("Должность"),
        widget=Select2Widget(attrs={'data-placeholder': _("Выберите должность...")})
    )
    department = forms.ModelChoiceField(
        queryset=Department.objects.all().order_by('name'), required=False, label=_("Отдел"),
        widget=Select2Widget(attrs={'data-placeholder': _("Выберите отдел...")})
    )
    image = forms.ImageField(required=False, label=_("Аватар"), widget=forms.ClearableFileInput(attrs={'class': FILE_INPUT_CLASSES}))

    class Meta(BaseUserCreationForm.Meta):
        model = User
        fields = BaseUserCreationForm.Meta.fields + ( # username, password1, password2 are from base
            'email', 'first_name', 'last_name', 'phone_number',
            'job_title', 'department', 'image'
        )
        # Widgets for username, password1, password2 are customized below

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({'class': TEXT_INPUT_CLASSES, 'placeholder': _("Логин")})
        self.fields['password2'].help_text = None # Remove default help_text for password confirmation
        for field_name in ['password1', 'password2']:
            self.fields[field_name].widget.attrs.update({'class': TEXT_INPUT_CLASSES, 'placeholder': _("Пароль") if field_name == 'password1' else _("Повторите пароль")})
        
        self.helper = FormHelper(self)
        self.helper.form_method = 'post'
        self.helper.form_tag = False
        self.helper.disable_csrf = True
        self.helper.layout = Layout(
            Fieldset(_("Учетные данные"),
                Field("username"), Field("email"), Field("password1"), Field("password2"),
                css_class="mb-6 pb-6 border-b border-gray-200 dark:border-dark-600"
            ),
            Fieldset(_("Личная информация"),
                Row(Column(Field("first_name"), css_class="md:w-1/2 px-2"), Column(Field("last_name"), css_class="md:w-1/2 px-2"), css_class="flex flex-wrap -mx-2 mb-4"),
                Field("phone_number", css_class="mb-4"),
                css_class="mb-6 pb-6 border-b border-gray-200 dark:border-dark-600"
            ),
            Fieldset(_("Рабочая информация"),
                Field("job_title", css_class="mb-4"), Field("department", css_class="mb-4"),
                css_class="mb-6 pb-6 border-b border-gray-200 dark:border-dark-600"
            ),
            Fieldset(_("Аватар"), Field("image"))
        )

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and User.objects.filter(email__iexact=email).exists():
            raise ValidationError(_("Пользователь с таким email уже существует."))
        return email


class UserUpdateForm(forms.ModelForm):
    email = forms.EmailField(required=True, label=_("Email"), widget=forms.EmailInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': 'your@email.com'}))
    first_name = forms.CharField(max_length=150, required=False, label=_("Имя"), widget=forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES}))
    last_name = forms.CharField(max_length=150, required=False, label=_("Фамилия"), widget=forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES}))
    phone_number = forms.CharField(max_length=25, required=False, label=_("Номер телефона"), widget=forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES}))
    job_title = forms.ModelChoiceField(
        queryset=JobTitle.objects.all().order_by('name'), required=False, label=_("Должность"),
        widget=Select2Widget(attrs={'data-placeholder': _("Выберите должность...")})
    )
    department = forms.ModelChoiceField(
        queryset=Department.objects.all().order_by('name'), required=False, label=_("Отдел"),
        widget=Select2Widget(attrs={'data-placeholder': _("Выберите отдел...")})
    )
    image = forms.ImageField(required=False, label=_("Аватар"), widget=forms.ClearableFileInput(attrs={'class': FILE_INPUT_CLASSES}))
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all().order_by('name'), required=False,
        widget=Select2MultipleWidget(attrs={'data-placeholder': _("Выберите группы...")}), label=_("Группы прав")
    )
    is_active = forms.BooleanField(required=False, label=_("Активен"), widget=forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}))
    is_staff = forms.BooleanField(required=False, label=_("Сотрудник (доступ в админку)"), widget=forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}))


    class Meta:
        model = User
        fields = [
            'username', 'email', 'first_name', 'last_name', 'phone_number',
            'job_title', 'department', 'image', 'is_active', 'is_staff', 'groups'
        ]
        widgets = { # For fields not explicitly defined above
            'username': forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _("Логин (нельзя изменить)")}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['username'].disabled = True # Username usually not changed after creation

        self.helper = FormHelper(self)
        self.helper.form_method = 'post'; self.helper.form_tag = False; self.helper.disable_csrf = True
        self.helper.layout = Layout(
            Fieldset(_("Учетные данные (только просмотр)"),
                Field("username"), css_class="mb-6 pb-6 border-b border-gray-200 dark:border-dark-600"
            ),
            Fieldset(_("Контактная и личная информация"),
                Field("email"),
                Row(Column(Field("first_name"), css_class="md:w-1/2 px-2"), Column(Field("last_name"), css_class="md:w-1/2 px-2"), css_class="flex flex-wrap -mx-2 mb-4"),
                Field("phone_number", css_class="mb-4"),
                css_class="mb-6 pb-6 border-b border-gray-200 dark:border-dark-600"
            ),
            Fieldset(_("Рабочая информация"),
                Field("job_title", css_class="mb-4"), Field("department", css_class="mb-4"),
                css_class="mb-6 pb-6 border-b border-gray-200 dark:border-dark-600"
            ),
            Fieldset(_("Аватар"), Field("image"), css_class="mb-6 pb-6 border-b border-gray-200 dark:border-dark-600"),
            Fieldset(_("Права и статус"),
                Div(Field("is_active"), css_class="mb-3"), Div(Field("is_staff"), css_class="mb-4"),
                Field("groups")
            )
        )

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and self.instance and self.instance.pk:
            if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
                 raise ValidationError(_("Пользователь с таким email уже существует."))
        return email


class UserProfileEditForm(forms.ModelForm): # For user to edit their own profile
    first_name = forms.CharField(max_length=150, required=False, label=_("Имя"), widget=forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES}))
    last_name = forms.CharField(max_length=150, required=False, label=_("Фамилия"), widget=forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES}))
    phone_number = forms.CharField(max_length=25, required=False, label=_("Номер телефона"), widget=forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES}))
    image = forms.ImageField(required=False, label=_("Аватар"), widget=forms.ClearableFileInput(attrs={'class': FILE_INPUT_CLASSES}))
    
    # Settings fields (not directly on User model, handled in save method)
    enable_email_notifications = forms.BooleanField(required=False, label=_("Получать уведомления по Email"), widget=forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}))
    tasks_per_page = forms.IntegerField(
        required=False, label=_("Задач на странице по умолчанию"), min_value=5, max_value=100,
        widget=forms.NumberInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': '15'}), help_text=_("От 5 до 100")
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'phone_number', 'image']
        # JobTitle and Department are usually set by admin, not by user themselves in basic profile edit.
        # If they should be editable by user, add them here and to layout.

    def __init__(self, *args, **kwargs):
        user_instance = kwargs.get('instance')
        initial_data = kwargs.get('initial', {})
        if user_instance and isinstance(user_instance.settings, dict):
            initial_data['enable_email_notifications'] = user_instance.settings.get('enable_email_notifications', True)
            initial_data['tasks_per_page'] = user_instance.settings.get('tasks_per_page', 15)
        else:
            initial_data.setdefault('enable_email_notifications', True)
            initial_data.setdefault('tasks_per_page', 15)
        kwargs['initial'] = initial_data

        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_method = 'post'; self.helper.form_tag = False; self.helper.disable_csrf = True
        self.helper.layout = Layout(
             Fieldset(_("Личная информация"),
                 Row(Column(Field("first_name"), css_class="md:w-1/2 px-2"), Column(Field("last_name"), css_class="md:w-1/2 px-2"), css_class="flex flex-wrap -mx-2 mb-4"),
                 Field("phone_number", css_class="mb-4"),
                 css_class="mb-6 pb-6 border-b border-gray-200 dark:border-dark-600"
             ),
             Fieldset(_("Аватар"), Field("image"), css_class="mb-6 pb-6 border-b border-gray-200 dark:border-dark-600"),
             Fieldset(_("Настройки уведомлений и интерфейса"),
                 Div(Field('enable_email_notifications'), css_class='mb-3'),
                 Div(Field('tasks_per_page', css_class="w-full sm:w-1/3"), css_class='mb-3'),
             )
        )

    def save(self, commit=True):
        user = super().save(commit=False)
        settings_changed = False
        if not isinstance(user.settings, dict): user.settings = {}

        if 'enable_email_notifications' in self.cleaned_data:
            new_val = self.cleaned_data['enable_email_notifications']
            if user.settings.get('enable_email_notifications', True) != new_val:
                user.settings['enable_email_notifications'] = new_val
                settings_changed = True
        
        if 'tasks_per_page' in self.cleaned_data:
            new_val = self.cleaned_data.get('tasks_per_page')
            if new_val is not None and user.settings.get('tasks_per_page') != new_val:
                user.settings['tasks_per_page'] = new_val
                settings_changed = True
            elif new_val is None and 'tasks_per_page' in user.settings:
                 del user.settings['tasks_per_page']
                 settings_changed = True

        if commit:
            model_fields_to_update = [field for field in self.changed_data if field in self.Meta.fields]
            if settings_changed and 'settings' not in model_fields_to_update:
                 model_fields_to_update.append('settings')
            if model_fields_to_update:
                 user.save(update_fields=model_fields_to_update)
            # else: no changes to save
        return user


class LoginForm(AuthenticationForm):
    username = forms.CharField(label=_("Имя пользователя или Email"), widget=forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _('Логин или Email'), 'autofocus': True}))
    password = forms.CharField(label=_("Пароль"), widget=forms.PasswordInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _('Пароль')}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False # Form tag is in template
        self.helper.disable_csrf = True # CSRF token in template
        self.helper.layout = Layout(
            Field("username", css_class="mb-4"),
            Field("password", css_class="mb-4"),
        )

class UserPasswordChangeForm(BasePasswordChangeForm):
    old_password = forms.CharField(label=_("Старый пароль"), widget=forms.PasswordInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _("Введите старый пароль"), 'autofocus': True}))
    new_password1 = forms.CharField(label=_("Новый пароль"), widget=forms.PasswordInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _("Введите новый пароль")}))
    new_password2 = forms.CharField(label=_("Подтверждение нового пароля"), widget=forms.PasswordInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _("Повторите новый пароль")}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['new_password2'].help_text = None # Remove default help text
        self.helper = FormHelper(self)
        self.helper.form_method = 'post'; self.helper.form_tag = False; self.helper.disable_csrf = True
        self.helper.layout = Layout(
            Field("old_password", css_class="mb-4"),
            Field("new_password1", css_class="mb-4"),
            Field("new_password2", css_class="mb-4"),
        )