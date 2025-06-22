# Модуль `AGENTS`

Эта документация описывает процесс разработки, структуру и стандарты для модуля `agents`. Модуль отвечает за управление сущностями "Агенты" в Django-проекте, предоставляя REST API для взаимодействия с мобильным или веб-приложением.

## 📜 Оглавление

1.  [Структура проекта](#-структура-проекта)
2.  [Разработка API](#-разработка-api)
    *   [Модель](#1-модель-данных-models)
    *   [Сериализатор](#2-сериализатор-serializers)
    *   [Представление (API ViewSet)](#3-представление-api-viewset)
    *   [Маршрутизация (URL)](#4-маршрутизация-urls)
3.  [Тестирование](#-тестирование)
4.  [Стиль кода](#-стиль-кода)
5.  [Безопасность](#-безопасность)
6.  [Инструменты](#-инструменты)
7.  [Работа с Git](#-работа-с-git-conventional-commits)
8.  [Ключевые рекомендации](#-ключевые-рекомендации)

---

## 📂 Структура проекта

Стандартная структура каталога `agents` для соблюдения консистентности.

```
project_root/
└── agents/
    ├── __init__.py               # Инициализация Python-пакета
    ├── admin.py                  # Регистрация моделей в Django Admin
    ├── apps.py                   # Конфигурация приложения
    ├── models.py                 # Модели базы данных (ORM)
    ├── serializers.py            # Сериализаторы DRF
    ├── views.py                  # Представления API (ViewSets)
    ├── urls.py                   # Маршруты (эндпоинты) API
    ├── permissions.py            # Пользовательские классы прав доступа (опционально)
    ├── services.py               # Бизнес-логика, вынесенная из представлений (опционально)
    └── tests/
        ├── __init__.py
        ├── test_models.py
        ├── test_views.py
        └── test_serializers.py
```

---

## ⚙️ Разработка API

Процесс создания нового эндпоинта включает четыре основных шага.

### 1. Модель данных (Models)

Определяем структуру данных в `agents/models.py`. Используйте `verbose_name` и `help_text` для улучшения читаемости в админ-панели и автодокументации API.

```python
# agents/models.py
from django.db import models

class Agent(models.Model):
    """Модель, представляющая агента."""
    name = models.CharField(
        "Имя агента",
        max_length=255
    )
    phone_number = models.CharField(
        "Номер телефона",
        max_length=20,
        help_text="Формат: +998901234567"
    )
    email = models.EmailField(
        "Email",
        unique=True,
        help_text="Уникальный email агента"
    )
    is_active = models.BooleanField(
        "Активен",
        default=True,
        help_text="Определяет, активен ли агент в системе"
    )
    created_at = models.DateTimeField(
        "Дата создания",
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        "Дата обновления",
        auto_now=True
    )

    class Meta:
        verbose_name = "Агент"
        verbose_name_plural = "Агенты"
        ordering = ['-created_at']

    def __str__(self):
        return self.name
```

### 2. Сериализатор (Serializers)

Преобразуем сложные типы данных (например, queryset'ы и экземпляры моделей) в нативные типы Python, которые легко преобразуются в JSON.

```python
# agents/serializers.py
from rest_framework import serializers
from .models import Agent

class AgentSerializer(serializers.ModelSerializer):
    """Сериализатор для модели Agent."""
    class Meta:
        model = Agent
        fields = (
            'id', 'name', 'phone_number', 'email',
            'is_active', 'created_at', 'updated_at'
        )
        read_only_fields = ('id', 'created_at', 'updated_at')
```

### 3. Представление (API ViewSet)

Обрабатываем HTTP-запросы и реализуем логику CRUD (Create, Retrieve, Update, Delete).

```python
# agents/views.py
from rest_framework import viewsets, permissions
from .models import Agent
from .serializers import AgentSerializer

class AgentViewSet(viewsets.ModelViewSet):
    """
    API эндпоинт для просмотра и редактирования агентов.
    Предоставляет полный набор CRUD-операций.
    """
    queryset = Agent.objects.filter(is_active=True)
    serializer_class = AgentSerializer
    permission_classes = [permissions.IsAuthenticated] # Доступ только для аутентифицированных пользователей
```

### 4. Маршрутизация (URLs)

Подключаем `ViewSet` к URL-адресам.

**В `agents/urls.py`:**

```python
# agents/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AgentViewSet

# Создаем роутер и регистрируем наш ViewSet
router = DefaultRouter()
router.register(r'agents', AgentViewSet, basename='agent')

# URL-адреса API определяются автоматически роутером
urlpatterns = [
    path('', include(router.urls)),
]
```

**Подключение в главном `project/urls.py`:**

```python
# project/urls.py
from django.urls import path, include

urlpatterns = [
    # ... другие пути
    path('api/v1/', include('agents.urls')), # Рекомендуется версионировать API
]
```

---

## ✅ Тестирование

Перед каждым коммитом обязательно запускайте тесты для вашего модуля.

```bash
python manage.py test agents
```

### Пример теста для View

Тесты должны покрывать как успешные сценарии, так и обработку ошибок.

```python
# agents/tests/test_views.py
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from agents.models import Agent

User = get_user_model()

class AgentAPITest(APITestCase):
    def setUp(self):
        """Настройка тестового окружения."""
        self.user = User.objects.create_user(username='testuser', password='securepassword123')
        self.client.force_authenticate(user=self.user)
        self.list_url = reverse('agent-list')

    def test_create_agent_success(self):
        """Проверка успешного создания агента."""
        data = {
            'name': 'Test Agent',
            'phone_number': '+998901234567',
            'email': 'agent@example.com'
        }
        response = self.client.post(self.list_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Agent.objects.count(), 1)
        self.assertEqual(Agent.objects.get().name, 'Test Agent')

    def test_create_agent_unauthorized(self):
        """Проверка, что неавторизованный пользователь не может создать агента."""
        self.client.logout()
        response = self.client.post(self.list_url, {})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
```

---

## 📐 Стиль кода

Соблюдение единого стиля кода критически важно для поддержки и развития проекта.

*   **Python**: Следуем **[PEP 8](https://www.python.org/dev/peps/pep-0008/)**.
*   **Автоформатирование**: Используем `black` для форматирования кода и `isort` для сортировки импортов.
*   **Линтинг**: Проверяем код с помощью `flake8`.
*   **Импорты**: Группируем в порядке:
    1.  Стандартные библиотеки Python (`os`, `sys`).
    2.  Сторонние библиотеки (`django`, `rest_framework`).
    3.  Локальные модули проекта (`.models`, `project.apps`).
*   **Именование**:
    *   `snake_case` для переменных, функций и методов.
    *   `CamelCase` для классов.

---

## 🔒 Безопасность

*   **Аутентификация и авторизация**: Всегда используйте `permission_classes`. По умолчанию — `IsAuthenticated`. Для сложной логики создавайте кастомные пермишены.
*   **Ограничение полей**: Не выводите в API чувствительные данные (хэши паролей, ключи). В сериализаторе используйте `fields` или `exclude` для точного контроля. Поля только для чтения указывайте в `read_only_fields`.
*   **Валидация**: Вся информация от пользователя должна проходить строгую валидацию в сериализаторах.
*   **Привязка к пользователю**: При создании объекта, связанного с текущим пользователем, устанавливайте связь на бэкенде, а не принимайте `user_id` от клиента.
    ```python
    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
    ```
*   **Ограничение запросов (Throttling)**: Настройте `throttling` в `settings.py` для защиты от DoS-атак.

---

## 🧪 Инструменты

*   **Документация API**: `drf-spectacular` (рекомендуется) или `drf-yasg` для автоматической генерации схемы OpenAPI 3.
*   **Тестирование**: `pytest` с плагинами (`pytest-django`, `pytest-cov`) или стандартный `unittest`.
*   **Отладка**: `django-debug-toolbar` для анализа запросов и `ipdb` для интерактивной отладки.
*   **Конфигурация**: `python-decouple` для управления настройками через переменные окружения (`.env`).

---

## 🔄 Работа с Git (Conventional Commits)

Используйте стандарт [Conventional Commits](https://www.conventionalcommits.org/) для сообщений к коммитам. Это упрощает анализ истории и автоматизацию релизов.

| Тип         | Назначение                                       |
| :---------- | :----------------------------------------------- |
| `feat`      | Новая функциональность (`feat(agents): ...`)     |
| `fix`       | Исправление ошибки (`fix(agents): ...`)          |
| `refactor`  | Рефакторинг кода без изменения поведения         |
| `test`      | Добавление или исправление тестов                |
| `docs`      | Изменения только в документации                  |
| `style`     | Правки стиля кода (форматирование, пропуски)     |
| `chore`     | Прочие изменения, не влияющие на код (сборка, CI) |

**Примеры:**

```bash
git commit -m "feat(agents): add api for creating agents"
git commit -m "fix(agents): correct email field serialization"
git commit -m "docs(agents): update development guide"
```

---

## 🧠 Ключевые рекомендации

*   **Сервисный слой**: Сложную бизнес-логику (например, отправка уведомлений, расчеты) выносите из `views.py` в отдельный файл `services.py`. Это упрощает переиспользование и тестирование.
*   **Оптимизация запросов**: Для предотвращения проблемы N+1 используйте `select_related` (для ForeignKey) и `prefetch_related` (для ManyToMany/ManyToOne) в `queryset` ваших ViewSet.
*   **Переменные окружения**: Никогда не храните секреты (ключи API, пароли от БД) в коде. Используйте `.env` файлы и библиотеку `python-decouple`.
*   **Логирование**: Настройте логирование для записи ошибок и важных событий в файл или внешнюю систему (Sentry, ELK).
*   **Консистентность**: Соблюдайте принятые в проекте конвенции, даже если они кажутся вам неидеальными. Единообразие важнее.
