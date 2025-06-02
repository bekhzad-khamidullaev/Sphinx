# qrfikr/forms.py
from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Review

class ReviewForm(forms.ModelForm):
    honeypot = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
        label=""
    )

    rating = forms.IntegerField(
        widget=forms.HiddenInput(attrs={'id': 'id_rating_hidden_input'}),
        min_value=1,
        max_value=5,
        required=True
    )

    class Meta:
        model = Review
        fields = ['rating', 'text', 'photo', 'contact_info']
        widgets = {
            'text': forms.Textarea(attrs={
                'rows': 6,
                'placeholder': _("Share your detailed experience, suggestions, or any issues you faced..."),
                'class': (
                    'w-full appearance-none bg-white dark:bg-slate-700/30 '
                    'text-slate-900 dark:text-slate-100 py-3 px-4 rounded-xl '
                    'border border-slate-300 dark:border-slate-600 '
                    'focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent '
                    'dark:focus:ring-indigo-400 dark:placeholder-slate-500 '
                    'transition-all duration-200 ease-in-out shadow-sm hover:shadow-md focus:shadow-lg text-base leading-relaxed'
                )
            }),
            'photo': forms.ClearableFileInput(attrs={
                'class': 'custom-file-input',
                'id': 'id_photo_input_actual'
            }),
            'contact_info': forms.TextInput(attrs={
                'placeholder': _("e.g., yourname@example.com or phone number"),
                'type': 'text',
                'class': (
                    'w-full appearance-none bg-white dark:bg-slate-700/30 '
                    'text-slate-900 dark:text-slate-100 py-3 px-4 rounded-xl '
                    'border border-slate-300 dark:border-slate-600 '
                    'focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent '
                    'dark:focus:ring-indigo-400 dark:placeholder-slate-500 '
                    'transition-all duration-200 ease-in-out shadow-sm hover:shadow-md focus:shadow-lg text-base'
                )
            }),
        }
        labels = {
            'rating': _("How would you rate your overall experience?"),
            'text': _("Your Detailed Feedback"),
            'photo': _("Attach a Photo (Optional)"),
            'contact_info': _("Contact Information (Optional)"),
        }
        help_texts = {
            'contact_info': _("We respect your privacy. This information will only be used to follow up on your feedback, if necessary."),
            'photo': _("Max file size 5MB. Allowed types: JPG, PNG, GIF, WEBP."),
        }
        error_messages = {
            'rating': {
                'required': _("Please select a rating to continue."),
                'min_value': _("Rating must be at least 1."),
                'max_value': _("Rating cannot be more than 5."),
            },
        }

    def clean_honeypot(self):
        value = self.cleaned_data['honeypot']
        if value:
            raise forms.ValidationError(_("Spam attempt detected."), code='spam_detected')
        return value

    def clean_rating(self):
        rating = self.cleaned_data.get('rating')
        if rating is None:
            raise forms.ValidationError(_("A rating is required."), code='rating_missing')
        
        # Проверяем, что значение рейтинга находится в допустимом диапазоне (1-5)
        # Это также покрывается min_value/max_value в определении поля, но можно и здесь.
        # RATING_CHOICES берутся из модели Review
        valid_ratings = [choice[0] for choice in Review.RATING_CHOICES]
        if rating not in valid_ratings:
             raise forms.ValidationError(_("Invalid rating value selected."), code='invalid_rating')
        return rating

    def clean_photo(self):
        photo = self.cleaned_data.get('photo', False)
        if photo:
            if photo.size > 5 * 1024 * 1024: # 5MB
                raise forms.ValidationError(_("The photo file is too large (max 5MB)."))
            
            valid_image_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
            if photo.content_type not in valid_image_types:
                raise forms.ValidationError(
                    _("Invalid file type. Only JPG, PNG, GIF, and WEBP images are allowed."),
                    code='invalid_image_type'
                )
        return photo