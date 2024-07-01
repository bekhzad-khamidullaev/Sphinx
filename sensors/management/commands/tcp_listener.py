import socket
import re
import logging
from django.core.management.base import BaseCommand
from django.core.management import call_command
from sensors.models import Sensor, Host
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
import datetime
from django.conf import settings
from django.utils import timezone


logger = logging.getLogger(__name__)


HOST = "0.0.0.0"
PORT = 1234

# HOST = settings.ALLOWED_HOSTS
# PORT = settings.TCP_LISTENER_PORT

class Command(BaseCommand):
    help = "TCP messages listener"

    def handle(self, *args, **options):

        
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((HOST, PORT))
                sock.listen()
                self.stdout.write(self.style.SUCCESS(f"Listening on {HOST}:{PORT}"))

                while True:
                    conn, addr = sock.accept()
                    self.stdout.write(self.style.SUCCESS(f"Connection established from {addr}"))
                    try:
                        parsed_data = conn.recv(1024).decode('utf-8')
                        pattern = re.compile(r'\n|#')
                        lines = pattern.split(parsed_data.strip('#'))
                        lines = list(filter(lambda x: x.strip(), lines))
                        hostname = lines[0]
                        sensor_id = lines[1]
                        temperature = lines[2]
                        error_code = lines[4]
                        

                        host, _ = Host.objects.get_or_create(name=hostname)
                        sensor, created = Sensor.objects.get_or_create(hostname=host, probe_sens_id=sensor_id)
                        # if created:
                        #     sensor = Sensor.objects.create(hostname=host, probe_sens_id=sensor_id, temperature=float(temperature), error=error_code, protocol='TCP')

                        sensor.temperature = round(float(temperature))
                        sensor.probe_sens_id = sensor_id
                        sensor.error = error_code
                        asia_tashkent_timezone = pytz.timezone('Asia/Tashkent')
                        sensor.last_update = astimezone(asia_tashkent_timezone)
                        # @csrf_exempt
                        # def heartbeat_endpoint(self, request):
                        #     if request.method == 'POST':
                        #         sensor.last_update = datetime.datetime.now()
                        #         return HttpResponse(status=200)
                        #     else:
                        #         return HttpResponse(status=405)
                        sensor.save()
                        self.stdout.write(self.style.SUCCESS(f"hostname:{sensor.hostname} sensor_id:{sensor.probe_sens_id} temperature:{sensor.temperature}, error_code:{sensor.error}, last_update:{sensor.last_update}"))
                        self.stdout.write(self.style.SUCCESS("SAVED"))
                    except socket.error as e:
                        logger.error(f"Socket error occurred: {e}")
                    except ValueError as e:
                        logger.error(f"ValueError occurred: {e}")
                    except Exception as e:
                        logger.error(f"Error occurred: {e}")
                    finally:
                        conn.close()

            except KeyboardInterrupt:
                self.stdout.write(self.style.ERROR("Keyboard interrupt received. Exiting..."))