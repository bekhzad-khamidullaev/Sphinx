from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from .models import NetPingDevice, Sensor
from lib.snmp_perform import perform_snmpget_with_mib, perform_snmpwalk
from django.conf import settings

def device_list(request):
    devices = NetPingDevice.objects.all()
    return render(request, 'device_list.html', {'devices': devices})

def device_detail(request, device_id):
    device = get_object_or_404(NetPingDevice, id=device_id)
    sensors = Sensor.objects.filter(device=device)
    return render(request, 'device_detail.html', {'device': device, 'sensors': sensors})

def snmp_get(request, device_id, oid_name):
    device = get_object_or_404(NetPingDevice, id=device_id)
    community = 'public'  # Adjust this as needed
    response = perform_snmpget_with_mib(device.ip_address, oid_name, community)
    return JsonResponse({'response': response})

def snmp_walk(request, device_id, oid):
    device = get_object_or_404(NetPingDevice, id=device_id)
    community = 'public'  # Adjust this as needed
    response = perform_snmpwalk(device.ip_address, oid, community)
    return JsonResponse({'response': response})
