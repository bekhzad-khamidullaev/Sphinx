# user_profiles/management/commands/generate_demo_data.py

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from user_profiles.models import Department, Role
from faker import Faker
import random

User = get_user_model()
fake = Faker('ru_RU')


class Command(BaseCommand):
    help = "Генерирует базовые отделы, роли, руководителей и сотрудников для фастфуд-компании"

    def handle(self, *args, **kwargs):
        self.stdout.write("🚀 Генерация отделов, ролей и сотрудников...")

        structure = {
            "Управление": ["Генеральный директор"],
            "Бухгалтерия": ["Главный бухгалтер", "Бухгалтер"],
            "Кадровая служба": ["HR-директор", "HR-специалист"],
            "Юридический отдел": ["Юрист"],
            "IT-отдел": ["IT-директор", "Системный администратор", "DevOps", "Разработчик"],
            "Отдел маркетинга": ["Маркетолог", "SMM-менеджер"],
            "Финансовый отдел": ["Финансовый аналитик"],
            "Служба закупок": ["Менеджер по закупкам"],
            "Отдел логистики": ["Логист", "Курьер"],
            "Операционный отдел": ["Операционный менеджер"],
            "Персонал ресторана": ["Менеджер смены", "Кассир", "Повар", "Уборщик"]
        }

        created_users = []
        created_roles = {}

        for dept_name, job_titles in structure.items():
            department, _ = Department.objects.get_or_create(name=dept_name)

            head_user = None
            for i, title in enumerate(job_titles):
                # Создание роли при необходимости
                if title not in created_roles:
                    created_roles[title], _ = Role.objects.get_or_create(name=title)

                first_name = fake.first_name()
                last_name = fake.last_name()
                email = f"{first_name.lower()}.{last_name.lower()}@fastfood.local"
                username = f"{first_name.lower()}{last_name.lower()}{random.randint(100, 999)}"

                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password="demo1234",
                    first_name=first_name,
                    last_name=last_name,
                    job_title=title,
                    department=department,
                )
                user.roles.add(created_roles[title])
                created_users.append(user)

                if i == 0:
                    department.head = user
                    department.save()

        self.stdout.write(self.style.SUCCESS(
            f"✅ Сгенерировано {len(structure)} отделов, {len(created_roles)} ролей и {len(created_users)} сотрудников"
        ))
