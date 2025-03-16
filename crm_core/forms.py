from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit
from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import gettext_lazy as _
from django.forms import modelformset_factory
from .models import (
    Task, TaskPhoto, Campaign, TaskCategory, 
    TaskSubcategory
)
from user_profiles.models import User, Role, Team


# --- Form for Team --- 
class TeamForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ["name", "team_leader", "members", "description"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input-field", "placeholder": _("Team name")}),
            "description": forms.Textarea(attrs={"class": "input-field", "placeholder": _("Team description"), "rows": 3}),
            "team_leader": forms.Select(attrs={"class": "input-field"}),
            "members": forms.SelectMultiple(attrs={"class": "input-field"}),
        }


# --- Form for Campaign --- 
class CampaignForm(forms.ModelForm):
    class Meta:
        model = Campaign
        fields = ["name", "description"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input-field", "placeholder": _("Campaign name")}),
            "description": forms.Textarea(attrs={"class": "input-field", "placeholder": _("Campaign description"), "rows": 3}),
        }


# --- Form for User Creation --- 
class UserCreateForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput,
        label=_("Password")
    )

    class Meta:
        model = User
        fields = ["username", "email", "password"]


# --- Form for Role --- 
class RoleForm(forms.ModelForm):
    class Meta:
        model = Role
        fields = ["name"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input-field", "placeholder": _("Role name")}),
        }


# --- Form for Task Category --- 
class TaskCategoryForm(forms.ModelForm):
    class Meta:
        model = TaskCategory
        fields = ["name", "description"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input-field", "placeholder": _("Category name")}),
            "description": forms.Textarea(attrs={"class": "input-field", "placeholder": _("Category description"), "rows": 3}),
        }


# --- Form for Task Subcategory --- 
class TaskSubcategoryForm(forms.ModelForm):
    class Meta:
        model = TaskSubcategory
        fields = ["category", "name", "description"]
        widgets = {
            "category": forms.Select(attrs={"class": "input-field"}),
            "name": forms.TextInput(attrs={"class": "input-field", "placeholder": _("Subcategory name")}),
            "description": forms.Textarea(attrs={"class": "input-field", "placeholder": _("Subcategory description"), "rows": 3}),
        }


# --- Form for Task --- 
class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = [
            "campaign", "category", "subcategory", "description",
            "assignee", "team", "status", "priority", 
        ]
        widgets = {
            "description": forms.Textarea(attrs={"class": "input-field", "placeholder": _("Task description"), "rows": 3}),
            "campaign": forms.Select(attrs={"class": "input-field"}),
            "category": forms.Select(attrs={"class": "input-field"}),
            "subcategory": forms.Select(attrs={"class": "input-field"}),
            "assignee": forms.Select(attrs={"class": "input-field"}),
            "team": forms.Select(attrs={"class": "input-field"}),
            "status": forms.Select(attrs={"class": "input-field"}),
            "priority": forms.Select(attrs={"class": "input-field"}),
        }

    def __init__(self, *args, **kwargs):
        super(TaskForm, self).__init__(*args, **kwargs)
        if self.instance and self.instance.team:
            self.fields["assignee"].queryset = User.objects.filter(user_profile__team=self.instance.team)


# --- Form for Task Photo --- 
class TaskPhotoForm(forms.ModelForm):
    class Meta:
        model = TaskPhoto
        fields = ["photo", "description"]
        widgets = {
            "description": forms.TextInput(attrs={"class": "input-field", "placeholder": _("Photo description (optional)")}),
            "photo": forms.FileInput(attrs={"class": "file-input"}),
        }


# --- FormSet for Task Photos --- 
TaskPhotoFormSet = modelformset_factory(
    TaskPhoto, form=TaskPhotoForm, extra=1, max_num=10, can_delete=True
)


# --- Form for Login --- 
class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label=_("Username"),
        widget=forms.TextInput(attrs={
            "class": "bg-gray-100 rounded-lg px-4 py-2 w-full text-gray-700",
            "placeholder": _("Enter username")
        })
    )
    password = forms.CharField(
        label=_("Password"),
        widget=forms.PasswordInput(attrs={
            "class": "bg-gray-100 rounded-lg px-4 py-2 w-full text-gray-700",
            "placeholder": _("Enter password")
        })
    )

    def __init__(self, *args, **kwargs):
        super(LoginForm, self).__init__(*args, **kwargs)
        # Optional: Add crispy layout
        self.helper = FormHelper()
        self.helper.form_class = 'form-horizontal'
        self.helper.add_input(Submit('submit', _('Login')))
