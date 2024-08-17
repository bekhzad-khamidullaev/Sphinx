from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Sensor, Problems, NetPingDevice


@receiver(post_save, sender=Sensor)
def create_problem_for_sensor(sender, instance, **kwargs):
    # Check if the sensor is of type temperature or humidity
    if instance.sensor_type in ['temperature', 'humidity']:
        if instance.value_current > instance.value_high_trshld or instance.value_current < instance.value_low_trshld:
            Problems.objects.create(
                host=instance.device,
                sensor=instance,
                problem_name=f"{instance.sensor_name} threshold breached",
                problem_severity='high',  # or set based on severity logic
                status=True
            )
    
    # Check if the sensor is of type IO and value_current is 1
    if instance.sensor_type == 'IO' and instance.value_current == 1:
        Problems.objects.create(
            host=instance.device,
            sensor=instance,
            problem_name=f"{instance.sensor_name} IO issue",
            problem_severity='warning',
            status=True
        )


@receiver(post_save, sender=NetPingDevice)
def create_problem_for_device(sender, instance, **kwargs):
    # Check if the device status is false
    if not instance.status:
        Problems.objects.create(
            host=instance,
            problem_name=f"Device {instance.hostname or instance.ip_address} is down",
            problem_severity='disaster',
            status=True
        )
