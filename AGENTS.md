# AGENTS

Документация по разработке модуля **AGENTS** в Django-проекте с REST API для мобильного приложения.

---

## 📂 Структура проекта

```
project_root/
├── agents/
│   ├── __init__.py
│   ├── models.py              # Модели базы данных
│   ├── serializers.py         # DRF-сериализаторы
│   ├── views.py               # API-представления
│   ├── permissions.py         # Кастомные права доступа (если нужно)
│   ├── urls.py                # Маршруты API
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── test_models.py
│   │   ├── test_views.py
│   │   ├── test_serializers.py
│   └── services.py            # Бизнес-логика (опционально)
```

---

## ⚙️ Разработка API

### 1. Модель

```python
# agents/models.py
from django.db import models

class Agent(models.Model):
    name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=20)
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name
```

### 2. Сериализатор

```python
# agents/serializers.py
from rest_framework import serializers
from .models import Agent

class AgentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Agent
        fields = ['id', 'name', 'phone_number', 'email', 'is_active']
```

### 3. ViewSet

```python
# agents/views.py
from rest_framework import viewsets, permissions
from .models import Agent
from .serializers import AgentSerializer

class AgentViewSet(viewsets.ModelViewSet):
    queryset = Agent.objects.all()
    serializer_class = AgentSerializer
    permission_classes = [permissions.IsAuthenticated]
```

### 4. URL конфигурация

```python
# agents/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AgentViewSet

router = DefaultRouter()
router.register(r'agents', AgentViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
```

**Подключение в `project/urls.py`:**

```python
path('api/', include('agents.urls')),
```

---

## ✅ Тестирование

Перед коммитом обязательно запускайте:

```bash
python manage.py test agents
```

### Пример теста

```python
# agents/tests/test_views.py
from rest_framework.test import APITestCase
from django.urls import reverse
from rest_framework import status
from django.contrib.auth.models import User
from agents.models import Agent

class AgentAPITest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='pass')
        self.client.login(username='testuser', password='pass')

    def test_create_agent(self):
        url = reverse('agent-list')
        data = {
            'name': 'Test Agent',
            'phone_number': '+998901234567',
            'email': 'agent@example.com'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Agent.objects.count(), 1)
```

---

## 📐 Стиль кода

* Используйте **PEP8**
* Отступ — **4 пробела**
* Импорты:

  1. Стандартные библиотеки
  2. Сторонние библиотеки
  3. Локальные модули
* `snake_case` — для переменных и функций
* `CamelCase` — для классов

---

## 🔒 Безопасность

* Используйте `IsAuthenticated` или кастомные permissions
* Ограничивайте поля на запись (через `read_only_fields`)
* Проверяйте `request.user` при создании объектов
* Включите `pagination`, `throttle`, `rate limits` в `settings.py`

---

## 🧪 Инструменты

* Тестирование: `pytest`, `unittest`, `APITestCase`
* Документация API: `drf_yasg`, `drf-spectacular`
* Фикстуры или фабрики: `factory_boy`, `mixer`
* CLI: `httpie`, `curl`, `Postman`

---

## 🔄 Коммиты (Conventional Commits)

| Тип         | Назначение                    |
| ----------- | ----------------------------- |
| `feat:`     | Новая функциональность        |
| `fix:`      | Исправление ошибки            |
| `refactor:` | Рефакторинг без новой логики  |
| `test:`     | Добавлены/обновлены тесты     |
| `docs:`     | Обновлена только документация |

### Примеры:

```bash
git commit -m "feat(agent): реализован API для создания агента"
git commit -m "fix(agent): исправлена ошибка сериализации email"
```

---

## 🧠 Рекомендации

* Выносите бизнес-логику в `services.py`
* Не пишите сложную логику в ViewSet напрямую
* Покрывайте тестами каждое действие API (CRUD)
* Добавьте `OpenAPI`-документацию для интеграции с мобильным приложением
* Используйте `.select_related()` / `.prefetch_related()` при необходимости

---
