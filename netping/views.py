from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from .models import NetPingDevice, Sensor, Problems, Comments
from snmp_utils.snmp_operations import perform_snmpget_with_mib, perform_snmpwalk
from django.conf import settings
from .serializers import DeviceSerializer, SensorSerializer
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view


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

def comments_list(request, pk):
    problem = get_object_or_404(Problems, pk=pk)
    comment = Comments.objects.filter(problem=problem)
    return render(request, 'comments.html', {'problem': problem, 'comment': comment})

# def comments_detail(request, pk):
#     comment = Comments.objects.filter(pk=pk)
#     return render(request, 'comments_detail.html', {'comment': comment})


def problems_list(request, pk):
    device = get_object_or_404(NetPingDevice, pk=pk)
    problems = Problems.objects.filter(sensor__device=device)
    return render(request, 'problems.html', {'problems': problems})


def problem_detail(request, pk):
    problem = get_object_or_404(Problems, pk=pk)
    return render(request, 'problem_detail.html', {'problem': problem})


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


#API part
class DeviceViewSet(viewsets.ModelViewSet):
    queryset = NetPingDevice.objects.all()
    serializer_class = DeviceSerializer


class NetPingDeviceCreateView(APIView):
    def post(self, request, format=None):
        serializer = DeviceSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
def update_sensor(request):
    # Extract parameters from query string
    sensor_id = request.GET.get('sensor_id')
    pk = request.GET.get('device')  # Assuming device is provided as an ID

    if not sensor_id or not pk:
        return Response({'error': 'Missing required parameters'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        device = NetPingDevice.objects.get(pk=pk)
    except NetPingDevice.DoesNotExist:
        return Response({'error': 'Device not found'}, status=status.HTTP_404_NOT_FOUND)

    # Collect other data from query parameters if necessary
    value_current = request.GET.get('value_current')
    sensor_type = request.GET.get('sensor_type')
    sensor_name = request.GET.get('sensor_name')

    # Update or create the sensor
    sensor, created = Sensor.objects.update_or_create(
        sensor_id=sensor_id,
        device=device,
        defaults={
            'value_current': value_current,
            'sensor_type': sensor_type,
            'sensor_name': sensor_name,
        }
    )

    return Response(SensorSerializer(sensor).data, status=status.HTTP_200_OK)