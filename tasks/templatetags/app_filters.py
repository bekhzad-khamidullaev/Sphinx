# tasks/templatetags/app_filters.py
from django import template
import logging  # Добавим логгирование для отладки
from ..models import Task
from urllib.parse import urlencode

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
def url_replace(context, field, value):
    """
    Replaces or adds a field/value query parameter to the current URL.
    Useful for pagination and sorting links.
    """
    query_params = context["request"].GET.copy()
    # Determine the next sort value (toggle direction)
    if field == "sort":
        current_sort = query_params.get("sort")
        if current_sort == value:  # If currently sorting ascending by this field
            query_params[field] = f"-{value}"  # Sort descending
        elif current_sort == f"-{value}":  # If currently sorting descending
            query_params[field] = value  # Sort ascending again
            # Alternatively, remove sort to go back to default:
            # del query_params[field]
        else:  # If sorting by another field or not sorting
            query_params[field] = value  # Sort ascending by this field
        # Reset page to 1 when changing sort order
        if "page" in query_params:
            del query_params["page"]
    else:
        # For other fields like 'page', just set the value
        query_params[field] = value

    return urlencode(query_params)
