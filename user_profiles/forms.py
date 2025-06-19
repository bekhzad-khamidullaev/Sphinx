# user_profiles/forms.py
import logging
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Fieldset, Row, Field, Div, Column
from django import forms
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.forms import (
    AuthenticationForm, UserCreationForm as BaseUserCreationForm, PasswordChangeForm as BasePasswordChangeForm
)
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django_select2.forms import Select2Widget, Select2MultipleWidget

from .models import User, Team, Department, JobTitle

logger = logging.getLogger(__name__)

BASE_INPUT_CLASSES = "block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm transition duration-150 ease-in-out"
TEXT_INPUT_CLASSES = f"form-input {BASE_INPUT_CLASSES}"
TEXTAREA_CLASSES = f"form-textarea {BASE_INPUT_CLASSES}"
SELECT_CLASSES = f"form-select {BASE_INPUT_CLASSES}"
CHECKBOX_CLASSES = "form-checkbox h-5 w-5 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500"
FILE_INPUT_CLASSES = "form-control block w-full text-sm text-gray-900 border border-gray-300 rounded-lg cursor-pointer bg-gray-50 focus:outline-none file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 transition"


class TeamForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ["name", "description", "team_leader", "department", "members"]
        widgets = {
            'name': forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _("Название команды")}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': TEXTAREA_CLASSES, 'placeholder': _("Описание команды (опционально)")}),
            'team_leader': Select2Widget(attrs={'data-placeholder': _("Выберите лидера...")}),
            'department': Select2Widget(attrs={'data-placeholder': _("Выберите отдел...")}),
            'members': Select2MultipleWidget(attrs={'data-placeholder': _("Выберите участников...")}),
        }
        labels = {
            "name": _("Название команды"),
            "description": _("Описание"),
            "team_leader": _("Лидер команды"),
            "department": _("Отдел"),
            "members": _("Участники")
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'team_leader' in self.fields:
            self.fields['team_leader'].queryset = User.objects.filter(is_active=True).order_by('username')
            self.fields['team_leader'].required = False
        if 'department' in self.fields:
            self.fields['department'].queryset = Department.objects.all().order_by('name')
            self.fields['department'].required = False
        if 'members' in self.fields:
            self.fields['members'].queryset = User.objects.filter(is_active=True).order_by('username')
            self.fields['members'].required = False


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
        queryset=Department.objects.all().order_by('name'),
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
        if self.instance and self.instance.pk:
            self.fields['parent'].queryset = Department.objects.exclude(pk=self.instance.pk).order_by('name')

        self.helper = FormHelper(self)
        self.helper.form_method = 'post'; self.helper.form_tag = False; self.helper.disable_csrf = True
        self.helper.layout = Layout(
            Field('name', css_class="mb-4"),
            Field('description', css_class="mb-4"),
            Field('parent', css_class="mb-4"),
            Field('head', css_class="mb-4"),
        )

    def clean_parent(self):
        parent = self.cleaned_data.get('parent')
        if parent and self.instance and self.instance.pk and parent.pk == self.instance.pk:
            raise ValidationError(_("Отдел не может быть сам себе родительским."))
        if parent and self.instance and self.instance.pk:
            p = parent
            while p:
                if p.pk == self.instance.pk:
                    raise ValidationError(_("Обнаружена циклическая зависимость в родительских отделах."))
                p = p.parent
        return parent


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


class GroupForm(forms.ModelForm):
    permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.all().order_by('content_type__app_label', 'codename'),
        required=False,
        widget=Select2MultipleWidget(attrs={'data-placeholder': _("Выберите разрешения...")}),
        label=_("Разрешения")
    )

    class Meta:
        model = Group
        fields = ["name", "permissions"]
        widgets = {
            'name': forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _("Название группы")}),
        }
        labels = {
            'name': _("Название группы"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_method = 'post'
        self.helper.form_tag = False
        self.helper.disable_csrf = True
        self.helper.layout = Layout(
            Field('name', css_class="mb-4"),
            Field('permissions', css_class="mb-4"),
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
        fields = BaseUserCreationForm.Meta.fields + (
            'email', 'first_name', 'last_name', 'phone_number',
            'job_title', 'department', 'image', 'teams', 'groups'
        )
        widgets = {
            'teams': Select2MultipleWidget(attrs={'data-placeholder': _("Выберите команды...")}),
            'groups': Select2MultipleWidget(attrs={'data-placeholder': _("Выберите группы прав...")}),
        }


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({'class': TEXT_INPUT_CLASSES, 'placeholder': _("Логин")})
        self.fields['password2'].help_text = None
        for field_name in ['password1', 'password2']:
            self.fields[field_name].widget.attrs.update({'class': TEXT_INPUT_CLASSES, 'placeholder': _("Пароль") if field_name == 'password1' else _("Повторите пароль")})

        if 'teams' in self.fields:
            self.fields['teams'].required = False
            self.fields['teams'].label = _("Команды")

        if 'groups' in self.fields:
            self.fields['groups'].required = False
            self.fields['groups'].label = _("Группы прав")


        self.helper = FormHelper(self)
        self.helper.form_method = 'post'
        self.helper.form_tag = False
        self.helper.disable_csrf = True
        self.helper.layout = Layout(
            Fieldset(_("Учетные данные"),
                Field("username"), Field("email"), Field("password1"), Field("password2"),
                css_class="mb-6 pb-6 border-b border-gray-200 "
            ),
            Fieldset(_("Личная информация"),
                Row(Column(Field("first_name"), css_class="md:w-1/2 px-2"), Column(Field("last_name"), css_class="md:w-1/2 px-2"), css_class="flex flex-wrap -mx-2 mb-4"),
                Field("phone_number", css_class="mb-4"),
                css_class="mb-6 pb-6 border-b border-gray-200 "
            ),
            Fieldset(_("Рабочая информация и доступ"),
                Field("job_title", css_class="mb-4"), Field("department", css_class="mb-4"),
                Field("teams", css_class="mb-4"),
                Field("groups", css_class="mb-4"),
                css_class="mb-6 pb-6 border-b border-gray-200 "
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
    is_active = forms.BooleanField(required=False, label=_("Активен"), widget=forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}))
    is_staff = forms.BooleanField(required=False, label=_("Сотрудник (доступ в админку)"), widget=forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}))
    is_superuser = forms.BooleanField(required=False, label=_("Суперпользователь"), widget=forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}))


    class Meta:
        model = User
        fields = [
            'username', 'email', 'first_name', 'last_name', 'phone_number',
            'job_title', 'department', 'image', 'is_active', 'is_staff', 'is_superuser',
            'groups', 'teams'
        ]
        widgets = {
            'username': forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _("Логин (нельзя изменить)")}),
            'groups': Select2MultipleWidget(attrs={'data-placeholder': _("Выберите группы...")}),
            'teams': Select2MultipleWidget(attrs={'data-placeholder': _("Выберите команды...")}),
        }

    def __init__(self, *args, **kwargs):
        self.request_user = kwargs.pop('request_user', None)
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            self.fields['username'].disabled = True
        
        if 'groups' in self.fields:
            self.fields['groups'].required = False
            self.fields['groups'].label = _("Группы прав")

        if 'teams' in self.fields:
            self.fields['teams'].required = False
            self.fields['teams'].label = _("Команды")

        if not (self.request_user and self.request_user.is_superuser):
            if 'is_superuser' in self.fields:
                self.fields['is_superuser'].disabled = True
            if self.instance and self.instance.is_superuser and self.instance != self.request_user:
                for field_name in ['is_staff', 'is_active', 'groups', 'teams', 'user_permissions']:
                    if field_name in self.fields:
                        self.fields[field_name].disabled = True


        self.helper = FormHelper(self)
        self.helper.form_method = 'post'; self.helper.form_tag = False; self.helper.disable_csrf = True
        self.helper.layout = Layout(
            Fieldset(_("Учетные данные (только просмотр)"),
                Field("username"), css_class="mb-6 pb-6 border-b border-gray-200 "
            ),
            Fieldset(_("Контактная и личная информация"),
                Field("email"),
                Row(Column(Field("first_name"), css_class="md:w-1/2 px-2"), Column(Field("last_name"), css_class="md:w-1/2 px-2"), css_class="flex flex-wrap -mx-2 mb-4"),
                Field("phone_number", css_class="mb-4"),
                css_class="mb-6 pb-6 border-b border-gray-200 "
            ),
            Fieldset(_("Рабочая информация"),
                Field("job_title", css_class="mb-4"), Field("department", css_class="mb-4"),
                Field("teams", css_class="mb-4"),
                css_class="mb-6 pb-6 border-b border-gray-200 "
            ),
            Fieldset(_("Аватар"), Field("image"), css_class="mb-6 pb-6 border-b border-gray-200 "),
            Fieldset(_("Права и статус"),
                Div(Field("is_active"), css_class="mb-3"),
                Div(Field("is_staff"), css_class="mb-4"),
                Div(Field("is_superuser"), css_class="mb-4"),
                Field("groups")
            )
        )

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and self.instance and self.instance.pk:
            if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
                 raise ValidationError(_("Пользователь с таким email уже существует."))
        return email

    def clean_is_superuser(self):
        is_superuser_val = self.cleaned_data.get('is_superuser')
        
        if 'is_superuser' in self.fields and self.fields['is_superuser'].disabled:
            return self.instance.is_superuser 
            
        if 'is_superuser' in self.cleaned_data and self.instance and self.instance.pk:
            if not is_superuser_val and self.instance.is_superuser:
                if User.objects.filter(is_superuser=True).exclude(pk=self.instance.pk).count() == 0:
                    raise ValidationError(_("Нельзя лишить статуса суперпользователя единственного суперпользователя в системе."))
        return is_superuser_val


