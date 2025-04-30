# room/forms.py
from django import forms
from django.conf import settings
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from .models import Room

User = get_user_model()

# --- Tailwind CSS Classes ---
BASE_INPUT_CLASSES = "block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm dark:bg-dark-700 dark:border-dark-600 dark:text-gray-200 dark:placeholder-gray-500"
TEXT_INPUT_CLASSES = f"form-input {BASE_INPUT_CLASSES}"
SELECT_MULTI_CLASSES = f"form-multiselect {BASE_INPUT_CLASSES} h-40" # Set height for multi-select
CHECKBOX_CLASSES = "form-checkbox h-4 w-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500 dark:bg-dark-600 dark:border-dark-500 dark:checked:bg-indigo-500 dark:focus:ring-offset-dark-800"

class RoomForm(forms.ModelForm):
    """Form used primarily for VALIDATING room creation/edit data, not necessarily rendering."""
    participants = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(), # Set in __init__
        required=False,
        widget=forms.SelectMultiple(attrs={'class': SELECT_MULTI_CLASSES}),
        label=_("Участники")
    )

    class Meta:
        model = Room
        fields = ['name', 'private', 'participants']
        widgets = {
            'name': forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES}),
            'private': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
        }
        labels = {'name': _("Название"), 'private': _("Приватная?")}

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None) # Expect user initiating action
        super().__init__(*args, **kwargs)
        # Set queryset excluding the current user
        participants_queryset = User.objects.filter(is_active=True)
        if self.user:
            participants_queryset = participants_queryset.exclude(pk=self.user.pk)
        self.fields['participants'].queryset = participants_queryset.order_by('username')

    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        if not name:
            raise forms.ValidationError(_("Название комнаты не может быть пустым."))
        # Check uniqueness (slug is unique, name doesn't have to be, but maybe preferred)
        # slug = slugify(name) or "room"
        # query = Room.objects.filter(slug__startswith=slug) # Check potential slug conflicts more loosely?
        # if self.instance and self.instance.pk: query = query.exclude(pk=self.instance.pk)
        # if query.exists():
        #     # Consider suggesting alternatives or better error
        #     raise forms.ValidationError(_("Комната с похожим названием/URL уже существует."))
        return name

    def clean(self):
        cleaned_data = super().clean()
        is_private = cleaned_data.get('private')
        participants = cleaned_data.get('participants')
        if is_private and not participants:
            self.add_error('participants', _("Для приватной комнаты нужно выбрать участников."))
        return cleaned_data

    def save(self, commit=True):
        # Override save to generate slug and add creator
        instance = super().save(commit=False)
        if not instance.pk and not instance.slug:
             base_slug = slugify(instance.name) or "room"
             slug = base_slug
             counter = 1
             while Room.objects.filter(slug=slug).exists():
                  slug = f"{base_slug}-{counter}"
                  counter += 1
             instance.slug = slug
        if commit:
             instance.save()
             self.save_m2m()
             # Ensure creator is a participant
             if self.user and instance.pk: # Ensure instance is saved
                 instance.participants.add(self.user)
        return instance