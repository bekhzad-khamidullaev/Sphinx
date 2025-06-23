
---

## 📁 Структура приложения

```
project_root/
├── app/
│   ├── __init__.py
│   ├── models.py              # Определение моделей
│   ├── serializers.py         # DRF-сериализаторы
│   ├── views.py               # ViewSet'ы
│   ├── urls.py                # API-маршруты
│   ├── permissions.py         # Кастомные permissions (опционально)
│   ├── services.py            # Бизнес-логика (по необходимости)
│   └── tests/
│       ├── test_models.py
│       ├── test_views.py
│       ├── test_serializers.py
```

---

## ⚙️ Этапы генерации API

### 1. Модель

```python
# app/models.py
from django.db import models

class App(models.Model):
    name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=20)
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name
```

### 2. Сериализатор

```python
# app/serializers.py
from rest_framework import serializers
from .models import App

class AppSerializer(serializers.ModelSerializer):
    class Meta:
        model = App
        fields = ['id', 'name', 'phone_number', 'email', 'is_active']
```

### 3. ViewSet

```python
# app/views.py
from rest_framework import viewsets, permissions
from .models import App
from .serializers import AppSerializer

class AppViewSet(viewsets.ModelViewSet):
    queryset = App.objects.all()
    serializer_class = AppSerializer
    permission_classes = [permissions.IsAuthenticated]
```

### 4. URL-роутинг

```python
# app/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AppViewSet

router = DefaultRouter()
router.register(r'apps', AppViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
```

**Подключение в `project/urls.py`:**

```python
path('api/', include('app.urls')),
```

---

## 🧪 Тестирование

Перед коммитом всегда запускайте:

```bash
python manage.py test app
```

### Пример теста

```python
# app/tests/test_views.py
from rest_framework.test import APITestCase
from django.urls import reverse
from rest_framework import status
from django.contrib.auth.models import User
from app.models import App

class AppAPITest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester', password='testpass')
        self.client.login(username='tester', password='testpass')

    def test_create_app(self):
        url = reverse('app-list')
        data = {
            'name': 'Test App',
            'phone_number': '+998901112233',
            'email': 'test@app.com'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(App.objects.count(), 1)
```

---

## 🧹 Стиль и правила

* PEP8

* Отступ — 4 пробела

* Порядок импортов:

  1. Стандартные библиотеки
  2. Сторонние библиотеки
  3. Внутренние модули

* Именование:

  * `snake_case` для переменных и функций
  * `CamelCase` для классов

---

## 🔐 Безопасность

* Используйте `IsAuthenticated` или кастомные permissions
* Используйте `read_only_fields` для неизменяемых полей
* Проверяйте `request.user` в `perform_create`
* Включите `pagination`, `rate throttling` и `permissions` в `settings.py`

---

## 🧰 Инструменты

* Тесты: `pytest`, `unittest`, `APITestCase`
* Документация: `drf-yasg`, `drf-spectacular`
* Фикстуры: `factory_boy`, `mixer`
* API-клиенты: `httpie`, `curl`, `Postman`

---

## ✅ Conventional Commits

| Тип         | Назначение             |
| ----------- | ---------------------- |
| `feat:`     | Новая функциональность |
| `fix:`      | Исправление бага       |
| `test:`     | Тесты                  |
| `docs:`     | Документация           |
| `refactor:` | Рефакторинг            |

**Примеры:**

```bash
git commit -m "feat(app): добавлен ViewSet и маршруты"
git commit -m "fix(app): корректный формат поля email"
```

---

## 🧠 Лучшие практики

* Вынесите сложную логику в `services.py`
* Не перегружайте ViewSet
* Покрывайте тестами все действия
* Используйте `select_related` / `prefetch_related` для оптимизации запросов
* Добавьте OpenAPI-документацию для фронтенда или мобильного приложения

---
