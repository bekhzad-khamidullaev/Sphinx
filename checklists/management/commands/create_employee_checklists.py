from django.core.management.base import BaseCommand
from checklists.models import ChecklistTemplate, ChecklistTemplateItem

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

        if created_onb:
            ChecklistTemplateItem.objects.get_or_create(
                template=onboarding,
                order=1,
                item_text="Оформить трудовой договор",
            )
            ChecklistTemplateItem.objects.get_or_create(
                template=onboarding,
                order=2,
                item_text="Создать учетную запись и выдать доступы",
            )

        if created_off:
            ChecklistTemplateItem.objects.get_or_create(
                template=offboarding,
                order=1,
                item_text="Собрать оборудование и документы",
            )
            ChecklistTemplateItem.objects.get_or_create(
                template=offboarding,
                order=2,
                item_text="Заблокировать учетную запись",
            )

        if created_onb or created_off:
            self.stdout.write(self.style.SUCCESS("Checklist templates created"))
        else:
            self.stdout.write(self.style.NOTICE("Checklist templates already exist"))

