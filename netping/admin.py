from django.contrib import admin
from .models import NetPingDevice, Sensor, Problems

@admin.register(NetPingDevice)
class NetPingDeviceAdmin(admin.ModelAdmin):
    list_display = ('hostname', 'location', 'last_updated')

@admin.register(Sensor)
class SensorAdmin(admin.ModelAdmin):
    list_display = ('device', 'sensor_id', 'sensor_type', 'sensor_name', 'last_reading', 'last_updated')


@admin.register(Problems)
class ProblemsAdmin(admin.ModelAdmin):
    list_display = ('host', 'problem_name', 'problem_severity')