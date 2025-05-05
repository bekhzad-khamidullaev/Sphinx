# user_profiles/forms.py
import logging
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Fieldset, Row, Field, Submit, HTML, Div
from crispy_forms.bootstrap import FormActions
from django import forms
from django.contrib.auth.models import Group
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm as BaseUserCreationForm, PasswordChangeForm
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from .models import User, Team, Department, JobTitle

logger = logging.getLogger(__name__)

def add_common_attrs(field, placeholder=None, input_class="form-control"):
    attrs = field.widget.attrs
    current_classes = attrs.get('class', '')
    if input_class not in current_classes.split():
        attrs['class'] = f'{current_classes} {input_class}'.strip()
    if placeholder and 'placeholder' not in attrs:
        attrs["placeholder"] = placeholder
    field.widget.attrs.update(attrs)

class TeamForm(forms.ModelForm):
    members = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        widget=forms.SelectMultiple(attrs={'class': 'select2-multiple w-full', 'data-placeholder': _("Выберите участников...")}),
        required=False,
        label=_("Участники")
    )
    team_leader = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select select2-single w-full', 'data-placeholder': _("Выберите лидера...")}),
        label=_("Лидер команды")
    )
    department = forms.ModelChoiceField(
        queryset=Department.objects.all().order_by('name'),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select select2-single w-full', 'data-placeholder': _("Выберите отдел...")}),
        label=_("Отдел")
    )

    class Meta:
        model = Team
        fields = ["name", "team_leader", "members", "department", "description"]
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': _("Название команды")}),
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': _("Описание команды (опционально)")}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_method = 'post'; self.helper.form_tag = False; self.helper.disable_csrf = True
        self.helper.layout = Layout(
            Field("name", css_class="mb-4"),
            Field("team_leader", css_class="mb-4"),
            Field("department", css_class="mb-4"),
            Field("members", css_class="mb-4"),
            Field("description", css_class="mb-4"),
        )

