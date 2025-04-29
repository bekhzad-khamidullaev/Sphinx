# checklists/forms.py
from django import forms
from django.utils.translation import gettext_lazy as _
from django.forms import inlineformset_factory, BaseInlineFormSet
from .models import (
    ChecklistTemplate,
    ChecklistTemplateItem,
    Checklist,
    ChecklistResult,
    ChecklistItemStatus
)

# --- Form for Checklist Template ---
class ChecklistTemplateForm(forms.ModelForm):
    class Meta:
        model = ChecklistTemplate
        fields = ['name', 'category', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input block w-full'}), # Add Tailwind classes
            'category': forms.Select(attrs={'class': 'form-select block w-full'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-textarea block w-full'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-checkbox h-5 w-5'}),
        }

# --- FormSet for Template Items (Optional, can use basic modelformset) ---
# class ChecklistTemplateItemForm(forms.ModelForm):
#     class Meta:
#         model = ChecklistTemplateItem
#         fields = ['order', 'item_text']
#         widgets = { ... }

ChecklistTemplateItemFormSet = inlineformset_factory(
    ChecklistTemplate,
    ChecklistTemplateItem,
    fields=('order', 'item_text'),
    extra=1,
    can_delete=True,
    widgets={
        'item_text': forms.TextInput(attrs={'class': 'form-input block w-full', 'placeholder': _('Текст пункта...')}),
        'order': forms.NumberInput(attrs={'class': 'form-input w-16 text-center', 'min': '0'}),
    }
)


# --- FormSet for Checklist Results (used in Perform View) ---
class BaseChecklistResultFormSet(BaseInlineFormSet):
    def add_fields(self, form, index):
        super().add_fields(form, index)
        # Display the item text read-only in the formset form
        form.fields['template_item_text'] = forms.CharField(
            label=_("Пункт"),
            initial=form.instance.template_item.item_text if form.instance else '',
            required=False,
            widget=forms.TextInput(attrs={'readonly': True, 'class': 'form-input block w-full bg-gray-100 dark:bg-dark-700 border-none'})
        )
        # Optionally reorder fields
        if 'template_item_text' in form.fields:
             form.order_fields(['template_item_text', 'status', 'comments'])


ChecklistResultFormSet = inlineformset_factory(
    Checklist, # Parent model
    ChecklistResult, # Model for the formset
    formset=BaseChecklistResultFormSet, # Use custom formset base class
    fields=('status', 'comments'), # Fields to edit
    extra=0, # Don't show extra forms, only those linked to template items
    can_delete=False, # Cannot delete results during performance
    widgets={
        # Using RadioSelect for better usability
        'status': forms.RadioSelect(attrs={'class': 'inline-flex items-center space-x-2'}),
        'comments': forms.Textarea(attrs={'rows': 1, 'class': 'form-textarea block w-full text-sm', 'placeholder': _('Комментарий (если нужно)...')}),
    }
)