from django.contrib import admin
from .models import SensorData

class SensorAdmin(admin.ModelAdmin):
    model = SensorData
    list_display = ['user','sensor_id']


admin.site.register(SensorData, SensorAdmin)

