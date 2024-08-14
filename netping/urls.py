from .views import device_list, device_detail, snmp_get, update_sensor , snmp_walk, DeviceViewSet, NetPingDeviceCreateView
from rest_framework import routers, permissions
from rest_framework.routers import DefaultRouter 
from django.urls import path, include
from drf_yasg.views import get_schema_view
from drf_yasg import openapi


router = DefaultRouter()
router.register(r'devices', DeviceViewSet, basename='device')

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
    path('', device_list, name='device_list'),
    path('device/<int:device_id>/', device_detail, name='device_detail'),
    path('device/<int:device_id>/snmpget/<str:oid_name>/<int:obj>/', snmp_get, name='snmp_get'),
    path('device/<int:device_id>/snmpwalk/<str:oid>/', snmp_walk, name='snmp_walk'),
    path('api/', include(router.urls)),
    path('api/create/', NetPingDeviceCreateView.as_view(), name='netping-create'),
    path('api/update/', update_sensor, name='sensor-create-update'),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('swagger<format>/', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
]
