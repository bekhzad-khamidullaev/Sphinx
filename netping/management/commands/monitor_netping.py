import requests
import yaml
from django.core.management.base import BaseCommand, CommandError

class Command(BaseCommand):
    help = 'Monitor NetPing device, autodiscover sensors, get sensor types and metrics'

    def add_arguments(self, parser):
        parser.add_argument('device_ip', type=str, help='IP address of the NetPing device')
        parser.add_argument('--port', type=int, default=80, help='Port of the NetPing device')

    def handle(self, *args, **options):
        device_ip = options['device_ip']
        port = options['port']
        url = f'http://{device_ip}:{port}/sensors'

        try:
            # Autodiscover sensors
            response = requests.get(url)
            response.raise_for_status()
            sensors_data = response.json()

            if not sensors_data:
                self.stdout.write(self.style.WARNING('No sensors found'))
                return

            self.stdout.write(self.style.SUCCESS('Sensors discovered successfully'))

            # Print sensor types and metrics
            for sensor in sensors_data.get('sensors', []):
                sensor_id = sensor.get('id')
                sensor_name = sensor.get('name')
                sensor_type = sensor.get('type')

                self.stdout.write(self.style.NOTICE(f'Sensor ID: {sensor_id}'))
                self.stdout.write(self.style.NOTICE(f'Sensor Name: {sensor_name}'))
                self.stdout.write(self.style.NOTICE(f'Sensor Type: {sensor_type}'))

                metrics_url = f'http://{device_ip}:{port}/sensors/{sensor_id}/metrics'
                metrics_response = requests.get(metrics_url)
                metrics_response.raise_for_status()
                metrics_data = metrics_response.json()

                if not metrics_data:
                    self.stdout.write(self.style.WARNING(f'No metrics found for sensor {sensor_id}'))
                    continue

                for metric in metrics_data.get('metrics', []):
                    metric_name = metric.get('name')
                    metric_value = metric.get('value')
                    self.stdout.write(self.style.SUCCESS(f'{metric_name}: {metric_value}'))

        except requests.RequestException as e:
            raise CommandError(f'Error fetching data from NetPing device: {e}')
