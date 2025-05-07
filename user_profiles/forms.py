import logging
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Fieldset, Row, Field, Submit, HTML, Div
from crispy_forms.bootstrap import FormActions
from django import forms
from django.contrib.auth.models import Group
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm as BaseUserCreationForm, PasswordChangeForm
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

# Импорты моделей из текущего приложения user_profiles
from .models import User, Team, Department, JobTitle

logger = logging.getLogger(__name__)

def add_common_attrs(field, placeholder=None, input_class="form-control"):
    """Adds common CSS classes and placeholder if not already set."""
    attrs = field.widget.attrs
    current_classes = attrs.get('class', '')
    # Добавляем класс только если его нет, чтобы не дублировать
    if input_class and input_class not in current_classes.split():
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
        # Используем css_class для добавления классов к полям Select2
        self.helper.layout = Layout(
            Field("name", css_class="mb-3"),
            Field("team_leader", css_class="mb-3 select2-single"), # Добавлен класс
            Field("department", css_class="mb-3 select2-single"), # Добавлен класс
            Field("members", css_class="mb-3 select2-multiple"), # Добавлен класс
            Field("description", css_class="mb-3"),
        )

class UserCreateForm(BaseUserCreationForm):
    email = forms.EmailField(required=True, label=_("Email"), widget=forms.EmailInput(attrs={'placeholder': 'your@email.com'}))
    first_name = forms.CharField(max_length=150, required=False, label=_("Имя"))
    last_name = forms.CharField(max_length=150, required=False, label=_("Фамилия"))
    phone_number = forms.CharField(max_length=20, required=False, label=_("Номер телефона"))
    # Используем ModelChoiceField для выбора существующей должности
    job_title = forms.ModelChoiceField(
        queryset=JobTitle.objects.all().order_by('name'),
        required=False,
        label=_("Должность"),
        widget=forms.Select(attrs={'class': 'form-select select2-single', 'data-placeholder': _("Выберите должность...")})
    )
    department = forms.ModelChoiceField( queryset=Department.objects.all().order_by('name'), required=False, label=_("Отдел"), widget=forms.Select(attrs={'class': 'form-select select2-single', 'data-placeholder': _("Выберите отдел...")}))
    image = forms.ImageField(required=False, label=_("Аватар"), widget=forms.ClearableFileInput)

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
        # Применяем общие атрибуты к полям, не имеющим явных виджетов в Meta
        # или не являющимися специфическими (пароль, email, файл, select)
        for field_name, field in self.fields.items():
             if 'password' in field_name: field.widget.attrs['placeholder'] = _("Задайте пароль")
             elif field_name == 'username': field.widget.attrs['placeholder'] = _("Имя пользователя (логин)")

             # Не добавляем form-control к Select, т.к. crispy-tailwind добавит свои классы
             if not isinstance(field.widget, (forms.PasswordInput, forms.EmailInput, forms.ClearableFileInput, forms.Select, forms.SelectMultiple)):
                 add_common_attrs(field) # Добавим базовый класс form-control, если нужен

        self.helper = FormHelper(self); self.helper.form_method = 'post'; self.helper.form_tag = False; self.helper.disable_csrf = True
        # Определяем Layout для crispy-forms-tailwind
        self.helper.layout = Layout(
            Fieldset(
                _("Учетные данные"),
                Field("username"),
                Field("email"),
                Field("password1"), # Используем имена полей из BaseUserCreationForm
                Field("password2"),
                css_class="border-b border-stroke dark:border-strokedark pb-4 mb-4" # Стилизация из шаблона TailAdmin
            ),
            Fieldset(
                _("Личная информация"),
                Field("first_name"),
                Field("last_name"),
                Field("phone_number"),
                 css_class="border-b border-stroke dark:border-strokedark pb-4 mb-4"
            ),
            Fieldset(
                 _("Рабочая информация"),
                 Field("job_title", css_class="select2-single"), # Класс для JS
                 Field("department", css_class="select2-single"), # Класс для JS
                 css_class="border-b border-stroke dark:border-strokedark pb-4 mb-4"
            ),
             Fieldset(
                  _("Аватар"),
                  Field("image"),
             )
             # Кнопки будут добавлены в шаблоне
        )

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and User.objects.filter(email__iexact=email).exists():
            raise ValidationError(_("Пользователь с таким email уже существует."))
        return email

