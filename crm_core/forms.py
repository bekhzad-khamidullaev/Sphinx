from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit
from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import gettext_lazy as _
from django.forms import modelformset_factory
from .models import (
    Task, TaskPhoto, Campaign, Role, TaskCategory, 
    TaskSubcategory, Team
)
from django.contrib.auth.models import User



# --- Форма комманд ---
class TeamForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ["name", "team_leader", "members", "description", "task_categories"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input-field", "placeholder": _("Название команды")}),
            "description": forms.Textarea(attrs={"class": "input-field", "placeholder": _("Описание команды"), "rows": 3}),
            "team_leader": forms.Select(attrs={"class": "input-field"}),
            "members": forms.SelectMultiple(attrs={"class": "input-field"}),
            "task_categories": forms.SelectMultiple(attrs={"class": "input-field"}),
        }



# --- Форма кампании ---
class CampaignForm(forms.ModelForm):
    class Meta:
        model = Campaign
        fields = ["name", "description"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input-field", "placeholder": _("Название кампании")}),
            "description": forms.Textarea(attrs={"class": "input-field", "placeholder": _("Описание кампании"), "rows": 3}),
        }



# --- Форма создания пользователя ---
class UserCreateForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput,
        label=_("Пароль")
    )

    class Meta:
        model = User
        fields = ["username", "email", "password"]



# --- Форма ролей ---
class RoleForm(forms.ModelForm):
    class Meta:
        model = Role
        fields = ["name"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input-field", "placeholder": _("Название роли")}),
        }



# --- Форма категории задач ---
class TaskCategoryForm(forms.ModelForm):
    class Meta:
        model = TaskCategory
        fields = ["name", "description"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input-field", "placeholder": _("Название категории")}),
            "description": forms.Textarea(attrs={"class": "input-field", "placeholder": _("Описание категории"), "rows": 3}),
        }



# --- Форма подкатегории задач ---
class TaskSubcategoryForm(forms.ModelForm):
    class Meta:
        model = TaskSubcategory
        fields = ["category", "name", "description"]
        widgets = {
            "category": forms.Select(attrs={"class": "input-field"}),
            "name": forms.TextInput(attrs={"class": "input-field", "placeholder": _("Название подкатегории")}),
            "description": forms.Textarea(attrs={"class": "input-field", "placeholder": _("Описание подкатегории"), "rows": 3}),
        }



# --- Форма задачи ---
class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = [
            "campaign", "category", "subcategory", "description",
            "assignee", "team", "status", "priority", #"deadline",
            # "start_date", "completion_date", "estimated_time"
        ]
        widgets = {
            "description": forms.Textarea(attrs={"class": "input-field", "placeholder": _("Описание задачи"), "rows": 3}),
            # "deadline": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "input-field"}),
            # "start_date": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "input-field"}),
            # "completion_date": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "input-field"}),
            "campaign": forms.Select(attrs={"class": "input-field"}),
            "category": forms.Select(attrs={"class": "input-field"}),
            "subcategory": forms.Select(attrs={"class": "input-field"}),
            "assignee": forms.Select(attrs={"class": "input-field"}),
            "team": forms.Select(attrs={"class": "input-field"}),
            "status": forms.Select(attrs={"class": "input-field"}),
            "priority": forms.Select(attrs={"class": "input-field"}),
            # "estimated_time": forms.TextInput(attrs={"class": "input-field", "placeholder": _("Оценочное время")}),
        }

    def __init__(self, *args, **kwargs):
        super(TaskForm, self).__init__(*args, **kwargs)
        if self.instance and self.instance.team:
             self.fields["assignee"].queryset = User.objects.filter(team=self.instance.team)



# --- Форма загрузки фото для задачи ---
class TaskPhotoForm(forms.ModelForm):
    class Meta:
        model = TaskPhoto
        fields = ["photo", "description"]
        widgets = {
            "description": forms.TextInput(attrs={"class": "input-field", "placeholder": _("Описание фото (необязательно)")}),
            "photo": forms.FileInput(attrs={"class": "file-input"}),
        }



# --- FormSet для загрузки нескольких фото к задаче ---
TaskPhotoFormSet = modelformset_factory(
    TaskPhoto, form=TaskPhotoForm, extra=1, max_num=10, can_delete=True
)



# --- Форма авторизации ---
class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label=_("Имя пользователя"),
        widget=forms.TextInput(attrs={
            "class": "bg-gray-100 rounded-lg px-4 py-2 w-full text-gray-700",
            "placeholder": _("Введите имя пользователя")
        })
    )
    password = forms.CharField(
        label=_("Пароль"),
        widget=forms.PasswordInput(attrs={
            "class": "bg-gray-100 rounded-lg px-4 py-2 w-full text-gray-700",
            "placeholder": _("Введите пароль")
        })
    )


    def __init__(self, *args, **kwargs):
        super(LoginForm, self).__init__(*args, **kwargs)
        # Optional: Add crispy layout
        self.helper = FormHelper()
        self.helper.form_class = 'form-horizontal'
        self.helper.add_input(Submit('submit', _('Войти')))
