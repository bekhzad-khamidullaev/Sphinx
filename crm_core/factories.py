import factory
import random
from datetime import timedelta
from django.utils import timezone
from faker import Faker
from crm_core.models import Campaign, TaskCategory, TaskSubcategory, Task, TaskPhoto
from user_profiles.models import Team, User

fake = Faker()


class CampaignFactory(factory.django.DjangoModelFactory):
    """Фабрика для создания кампаний"""
    class Meta:
        model = Campaign

    name = factory.Sequence(lambda n: f"Campaign {n}")
    description = factory.LazyAttribute(lambda _: fake.text(max_nb_chars=200))
    start_date = factory.LazyFunction(timezone.now)
    end_date = factory.LazyFunction(lambda: timezone.now() + timedelta(days=random.randint(10, 100)))


class TaskCategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TaskCategory

    name = factory.Sequence(lambda n: f"Category {n}")
    description = factory.LazyAttribute(lambda _: fake.text(max_nb_chars=150))


class TaskSubcategoryFactory(factory.django.DjangoModelFactory):
    """Фабрика для создания подкатегорий задач"""
    class Meta:
        model = TaskSubcategory

    category = factory.SubFactory(TaskCategoryFactory)
    name = factory.Sequence(lambda n: f"SubCategory {n}")
    description = factory.LazyAttribute(lambda _: fake.text(max_nb_chars=150))


class TeamFactory(factory.django.DjangoModelFactory):
    """Фабрика для создания команд"""
    class Meta:
        model = Team

    name = factory.Sequence(lambda n: f"Team {n}")
    team_leader = factory.Iterator(User.objects.all())

    @factory.post_generation
    def members(self, create, extracted, **kwargs):
        """Добавляет пользователей в команду после создания"""
        if not create:
            return
        if extracted:
            self.members.set(extracted)  # Используем переданный список пользователей
        else:
            self.members.set(User.objects.order_by('?')[:5])  # Случайные 5 пользователей


class TaskFactory(factory.django.DjangoModelFactory):
    """Фабрика для создания задач"""
    class Meta:
        model = Task

    team = factory.SubFactory(TeamFactory)
    campaign = factory.SubFactory(CampaignFactory)
    category = factory.SubFactory(TaskCategoryFactory)
    subcategory = factory.SubFactory(TaskSubcategoryFactory)
    description = factory.LazyAttribute(lambda _: fake.text(max_nb_chars=250))
    assignee = factory.Iterator(User.objects.all())  # Берем случайного пользователя
    team = factory.Iterator(Team.objects.all())  # Берем случайную команду
    status = factory.LazyAttribute(lambda _: random.choice([s[0] for s in Task.TASK_STATUS_CHOICES]))
    priority = factory.LazyAttribute(lambda _: random.choice(Task.TaskPriority.values))
    deadline = factory.LazyFunction(lambda: timezone.now() + timedelta(days=random.randint(1, 30)))


class TaskPhotoFactory(factory.django.DjangoModelFactory):
    """Фабрика для создания фото к задачам"""
    class Meta:
        model = TaskPhoto

    task = factory.SubFactory(TaskFactory)
    photo = factory.django.ImageField(color='blue')  # Фейковое изображение
    description = factory.LazyAttribute(lambda _: fake.sentence())
