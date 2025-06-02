# qrfikr/templatetags/form_attrs.py
from django import template
from django.forms.boundfield import BoundField

register = template.Library()

@register.filter(name='attr')
def attr(field, attrs_str):
    if isinstance(field, BoundField):
        attrs = {}
        for pair in attrs_str.split(','):
            if ':' in pair:
                key, value = pair.split(':', 1)
                attrs[key.strip()] = value.strip()
        return field.as_widget(attrs=attrs)
    return str(field) # Or raise an error