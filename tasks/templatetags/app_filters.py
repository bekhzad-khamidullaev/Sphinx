# tasks/templatetags/app_filters.py
from django import template
import logging # Добавим логгирование для отладки

register = template.Library()
logger = logging.getLogger(__name__)

@register.filter(name='add_css_class')
def add_css_class(field, css_class):
    """Добавляет CSS класс к виджету поля формы."""
    try:
        return field.as_widget(attrs={"class": css_class})
    except Exception as e:
        logger.error(f"Error adding CSS class in template tag: {e}")
        return field # Возвращаем поле как есть в случае ошибки

@register.filter(name='getkey')
def getkey(dictionary, key):
    """
    Возвращает значение из словаря по ключу.
    Использование в шаблоне: {{ dictionary|getkey:key }}
    """
    try:
        # Проверяем, что dictionary действительно словарь
        if isinstance(dictionary, dict):
            return dictionary.get(key, '')
        else:
            logger.warning(f"Template tag 'getkey' received non-dict type: {type(dictionary)}")
            return ''
    except Exception as e:
        logger.error(f"Error in template tag 'getkey': {e}")
        return ''

# --- ИСПРАВЛЕНИЕ ЗДЕСЬ ---
@register.filter(name='getattr')
def get_attribute(obj, attr_name, default=None):
    """
    Получает атрибут объекта по имени. Возвращает default, если атрибут не найден.
    Использование: {{ my_object|getattr:"attribute_name" }}
                 {{ my_object|getattr:"attribute_name, 'значение по умолчанию'" }}
                 (Примечание: default как строка может быть неудобно, возможно, лучше оставить None)
    """
    try:
        # Используем встроенную getattr с тремя аргументами
        return getattr(obj, str(attr_name), default)
    except Exception as e:
        # Логгируем ошибку, если что-то пошло не так (например, attr_name не строка)
        logger.error(f"Error in template tag 'getattr' (obj: {obj}, attr_name: {attr_name}): {e}")
        return default # Возвращаем значение по умолчанию в случае ошибки
# --- КОНЕЦ ИСПРАВЛЕНИЯ ---

# Фильтр для добавления атрибутов (может быть полезен)
@register.filter(name='attr')
def add_attr(field, attr_string):
    """
    Добавляет произвольные атрибуты к виджету поля формы.
    Использование: {{ field|attr:"placeholder=Введите текст, data-custom=значение" }}
    """
    try:
        attrs = {}
        pairs = attr_string.split(',')
        for pair in pairs:
            if '=' in pair:
                key, value = pair.split('=', 1)
                attrs[key.strip()] = value.strip().strip('"\'') # Убираем кавычки
        return field.as_widget(attrs=attrs)
    except Exception as e:
         logger.error(f"Error adding attributes in template tag 'attr': {e}")
         return field