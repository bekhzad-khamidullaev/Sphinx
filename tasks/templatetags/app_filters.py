from django import template

register = template.Library()

@register.filter(name='add_css_class')
def add_css_class(field, css_class):
    return field.as_widget(attrs={"class": css_class})


@register.filter(name='getkey')
def getkey(dictionary, key):
    """
    Возвращает значение из словаря по ключу.
    Использование в шаблоне: {{ dictionary|getkey:key }}
    """
    return dictionary.get(key, '')

@register.filter
def getattr(obj, attr):
    """Получает атрибут объекта или возвращает None."""
    return getattr(obj, attr, None)