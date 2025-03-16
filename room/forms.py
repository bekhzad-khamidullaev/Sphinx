from django import forms
from user_profiles.models import User
from .models import Room

class RoomForm(forms.ModelForm):
    participants = forms.ModelMultipleChoiceField(queryset=User.objects.all(), required=False)

    class Meta:
        model = Room
        fields = ['name', 'private', 'participants']
