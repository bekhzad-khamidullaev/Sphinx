from django.db.models import Count
from .models import Task

def task_summary_report():
    """
    Формирует отчет о количестве задач по статусам.

    Возвращает словарь, где:
        - ключи — строковые названия статусов задач,
        - значения — количество задач с этим статусом.
    """
    task_counts = (
        Task.objects.values("status")
        .annotate(count=Count("id"))
        .order_by("status")
    )

    return {item["status"]: item["count"] for item in task_counts}
