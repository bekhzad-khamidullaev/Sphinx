# tasks/templatetags/app_filters.py
from django import template
import logging
from ..models import Task
from urllib.parse import urlencode
import os

register = template.Library()
logger = logging.getLogger(__name__)


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


@register.filter(name="get_priority_color")
def get_priority_color(priority_value):
    try:
        priority_value = int(priority_value)
    except (ValueError, TypeError):
        return "border-gray-300 dark:border-gray-500"

    if priority_value == Task.TaskPriority.HIGH:
        return "border-red-500 dark:border-red-400"
    elif priority_value == Task.TaskPriority.MEDIUM_HIGH:
        return "border-orange-500 dark:border-orange-400"
    elif priority_value == Task.TaskPriority.MEDIUM:
        return "border-yellow-500 dark:border-yellow-400"
    elif priority_value == Task.TaskPriority.MEDIUM_LOW:
        return "border-blue-500 dark:border-blue-400"
    elif priority_value == Task.TaskPriority.LOW:
        return "border-green-500 dark:border-green-400"
    else:
        return "border-gray-300 dark:border-gray-500"


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