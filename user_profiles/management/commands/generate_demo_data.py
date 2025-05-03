from django.core.management.base import BaseCommand
from user_profiles.models import Department


class Command(BaseCommand):
    help = "Генерирует только отделы (структуру штата) для фастфуд-компании"

    def handle(self, *args, **kwargs):
        departments = [
            "Управление",
            "Бухгалтерия",
            "Кадровая служба",
            "Юридический отдел",
            "IT-отдел",
            "Отдел маркетинга",
            "Финансовый отдел",
            "Служба закупок",
            "Отдел логистики",
            "Операционный отдел",
            "Персонал ресторана",
        ]

        created_count = 0
        for name in departments:
            department, created = Department.objects.get_or_create(name=name)
            if created:
                created_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"✅ Сгенерировано {created_count} новых отделов (всего: {len(departments)})"
        ))
