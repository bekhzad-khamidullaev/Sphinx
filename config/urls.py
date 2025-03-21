from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls.i18n import set_language
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from django.conf.urls.i18n import i18n_patterns


# Swagger API документация
schema_view = get_schema_view(
    openapi.Info(
        title="ServiceDesk 2.0 API",
        default_version="v1",
        description="API для ServiceDesk 2.0",
        contact=openapi.Contact(email="contact@example.com"),
        license=openapi.License(name="BSD License"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)


urlpatterns = i18n_patterns(
    path('', include('user_profiles.urls')),

    path("__reload__/", include("django_browser_reload.urls")),

    # Панель администратора
    path("admin/", admin.site.urls),

    # Локализация
    path("i18n/", set_language, name="set_language"),
    path("api-auth/", include("rest_framework.urls")),

    # Подключение маршрутов приложения `tasks`
    path("core/", include("tasks.urls")),
    
    # Подключение маршрутов приложения `chats`
    path("rooms/", include("room.urls")),

    # Swagger UI
    path("swagger/", schema_view.with_ui("swagger", cache_timeout=0), name="schema-swagger-ui"),
    path("redoc/", schema_view.with_ui("redoc", cache_timeout=0), name="schema-redoc"),
) + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)