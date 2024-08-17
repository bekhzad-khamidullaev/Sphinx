import time
import logging
import re
from django.core.paginator import Paginator
from django.core.management.base import BaseCommand
from netping.models import NetPingDevice as Devices
from netping.models import Branch, Sensor
from snmp_utils.snmp_operations import perform_snmpget_with_mib
from django.db.models import Count

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("SNMP RESPONSE")

def convert_uptime_to_human_readable(uptime_in_hundredths):
    total_seconds = int(uptime_in_hundredths) / 100.0
    days = total_seconds // (24 * 3600)
    hours = (total_seconds % (24 * 3600)) // 3600
    return f"{int(days)} days, {int(hours)} hours"

class Command(BaseCommand):
    help = 'Update device data'

    def handle(self, *args, **options):
        devices_per_page = 10
        delay_seconds = 3600

        while True:
            paginator = Paginator(Devices.objects.filter(status=True).order_by('-pk'), devices_per_page)

            for page_number in range(1, paginator.num_pages + 1):
                selected_devices = paginator.page(page_number)
                branches = Branch.objects.all()
                duplicate_ips = Devices.objects.values('ip_address').annotate(count=Count('ip_address')).filter(count__gt=1)

                for device in selected_devices:
                    SNMP_COMMUNITY = device.snmp_community_ro
                    sensor = Sensor.objects.get(device=device.pk)
                    sensorid = sensor.sensor_id
                    if sensor.sensor_type == 
                    value_current_temp = perform_snmpget_with_mib(device.ip_address, 'npThermoValue', sensorid, SNMP_COMMUNITY)

