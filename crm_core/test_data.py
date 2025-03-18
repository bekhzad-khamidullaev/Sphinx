from django.contrib.auth import get_user_model
from django.db import transaction
from user_profiles.models import Team
from crm_core.factories import (
    CampaignFactory, TaskCategoryFactory, TaskSubcategoryFactory, 
    TaskFactory, TaskPhotoFactory
)

User = get_user_model()


def create_users():
    """Создание тестовых пользователей."""
    if User.objects.count() < 10:
        print("Создаём пользователей...")
        users = [
            User.objects.create_user(username=f'test_user{i}', password='password123')
            for i in range(10)
        ]
        print(f"Создано {len(users)} пользователей")
    return list(User.objects.all())


def create_teams(users):
    """Создание тестовых команд."""
    if Team.objects.count() < 5:
        print("Создаём команды...")
        teams = []
        for i in range(5):
            team_leader = users[i % len(users)]
            team = Team.objects.create(name=f"Team {i}", team_leader=team_leader)
            team.members.set(users[:5])  # Добавляем первых 5 пользователей
            teams.append(team)
        print(f"Создано {len(teams)} команд")

    # Проверяем, что у всех команд есть лидер
    for team in Team.objects.filter(team_leader__isnull=True):
        team.team_leader = users[0]
        team.save()

    # Проверяем, что у всех команд есть участники
    for team in Team.objects.all():
        if team.members.count() == 0:
            team.members.set(users[:5])
            team.save()

    print("Команды успешно созданы и заполнены!")


def create_test_data():
    """Создание тестовых данных с Factory Boy."""
    print("Создаём тестовые данные...")

    campaigns = CampaignFactory.create_batch(5)
    print(f"Создано {len(campaigns)} кампаний")

    categories = TaskCategoryFactory.create_batch(10)
    print(f"Создано {len(categories)} категорий")

    subcategories = TaskSubcategoryFactory.create_batch(20)
    print(f"Создано {len(subcategories)} подкатегорий")

    tasks = TaskFactory.create_batch(500)  # Увеличено
    print(f"Создано {len(tasks)} задач")

    photos = TaskPhotoFactory.create_batch(1000)  # Увеличено
    print(f"Создано {len(photos)} фотографий")


def main():
    """Основной процесс создания данных."""
    with transaction.atomic():
        users = create_users()
        create_teams(users)
        create_test_data()

    print("База данных полностью заполнена тестовыми данными!")


if __name__ == "__main__":
    main()