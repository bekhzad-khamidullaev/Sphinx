from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view
from ..models import NetPingDevice, Sensor
from ..serializers import DeviceSerializer, SensorSerializer

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
    sensor_id = request.GET.get('sensor_id')
    pk = request.GET.get('device')

    if not sensor_id or not pk:
        return Response({'error': 'Missing required parameters'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        device = NetPingDevice.objects.get(pk=pk)
    except NetPingDevice.DoesNotExist:
        return Response({'error': 'Device not found'}, status=status.HTTP_404_NOT_FOUND)

    value_current = request.GET.get('value_current')
    sensor_type = request.GET.get('sensor_type')
    sensor_name = request.GET.get('sensor_name')

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
