# tasks/templatetags/app_filters.py
from django import template
import logging  # Добавим логгирование для отладки
from ..models import Task
from urllib.parse import urlencode
import os

register = template.Library()
logger = logging.getLogger(__name__)


@register.filter(name="add_css_class")
def add_css_class(field, css_class):
    """Добавляет CSS класс к виджету поля формы."""
    try:
        return field.as_widget(attrs={"class": css_class})
    except Exception as e:
        logger.error(f"Error adding CSS class in template tag: {e}")
        return field  # Возвращаем поле как есть в случае ошибки


@register.filter(name="getkey")
def getkey(dictionary, key):
    """
    Возвращает значение из словаря по ключу.
    Использование в шаблоне: {{ dictionary|getkey:key }}
    """
    try:
        # Проверяем, что dictionary действительно словарь
        if isinstance(dictionary, dict):
            return dictionary.get(key, "")
        else:
            logger.warning(
                f"Template tag 'getkey' received non-dict type: {type(dictionary)}"
            )
            return ""
    except Exception as e:
        logger.error(f"Error in template tag 'getkey': {e}")
        return ""


# --- ИСПРАВЛЕНИЕ ЗДЕСЬ ---
@register.filter(name="getattr")
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
        logger.error(
            f"Error in template tag 'getattr' (obj: {obj}, attr_name: {attr_name}): {e}"
        )
        return default  # Возвращаем значение по умолчанию в случае ошибки


# --- КОНЕЦ ИСПРАВЛЕНИЯ ---


# Фильтр для добавления атрибутов (может быть полезен)
@register.filter(name="attr")
def add_attr(field, attr_string):
    """
    Добавляет произвольные атрибуты к виджету поля формы.
    Использование: {{ field|attr:"placeholder=Введите текст, data-custom=значение" }}
    """
    try:
        attrs = {}
        pairs = attr_string.split(",")
        for pair in pairs:
            if "=" in pair:
                key, value = pair.split("=", 1)
                attrs[key.strip()] = value.strip().strip("\"'")  # Убираем кавычки
        return field.as_widget(attrs=attrs)
    except Exception as e:
        logger.error(f"Error adding attributes in template tag 'attr': {e}")
        return field


@register.filter(name="get_priority_color")
def get_priority_color(priority_value):
    """
    Maps a Task priority integer value to a Tailwind CSS border color class.
    """
    # Ensure priority_value is an integer if it comes directly from model
    try:
        priority_value = int(priority_value)
    except (ValueError, TypeError):
        return "border-gray-300 dark:border-gray-500"  # Default/fallback color

    if priority_value == Task.TaskPriority.HIGH:
        return "border-red-500 dark:border-red-400"
    elif priority_value == Task.TaskPriority.MEDIUM_HIGH:
        # Using Orange as an example for Medium-High
        return "border-orange-500 dark:border-orange-400"
    elif priority_value == Task.TaskPriority.MEDIUM:
        return "border-yellow-500 dark:border-yellow-400"
    elif priority_value == Task.TaskPriority.MEDIUM_LOW:
        # Using Blue as an example for Medium-Low
        return "border-blue-500 dark:border-blue-400"
    elif priority_value == Task.TaskPriority.LOW:
        return "border-green-500 dark:border-green-400"
    else:
        # Default color for unknown priorities
        return "border-gray-300 dark:border-gray-500"


@register.filter(name="replace")
def replace_string(value, args):
    """Replaces occurrences of a string with another."""
    if not isinstance(value, str) or not args:
        return value
    try:
        old, new = args.split(",")
        return value.replace(old, new)
    except ValueError:
        return value  # Error in arguments


@register.simple_tag(takes_context=True)
def url_replace(context, **kwargs):
    """
    Updates query parameters in the current URL.

    Usage: {% url_replace param1=value1 param2=value2 %}
    Example for page: {% url_replace page=page_obj.next_page_number %}
    Example for sort (toggles direction): {% url_replace sort=column_name %}
    Example for page and keeping sort: {% url_replace page=1 sort=current_sort %}

    It intelligently handles the 'sort' parameter to toggle direction.
    """
    request = context.get("request")
    if not request:
        logger.error("Request object not found in context for url_replace tag.")
        return ""
    query_params = request.GET.copy()

    for field, value in kwargs.items():
        # Special handling for 'sort' parameter to toggle direction
        if field == "sort":
            current_sort = query_params.get("sort")
            column_name = str(value) # Ensure it's a string
            if current_sort == column_name:
                query_params[field] = f"-{column_name}" # Toggle to descending
            elif current_sort == f"-{column_name}":
                 query_params[field] = column_name # Toggle back to ascending
                 # Alternatively, remove sort completely: del query_params[field]
            else:
                query_params[field] = column_name # Set initial ascending sort
            # Reset page when changing sort
            query_params.pop("page", None)
        elif value is None or value == '':
             query_params.pop(field, None) # Remove param if value is empty/None
        else:
            query_params[field] = str(value) # Set/update other params

    return query_params.urlencode()

@register.filter(name='filename')
def filename(value):
    """ Extracts filename from a FileField's name/path. """
    if hasattr(value, 'name'):
        return os.path.basename(value.name)
    elif isinstance(value, str):
         return os.path.basename(value)
    return value