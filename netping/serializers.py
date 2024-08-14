from rest_framework import serializers
from .models import NetPingDevice, Sensor

class DeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NetPingDevice
        fields = '__all__'


# class NetPingDeviceSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = NetPingDevice
#         fields = ['ip_address', 'location', 'hostname', 'snmp_community_ro', 'snmp_community_rw', 'status', 'uptime']

class SensorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sensor
        fields = ['device', 'sensor_id', 'sensor_type', 'sensor_name', 'last_reading', 'last_updated', 'problem']