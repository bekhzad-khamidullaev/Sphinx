from django.shortcuts import render
from rest_framework import generics, permissions
from rest_framework_simplejwt.views import TokenObtainPairView
from .models import SensorData
from .serializers import SensorDataSerializer
from rest_framework_simplejwt.authentication import JWTAuthentication

class SensorDataView(generics.ListCreateAPIView):
    queryset = SensorData.objects.all()
    serializer_class = SensorDataSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def perform_create(self, serializer):
        sensor_id = serializer.validated_data['sensor_id']
        user = self.request.user
        
        # Check if a SensorData instance with the same sensor_id already exists
        instance, created = SensorData.objects.get_or_create(sensor_id=sensor_id, defaults={'user': user})

        if not created:
            # Update the existing instance with the new data
            instance.temperature = round(serializer.validated_data.get('temperature', instance.temperature), 2)
            instance.humidity = round(serializer.validated_data.get('humidity', instance.humidity), 2)
            instance.heat_index = round(serializer.validated_data.get('heat_index', instance.heat_index), 2)
            instance.uptime = serializer.validated_data.get('uptime', instance.uptime)  # uptime is now in hours
            instance.datetime = serializer.validated_data.get('datetime', instance.datetime)
            instance.save()

        return instance

class CustomTokenObtainPairView(TokenObtainPairView):
    pass

def sensors(request):
    sensors = SensorData.objects.all()  # Execute the queryset
    return render(request, 'sensors_list.html', {"sensors": sensors})