# ==============================================================================
# Form for User Update (for Admin/Staff)
# ==============================================================================
class UserUpdateForm(forms.ModelForm):
    # Явно определяем поля, для которых нужны специальные виджеты или queryset
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all().order_by('name'),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'select2-multiple', 'data-placeholder': _("Выберите группы...")}),
        label=_("Группы прав")
    )
    department = forms.ModelChoiceField(
        queryset=Department.objects.all().order_by('name'),
        required=False,
        label=_("Отдел"),
        widget=forms.Select(attrs={'class': 'form-select select2-single', 'data-placeholder': _("Выберите отдел...")})
    )
    job_title = forms.ModelChoiceField(
        queryset=JobTitle.objects.all().order_by('name'),
        required=False,
        label=_("Должность"),
        widget=forms.Select(attrs={'class': 'form-select select2-single', 'data-placeholder': _("Выберите должность...")})
    )
    image = forms.ImageField(required=False, label=_("Аватар"), widget=forms.ClearableFileInput)
    is_active = forms.BooleanField(required=False, label=_("Активен"), widget=forms.CheckboxInput()) # Упрощенный виджет
    is_staff = forms.BooleanField(required=False, label=_("Сотрудник (доступ в админку)"), widget=forms.CheckboxInput()) # Упрощенный виджет

    class Meta:
        model = User
        # Перечисляем все поля, которые должны быть в форме
        fields = [
            'username', 'email', 'first_name', 'last_name', 'phone_number',
            'job_title', 'department', 'image', 'is_active', 'is_staff', 'groups'
        ]
        # Виджеты для простых полей, если нужны плейсхолдеры
        widgets = {
            'username': forms.TextInput(attrs={'placeholder': _("Имя пользователя (логин)")}),
            'email': forms.EmailInput(attrs={'placeholder': 'your@email.com'}),
            'first_name': forms.TextInput(attrs={'placeholder': _("Имя")}),
            'last_name': forms.TextInput(attrs={'placeholder': _("Фамилия")}),
            'phone_number': forms.TextInput(attrs={'placeholder': _("Номер телефона")}),
            # Для ForeignKey и ManyToMany виджеты определены выше
            # Для BooleanField и ImageField тоже определены выше
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_method = 'post'; self.helper.form_tag = False; self.helper.disable_csrf = True
        # Структурируем форму с помощью Layout и Fieldset
        self.helper.layout = Layout(
             Fieldset( _("Основная информация"),
                 Field('username'), Field('email'), Field('first_name'),
                 Field('last_name'), Field('phone_number'),
                 css_class="border-b border-stroke dark:border-strokedark pb-4 mb-4"
             ),
             Fieldset( _("Рабочая информация"),
                 Field('job_title', css_class='select2-single'), # Класс для JS
                 Field('department', css_class='select2-single'), # Класс для JS
                 css_class="border-b border-stroke dark:border-strokedark pb-4 mb-4"
             ),
             Fieldset( _("Аватар"),
                 Field('image'),
                 css_class="border-b border-stroke dark:border-strokedark pb-4 mb-4"
             ),
             Fieldset( _("Права и статус"),
                 # Оборачиваем чекбоксы для лучшего отображения с crispy-tailwind
                 Div(Field('is_active'), css_class='mb-2'),
                 Div(Field('is_staff'), css_class='mb-4'),
                 Field('groups', css_class='select2-multiple'), # Класс для JS
             ),
             # Кнопки будут в шаблоне
        )

    def clean_email(self):
        email = self.cleaned_data.get('email');
        # Проверка уникальности email при редактировании (исключая текущего пользователя)
        if email and self.instance and self.instance.pk and email.lower() != self.instance.email.lower():
            if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
                 raise ValidationError(_("Пользователь с таким email уже существует."))
        return email

class UserProfileEditForm(forms.ModelForm):
    # Явно определяем поля, чтобы контролировать виджеты и порядок
    first_name = forms.CharField(max_length=150, required=False, label=_("Имя"))
    last_name = forms.CharField(max_length=150, required=False, label=_("Фамилия"))
    phone_number = forms.CharField(max_length=20, required=False, label=_("Номер телефона"))
    job_title = forms.ModelChoiceField( # <-- Исправлено
        queryset=JobTitle.objects.all().order_by('name'),
        required=False,
        label=_("Должность"),
        widget=forms.Select(attrs={'class': 'form-select select2-single', 'data-placeholder': _("Выберите должность...")})
    )
    department = forms.ModelChoiceField(
        queryset=Department.objects.all().order_by('name'),
        required=False, label=_("Отдел"),
        widget=forms.Select(attrs={'class': 'form-select select2-single', 'data-placeholder': _("Выберите отдел...")})
    )
    image = forms.ImageField(required=False, label=_("Аватар"), widget=forms.ClearableFileInput)
    # Поля настроек, не связанные напрямую с моделью
    enable_email_notifications = forms.BooleanField(
        required=False,
        label=_("Получать уведомления по Email"),
        # Используем стандартный CheckboxInput, crispy-tailwind должен его стилизовать
        widget=forms.CheckboxInput()
    )
    tasks_per_page = forms.IntegerField(
        required=False, label=_("Задач на странице по умолчанию"),
        min_value=5, max_value=100,
        # Используем стандартный NumberInput, crispy-tailwind стилизует
        widget=forms.NumberInput(attrs={'placeholder': '15'}),
        help_text=_("От 5 до 100")
    )

    class Meta:
        model = User
        # Поля модели, которые редактируются этой формой
        fields = [ 'first_name', 'last_name', 'phone_number', 'job_title', 'department', 'image' ]
        # Можно добавить виджеты для простых полей здесь, если нужны плейсхолдеры
        widgets = {
             'first_name': forms.TextInput(attrs={'placeholder': _("Ваше имя")}),
             'last_name': forms.TextInput(attrs={'placeholder': _("Ваша фамилия")}),
             'phone_number': forms.TextInput(attrs={'placeholder': _("Контактный телефон")}),
        }


    def __init__(self, *args, **kwargs):
        # Получаем пользователя из instance для инициализации полей настроек
        user = kwargs.get('instance')
        initial = kwargs.get('initial', {})
        if user and isinstance(user.settings, dict):
            initial['enable_email_notifications'] = user.settings.get('enable_email_notifications', True)
            initial['tasks_per_page'] = user.settings.get('tasks_per_page', 15)
        else:
            # Значения по умолчанию, если пользователя нет или settings не словарь
            initial.setdefault('enable_email_notifications', True)
            initial.setdefault('tasks_per_page', 15)
        kwargs['initial'] = initial # Передаем обновленный initial

        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_method = 'post'; self.helper.form_tag = False; self.helper.disable_csrf = True
        # Определяем Layout, соответствующий шаблону TailAdmin
        self.helper.layout = Layout(
             Fieldset( _("Личная информация"),
                 Field('first_name'), Field('last_name'), Field('phone_number'),
                 css_class='border-b border-stroke dark:border-strokedark pb-4 mb-4'), # Стиль из шаблона
             Fieldset( _("Рабочая информация"),
                 Field('job_title', css_class='select2-single'), # Класс для JS
                 Field('department', css_class='select2-single'), # Класс для JS
                 css_class='border-b border-stroke dark:border-strokedark pb-4 mb-4'),
             Fieldset( _("Аватар"),
                 Field('image'),
                 css_class='border-b border-stroke dark:border-strokedark pb-4 mb-4'),
             Fieldset( _("Настройки уведомлений и интерфейса"),
                 # Оборачиваем чекбокс и поле числа для лучшего контроля разметки
                 Div(Field('enable_email_notifications'), css_class='mb-3'),
                 Div(Field('tasks_per_page'), css_class='mb-3 w-full md:w-1/4'), # Ограничим ширину поля
             )
             # Кнопки будут в шаблоне
        )

    def save(self, commit=True):
        user = super().save(commit=False) # Получаем объект пользователя без сохранения в БД

        settings_changed = False
        # Гарантируем, что settings является словарем
        if not isinstance(user.settings, dict):
            user.settings = {}

        # Обрабатываем поле 'enable_email_notifications'
        # cleaned_data содержит значение из формы, если оно было отправлено (даже False)
        if 'enable_email_notifications' in self.cleaned_data:
            email_notif_value = self.cleaned_data['enable_email_notifications']
            if user.settings.get('enable_email_notifications', True) != email_notif_value:
                user.settings['enable_email_notifications'] = email_notif_value
                settings_changed = True
        # Если поле не было в форме (редко, но возможно), оставляем старое значение

        # Обрабатываем поле 'tasks_per_page'
        if 'tasks_per_page' in self.cleaned_data:
             tasks_page_value = self.cleaned_data.get('tasks_per_page') # Может быть None, если поле пустое и не required
             # Сравниваем с текущим значением (или None, если его нет)
             if tasks_page_value is not None and user.settings.get('tasks_per_page') != tasks_page_value:
                  user.settings['tasks_per_page'] = tasks_page_value
                  settings_changed = True
             elif tasks_page_value is None and 'tasks_per_page' in user.settings:
                  # Если пользователь очистил поле, удаляем настройку (или ставим дефолт?)
                  # Пока удалим:
                  del user.settings['tasks_per_page']
                  settings_changed = True

        if commit:
            # Определяем, какие поля модели (из Meta.fields) изменились
            model_fields_to_update = [field for field in self.changed_data if field in self.Meta.fields]

            # Если изменились настройки, добавляем поле 'settings' к списку для обновления
            if settings_changed:
                if 'settings' not in model_fields_to_update:
                     model_fields_to_update.append('settings')

            # Сохраняем только измененные поля
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
            Field("username", css_class="mb-3"), # Используем классы Tailwind/Bootstrap по необходимости
            Field("password", css_class="mb-3"),
            # Кнопка рендерится в шаблоне registration/login.html
        )
