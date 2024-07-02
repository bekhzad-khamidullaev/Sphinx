import logging
from django.core.management.base import BaseCommand
from sensors.models import SensorData
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Check status"

    def handle(self, *args, **options):
        try:
            sensors = SensorData.objects.all()
            while True:
                self.stdout.write(self.style.SUCCESS(f"Loop started"))
                for sensor in sensors:

                    if timezone.now() - sensor.datetime < timedelta(minutes=1):
                        sensor.status = True
                        self.stdout.write(self.style.SUCCESS(f"sensor: {sensor.sensor_id} status True"))
                    else:
                        sensor.status = False
                        self.stdout.write(self.style.SUCCESS("status False"))
                    sensor.save()
                    self.stdout.write(self.style.SUCCESS("SAVED"))
        except KeyboardInterrupt:
            self.stdout.write(self.style.ERROR("Keyboard interrupt received. Exiting..."))
