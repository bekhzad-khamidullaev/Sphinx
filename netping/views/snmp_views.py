from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from ..models import NetPingDevice
from snmp_utils.snmp_operations import perform_snmpget_with_mib, perform_snmpwalk

def snmp_get(request, pk, obj, oid_name):
    device = get_object_or_404(NetPingDevice, pk=pk)
    community = device.snmp_community_ro
    response = perform_snmpget_with_mib(device.ip_address, oid_name, obj, community)
    return JsonResponse({'response': response})

def snmp_walk(request, pk, oid):
    device = get_object_or_404(NetPingDevice, pk=pk)
    community = device.snmp_community_ro
    response = perform_snmpwalk(device.ip_address, oid, community)
    return JsonResponse({'response': response})
