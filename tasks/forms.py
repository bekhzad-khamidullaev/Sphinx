from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Field
from crispy_forms.bootstrap import FormActions
from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.forms import modelformset_factory
from .models import (
    Task, TaskPhoto, Campaign, TaskCategory,
    TaskSubcategory
)
from user_profiles.models import User, Role, Team

# --- Utility function for adding common attributes ---
def add_common_attrs(field, placeholder=None, input_class="input-field"):
    """Adds common attributes to a form field."""
    attrs = {"class": input_class}
    if placeholder:
        attrs["placeholder"] = placeholder
    field.widget.attrs.update(attrs)


# --- Form for Team ---
class TeamForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ["name", "team_leader", "members", "description"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_common_attrs(self.fields["name"], placeholder=_("Team name"))
        add_common_attrs(self.fields["description"], placeholder=_("Team description"))
        self.fields["description"].widget.attrs["rows"] = 3
        add_common_attrs(self.fields["team_leader"])
        add_common_attrs(self.fields["members"])

        self.helper = FormHelper()
        self.helper.layout = Layout(
            Field("name"),
            Field("team_leader"),
            Field("members"),
            Field("description"),
            FormActions(
                Submit("submit", _("Save Team"), css_class="btn btn-success"),
                css_class="mt-2"
            )
        )

    def clean_name(self):
        name = self.cleaned_data.get("name")
        if Team.objects.filter(name__iexact=name).exists() and (not self.instance or self.instance.name != name):
            raise ValidationError(_("This team name is already in use."))
        return name


# --- Form for Campaign ---
class CampaignForm(forms.ModelForm):
    class Meta:
        model = Campaign
        fields = ["name", "description", "start_date", "end_date"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_common_attrs(self.fields["name"], placeholder=_("Campaign name"))
        add_common_attrs(self.fields["description"], placeholder=_("Campaign description"))
        self.fields["description"].widget.attrs["rows"] = 3

        self.helper = FormHelper()
        self.helper.layout = Layout(
            Field("name"),
            Field("description"),
            Field("start_date"),
            Field("end_date"),
            FormActions(
                Submit("submit", _("Save Campaign"), css_class="btn btn-success"),
                css_class="mt-2"
            )
        )

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")

        if start_date and end_date and start_date > end_date:
            raise ValidationError(_("End date cannot be before start date."))

        return cleaned_data


# --- Form for User Creation ---
class UserCreateForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "input-field", "placeholder": _("Password")}),
        label=_("Password")
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "input-field", "placeholder": _("Confirm Password")}),
        label=_("Confirm Password"),
        required=True,
    )

    class Meta:
        model = User
        fields = ["username", "email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_common_attrs(self.fields["username"], placeholder=_("Username"))
        add_common_attrs(self.fields["email"], placeholder=_("Email"))

        self.helper = FormHelper()
        self.helper.layout = Layout(
            Field("username"),
            Field("email"),
            Field("password"),
            Field("password_confirm"),
            FormActions(
                Submit("submit", _("Register"), css_class="btn btn-primary"),
                css_class="mt-2"
            )
        )

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")

        if password != password_confirm:
            raise ValidationError(_("Passwords do not match."))

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data["password"]
        user.set_password(password)  # Hash the password
        if commit:
            user.save()
        return user


# --- Form for Role ---
class RoleForm(forms.ModelForm):
    class Meta:
        model = Role
        fields = ["name"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_common_attrs(self.fields["name"], placeholder=_("Role name"))

        self.helper = FormHelper()
        self.helper.layout = Layout(
            Field("name"),
            FormActions(
                Submit("submit", _("Save Role"), css_class="btn btn-success"),
                css_class="mt-2"
            )
        )

    def clean_name(self):
        name = self.cleaned_data.get("name")
        if Role.objects.filter(name__iexact=name).exists() and (not self.instance or self.instance.name != name):
            raise ValidationError(_("This role name is already in use."))
        return name


# --- Form for Task Category ---
class TaskCategoryForm(forms.ModelForm):
    class Meta:
        model = TaskCategory
        fields = ["name", "description"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_common_attrs(self.fields["name"], placeholder=_("Category name"))
        add_common_attrs(self.fields["description"], placeholder=_("Category description"))
        self.fields["description"].widget.attrs["rows"] = 3

        self.helper = FormHelper()
        self.helper.layout = Layout(
            Field("name"),
            Field("description"),
            FormActions(
                Submit("submit", _("Save Category"), css_class="btn btn-success"),
                css_class="mt-2"
            )
        )

    def clean_name(self):
        name = self.cleaned_data.get("name")
        if TaskCategory.objects.filter(name__iexact=name).exists() and (not self.instance or self.instance.name != name):
            raise ValidationError(_("This category name is already in use."))
        return name


# --- Form for Task Subcategory ---
class TaskSubcategoryForm(forms.ModelForm):
    class Meta:
        model = TaskSubcategory
        fields = ["category", "name", "description"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_common_attrs(self.fields["category"])
        add_common_attrs(self.fields["name"], placeholder=_("Subcategory name"))
        add_common_attrs(self.fields["description"], placeholder=_("Subcategory description"))
        self.fields["description"].widget.attrs["rows"] = 3

        self.helper = FormHelper()
        self.helper.layout = Layout(
            Field("category"),
            Field("name"),
            Field("description"),
            FormActions(
                Submit("submit", _("Save Subcategory"), css_class="btn btn-success"),
                css_class="mt-2"
            )
        )

    def clean(self):
        cleaned_data = super().clean()
        category = cleaned_data.get("category")
        name = cleaned_data.get("name")

        if category and name and TaskSubcategory.objects.filter(category=category, name__iexact=name).exists() and (not self.instance or (self.instance.category != category or self.instance.name != name)):
            raise ValidationError(_("A subcategory with this name already exists in this category."))

        return cleaned_data


# --- Form for Task ---
class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = [
            "campaign", "category", "subcategory", "description",
            "assignee", "team", "status", "priority", "deadline", "start_date", "estimated_time"
        ]
        widgets = {
            "deadline": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "start_date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "estimated_time": forms.TimeInput(attrs={"type": "time"}),  # If duration is better suited for time
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        add_common_attrs(self.fields["campaign"])
        add_common_attrs(self.fields["category"])
        add_common_attrs(self.fields["subcategory"])
        add_common_attrs(self.fields["description"], placeholder=_("Task description"))
        self.fields["description"].widget.attrs["rows"] = 3
        add_common_attrs(self.fields["assignee"])
        add_common_attrs(self.fields["team"])
        add_common_attrs(self.fields["status"])
        add_common_attrs(self.fields["priority"])

        if self.instance and self.instance.team:
            self.fields["assignee"].queryset = User.objects.filter(user_profile__team=self.instance.team)
        else:
            self.fields["assignee"].queryset = User.objects.none()

        self.helper = FormHelper()
        self.helper.layout = Layout(
            Field("campaign"),
            Field("category"),
            Field("subcategory"),
            Field("description"),
            Field("assignee"),
            Field("team"),
            Field("status"),
            Field("priority"),
            Field("deadline"),
            Field("start_date"),
            Field("estimated_time"),
            FormActions(
                Submit("submit", _("Save Task"), css_class="btn btn-success"),
                css_class="mt-2"
            )
        )

    def clean(self):
        cleaned_data = super().clean()
        assignee = cleaned_data.get("assignee")
        team = cleaned_data.get("team")
        category = cleaned_data.get("category")
        subcategory = cleaned_data.get("subcategory")
        deadline = cleaned_data.get("deadline")
        start_date = cleaned_data.get("start_date")
        estimated_time = cleaned_data.get("estimated_time")

        if assignee and team:
            raise ValidationError(_("Task cannot be assigned to both a user and a team."))

        if category and subcategory and category != subcategory.category:
            raise ValidationError(_("Subcategory does not belong to the selected category."))

        if deadline and start_date and deadline < start_date:
            raise ValidationError(_("Deadline cannot be before start date."))

        # Validation for estimated time being a reasonable value
        if estimated_time and estimated_time.total_seconds() <= 0:  # Assuming total_seconds() is applicable for DurationField
            raise ValidationError(_("Estimated time must be a positive duration."))

        return cleaned_data


# --- Form for Task Photo ---
class TaskPhotoForm(forms.ModelForm):
    class Meta:
        model = TaskPhoto
        fields = ["photo", "description"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_common_attrs(self.fields["description"], placeholder=_("Photo description (optional)"))
        self.fields["photo"].widget.attrs["class"] = "file-input"

        self.helper = FormHelper()
        self.helper.layout = Layout(
            Field("photo"),
            Field("description"),
            FormActions(
                Submit("submit", _("Upload Photo"), css_class="btn btn-success"),
                css_class="mt-2"
            )
        )


# --- FormSet for Task Photos ---
TaskPhotoFormSet = modelformset_factory(
    TaskPhoto, form=TaskPhotoForm, extra=1, max_num=10, can_delete=True
)


# --- Form for Login ---
class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_common_attrs(self.fields["username"], placeholder=_("Enter username"), input_class="bg-gray-100 rounded-lg px-4 py-2 w-full text-gray-700")
        add_common_attrs(self.fields["password"], placeholder=_("Enter password"), input_class="bg-gray-100 rounded-lg px-4 py-2 w-full text-gray-700")

        self.helper = FormHelper()
        self.helper.form_class = 'form-horizontal'
        self.helper.layout = Layout(
            Field("username"),
            Field("password"),
            FormActions(
                Submit("submit", _("Login"), css_class="btn btn-primary"),
                css_class="mt-2"
            )
        )