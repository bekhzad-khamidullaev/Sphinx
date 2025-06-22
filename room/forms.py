# room/forms.py
from django import forms
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django_select2.forms import Select2MultipleWidget

from .models import Room

User = get_user_model()

# --- Base CSS classes ---
BASE_INPUT_CLASSES = "block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm transition duration-150 ease-in-out"
TEXT_INPUT_CLASSES = f"form-input {BASE_INPUT_CLASSES}"
# SELECT_MULTI_CLASSES = f"form-multiselect {BASE_INPUT_CLASSES} h-40" # Deprecated: using Select2 instead
CHECKBOX_CLASSES = "form-checkbox h-4 w-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500"


class RoomForm(forms.ModelForm):
    participants = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        required=False,
        widget=Select2MultipleWidget(attrs={
            'data-placeholder': _("Выберите участников..."),
            'class': 'form-select select2-basic block w-full text-sm'
        }),
        label=_("Участники"),
        help_text=_("Выберите участников, если комната приватная. Вы (создатель) будете добавлены автоматически.")
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
        }
        labels = {
            'name': _("Название комнаты"),
            'private': _("Сделать приватной?"),
        }
        help_texts = {
            'private': _("Только добавленные участники (и вы) смогут видеть приватную комнату и сообщения в ней."),
        }

    def __init__(self, *args, **kwargs):
        self.request_user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        participants_qs = User.objects.filter(is_active=True).order_by('username')
        if self.request_user:
            participants_qs = participants_qs.exclude(pk=self.request_user.pk)
        self.fields['participants'].queryset = participants_qs

    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        if not name:
            raise forms.ValidationError(_("Название комнаты не может быть пустым."))
        
        # Проверка на уникальность имени комнаты (если это бизнес-требование)
        # query = Room.objects.filter(name__iexact=name)
        # if self.instance and self.instance.pk:
        #     query = query.exclude(pk=self.instance.pk)
        # if query.exists():
        #     raise forms.ValidationError(_("Комната с таким названием уже существует."))
        return name

    def clean(self):
        cleaned_data = super().clean()
        is_private = cleaned_data.get('private')
        participants = cleaned_data.get('participants')

        # Если комната приватная, и не выбран ни один участник (кроме создателя, который добавляется во view),
        # можно выдавать ошибку. Однако, если создатель - единственный обязательный участник,
        # эта проверка может быть излишней, так как форма позволит создать приватную комнату без других участников.
        if is_private and not participants:
            # Раскомментируйте, если хотите сделать выбор участников обязательным для приватных комнат
            # self.add_error('participants', _("Для приватной комнаты выберите хотя бы одного участника (кроме вас)."))
            pass # Сейчас разрешаем создавать приватные комнаты без доп. участников, создатель добавится во view.
        return cleaned_data
