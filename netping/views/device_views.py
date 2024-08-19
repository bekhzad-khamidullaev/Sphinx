from django.shortcuts import render, get_object_or_404
from ..models import NetPingDevice, Problems

def device_list(request):
    devices = NetPingDevice.objects.all()
    return render(request, 'netping_list.html', {'devices': devices})

def device_detail(request, pk):
    device = get_object_or_404(NetPingDevice, pk=pk)
    
    # Get all problems associated with this device
    problems = Problems.objects.filter(host=device)

    # Check if there are any problems associated with the device
    has_problems = problems.exists()

    context = {
        'device': device,
        'has_problems': has_problems,
        'problems': problems,
    }
    return render(request, 'netping_detail.html', context)
