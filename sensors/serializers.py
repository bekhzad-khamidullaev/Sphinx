from rest_framework import serializers
from .models import SensorData

class SensorDataSerializer(serializers.ModelSerializer):
    uptime = serializers.FloatField(write_only=True)
    uptime_hours = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = SensorData
        fields = ['sensor_id', 'temperature', 'humidity', 'heat_index', 'uptime', 'uptime_hours', 'datetime']

    def get_uptime_hours(self, obj):
        return round(obj.uptime, 2)

    def validate_uptime(self, value):
        return round(value / 3600, 2)