class UserCreateForm(BaseUserCreationForm):
    email = forms.EmailField(required=True, label=_("Email"), widget=forms.EmailInput(attrs={'placeholder': 'your@email.com'}))
    first_name = forms.CharField(max_length=150, required=False, label=_("Имя"))
    last_name = forms.CharField(max_length=150, required=False, label=_("Фамилия"))
    phone_number = forms.CharField(max_length=20, required=False, label=_("Номер телефона"))
    department = forms.ModelChoiceField(
        queryset=Department.objects.all().order_by('name'),
        required=False,
        label=_("Отдел"),
    )
    image = forms.ImageField(required=False, label=_("Аватар"))

    class Meta(BaseUserCreationForm.Meta):
        model = User
        fields = BaseUserCreationForm.Meta.fields + (
            'email', 'first_name', 'last_name', 'phone_number',
            'job_title',
            'department', 'image'
        )
        widgets = {
            'job_title': forms.Select(attrs={
                'class': 'form-select select2-single w-full',
                'data-placeholder': _("Выберите должность...")
            }),
            'department': forms.Select(attrs={
                'class': 'form-select select2-single w-full',
                'data-placeholder': _("Выберите отдел...")
            }),
             'image': forms.ClearableFileInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
             if 'password' in field_name: field.widget.attrs['placeholder'] = _("Задайте пароль")
             elif field_name == 'username': field.widget.attrs['placeholder'] = _("Имя пользователя (логин)")

        self.helper = FormHelper(self)
        self.helper.form_method = 'post'
        self.helper.form_tag = False
        self.helper.disable_csrf = True
        self.helper.layout = Layout(
            Fieldset(
                _("Учетные данные"),
                Field("username", css_class="mb-4"),
                Field("email", css_class="mb-4"),
                Field("password", css_class="mb-4"),
                Field("password2", css_class="mb-4"),
            ),
            Fieldset(
                _("Личная информация"),
                Field("first_name", css_class="mb-4"),
                Field("last_name", css_class="mb-4"),
                Field("phone_number", css_class="mb-4"),
            ),
            Fieldset(
                 _("Рабочая информация"),
                 Field("job_title", css_class="mb-4"),
                 Field("department", css_class="mb-4"),
            ),
             Fieldset(
                  _("Аватар"),
                  Field("image", css_class="mb-4"),
             )
        )

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and User.objects.filter(email__iexact=email).exists():
            raise ValidationError(_("Пользователь с таким email уже существует."))
        return email

class UserUpdateForm(forms.ModelForm):
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all().order_by('name'),
        required=False,
        label=_("Группы прав")
    )
    department = forms.ModelChoiceField(
        queryset=Department.objects.all().order_by('name'),
        required=False,
        label=_("Отдел"),
    )

    class Meta:
        model = User
        fields = [
            'username', 'email', 'first_name', 'last_name', 'phone_number',
            'job_title',
            'department', 'image', 'is_active', 'is_staff', 'groups'
        ]
        widgets = {
            'username': forms.TextInput(attrs={'placeholder': _("Имя пользователя (логин)")}),
            'email': forms.EmailInput(attrs={'placeholder': 'your@email.com'}),
            'image': forms.ClearableFileInput(),
            'is_active': forms.CheckboxInput(),
            'is_staff': forms.CheckboxInput(),
             'job_title': forms.Select(attrs={
                 'class': 'form-select select2-single w-full',
                 'data-placeholder': _("Выберите должность...")
             }),
             'department': forms.Select(attrs={
                 'class': 'form-select select2-single w-full',
                 'data-placeholder': _("Выберите отдел...")
             }),
             'groups': forms.SelectMultiple(attrs={
                 'class': 'select2-multiple w-full',
                 'data-placeholder': _("Выберите группы...")
             }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_method = 'post'
        self.helper.form_tag = False
        self.helper.disable_csrf = True
        self.helper.layout = Layout(
            Fieldset(
                _("Основная информация"),
                Div(
                    Field('username'), Field('email'),
                    css_class='grid md:grid-cols-2 gap-x-4 mb-4'
                ),
                Div(
                    Field('first_name'), Field('last_name'),
                    css_class='grid md:grid-cols-2 gap-x-4 mb-4'
                ),
                 Div(
                     Field('phone_number'), Field('job_title'),
                     css_class='grid md:grid-cols-2 gap-x-4 mb-4'
                 ),
                 Field('department', css_class='mb-4'),
                 Field('image', css_class='mb-4'),
            ),
             Fieldset(
                 _("Права и статус"),
                 Div(
                     Field('is_active'), Field('is_staff'),
                     css_class='grid md:grid-cols-2 gap-x-4 mb-4'
                 ),
                 Field('groups', css_class='mb-4'),
             ),
        )

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and self.instance and self.instance.pk and self.instance.email.lower() != email.lower():
            if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
                raise ValidationError(_("Пользователь с таким email уже существует."))
        return email

class UserProfileEditForm(forms.ModelForm):
    first_name = forms.CharField(max_length=150, required=False, label=_("Имя"))
    last_name = forms.CharField(max_length=150, required=False, label=_("Фамилия"))
    phone_number = forms.CharField(max_length=20, required=False, label=_("Номер телефона"))
    department = forms.ModelChoiceField(
        queryset=Department.objects.all().order_by('name'),
        required=False,
        label=_("Отдел"),
    )
    image = forms.ImageField(required=False, label=_("Аватар"))

    enable_email_notifications = forms.BooleanField(
        required=False,
        label=_("Получать уведомления по Email"),
        widget=forms.CheckboxInput(attrs={'class': 'form-checkbox h-5 w-5 text-blue-600 rounded border-gray-300 focus:ring-blue-500 dark:bg-dark-700 dark:border-dark-600 dark:checked:bg-blue-500 dark:focus:ring-offset-dark-800'})
    )
    tasks_per_page = forms.IntegerField(
        required=False,
        label=_("Задач на странице по умолчанию"),
        min_value=5, max_value=100,
        widget=forms.NumberInput(attrs={'placeholder': '15', 'class': 'form-input block w-24 rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm dark:bg-dark-700 dark:border-dark-600 dark:text-gray-300'}),
        help_text=_("От 5 до 100")
    )

    class Meta:
        model = User
        fields = [ 'first_name', 'last_name', 'phone_number', 'job_title', 'department', 'image' ]
        widgets = {
            'job_title': forms.Select(attrs={
                 'class': 'form-select select2-single w-full',
                 'data-placeholder': _("Выберите должность...")
             }),
            'department': forms.Select(attrs={
                 'class': 'form-select select2-single w-full',
                 'data-placeholder': _("Выберите отдел...")
             }),
            'image': forms.ClearableFileInput(),
        }


    def __init__(self, *args, **kwargs):
        user = kwargs.get('instance')
        initial = kwargs.get('initial', {})
        if user and isinstance(user.settings, dict):
            initial['enable_email_notifications'] = user.settings.get('enable_email_notifications', True)
            initial['tasks_per_page'] = user.settings.get('tasks_per_page', 15)
        else:
            initial.setdefault('enable_email_notifications', True)
            initial.setdefault('tasks_per_page', 15)
        kwargs['initial'] = initial

        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_method = 'post'
        self.helper.form_tag = False
        self.helper.disable_csrf = True
        self.helper.layout = Layout(
            Fieldset(
                _("Личная информация"),
                Div(
                    Field('first_name'), Field('last_name'),
                    css_class='grid md:grid-cols-2 gap-x-4 mb-4'
                ),
                Field('phone_number', css_class='mb-4'),
                css_class='border-b border-gray-200 dark:border-dark-600 pb-6 mb-6'
            ),
            Fieldset(
                _("Рабочая информация"),
                Field('job_title', css_class='mb-4'),
                Field('department', css_class='mb-4'),
                css_class='border-b border-gray-200 dark:border-dark-600 pb-6 mb-6'
            ),
             Fieldset(
                 _("Аватар"),
                 Field('image', css_class='mb-4'),
                 css_class='border-b border-gray-200 dark:border-dark-600 pb-6 mb-6'
             ),
            Fieldset(
                _("Настройки уведомлений и интерфейса"),
                Div(
                    Field('enable_email_notifications'),
                    css_class='flex items-center mb-4'
                ),
                 Div(
                     Field('tasks_per_page'),
                     css_class='mb-4'
                 ),
             )
        )

    def save(self, commit=True):
        user = super().save(commit=False)

        settings_changed = False
        if not isinstance(user.settings, dict):
            user.settings = {}

        current_notif_setting = user.settings.get('enable_email_notifications', True)
        new_notif_setting = self.cleaned_data.get('enable_email_notifications', current_notif_setting)
        if current_notif_setting != new_notif_setting:
            user.settings['enable_email_notifications'] = new_notif_setting
            settings_changed = True

        current_tasks_setting = user.settings.get('tasks_per_page', 15)
        new_tasks_setting = self.cleaned_data.get('tasks_per_page')
        if new_tasks_setting is not None and current_tasks_setting != new_tasks_setting:
             user.settings['tasks_per_page'] = new_tasks_setting
             settings_changed = True

        if commit:
            model_fields_to_update = [field for field in self.changed_data if field in self.Meta.fields]
            if settings_changed:
                if 'settings' not in model_fields_to_update:
                     model_fields_to_update.append('settings')

            if model_fields_to_update:
                 user.save(update_fields=model_fields_to_update)
                 logger.info(f"User profile {user.username} updated fields: {model_fields_to_update}")
            else:
                 logger.info(f"User profile {user.username}: No changes detected in model fields or settings.")
        return user

class LoginForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={'placeholder': _('Имя пользователя или Email')}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'placeholder': _('Пароль')}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.disable_csrf = True
        self.helper.layout = Layout(
            Field("username", css_class="mb-4"),
            Field("password", css_class="mb-4"),
        )

class StyledPasswordChangeForm(PasswordChangeForm):
     def __init__(self, *args, **kwargs):
         super().__init__(*args, **kwargs)
         self.helper = FormHelper()
         self.helper.form_method = 'post'
         self.helper.form_tag = False
         self.helper.disable_csrf = True
         self.helper.layout = Layout(
             Field('old_password', css_class='mb-4', placeholder=_('Текущий пароль')),
             Field('new_password1', css_class='mb-4', placeholder=_('Новый пароль')),
             Field('new_password2', css_class='mb-4', placeholder=_('Подтвердите новый пароль')),
         )