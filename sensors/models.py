from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from config import settings
from simple_history.models import HistoricalRecords

class SensorData(models.Model):
    sensor_id = models.CharField(max_length=100)
    temperature = models.FloatField(null=True)
    humidity = models.FloatField(null=True)
    heat_index = models.FloatField(null=True)
    uptime = models.CharField(max_length=50)
    datetime = models.DateTimeField(default=timezone.now)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    status = models.BooleanField(default=False)
    history = HistoricalRecords()

    class Meta:
        permissions = [
            ("can_view_sensor_data", "Can view sensor data"),
            ("can_edit_sensor_data", "Can edit sensor data"),
        ]

    def __str__(self):
        return f"Sensor {self.sensor_id} - {self.datetime}"

    def save(self, *args, **kwargs):
        if not self.datetime:
            self.datetime = timezone.now()

        if self.pk:
            last_modified = SensorData.objects.filter(pk=self.pk).values_list('datetime', flat=True).first()
            if last_modified and timezone.now() - last_modified > timedelta(minutes=1):
                self.status = False
            else:
                self.status = True

        super().save(*args, **kwargs)
