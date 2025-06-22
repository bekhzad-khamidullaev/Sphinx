from django.core.management.base import BaseCommand
from checklists.models import ChecklistTemplate

class Command(BaseCommand):
    help = "Create onboarding and offboarding checklist templates"

    def handle(self, *args, **options):
        onboarding, created_onb = ChecklistTemplate.objects.get_or_create(
            name="Чеклист на прием нового сотрудника",
            defaults={"description": "Задачи и документы для онбординга"}
        )
        offboarding, created_off = ChecklistTemplate.objects.get_or_create(
            name="Чеклист на увольнение",
            defaults={"description": "Задачи при завершении работы сотрудника"}
        )
        if created_onb or created_off:
            self.stdout.write(self.style.SUCCESS("Checklist templates created"))
        else:
            self.stdout.write(self.style.NOTICE("Checklist templates already exist"))

