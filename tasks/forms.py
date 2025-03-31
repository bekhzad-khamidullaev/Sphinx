# tasks/forms.py
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Field, Div, HTML
from crispy_forms.bootstrap import FormActions, PrependedText, AppendedText
from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm as BaseUserCreationForm # Import base form
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.forms import modelformset_factory, inlineformset_factory # Correct import for inlineformset_factory
from django.utils import timezone # For date/time validation

from .models import (
    Task, TaskPhoto, Project, TaskCategory,
    TaskSubcategory
)
# Импортируем User и Team из user_profiles
from user_profiles.models import User, Team, Department # Removed Role import

# --- Utility function for adding common attributes ---
def add_common_attrs(field, placeholder=None, input_class="form-control"): # Default BS5 class
    """Adds common attributes to a form field."""
    attrs = field.widget.attrs
    current_classes = attrs.get('class', '')
    attrs['class'] = f'{current_classes} {input_class}'.strip()
    if placeholder:
        attrs["placeholder"] = placeholder
    field.widget.attrs.update(attrs)

# --- Form for Team ---
class TeamForm(forms.ModelForm):
    members = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        widget=forms.SelectMultiple(attrs={'class': 'select2-multiple'}), # Example using Select2
        required=False,
        label=_("Участники")
    )

    class Meta:
        model = Team
        fields = ["name", "team_leader", "members", "department", "description"]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_common_attrs(self.fields["name"], placeholder=_("Название команды"))
        add_common_attrs(self.fields["description"], placeholder=_("Описание (опционально)"))
        add_common_attrs(self.fields["team_leader"], input_class='form-select')
        add_common_attrs(self.fields["department"], input_class='form-select')
        # Members field already customized above

        self.helper = FormHelper()
        self.helper.layout = Layout(
            Field("name"),
            Field("team_leader"),
            Field("department"),
            Field("members"), # Use the customized field
            Field("description"),
            FormActions(
                Submit("submit", _("Сохранить команду"), css_class="btn btn-primary"),
                # Add cancel button if needed, e.g., for modals
                # HTML('<button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Отмена</button>')
            )
        )

    # clean_name validation is handled by unique=True on the model field now


# --- Form for Project ---
class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ["name", "description", "start_date", "end_date"] # Add owner/status if needed
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date", 'class': 'form-control'}),
            "end_date": forms.DateInput(attrs={"type": "date", 'class': 'form-control'}),
            "description": forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_common_attrs(self.fields["name"], placeholder=_("Название проекта"))
        add_common_attrs(self.fields["description"], placeholder=_("Детальное описание проекта"))
        # Date fields styled via widget

        self.helper = FormHelper()
        self.helper.layout = Layout(
            Field("name"),
            Field("description"),
            Div(
                 Field("start_date", wrapper_class="col-md-6"),
                 Field("end_date", wrapper_class="col-md-6"),
                 css_class="row mb-3"
            ),
             # Add owner/status fields here if they exist
            FormActions(
                Submit("submit", _("Сохранить проект"), css_class="btn btn-primary"),
            )
        )

    # clean method validation for dates is handled by model's clean()


# --- Form for User Creation (Extending Django's base) ---
# Use this if you need more control than the default UserCreationForm
class UserCreateForm(BaseUserCreationForm): # Inherit from the base form
    # Add custom fields here if they are required on creation and not in BaseUserCreationForm
    email = forms.EmailField(required=True, label=_("Email"))
    first_name = forms.CharField(max_length=150, required=False, label=_("Имя"))
    last_name = forms.CharField(max_length=150, required=False, label=_("Фамилия"))
    phone_number = forms.CharField(max_length=20, required=False, label=_("Номер телефона"))
    job_title = forms.CharField(max_length=100, required=False, label=_("Должность"))
    department = forms.ModelChoiceField(
        queryset=Department.objects.all(),
        required=False,
        label=_("Отдел"),
        widget=forms.Select(attrs={'class': 'form-select'})
        )
    image = forms.ImageField(required=False, label=_("Аватар"))


    class Meta(BaseUserCreationForm.Meta):
        model = User # Use your custom User model
        # Fields included from BaseUserCreationForm: username, password1, password2
        # Add your custom fields:
        fields = BaseUserCreationForm.Meta.fields + (
            'email', 'first_name', 'last_name', 'phone_number',
            'job_title', 'department', 'image'
            )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Apply styling to all fields generically or individually
        for field_name, field in self.fields.items():
             add_common_attrs(field)
             if 'password' in field_name:
                 add_common_attrs(field, placeholder=_("Пароль"))
             elif field_name == 'username':
                 add_common_attrs(field, placeholder=_("Имя пользователя (логин)"))
             elif field_name == 'email':
                  add_common_attrs(field, placeholder=_("your@email.com"))

        self.helper = FormHelper()
        self.helper.layout = Layout(
             # Reuse fields from Meta
            Field("username"),
            Field("email"),
            Field("first_name"),
            Field("last_name"),
            Field("phone_number"),
            Field("job_title"),
            Field("department"),
            Field("image"),
            Field("password"), # Renamed from password1 by BaseUserCreationForm
            Field("password_confirmation"), # Renamed from password2
             FormActions(
                Submit("submit", _("Создать пользователя"), css_class="btn btn-primary"),
            )
        )

    def clean_email(self):
        # Add validation for unique email
        email = self.cleaned_data.get('email')
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError(_("Пользователь с таким email уже существует."))
        return email

