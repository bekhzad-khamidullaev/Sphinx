# user_profiles/forms.py
import logging
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Fieldset, Row, Field, Submit, HTML, Div
from crispy_forms.bootstrap import FormActions
from django import forms
from django.contrib.auth.models import Group
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm as BaseUserCreationForm
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

# Импорты моделей из текущего приложения user_profiles
from .models import User, Team, Department

logger = logging.getLogger(__name__)

# --- Utility function --- (Можно вынести в utils.py)
def add_common_attrs(field, placeholder=None, input_class="form-control"):
    attrs = field.widget.attrs
    current_classes = attrs.get('class', '')
    if input_class not in current_classes.split():
        attrs['class'] = f'{current_classes} {input_class}'.strip()
    if placeholder and 'placeholder' not in attrs:
        attrs["placeholder"] = placeholder
    field.widget.attrs.update(attrs)

# ==============================================================================
# Form for Team
# ==============================================================================
class TeamForm(forms.ModelForm):
    members = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        widget=forms.SelectMultiple(attrs={'class': 'select2-multiple', 'data-placeholder': _("Выберите участников...")}),
        required=False,
        label=_("Участники")
    )
    team_leader = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select select2-single', 'data-placeholder': _("Выберите лидера...")}),
        label=_("Лидер команды")
    )
    department = forms.ModelChoiceField(
        queryset=Department.objects.all().order_by('name'),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select select2-single', 'data-placeholder': _("Выберите отдел...")}),
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
        self.helper.layout = Layout( Field("name", css_class="mb-3"), Field("team_leader", css_class="mb-3"), Field("department", css_class="mb-3"), Field("members", css_class="mb-3"), Field("description", css_class="mb-3"),)

# ==============================================================================
# Form for User Creation
# ==============================================================================
class UserCreateForm(BaseUserCreationForm):
    email = forms.EmailField(required=True, label=_("Email"), widget=forms.EmailInput(attrs={'placeholder': 'your@email.com'}))
    first_name = forms.CharField(max_length=150, required=False, label=_("Имя"))
    last_name = forms.CharField(max_length=150, required=False, label=_("Фамилия"))
    phone_number = forms.CharField(max_length=20, required=False, label=_("Номер телефона"))
    job_title = forms.CharField(max_length=100, required=False, label=_("Должность"))
    department = forms.ModelChoiceField( queryset=Department.objects.all().order_by('name'), required=False, label=_("Отдел"), widget=forms.Select(attrs={'class': 'form-select select2-single', 'data-placeholder': _("Выберите отдел...")}))
    image = forms.ImageField(required=False, label=_("Аватар"), widget=forms.ClearableFileInput)

    class Meta(BaseUserCreationForm.Meta):
        model = User
        fields = BaseUserCreationForm.Meta.fields + ( 'email', 'first_name', 'last_name', 'phone_number', 'job_title', 'department', 'image' )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
             if 'password' in field_name: field.widget.attrs['placeholder'] = _("Пароль")
             elif field_name == 'username': field.widget.attrs['placeholder'] = _("Имя пользователя (логин)")
             # --- ИЗМЕНЕНИЕ ЗДЕСЬ: Убрали проверку self.Meta.widgets ---
             if not isinstance(field.widget, (forms.PasswordInput, forms.EmailInput, forms.ClearableFileInput, forms.Select)):
                 add_common_attrs(field)
             elif field_name == 'department':
                 # Убедимся, что класс select2-single добавлен, если это Select виджет
                 if isinstance(field.widget, forms.Select):
                      field.widget.attrs['class'] = 'form-select select2-single'
        self.helper = FormHelper(self); self.helper.form_method = 'post'; self.helper.form_tag = False; self.helper.disable_csrf = True
        # --- Обновляем Layout, чтобы явно использовать классы для виджетов Select2 ---
        self.helper.layout = Layout(
            Fieldset(
                _("Учетные данные"),
                Field("username"),
                Field("email"),
                Field("password1"), # Правильное имя поля
                Field("password2"), # Правильное имя поля
            ),
            Fieldset(
                _("Личная информация"),
                Field("first_name"),
                Field("last_name"),
                Field("phone_number"),
            ),
            Fieldset(
                 _("Рабочая информация"),
                 Field("job_title"),
                 # Явно указываем класс для Select2 виджета отдела
                 Field("department", css_class="select2-single"),
            ),
             Fieldset(
                  _("Аватар"),
                  # Для ClearableFileInput обычно не нужны доп. классы
                  Field("image"),
             )
        )


    def clean_email(self):
        email = self.cleaned_data.get('email');
        if email and User.objects.filter(email__iexact=email).exists(): raise ValidationError(_("Пользователь с таким email уже существует."))
        return email

# ==============================================================================
# Form for User Update
# ==============================================================================
class UserUpdateForm(forms.ModelForm):
    groups = forms.ModelMultipleChoiceField( queryset=Group.objects.all().order_by('name'), required=False, widget=forms.SelectMultiple(attrs={'class': 'select2-multiple', 'data-placeholder': _("Выберите группы...")}), label=_("Группы прав"))
    department = forms.ModelChoiceField( queryset=Department.objects.all().order_by('name'), required=False, label=_("Отдел"), widget=forms.Select(attrs={'class': 'form-select select2-single', 'data-placeholder': _("Выберите отдел...")}))

    class Meta:
        model = User
        fields = [ 'username', 'email', 'first_name', 'last_name', 'phone_number', 'job_title', 'department', 'image', 'is_active', 'is_staff', 'groups']
        widgets = { 'username': forms.TextInput(attrs={'placeholder': _("Имя пользователя (логин)")}), 'email': forms.EmailInput(attrs={'placeholder': 'your@email.com'}), 'image': forms.ClearableFileInput(), 'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}), 'is_staff': forms.CheckboxInput(attrs={'class': 'form-check-input'}), }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name not in self.Meta.widgets and not isinstance(field, (forms.ModelMultipleChoiceField, forms.ModelChoiceField)): add_common_attrs(field)
        self.helper = FormHelper(self); self.helper.form_method = 'post'; self.helper.form_tag = False; self.helper.disable_csrf = True
        self.helper.layout = Layout( Fieldset( _("Основная информация"), Row( Field('username', wrapper_class='col-md-6'), Field('email', wrapper_class='col-md-6'), css_class='mb-3'), Row( Field('first_name', wrapper_class='col-md-6'), Field('last_name', wrapper_class='col-md-6'), css_class='mb-3'), Row( Field('phone_number', wrapper_class='col-md-6'), Field('job_title', wrapper_class='col-md-6'), css_class='mb-3'), Field('department', css_class='mb-3'), Field('image', css_class='mb-3'), ), Fieldset( _("Права и статус"), Row( Div(Field('is_active'), css_class='form-check form-switch mb-2 col-md-6'), Div(Field('is_staff'), css_class='form-check form-switch mb-2 col-md-6'), css_class='mb-3' ), Field('groups', css_class='mb-3'), ),)

    def clean_email(self):
        email = self.cleaned_data.get('email');
        if email and self.instance and self.instance.pk and email != self.instance.email:
            if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists(): raise ValidationError(_("Пользователь с таким email уже существует."))
        return email

# ==============================================================================
# Form for User Profile Edit (by user)
# ==============================================================================
class UserProfileEditForm(forms.ModelForm):
    first_name = forms.CharField(max_length=150, required=False, label=_("Имя"))
    last_name = forms.CharField(max_length=150, required=False, label=_("Фамилия"))
    phone_number = forms.CharField(max_length=20, required=False, label=_("Номер телефона"))
    job_title = forms.CharField(max_length=100, required=False, label=_("Должность"))
    department = forms.ModelChoiceField( queryset=Department.objects.all().order_by('name'), required=False, label=_("Отдел"), widget=forms.Select(attrs={'class': 'form-select select2-single', 'data-placeholder': _("Выберите отдел...")}))
    image = forms.ImageField(required=False, label=_("Аватар"), widget=forms.ClearableFileInput)
    enable_email_notifications = forms.BooleanField( required=False, label=_("Получать уведомления по Email"), widget=forms.CheckboxInput(attrs={'class': 'form-checkbox h-5 w-5 text-blue-600 rounded border-gray-300 focus:ring-blue-500'}))
    tasks_per_page = forms.IntegerField( required=False, label=_("Задач на странице по умолчанию"), min_value=5, max_value=100, widget=forms.NumberInput(attrs={'placeholder': '15', 'class': 'form-input mt-1 block w-20 rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'}), help_text=_("От 5 до 100"))

    class Meta:
        model = User
        fields = [ 'first_name', 'last_name', 'phone_number', 'job_title', 'department', 'image' ]

    def __init__(self, *args, **kwargs):
        user = kwargs.get('instance'); initial = kwargs.get('initial', {})
        if user and isinstance(user.settings, dict): initial['enable_email_notifications'] = user.settings.get('enable_email_notifications', True); initial['tasks_per_page'] = user.settings.get('tasks_per_page', 15)
        else: initial.setdefault('enable_email_notifications', True); initial.setdefault('tasks_per_page', 15)
        kwargs['initial'] = initial
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self); self.helper.form_method = 'post'; self.helper.form_tag = False; self.helper.disable_csrf = True
        self.helper.layout = Layout( Fieldset( _("Личная информация"), Row( Field('first_name', wrapper_class='col-md-6'), Field('last_name', wrapper_class='col-md-6'), css_class='mb-3'), Field('phone_number', css_class='mb-3'), css_class='border-b border-gray-200 dark:border-dark-600 pb-4 mb-4'), Fieldset( _("Рабочая информация"), Field('job_title', css_class='mb-3'), Field('department', css_class='mb-3'), css_class='border-b border-gray-200 dark:border-dark-600 pb-4 mb-4'), Fieldset( _("Аватар"), Field('image', css_class='mb-3'), css_class='border-b border-gray-200 dark:border-dark-600 pb-4 mb-4'), Fieldset( _("Настройки уведомлений и интерфейса"), Div( Field('enable_email_notifications', wrapper_class='flex items-center'), css_class='form-check form-switch mb-3'), Field('tasks_per_page', css_class='mb-3'),))

    def save(self, commit=True):
        user = super().save(commit=False)

        settings_changed = False
        if not isinstance(user.settings, dict): user.settings = {}


        email_notif_value = self.cleaned_data.get('enable_email_notifications', user.settings.get('enable_email_notifications', True)) # Берем новое значение или старое
        if user.settings.get('enable_email_notifications', True) != email_notif_value:
            user.settings['enable_email_notifications'] = email_notif_value
            settings_changed = True

        tasks_page_value = self.cleaned_data.get('tasks_per_page')

        if tasks_page_value is not None and user.settings.get('tasks_per_page') != tasks_page_value:
             user.settings['tasks_per_page'] = tasks_page_value
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
                 logger.info(f"User profile {user.username}: No changes detected.")
        return user

# ==============================================================================
# Form for Login
# ==============================================================================
class LoginForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={'placeholder': _('Имя пользователя или Email'), 'class': 'form-control'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'placeholder': _('Пароль'), 'class': 'form-control'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False # Тег <form> будет в шаблоне
        self.helper.disable_csrf = True # CSRF токен будет в шаблоне
        self.helper.layout = Layout(
            Field("username", css_class="mb-3"),
            Field("password", css_class="mb-3"),
            # Кнопка рендерится в шаблоне registration/login.html
            # Submit('submit', _('Войти'), css_class='btn btn-primary w-100')
        )