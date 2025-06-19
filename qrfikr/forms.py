from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Review

BASE_INPUT_CLASSES = (
    "block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm "
    "focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
)
TEXT_INPUT_CLASSES = f"form-input {BASE_INPUT_CLASSES}"
TEXTAREA_CLASSES = f"form-textarea {BASE_INPUT_CLASSES}"
FILE_INPUT_CLASSES = (
    "form-control block w-full text-sm text-gray-900 border border-gray-300 "
    "rounded-lg cursor-pointer bg-gray-50 focus:outline-none"
)


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ['rating', 'category', 'text', 'photo', 'contact_info']
        widgets = {
            'rating': forms.RadioSelect(
                choices=Review.RATING_CHOICES,
                attrs={'class': 'space-x-2'}
            ),
            'category': forms.Select(attrs={'class': TEXT_INPUT_CLASSES}),
            'text': forms.Textarea(attrs={'rows': 4, 'class': TEXTAREA_CLASSES}),
            'photo': forms.ClearableFileInput(attrs={'class': FILE_INPUT_CLASSES}),
            'contact_info': forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES}),
        }
        labels = {
            'text': _('Feedback'),
            'category': _('Category'),
            'photo': _('Photo'),
            'contact_info': _('Contact info'),
        }