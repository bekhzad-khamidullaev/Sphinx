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

def extract_value(snmp_list):
    value = None
    if snmp_list:
        match = re.search(r'=\s*(\S+)', snmp_list[0])
        if match:
            value = match.group(1)
    return value

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
                    sensors = Sensor.objects.filter(device=device)
                    for sensor in sensors:
                        sensorid = sensor.sensor_id
                        type = sensor.sensor_type
                        if type == 1:
                            value_current_long = extract_value(perform_snmpget_with_mib(device.ip_address, 'npThermoValuePrecise', sensorid, SNMP_COMMUNITY))
                            value_current = extract_value(perform_snmpget_with_mib(device.ip_address, 'npThermoValue', sensorid, SNMP_COMMUNITY))
                            status = extract_value(perform_snmpget_with_mib(device.ip_address, 'npThermoStatus', sensorid, SNMP_COMMUNITY))
                            value_low_trshld = extract_value(perform_snmpget_with_mib(device.ip_address, 'npThermoLow', sensorid, SNMP_COMMUNITY))
                            value_high_trshld = extract_value(perform_snmpget_with_mib(device.ip_address, 'npThermoHigh', sensorid, SNMP_COMMUNITY))
                            sensor_name = extract_value(perform_snmpget_with_mib(device.ip_address, 'npThermoMemo', sensorid, SNMP_COMMUNITY))
                        elif type == 2:
                            value_current = extract_value(perform_snmpget_with_mib(device.ip_address, 'npRelHumValue', sensorid, SNMP_COMMUNITY))
                            status = extract_value(perform_snmpget_with_mib(device.ip_address, 'npRelHumStatus', sensorid, SNMP_COMMUNITY))
                            value_low_trshld = extract_value(perform_snmpget_with_mib(device.ip_address, 'npRelHumSafeRangeLow', sensorid, SNMP_COMMUNITY))
                            value_high_trshld = extract_value(perform_snmpget_with_mib(device.ip_address, 'npRelHumSafeRangeHigh', sensorid, SNMP_COMMUNITY))
                            sensor_name = extract_value(perform_snmpget_with_mib(device.ip_address, 'npRelHumMemo', sensorid, SNMP_COMMUNITY))

                        print(f'current value: {value_current}, status: {status}, high trshld: {value_low_trshld}, low trshld: {value_low_trshld}, name: {sensor_name}')
                        sensor.status = int(status)
                        sensor.value_current = float(value_current)
                        sensor.value_high_trshld = int(value_high_trshld)
                        sensor.value_low_trshld = int(value_low_trshld)
                        sensor.sensor_name = str(sensor_name)

                        sensor.save()