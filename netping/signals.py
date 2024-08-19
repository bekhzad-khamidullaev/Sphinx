from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Sensor, Problems, NetPingDevice

@receiver(post_save, sender=Sensor)
def create_or_resolve_problem_for_sensor(sender, instance, **kwargs):
    # Check if the sensor is of type temperature or humidity
    if instance.sensor_type in [1, 2]:
        if instance.value_current > instance.value_high_trshld or instance.value_current < instance.value_low_trshld:
            # Create a new problem
            Problems.objects.create(
                host=instance.device,
                sensor=instance,
                problem_name=f"{instance.sensor_name} threshold breached",
                problem_severity=4,
                status=True
            )
        else:
            # Close the specific threshold breach problem
            Problems.objects.filter(
                host=instance.device,
                sensor=instance,
                problem_name=f"{instance.sensor_name} threshold breached",
                status=True
            ).update(status=False)

    # Check if the sensor is of type IO and value_current is 1 (indicates a problem)
    if instance.sensor_type == 'IO':
        if instance.value_current == 1:
            # Create a new problem
            Problems.objects.create(
                host=instance.device,
                sensor=instance,
                problem_name=f"{instance.sensor_name} IO issue",
                problem_severity='warning',
                status=True
            )
        else:
            # Close the specific IO issue problem
            Problems.objects.filter(
                host=instance.device,
                sensor=instance,
                problem_name=f"{instance.sensor_name} IO issue",
                status=True
            ).update(status=False)

@receiver(post_save, sender=NetPingDevice)
def create_or_resolve_problem_for_device(sender, instance, **kwargs):
    if not instance.status:
        # Create a new problem
        Problems.objects.create(
            host=instance,
            problem_name=f"Device {instance.hostname or instance.ip_address} is down",
            problem_severity=4,
            status=True
        )
    else:
        # Close the specific device down problem
        Problems.objects.filter(
            host=instance,
            problem_name=f"Device {instance.hostname or instance.ip_address} is down",
            status=True
        ).update(status=False)
