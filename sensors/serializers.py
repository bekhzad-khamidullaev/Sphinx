from rest_framework import serializers
from .models import SensorData

class SensorDataSerializer(serializers.ModelSerializer):
    uptime = serializers.FloatField(write_only=True)
    uptime_hours = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = SensorData
        fields = ['sensor_id', 'temperature', 'humidity', 'heat_index', 'uptime', 'uptime_hours', 'datetime']

    def get_uptime_hours(self, obj):
        return round(obj.uptime, 2)  # uptime is already in hours in the database

    def validate_uptime(self, value):
        # Convert uptime from seconds to hours before saving to the database
        return round(value / 3600, 2)
