# room/forms.py
from django import forms
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from .models import Room

User = get_user_model()

# Эти классы могут быть вынесены в глобальный файл стилей или определены в base.html,
# здесь для примера и консистентности с вашим исходным кодом
BASE_INPUT_CLASSES = "block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm dark:bg-dark-700 dark:border-dark-600 dark:text-gray-200 dark:placeholder-gray-500"
TEXT_INPUT_CLASSES = f"form-input {BASE_INPUT_CLASSES}"
SELECT_MULTI_CLASSES = f"form-multiselect {BASE_INPUT_CLASSES} h-40"
CHECKBOX_CLASSES = "form-checkbox h-4 w-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500 dark:bg-dark-600 dark:border-dark-500 dark:checked:bg-indigo-500 dark:focus:ring-offset-dark-800"


class RoomForm(forms.ModelForm):
    participants = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(), # Начальный пустой queryset
        required=False, # Не обязательно, если комната не приватная
        widget=forms.SelectMultiple(attrs={'class': SELECT_MULTI_CLASSES}),
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
        self.request_user = kwargs.pop('user', None) # Пользователь, создающий комнату
        super().__init__(*args, **kwargs)

        # Настраиваем queryset для участников, исключая текущего пользователя,
        # так как он будет добавлен автоматически.
        participants_qs = User.objects.filter(is_active=True).order_by('username')
        if self.request_user:
            participants_qs = participants_qs.exclude(pk=self.request_user.pk)
        self.fields['participants'].queryset = participants_qs

    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        if not name:
            raise forms.ValidationError(_("Название комнаты не может быть пустым."))
        # Можно добавить проверку на уникальность имени комнаты, если это требуется
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

        if is_private and not participants:
            # Для приватной комнаты можно требовать хотя бы одного участника *помимо создателя*.
            # Но если создатель добавляется автоматически, это условие может быть не нужно,
            # или его можно изменить на "хотя бы N участников".
            # Пока оставим как в вашем коде, если это было требование.
            self.add_error('participants', _("Для приватной комнаты выберите хотя бы одного участника (кроме вас)."))
        return cleaned_data