from django.db import models

class NetPingDevice(models.Model):
    ip_address = models.CharField(max_length=15)
    location = models.CharField(max_length=255, blank=True, null=True)
    last_updated = models.DateTimeField(auto_now=True)

class Sensor(models.Model):
    device = models.ForeignKey(NetPingDevice, on_delete=models.CASCADE)
    sensor_id = models.CharField(max_length=255)
    sensor_type = models.CharField(max_length=255)
    sensor_name = models.CharField(max_length=255)
    last_reading = models.FloatField()
    last_updated = models.DateTimeField(auto_now=True)
