from django.contrib import admin
from .models import NetPingDevice, Sensor

@admin.register(NetPingDevice)
class NetPingDeviceAdmin(admin.ModelAdmin):
    list_display = ('ip_address', 'location', 'last_updated')

@admin.register(Sensor)
class SensorAdmin(admin.ModelAdmin):
    list_display = ('device', 'sensor_id', 'sensor_type', 'sensor_name', 'last_reading', 'last_updated')
