from django import template

register = template.Library()

@register.filter(name='add_css_class')
def add_css_class(field, css_class):
    return field.as_widget(attrs={"class": css_class})