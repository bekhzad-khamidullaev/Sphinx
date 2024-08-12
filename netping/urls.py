from django.urls import path
from .views import device_list, device_detail, snmp_get, snmp_walk

urlpatterns = [
    path('', device_list, name='device_list'),
    path('device/<int:device_id>/', device_detail, name='device_detail'),
    path('device/<int:device_id>/snmpget/<str:oid_name>/<int:obj>/', snmp_get, name='snmp_get'),
    path('device/<int:device_id>/snmpwalk/<str:oid>/', snmp_walk, name='snmp_walk'),
]