class UserProfileEditForm(forms.ModelForm):
    first_name = forms.CharField(max_length=150, required=False, label=_("Имя"), widget=forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES}))
    last_name = forms.CharField(max_length=150, required=False, label=_("Фамилия"), widget=forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES}))
    phone_number = forms.CharField(max_length=25, required=False, label=_("Номер телефона"), widget=forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES}))
    image = forms.ImageField(required=False, label=_("Аватар"), widget=forms.ClearableFileInput(attrs={'class': FILE_INPUT_CLASSES}))

    enable_email_notifications = forms.BooleanField(required=False, label=_("Получать уведомления по Email"), widget=forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}))
    tasks_per_page = forms.IntegerField(
        required=False, label=_("Задач на странице по умолчанию"), min_value=5, max_value=100,
        widget=forms.NumberInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': '15'}), help_text=_("От 5 до 100")
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'phone_number', 'image']


    def __init__(self, *args, **kwargs):
        user_instance = kwargs.get('instance')
        initial_data = kwargs.get('initial', {})
        if user_instance:
            initial_data['enable_email_notifications'] = user_instance.get_setting('enable_email_notifications', True)
            initial_data['tasks_per_page'] = user_instance.get_setting('tasks_per_page', 15)
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
                 css_class="mb-6 pb-6 border-b border-gray-200 "
             ),
             Fieldset(_("Аватар"), Field("image"), css_class="mb-6 pb-6 border-b border-gray-200 "),
             Fieldset(_("Настройки уведомлений и интерфейса"),
                 Div(Field('enable_email_notifications'), css_class='mb-3'),
                 Div(Field('tasks_per_page', css_class="w-full sm:w-1/3"), css_class='mb-3'),
             )
        )

    def save(self, commit=True):
        user = super().save(commit=False)
        settings_changed = False

        if 'enable_email_notifications' in self.cleaned_data:
            new_val = self.cleaned_data['enable_email_notifications']
            if user.set_setting('enable_email_notifications', new_val, save_now=False):
                settings_changed = True

        if 'tasks_per_page' in self.cleaned_data:
            new_val = self.cleaned_data.get('tasks_per_page')
            if new_val is not None:
                if user.set_setting('tasks_per_page', new_val, save_now=False):
                    settings_changed = True
            elif user.get_setting('tasks_per_page') is not None:
                if 'tasks_per_page' in user.settings:
                    del user.settings['tasks_per_page']
                    settings_changed = True

        if commit:
            fields_to_update = [field for field in self.changed_data if field in self.Meta.fields]
            if settings_changed:
                if 'settings' not in fields_to_update:
                    fields_to_update.append('settings')
            if fields_to_update:
                 user.save(update_fields=fields_to_update)

        return user


class LoginForm(AuthenticationForm):
    username = forms.CharField(label=_("Имя пользователя или Email"), widget=forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _('Логин или Email'), 'autofocus': True}))
    password = forms.CharField(label=_("Пароль"), widget=forms.PasswordInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _('Пароль')}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.disable_csrf = True
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
        self.fields['new_password2'].help_text = None
        self.helper = FormHelper(self)
        self.helper.form_method = 'post'; self.helper.form_tag = False; self.helper.disable_csrf = True
        self.helper.layout = Layout(
            Field("old_password", css_class="mb-4"),
            Field("new_password1", css_class="mb-4"),
            Field("new_password2", css_class="mb-4"),
        )