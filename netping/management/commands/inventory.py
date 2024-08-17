import time
import logging
import re
from django.core.paginator import Paginator
from django.core.management.base import BaseCommand
from netping.models import NetPingDevice as Devices, Branch
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
                    snmp_response_hostname = perform_snmpget_with_mib(device.ip_address, 'sysName', 0, SNMP_COMMUNITY, mib='SNMPv2-MIB')
                    snmp_response_uptime = perform_snmpget_with_mib(device.ip_address, 'sysUpTime', 0, SNMP_COMMUNITY, mib='SNMPv2-MIB')


                    if not snmp_response_hostname or not snmp_response_uptime:
                        logger.warning(f"No SNMP response received for IP address: {device.ip_address}")
                        continue

                    try:
                        match_hostname = re.search(r'SNMPv2-MIB::sysName.0 = (.+)', snmp_response_hostname[0])
                        if match_hostname:
                            device.hostname = match_hostname.group(1).strip()
                            logger.info(f"Updated hostname: {device.hostname}")
                            device.save()  # Corrected: Adding parentheses to save method
                        else:
                            raise ValueError(f"Unexpected SNMP response format for hostname: {snmp_response_hostname}.")
                    except Exception as e:
                        logger.error(f"Error processing hostname for {device.ip_address}: {e}")
                        continue

                    try:
                        match_uptime = re.search(r'SNMPv2-MIB::sysUpTime.0\s*=\s*(\d+)', snmp_response_uptime[0])
                        if match_uptime:
                            device.uptime = convert_uptime_to_human_readable(match_uptime.group(1).strip())
                            logger.info(f"Updated uptime: {device.uptime}")
                            device.save()  # Corrected: Adding parentheses to save method
                        else:
                            raise ValueError(f"Unexpected SNMP response format for uptime: {snmp_response_uptime}.")
                    except Exception as e:
                        logger.error(f"Error processing uptime for {device.ip_address}: {e}")
                        continue

                    for duplicate_ip in duplicate_ips:
                        ip = duplicate_ip['ip_address']
                        duplicate_hosts = Devices.objects.filter(ip_address=ip).order_by('-id')[1:]
                        for duplicate_host in duplicate_hosts:
                            duplicate_host.delete()

            time.sleep(delay_seconds)

if __name__ == '__main__':
    Command().handle()
