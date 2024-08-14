from .models import NetPingDevice

def devices(request):
    all_devices = NetPingDevice.objects.all()
    return {'devices': all_devices}
