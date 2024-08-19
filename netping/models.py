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


SENSOR_TYPE = [
    (1, "Temperature"),
    (2, "Humidity"),
    (3, "Voltage sensor"),
    (4, "Door contact"),
    (5, "Movement detector"),
]

SENSOR_STATUS = [
    (0, "Sensor failure or disconnection"),
    (1, "Below normal"),
    (2, "Normal"),
    (3, "Above normal"),
]

SEVERITY = [
    (0, "Not classified"),
    (1, "Information"),
    (2, "Warning"),
    (3, "Average"),
    (4, "High"),
    (5, "Disaster"),
]


@receiver(post_migrate)
def create_branch_permissions(sender, **kwargs):
    content_type = ContentType.objects.get_for_model(Branch)
    branches = Branch.objects.all()
    history = HistoricalRecords()

    for branch in branches:
        if branch.name:
            codename = f'view_{branch.name.lower().replace(" ", "_")}'
            name = f'Can view devices in {branch.name}'
        else:
            codename = f'view_branch_{branch.pk}'
            name = f'Can view devices in Branch {branch.pk}'

        permission, created = Permission.objects.get_or_create(
            codename=codename,
            defaults={'name': name, 'content_type': content_type},
        )
        if created:
            print(f'Created permission {name} for {branch.name}')


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
    history = HistoricalRecords()

    def get_device_status(self):
        cache_key = f'device_status_{self.pk}'
        status = cache.get(cache_key)

        if status is None:
            status = self.status
            cache.set(cache_key, status, timeout=settings.CACHE_TIMEOUT)

        return status


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
    sensor_id = models.IntegerField(blank=True, null=True)
    sensor_type = models.IntegerField(choices=SENSOR_TYPE)
    sensor_name = models.CharField(max_length=255, blank=True, null=True)
    status = models.IntegerField(default=0, choices=SENSOR_STATUS, blank=True, null=True)
    value_high_trshld = models.IntegerField(default=0, blank=True, null=True)
    value_current = models.FloatField(blank=True, null=True)
    value_current_long = models.FloatField(blank=True, null=True)
    value_low_trshld = models.IntegerField(default=0, blank=True, null=True)
    last_updated = models.DateTimeField(auto_now=True, blank=True, null=True)
    # problem = models.ForeignKey('Problems', on_delete=models.SET_NULL, null=True, blank=True, related_name='sensor')
    created = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    history = HistoricalRecords()


    def save(self, *args, **kwargs):
        self.last_updated = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.sensor_name} - {self.sensor_type}"


class Problems(models.Model):
    host = models.ForeignKey(NetPingDevice, on_delete=models.CASCADE, related_name='problem_set')
    sensor = models.ForeignKey(Sensor, related_name='problem_set', on_delete=models.CASCADE, null=True, blank=True)
    problem_name = models.CharField(max_length=100)
    problem_severity = models.IntegerField(choices=SEVERITY)
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
        return f"{self.host.hostname} - {self.problem_name}"


class Comments(models.Model):
    comment = models.CharField(max_length=300, blank=True, null=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    last_update = models.DateTimeField(auto_now=True, blank=True, null=True)
    problem = models.ForeignKey(Problems, related_name='comment', null=True, blank=True, on_delete=models.CASCADE)
    history = HistoricalRecords()
    created = models.DateTimeField(auto_now_add=True, blank=True, null=True)


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
