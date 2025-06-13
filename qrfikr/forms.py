from django import forms
from .models import Review
from django.utils.translation import gettext_lazy as _


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ['rating', 'text', 'photo', 'contact_info']
        widgets = {
            'rating': forms.RadioSelect(choices=Review.RATING_CHOICES),
            'text': forms.Textarea(attrs={'rows': 4}),
        }
        labels = {
            'text': _('Feedback'),
            'photo': _('Photo'),
            'contact_info': _('Contact info'),
        }
