# room/forms.py
import logging
from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory, BaseInlineFormSet
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model # Import get_user_model

from .models import Room

# Get the User model correctly AFTER apps are loaded
User = get_user_model()
logger = logging.getLogger(__name__)

# --- Reusable Tailwind CSS Classes ---
BASE_INPUT_CLASSES = "block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm dark:bg-dark-700 dark:border-dark-600 dark:text-gray-200 dark:placeholder-gray-500"
TEXT_INPUT_CLASSES = f"form-input {BASE_INPUT_CLASSES}"
SELECT_MULTI_CLASSES = f"form-multiselect {BASE_INPUT_CLASSES} h-40" # Set height for multi-select
CHECKBOX_CLASSES = "form-checkbox h-4 w-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500 dark:bg-dark-600 dark:border-dark-500 dark:checked:bg-indigo-500 dark:focus:ring-offset-dark-800"

class RoomForm(forms.ModelForm):
    """Form used primarily for VALIDATING room creation/edit data."""
    # Define the field type here, but set the queryset in __init__
    participants = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(), # Start with an empty queryset
        required=False,
        widget=forms.SelectMultiple(attrs={'class': SELECT_MULTI_CLASSES, 'size': '8'}),
        label=_("Участники (для приватных комнат)"),
        help_text=_("Выберите участников, если комната приватная (удерживайте Ctrl/Cmd для выбора нескольких).")
    )

    class Meta:
        model = Room
        fields = ['name', 'private', 'participants']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': TEXT_INPUT_CLASSES,
                'placeholder': _("Название новой комнаты...")
            }),
            'private': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
            # Participants widget is defined in the field above
        }
        labels = {
            'name': _("Название комнаты"),
            'private': _("Сделать приватной?"),
        }
        help_texts = {
             'private': _("Только добавленные участники смогут видеть приватную комнату и сообщения в ней."),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None) # Get the request user if passed
        super().__init__(*args, **kwargs)
        # Set the queryset for participants HERE, after User model is resolved
        participants_queryset = User.objects.filter(is_active=True)
        if self.user:
            # Exclude the current user from the list of choices
            participants_queryset = participants_queryset.exclude(pk=self.user.pk)
        self.fields['participants'].queryset = participants_queryset.order_by('username')
        logger.debug(f"RoomForm initialized. Participants queryset set (excluding user {self.user.pk if self.user else 'None'}).")


    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        if not name:
            raise forms.ValidationError(_("Название комнаты не может быть пустым."))
        # Optional: Check for existing room name uniqueness if desired
        # query = Room.objects.filter(name__iexact=name)
        # if self.instance and self.instance.pk: query = query.exclude(pk=self.instance.pk)
        # if query.exists(): raise forms.ValidationError(_("Комната с таким названием уже существует."))
        return name

    def clean(self):
        cleaned_data = super().clean()
        is_private = cleaned_data.get('private')
        participants = cleaned_data.get('participants')
        # Check if participants are required for a private room
        if is_private and not participants:
            logger.warning("Validation Error: Participants are required for a private room.")
            self.add_error('participants', _("Для приватной комнаты необходимо выбрать хотя бы одного участника."))
        return cleaned_data

    def save(self, commit=True):
        # Form's save now only handles basic saving and M2M.
        # Slug generation and explicit creator addition moved to the view.
        instance = super().save(commit=commit)
        # Note: save_m2m() is called *after* instance.save() in the view
        # Adding creator to participants is also handled in the view after save.
        return instance