# --- Form for User Update (Example) ---
class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = [ # Exclude sensitive fields like password unless handled separately
            'username', 'email', 'first_name', 'last_name', 'phone_number',
            'job_title', 'department', 'image', 'is_active', 'is_staff', 'groups' # Include groups/permissions if needed
        ]
        widgets = {
            'groups': forms.SelectMultiple(attrs={'class': 'select2-multiple'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if isinstance(field.widget, (forms.CheckboxInput)):
                 # Apply different class for checkboxes if needed
                 field.widget.attrs['class'] = 'form-check-input'
            elif isinstance(field.widget, (forms.Select, forms.SelectMultiple)):
                 field.widget.attrs['class'] = 'form-select'
            else:
                add_common_attrs(field)

        self.helper = FormHelper()
        self.helper.layout = Layout(
            # Structure the form layout
             Div(
                 Field('username', wrapper_class='col-md-6'),
                 Field('email', wrapper_class='col-md-6'),
                 css_class='row mb-3'
             ),
             Div(
                 Field('first_name', wrapper_class='col-md-6'),
                 Field('last_name', wrapper_class='col-md-6'),
                 css_class='row mb-3'
             ),
             Div(
                 Field('phone_number', wrapper_class='col-md-6'),
                 Field('job_title', wrapper_class='col-md-6'),
                 css_class='row mb-3'
             ),
             Field('department'),
             Field('image'),
             HTML('<hr>'),
             Div(
                 Field('is_active', wrapper_class='col-auto'),
                 Field('is_staff', wrapper_class='col-auto'),
                 css_class='row mb-3 align-items-center'
             ),
             Field('groups'), # Add permissions field if needed
             FormActions(
                Submit("submit", _("Сохранить изменения"), css_class="btn btn-primary"),
            )
        )
    def clean_email(self):
         # Ensure email remains unique when updating
        email = self.cleaned_data.get('email')
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise ValidationError(_("Пользователь с таким email уже существует."))
        return email


# --- Удаляем RoleForm ---
# class RoleForm(forms.ModelForm):
#    # ... (код RoleForm удален) ...
# ---


# --- Form for Task Category ---
class TaskCategoryForm(forms.ModelForm):
    class Meta:
        model = TaskCategory
        fields = ["name", "description"]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_common_attrs(self.fields["name"], placeholder=_("Название категории"))
        add_common_attrs(self.fields["description"], placeholder=_("Описание (опционально)"))

        self.helper = FormHelper()
        self.helper.layout = Layout(
            Field("name"),
            Field("description"),
            FormActions(
                Submit("submit", _("Сохранить категорию"), css_class="btn btn-primary"),
            )
        )
    # clean_name validation handled by unique=True on model


# --- Form for Task Subcategory ---
class TaskSubcategoryForm(forms.ModelForm):
    class Meta:
        model = TaskSubcategory
        fields = ["category", "name", "description"]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_common_attrs(self.fields["category"], input_class='form-select')
        add_common_attrs(self.fields["name"], placeholder=_("Название подкатегории"))
        add_common_attrs(self.fields["description"], placeholder=_("Описание (опционально)"))

        self.helper = FormHelper()
        self.helper.layout = Layout(
            Field("category"),
            Field("name"),
            Field("description"),
            FormActions(
                Submit("submit", _("Сохранить подкатегорию"), css_class="btn btn-primary"),
            )
        )
    # clean method validation for unique_together handled by model constraint


# --- Form for Task ---
class TaskForm(forms.ModelForm):
    # Fields for assigning users/roles - replace direct assignee/team
    responsible_user = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        required=False, # Make optional if responsibility is not always assigned initially
        label=_("Ответственный"),
        widget=forms.Select(attrs={'class': 'form-select select2-single'}) # Example Select2
    )
    executors = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        required=False,
        label=_("Исполнители"),
        widget=forms.SelectMultiple(attrs={'class': 'select2-multiple'}) # Example Select2
    )
    watchers = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        required=False,
        label=_("Наблюдатели"),
        widget=forms.SelectMultiple(attrs={'class': 'select2-multiple'}) # Example Select2
    )

    class Meta:
        model = Task
        # Remove assignee/team, add title
        fields = [
            "project", "title", "description", "category", "subcategory",
            "status", "priority", "deadline", "start_date", "estimated_time",
            # Add the role fields defined above
            "responsible_user", "executors", "watchers"
        ]
        widgets = {
            "deadline": forms.DateTimeInput(attrs={"type": "datetime-local", 'class': 'form-control'}),
            "start_date": forms.DateTimeInput(attrs={"type": "datetime-local", 'class': 'form-control'}),
            "description": forms.Textarea(attrs={'rows': 5}),
            # Use TimeInput for DurationField if only time matters, or handle parsing
            "estimated_time": forms.TextInput(attrs={'placeholder': _('Напр., 2h 30m'), 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        # Pop role data before calling super if updating an existing task
        initial_roles = {}
        instance = kwargs.get('instance')
        if instance:
             initial_roles['responsible_user'] = instance.user_roles.filter(role=TaskUserRole.RoleChoices.RESPONSIBLE).first().user if instance.user_roles.filter(role=TaskUserRole.RoleChoices.RESPONSIBLE).exists() else None
             initial_roles['executors'] = list(instance.user_roles.filter(role=TaskUserRole.RoleChoices.EXECUTOR).values_list('user_id', flat=True))
             initial_roles['watchers'] = list(instance.user_roles.filter(role=TaskUserRole.RoleChoices.WATCHER).values_list('user_id', flat=True))
             # Add initial roles to initial data if not already present
             kwargs['initial'] = {**initial_roles, **kwargs.get('initial', {})}


        super().__init__(*args, **kwargs)

        # Apply styling
        add_common_attrs(self.fields["project"], input_class='form-select')
        add_common_attrs(self.fields["title"], placeholder=_("Краткое название задачи"))
        add_common_attrs(self.fields["description"], placeholder=_("Подробное описание, шаги, требования..."))
        add_common_attrs(self.fields["category"], input_class='form-select')
        add_common_attrs(self.fields["subcategory"], input_class='form-select')
        add_common_attrs(self.fields["status"], input_class='form-select')
        add_common_attrs(self.fields["priority"], input_class='form-select')
        # Role fields styled via widgets in declaration

        # Dynamic filtering for subcategory based on category (requires JS)
        # self.fields['subcategory'].queryset = TaskSubcategory.objects.none()
        # if 'category' in self.data:
        #     # ... JS will populate this ...
        # elif self.instance and self.instance.pk and self.instance.category:
        #     self.fields['subcategory'].queryset = self.instance.category.subcategories.order_by('name')

        self.helper = FormHelper()
        self.helper.layout = Layout(
            Field("project"),
            Field("title"),
            Field("description"),
            Div(
                 Field("category", wrapper_class="col-md-6"),
                 Field("subcategory", wrapper_class="col-md-6"),
                 css_class="row mb-3"
            ),
             HTML("<hr>"),
             Field("responsible_user"),
             Field("executors"),
             Field("watchers"),
             HTML("<hr>"),
             Div(
                 Field("status", wrapper_class="col-md-6"),
                 Field("priority", wrapper_class="col-md-6"),
                 css_class="row mb-3"
            ),
            Div(
                 Field("start_date", wrapper_class="col-md-4"),
                 Field("deadline", wrapper_class="col-md-4"),
                 Field("estimated_time", wrapper_class="col-md-4"),
                 css_class="row mb-3"
            ),
            FormActions(
                Submit("submit", _("Сохранить задачу"), css_class="btn btn-primary"),
            )
        )

    def clean_estimated_time(self):
        # Example: Convert human-readable duration (e.g., "2h 30m") to DurationField
        # This requires a parsing library or custom logic
        duration_str = self.cleaned_data.get('estimated_time')
        if isinstance(duration_str, timedelta): # Already a timedelta?
            return duration_str
        if duration_str:
             try:
                 # Basic parsing example (needs improvement for robustness)
                 # Assume format like "Xh Ym" or "Ym" or "Xh"
                 parts = duration_str.lower().split()
                 hours = 0
                 minutes = 0
                 for part in parts:
                     if 'h' in part:
                         hours = int(part.replace('h', ''))
                     elif 'm' in part:
                         minutes = int(part.replace('m', ''))
                 if hours == 0 and minutes == 0 and duration_str.isdigit(): # Maybe just minutes entered
                      minutes = int(duration_str)

                 if hours > 0 or minutes > 0:
                      return timedelta(hours=hours, minutes=minutes)
                 else:
                      raise ValidationError(_("Неверный формат оценки времени. Используйте, например, '2h 30m', '1h', '45m'."))
             except (ValueError, TypeError):
                 raise ValidationError(_("Неверный формат оценки времени."))
        return None # Return None if empty

    def save(self, commit=True):
        # Override save to handle role assignment
        task = super().save(commit=False) # Get the task instance without saving yet

        if commit:
            if not hasattr(task, 'created_by') or not task.created_by:
                 # Attempt to get user from request if available (might need passing request to form)
                 # This is tricky, better to set created_by in the view before calling form.save()
                 pass
            task.save() # Save the task first to get an ID
            self._save_roles(task) # Save the roles from the form fields
            self.save_m2m() # Important for other M2M fields if any

        return task

    def _save_roles(self, task):
        # Clear existing roles managed by this form (resp, exec, watcher)
        TaskUserRole.objects.filter(
            task=task,
            role__in=[TaskUserRole.RoleChoices.RESPONSIBLE,
                      TaskUserRole.RoleChoices.EXECUTOR,
                      TaskUserRole.RoleChoices.WATCHER]
        ).delete()

        roles_to_create = []
        responsible = self.cleaned_data.get('responsible_user')
        executors = self.cleaned_data.get('executors', User.objects.none())
        watchers = self.cleaned_data.get('watchers', User.objects.none())

        # Keep track of users already assigned a primary role (Resp/Exec)
        primary_users = set()

        if responsible:
            roles_to_create.append(TaskUserRole(task=task, user=responsible, role=TaskUserRole.RoleChoices.RESPONSIBLE))
            primary_users.add(responsible)

        for user in executors:
             if user not in primary_users: # Don't make executor if already responsible
                roles_to_create.append(TaskUserRole(task=task, user=user, role=TaskUserRole.RoleChoices.EXECUTOR))
                primary_users.add(user)

        # Add creator as watcher automatically if not already assigned a role? (Optional)
        # creator = getattr(task, 'created_by', None)
        # if creator and creator not in primary_users:
        #     roles_to_create.append(TaskUserRole(task=task, user=creator, role=TaskUserRole.RoleChoices.WATCHER))
        #     primary_users.add(creator) # Add creator to primary_users to avoid double-adding below

        for user in watchers:
            if user not in primary_users: # Only add as watcher if not Responsible or Executor
                roles_to_create.append(TaskUserRole(task=task, user=user, role=TaskUserRole.RoleChoices.WATCHER))

        if roles_to_create:
            TaskUserRole.objects.bulk_create(roles_to_create, ignore_conflicts=True) # ignore_conflicts handles potential race conditions if needed


# --- Form for Task Photo ---
class TaskPhotoForm(forms.ModelForm):
    class Meta:
        model = TaskPhoto
        fields = ["photo", "description"] # Removed 'task' as it's handled by formset
        widgets = {
             'description': forms.Textarea(attrs={'rows': 2}),
             'photo': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_common_attrs(self.fields["description"], placeholder=_("Краткое описание фото (опционально)"))
        # self.helper = FormHelper() # Helper might be overkill for inline forms
        # self.helper.form_tag = False # Important for formsets
        # self.helper.disable_csrf = True


# --- FormSet for Task Photos ---
# Use inlineformset_factory in the view instead of defining a global formset here
# This allows passing the request/instance correctly.
# TaskPhotoFormSet = modelformset_factory(
#     TaskPhoto, form=TaskPhotoForm, extra=1, max_num=10, can_delete=True
# )


# --- Form for Login ---
class LoginForm(AuthenticationForm):
    # Inherits username/password fields
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Apply Bootstrap classes or Tailwind classes depending on your setup
        add_common_attrs(self.fields["username"], placeholder=_("Имя пользователя или Email"))
        add_common_attrs(self.fields["password"], placeholder=_("Пароль"))

        self.helper = FormHelper()
        self.helper.form_class = 'form-horizontal' # Or remove for default vertical layout
        self.helper.label_class = 'col-lg-2' # Adjust grid classes as needed
        self.helper.field_class = 'col-lg-10'
        self.helper.layout = Layout(
            Field("username"),
            Field("password"),
             # Add remember me checkbox if needed
             # Div(
             #     HTML('<a href="#">Забыли пароль?</a>'), # Link to password reset
             #     css_class='mb-3'
             # ),
            FormActions(
                Submit("submit", _("Войти"), css_class="btn btn-primary w-100"), # Full width button
            )
        )