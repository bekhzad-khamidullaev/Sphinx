from django.db import models
from django.core.cache import cache
from encrypted_model_fields.fields import EncryptedCharField
from django.utils import timezone
from simple_history.models import HistoricalRecords
from ipaddress import ip_address, IPv4Network
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_migrate
from django.dispatch import receiver
from django.contrib.auth.models import Group
from django.conf import settings


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
    snmp_community_ro = EncryptedCharField(max_length=100, default='SWITCH', null=True, blank=True)
    snmp_community_rw = EncryptedCharField(max_length=100, default='SWITCH', null=True, blank=True)
    last_updated = models.DateTimeField(auto_now=True)
    status = models.BooleanField(default=False, null=True, blank=True)
    uptime = models.CharField(max_length=200, blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True, blank=True, null=True)

    def get_device_status(self):
        cache_key = f'device_status_{self.pk}'
        status = cache.get(cache_key)

        if status is None:
            status = self.status  # получаем статус из базы данных
            cache.set(cache_key, status, timeout=settings.CACHE_TIMEOUT)

    class Meta:
        managed = True
        db_table = 'netping'
        unique_together = (('hostname', 'ip_address'),)
        indexes = [
            models.Index(fields=['status', 'hostname', 'ip_address']),
        ]

    def save(self, *args, **kwargs):
        self.last_updated = timezone.now()
        super().save(*args, **kwargs)
        
    def __str__(self):
        return self.hostname or self.ip_address
    

class Sensor(models.Model):
    device = models.ForeignKey(NetPingDevice, on_delete=models.CASCADE, related_name='sensor_set')
    sensor_id = models.CharField(max_length=255)
    sensor_type = models.CharField(max_length=255)
    sensor_name = models.CharField(max_length=255)
    status = models.IntegerField(default=0)
    value_high_trshld = models.IntegerField(default=0)
    value_current = models.FloatField()
    value_low_trshld = models.IntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)
    # problem = models.ForeignKey('Problems', on_delete=models.SET_NULL, null=True, blank=True, related_name='sensor')
    history = HistoricalRecords()

    def save(self, *args, **kwargs):
        self.last_updated = timezone.now()
        super().save(*args, **kwargs)


class Problems(models.Model):
    SEVERITY = {
        "notclassified" : "Not classified",
        "information" : "Information",
        "warning" : "Warning",
        "average" : "Average",
        "high" : "High",
        "disaster" : "Disaster"
    }
    host = models.ForeignKey(NetPingDevice, on_delete=models.CASCADE, related_name='problem_set')
    sensor = models.ForeignKey(Sensor, related_name='problem_set', on_delete=models.CASCADE, default='')
    problem_name = models.CharField(max_length=100)
    problem_severity = models.CharField(max_length=20, choices=SEVERITY, default='notclassified')
    status = models.BooleanField(default=True, null=True, blank=True)
    # comments = models.ForeignKey('Comments', on_delete=models.CASCADE, related_name='problem')
    created = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    last_updated = models.DateTimeField(auto_now=True, blank=True, null=True)
    history = HistoricalRecords()
    
    class Meta:
        managed = True
        db_table = 'problems'
        indexes = [
            models.Index(fields=['status', 'host']),
        ]
        
    def save(self, *args, **kwargs):
        self.last_updated = timezone.now()
        super().save(*args, **kwargs)
        
    def __str__(self):
        return self.host.hostname and self.problem_name


class Comments(models.Model):
    comment = models.CharField(max_length=300, blank=True, null=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    last_update = models.DateTimeField(auto_now=True, blank=True, null=True)
    problem = models.ForeignKey(Problems, related_name='comment', null=True, blank=True, default='', on_delete=models.CASCADE)

    class Meta:
        managed = True
        db_table = 'comments'

    def save(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        if user:
            self.user = user
        self.last_update = timezone.now()
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"Comment by {self.user} on {self.last_update}"
