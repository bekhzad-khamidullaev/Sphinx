from django.contrib import admin
from .models import NetPingDevice, Sensor, Problems, Comments

@admin.register(NetPingDevice)
class NetPingDeviceAdmin(admin.ModelAdmin):
    list_display = ('pk', 'hostname', 'location', 'last_updated')

@admin.register(Sensor)
class SensorAdmin(admin.ModelAdmin):
    list_display = ('pk', 'device', 'sensor_id', 'sensor_type', 'sensor_name')


@admin.register(Problems)
class ProblemsAdmin(admin.ModelAdmin):
    list_display = ('pk', 'host', 'problem_name', 'problem_severity')


@admin.register(Comments)
class CommentsAdmin(admin.ModelAdmin):
    list_display = ('pk', 'user', 'last_update', 'short_comment')

    def short_comment(self, obj):
        return obj.comment[:15] + '...' if len(obj.comment) > 15 else obj.comment

    short_comment.short_description = 'Comment'