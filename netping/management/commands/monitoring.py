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


class Command(BaseCommand):
    help = 'Monitoring'
    



    def handle(self, *args, **options):
        devices_per_page = 10
        delay_seconds = 1

        while True:
            paginator = Paginator(Devices.objects.filter(status=True).order_by('-pk'), devices_per_page)

            for page_number in range(1, paginator.num_pages + 1):
                selected_devices = paginator.page(page_number)
                branches = Branch.objects.all()
                duplicate_ips = Devices.objects.values('ip_address').annotate(count=Count('ip_address')).filter(count__gt=1)

                for device in selected_devices:
                    SNMP_COMMUNITY = device.snmp_community_ro
                    sensor_list = perform_snmpget_with_mib(device.ip_address, 'npRelHumN', 0, SNMP_COMMUNITY)

