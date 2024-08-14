from django.shortcuts import render, get_object_or_404
from ..models import NetPingDevice

def device_list(request):
    devices = NetPingDevice.objects.all()
    return render(request, 'netping_list.html', {'devices': devices})

def device_detail(request, pk):
    device = get_object_or_404(NetPingDevice, pk=pk)
    has_problems = any(sensor.problem_set.exists() for sensor in device.sensor_set.all())
    context = {
        'device': device,
        'has_problems': has_problems,
    }
    return render(request, 'netping_detail.html', context)
