from .views.api_views import *
from .views.snmp_views import * 
from .views.device_views import *
from .views.problem_views import *
from rest_framework import routers, permissions
from rest_framework.routers import DefaultRouter
from django.urls import path, include
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

# DRF Router for API views
router = DefaultRouter()
router.register(r'devices', DeviceViewSet, basename='device')

# Swagger Schema View
schema_view = get_schema_view(
    openapi.Info(
        title="Monitoring API",
        default_version='v1',
        description="API для системы мониторинга",
        terms_of_service="https://www.google.com/policies/terms/",
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    # Device and SNMP related views
    path('', device_list, name='device_list'),
    path('device/<int:pk>/', device_detail, name='device_detail'),
    path('device/<int:pk>/snmpget/<str:oid_name>/<int:obj>/', snmp_get, name='snmp_get'),
    path('device/<int:pk>/snmpwalk/<str:oid>/', snmp_walk, name='snmp_walk'),

    # Problems and Comments related views
    path('problems/', problems_list, name='problems_list'),
    path('problems/<int:pk>/', problem_detail, name='problem_detail'),
    path('comments/<int:pk>/', comments_list, name='comments_list'),
    # Uncomment if you need comments_detail view
    # path('comments/<int:pk>/', comments_detail, name='comments_detail'),

    # API views using DRF router
    path('api/', include(router.urls)),
    path('api/create/', NetPingDeviceCreateView.as_view(), name='netping-create'),
    path('api/update/', update_sensor, name='sensor-create-update'),

    # Swagger and ReDoc documentation views
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('swagger.<format>/', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
]
