import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'your_project_name.settings')  # Замените 'your_project_name' на имя вашего проекта
django.setup()

from faker import Faker
from crm_core.models import Project, TaskCategory, TaskSubcategory, Task, TaskPhoto
from user_profiles.models import Team, UserProfile  # Импортируем модели из user_profiles
from django.contrib.auth import get_user_model
from django.utils import timezone
import random
from datetime import timedelta

fake = Faker('ru_RU')  # Используем русскую локализацию для Faker, если нужно русские данные

def populate_projects(num_projects=5):
    """Создает фиктивные кампании."""
    for _ in range(num_projects):
        name = fake.company() + " кампания"
        project = Project(
            name=name,
            description=fake.text(),
            start_date=fake.date_between(start_date='-30d', end_date='today'),
            end_date=fake.date_between(start_date='today', end_date='+30d'),
        )
        project.save()
        print(f"Создана кампания: {project.name}")

def populate_task_categories(num_categories=5):
    """Создает фиктивные категории задач."""
    for _ in range(num_categories):
        name = fake.word().capitalize() + " Категория"
        category = TaskCategory(
            name=name,
            description=fake.text(),
        )
        category.save()
        print(f"Создана категория задач: {category.name}")

def populate_task_subcategories(num_subcategories=10):
    """Создает фиктивные подкатегории задач."""
    categories = TaskCategory.objects.all()
    if not categories:
        print("Сначала создайте категории задач!")
        return

    for _ in range(num_subcategories):
        category = random.choice(categories)
        name = fake.word().capitalize() + " Подкатегория"
        subcategory = TaskSubcategory(
            category=category,
            name=name,
            description=fake.text(),
        )
        subcategory.save()
        print(f"Создана подкатегория задач: {subcategory.name} в категории {category.name}")

def populate_tasks(num_tasks=20):
    """Создает фиктивные задачи."""
    projects = Project.objects.all()
    categories = TaskCategory.objects.all()
    subcategories = TaskSubcategory.objects.all()
    users = get_user_model().objects.all()  # Получаем всех пользователей
    teams = Team.objects.all() # Получаем все команды

    if not projects or not categories or not subcategories or not users or not teams:
        print("Сначала создайте кампании, категории, подкатегории, пользователей и команды!")
        return

    task_statuses = ["new", "in_progress", "on_hold", "completed", "cancelled", "overdue"]
    task_priorities = [Task.TaskPriority.HIGH, Task.TaskPriority.MEDIUM_HIGH, Task.TaskPriority.MEDIUM, Task.TaskPriority.MEDIUM_LOW, Task.TaskPriority.LOW]

    for _ in range(num_tasks):
        project = random.choice(projects)
        category = random.choice(categories) if categories else None
        subcategory = random.choice(subcategories) if subcategories else None
        assignee = random.choice(users) if users else None
        team = random.choice(teams) if teams else None
        created_by = random.choice(users) if users else None

        deadline = fake.date_time_between(start_date='now', end_date='+30d')
        start_date = fake.date_time_between(start_date='-30d', end_date='now')
        completion_date = None
        if random.random() < 0.5: # 50% задач будут выполнены
            completion_date = fake.date_time_between(start_date=start_date, end_date=deadline)


        task = Task(
            project=project,
            category=category,
            subcategory=subcategory,
            description=fake.text(),
            assignee=assignee,
            team=team,
            status=random.choice(task_statuses),
            priority=random.choice(task_priorities),
            deadline=deadline,
            start_date=start_date,
            completion_date=completion_date,
            estimated_time=timedelta(hours=random.randint(1, 24)), # Случайное время выполнения
            created_by=created_by,
        )
        task.save() # save() автоматически генерирует task_number
        print(f"Создана задача: {task.task_number} в кампании {project.name}")

def populate_task_photos(num_photos=30):
    """Создает фиктивные фотографии задач."""
    tasks = Task.objects.all()
    if not tasks:
        print("Сначала создайте задачи!")
        return

    for _ in range(num_photos):
        task = random.choice(tasks)
        # Для фиктивных данных можно не создавать реальные файлы, а просто указать путь или оставить поле photo пустым.
        # Если вы хотите использовать фиктивные изображения, вам потребуется более сложная настройка.
        task_photo = TaskPhoto(
            task=task,
            description=fake.sentence(),
            # photo = None  # Или можно указать путь к фиктивному изображению, если нужно
        )
        task_photo.save()
        print(f"Создано фото для задачи: {task.task_number}")


if __name__ == '__main__':
    print("Заполнение базы данных фиктивными данными...")

    # Важно соблюдать порядок создания, чтобы не было ошибок внешних ключей
    populate_projects()
    populate_task_categories()
    populate_task_subcategories()

    # Предполагается, что у вас уже есть пользователи и команды в системе.
    # Если нет, вам нужно будет добавить функции для их создания или создать их вручную.
    # Например, можно добавить функции populate_users() и populate_teams() если необходимо.

    populate_tasks()
    populate_task_photos()

    print("Заполнение базы данных завершено!")