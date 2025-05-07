# tasks/templatetags/app_filters.py
from django import template
import logging
import os
from urllib.parse import urlencode
from django.utils.safestring import mark_safe # Для безопасного вывода HTML
from datetime import timedelta
from ..models import Task # Для Task.TaskPriority

register = template.Library()
logger = logging.getLogger(__name__)


@register.filter(name="add_css_class")
def add_css_class(bound_field, css_class):
    """Добавляет CSS класс к виджету поля формы Django."""
    if hasattr(bound_field, 'field') and hasattr(bound_field.field, 'widget') and hasattr(bound_field.field.widget, 'attrs'):
        old_class = bound_field.field.widget.attrs.get('class', '')
        new_class = f'{old_class} {css_class}'.strip()
        return bound_field.as_widget(attrs={"class": new_class})
    return bound_field # Возвращаем поле как есть, если что-то пошло не так


@register.filter(name="get_key_from_dict") # Переименовал для ясности
def get_key_from_dict(dictionary, key):
    """
    Возвращает значение из словаря по ключу.
    Использование в шаблоне: {{ my_dictionary|get_key_from_dict:my_key_var }}
    """
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    logger.warning(f"Template tag 'get_key_from_dict' received non-dict type: {type(dictionary)} for key '{key}'")
    return None


@register.filter(name="get_attribute") # Переименовал для ясности
def get_attribute_from_object(obj, attr_name):
    """
    Получает атрибут объекта по имени. Возвращает None, если атрибут не найден.
    Использование: {{ my_object|get_attribute:"attribute_name_as_string" }}
    """
    try:
        return getattr(obj, str(attr_name), None)
    except Exception as e:
        logger.error(f"Error in template tag 'get_attribute' (obj: {type(obj)}, attr_name: {attr_name}): {e}")
        return None


@register.filter(name="add_attrs_to_field") # Переименовал для ясности
def add_attrs_to_field(bound_field, attr_string):
    """
    Добавляет произвольные атрибуты к виджету поля формы.
    Использование: {{ field|add_attrs_to_field:"placeholder=Введите текст,data-custom=значение" }}
    """
    try:
        attrs_dict = {}
        if attr_string:
            pairs = attr_string.split(",")
            for pair in pairs:
                if "=" in pair:
                    key, value = pair.split("=", 1)
                    attrs_dict[key.strip()] = value.strip().strip("\"'")
        
        if hasattr(bound_field, 'field') and hasattr(bound_field.field, 'widget') and hasattr(bound_field.field.widget, 'attrs'):
            # Объединяем существующие атрибуты с новыми
            current_attrs = bound_field.field.widget.attrs.copy()
            current_attrs.update(attrs_dict)
            return bound_field.as_widget(attrs=current_attrs)
        return bound_field.as_widget(attrs=attrs_dict) # Если нет существующих, просто устанавливаем новые
    except Exception as e:
        logger.error(f"Error adding attributes in template tag 'add_attrs_to_field': {e}")
        return bound_field


@register.filter(name="get_priority_tailwind_color") # Более специфичное имя
def get_priority_tailwind_color(priority_value):
    """
    Сопоставляет значение приоритета задачи с CSS-классом Tailwind для цвета (например, границы или фона).
    """
    try:
        priority_value = int(priority_value)
    except (ValueError, TypeError):
        return "border-gray-400 dark:border-gray-600" # Цвет по умолчанию

    color_map = {
        Task.TaskPriority.HIGH: "border-red-500 dark:border-red-400",
        Task.TaskPriority.MEDIUM_HIGH: "border-orange-500 dark:border-orange-400",
        Task.TaskPriority.MEDIUM: "border-yellow-500 dark:border-yellow-400",
        Task.TaskPriority.MEDIUM_LOW: "border-blue-500 dark:border-blue-400", # Или другой цвет, например, lime
        Task.TaskPriority.LOW: "border-green-500 dark:border-green-400",
    }
    return color_map.get(priority_value, "border-gray-400 dark:border-gray-600")


@register.filter(name="replace_str") # Переименовал для ясности
def replace_str(value, args_str):
    """Заменяет вхождения строки. Аргументы: 'старое,новое'"""
    if not isinstance(value, str) or not args_str:
        return value
    try:
        old_str, new_str = args_str.split(",", 1) # Разделяем только по первой запятой
        return value.replace(old_str, new_str)
    except ValueError:
        logger.warning(f"Invalid arguments for replace_str filter: '{args_str}'. Expected 'old,new'.")
        return value


@register.simple_tag(takes_context=True)
def query_transform(context, **kwargs): # Переименовал для лучшего понимания
    """
    Обновляет или добавляет GET-параметры в текущем URL.
    Используется для пагинации, сортировки, фильтрации.

    Пример использования:
    <a href="?{% query_transform page=paginator.next_page_number sort=current_sort %}">Next</a>
    <a href="?{% query_transform sort='title' %}">Sort by Title</a>
    <a href="?{% query_transform sort='-title' %}">Sort by Title DESC</a>
    <a href="?{% query_transform filter_status='new' page=1 %}">Filter by New Status</a>
    """
    request = context.get("request")
    if not request:
        logger.error("Request object not found in context for query_transform tag.")
        return ""
    
    query_params = request.GET.copy() # Копируем текущие GET-параметры

    for key, value in kwargs.items():
        # Если значение None или пустая строка, удаляем параметр (для сброса фильтров)
        if value is None or str(value) == '':
            query_params.pop(key, None)
        else:
            query_params[key] = str(value) # Устанавливаем или обновляем параметр

    return query_params.urlencode()


@register.filter(name='basename') # Переименовал для ясности
def basename_from_path(file_path_or_field):
    """ Извлекает имя файла из пути или FileField. """
    path_to_process = None
    if hasattr(file_path_or_field, 'name'): # Для FileField
        path_to_process = file_path_or_field.name
    elif isinstance(file_path_or_field, str): # Для строки пути
        path_to_process = file_path_or_field
    
    if path_to_process:
        return os.path.basename(path_to_process)
    return file_path_or_field # Возвращаем исходное значение, если не удалось обработать


@register.filter(name="timedelta_to_hm_str")
def timedelta_to_hm_str(td_value):
    """Преобразует timedelta в строку "Xч Yм" или "Yм", если часы = 0."""
    if not isinstance(td_value, timedelta):
        return ""
    
    total_seconds = int(td_value.total_seconds())
    if total_seconds < 0: # Не обрабатываем отрицательные значения здесь
        return "0м"

    days = total_seconds // 86400
    remaining_seconds_after_days = total_seconds % 86400
    
    hours = remaining_seconds_after_days // 3600
    remaining_seconds_after_hours = remaining_seconds_after_days % 3600
    
    minutes = remaining_seconds_after_hours // 60

    parts = []
    if days > 0:
        parts.append(f"{days}д")
    if hours > 0:
        parts.append(f"{hours}ч")
    if minutes > 0 or (days == 0 and hours == 0): # Показываем минуты, если это единственное или есть другие части
        parts.append(f"{minutes}м")
    
    return " ".join(parts) if parts else "0м"