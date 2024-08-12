from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords
from ipaddress import ip_address, IPv4Network
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_migrate
from django.dispatch import receiver
from django.contrib.auth.models import Group


@receiver(post_migrate)
def create_branch_permissions(sender, **kwargs):

    content_type = ContentType.objects.get_for_model(Branch)
    branches = Branch.objects.all()

    for branch in branches:
        if branch.name:
            codename = f'view_{branch.name.lower().replace(" ", "_")}'
            name = f'Can view devices in {branch.name}'
        else:
            codename = f'view_branch_{branch.pk}'
            name = f'Can view devices in Branch {branch.pk}'
        permission, created = Permission.objects.get_or_create(
            codename=codename,
            name=name,
            content_type=content_type,
        )


class Branch(models.Model):
    name = models.CharField(max_length=200, null=True, blank=True)
    
    class Meta:
        managed = True
        db_table = 'branch'

    def __str__(self):
        return self.name


class NetPingDevice(models.Model):
    ip_address = models.GenericIPAddressField(protocol='both', null=True, blank=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    hostname = models.CharField(max_length=200, null=True, blank=True)
    snmp_community_ro = models.CharField(max_length=20, default='device', null=True, blank=True)
    snmp_community_rw = models.CharField(max_length=20, default='device', null=True, blank=True)
    last_updated = models.DateTimeField(auto_now=True)
    status = models.BooleanField(default=False, null=True, blank=True)
    uptime = models.CharField(max_length=200, blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True, blank=True, null=True)

    class Meta:
        managed = True
        db_table = 'netping'
        unique_together = (('hostname', 'ip_address'),)
        indexes = [
            models.Index(fields=['status', 'hostname', 'ip_address']),
        ]

    def save(self, *args, **kwargs):
        self.last_update = timezone.now()
        super().save(*args, **kwargs)
        
    def __str__(self):
        return self.hostname or self.ip_address
    

class Sensor(models.Model):
    device = models.ForeignKey(NetPingDevice, on_delete=models.CASCADE)
    sensor_id = models.CharField(max_length=255)
    sensor_type = models.CharField(max_length=255)
    sensor_name = models.CharField(max_length=255)
    last_reading = models.FloatField()
    last_updated = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()
