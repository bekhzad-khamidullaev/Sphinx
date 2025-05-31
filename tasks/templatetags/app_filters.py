# tasks/templatetags/app_filters.py
from django import template
from django.utils.safestring import mark_safe
import json
from django.core.serializers.json import DjangoJSONEncoder
import logging
from ..models import Task
from urllib.parse import urlencode
import os
from django.utils.timesince import timesince as timesince_
from django.utils.translation import gettext_lazy as _

register = template.Library()
logger = logging.getLogger(__name__)


@register.filter
def filename(value):
    if hasattr(value, 'name'):
        return os.path.basename(value.name)
    return str(value)

@register.filter(name='endswith_date')
def endswith_date(value):
    return value.endswith('date') or value.endswith('Date')

@register.filter(name='endswith_datetime')
def endswith_datetime(value):
    return value.endswith('datetime') or value.endswith('DateTime')

@register.filter(name='endswith_time')
def endswith_time(value):
    return value.endswith('time') or value.endswith('Time')

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)

@register.filter
def timesince_min_minutes(d, threshold_minutes=1):
    """
    Returns timesince if the difference is greater than threshold_minutes,
    otherwise returns None.
    threshold_minutes: The minimum difference in minutes to show the timesince.
    """
    if not d:
        return None
    # Calculate difference in seconds
    diff_seconds = (timezone.now() - d).total_seconds()
    if diff_seconds > (threshold_minutes * 60):
        return timesince_(d)
    return None


# Другие фильтры, если нужны, например, для приоритетов задач
@register.filter
def get_priority_border_color(priority_value):
    # Ваша логика для определения цвета рамки
    # priority_mapping = {
    #     Task.TaskPriority.HIGH: "border-red-500",
    #     Task.TaskPriority.MEDIUM: "border-yellow-500",
    #     ...
    # }
    # return priority_mapping.get(priority_value, "border-gray-300")
    return "border-gray-300" # Placeholder

@register.filter
def get_priority_text_color(priority_value):
    # Ваша логика
    return "text-gray-700" # Placeholder

@register.simple_tag(takes_context=True)
def url_replace(context, **kwargs):
    query = context['request'].GET.copy()
    for k, v in kwargs.items():
        query[k] = v
    return query.urlencode()

@register.filter
def add_if_not_empty(value, to_add):
    if value:
        return str(value) + str(to_add)
    return ''

@register.filter
def get_field_label(form, field_name):
    try:
        return form.fields[field_name].label
    except KeyError:
        return field_name.replace("_", " ").title()


@register.filter(name="add_css_class")
def add_css_class(field, css_class):
    try:
        return field.as_widget(attrs={"class": css_class})
    except Exception as e:
        logger.error(f"Error adding CSS class in template tag: {e}")
        return field


@register.filter(name="getkey")
def getkey(dictionary, key):
    try:
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


@register.filter(name="getattr")
def get_attribute(obj, attr_name, default=None):
    try:
        return getattr(obj, str(attr_name), default)
    except Exception as e:
        logger.error(
            f"Error in template tag 'getattr' (obj: {obj}, attr_name: {attr_name}): {e}"
        )
        return default


@register.filter(name="attr")
def add_attr(field, attr_string):
    try:
        attrs = {}
        pairs = attr_string.split(",")
        for pair in pairs:
            if "=" in pair:
                key, value = pair.split("=", 1)
                attrs[key.strip()] = value.strip().strip("\"'")
        return field.as_widget(attrs=attrs)
    except Exception as e:
        logger.error(f"Error adding attributes in template tag 'attr': {e}")
        return field


@register.filter
def get_item(dictionary, key):
    if hasattr(dictionary, 'get'):
        return dictionary.get(key)
    return None

@register.filter
def get_priority_color(priority_value):
    """
    Returns a border color class based on task priority.
    Example usage: class="border-l-4 {{ task.priority|get_priority_color }}"
    """
    # Assuming Task model is accessible here or you pass priority numeric value
    # from .models import Task # Avoid direct model import in templatetags if possible
    # Or use numeric values directly
    if priority_value == 1: # HIGH
        return 'border-red-500 dark:border-red-400'
    elif priority_value == 2: # MEDIUM_HIGH
        return 'border-orange-500 dark:border-orange-400'
    elif priority_value == 3: # MEDIUM
        return 'border-yellow-500 dark:border-yellow-400'
    elif priority_value == 4: # MEDIUM_LOW
        return 'border-blue-500 dark:border-blue-400'
    elif priority_value == 5: # LOW
        return 'border-green-500 dark:border-green-400'
    return 'border-gray-300 dark:border-gray-500' # Default

@register.filter
def get_priority_border_color(priority_value):
    if priority_value == 1: return 'border-red-500 dark:border-red-400'
    elif priority_value == 2: return 'border-orange-500 dark:border-orange-400'
    elif priority_value == 3: return 'border-yellow-500 dark:border-yellow-400'
    elif priority_value == 4: return 'border-blue-500 dark:border-blue-400'
    elif priority_value == 5: return 'border-green-500 dark:border-green-400'
    return 'border-gray-300 dark:border-gray-500'

@register.filter
def get_priority_text_color(priority_value):
    if priority_value == 1: return 'text-red-500 dark:text-red-400'
    elif priority_value == 2: return 'text-orange-500 dark:text-orange-400'
    elif priority_value == 3: return 'text-yellow-500 dark:text-yellow-400'
    elif priority_value == 4: return 'text-blue-500 dark:text-blue-400'
    elif priority_value == 5: return 'text-green-500 dark:text-green-400'
    return 'text-gray-500 dark:text-gray-400'


@register.filter(name='json_script')
def json_script(value, element_id):
    """
    Safely render a Python variable as JSON in a <script> tag.
    Encodes with DjangoJSONEncoder for date/time/decimal handling.
    Usage: {{ mydata|json_script:"my_data_script_id" }}
    """
    json_data = json.dumps(value, cls=DjangoJSONEncoder)
    return mark_safe(f'<script id="{element_id}" type="application/json">{json_data}</script>')


@register.filter(name="replace")
def replace_string(value, args):
    if not isinstance(value, str) or not args:
        return value
    try:
        old, new = args.split(",")
        return value.replace(old, new)
    except ValueError:
        return value


@register.simple_tag(takes_context=True)
def url_replace(context, **kwargs):
    request = context.get("request")
    if not request:
        logger.error("Request object not found in context for url_replace tag.")
        return ""
    query_params = request.GET.copy()

    for field, value in kwargs.items():
        if field == "sort":
            current_sort = query_params.get("sort")
            column_name = str(value)
            if current_sort == column_name:
                query_params[field] = f"-{column_name}"
            elif current_sort == f"-{column_name}":
                 query_params[field] = column_name
            else:
                query_params[field] = column_name
            query_params.pop("page", None)
        elif value is None or value == '':
             query_params.pop(field, None)
        else:
            query_params[field] = str(value)

    return query_params.urlencode()

@register.filter(name='filename')
def filename(value):
    if hasattr(value, 'name'):
        return os.path.basename(value.name)
    elif isinstance(value, str):
         return os.path.basename(value)
    return value