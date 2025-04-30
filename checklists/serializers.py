# checklists/serializers.py
from rest_framework import serializers
from .models import Location, ChecklistPoint

class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = ['id', 'name', 'description', 'parent']

class ChecklistPointSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source='location.name', read_only=True)

    class Meta:
        model = ChecklistPoint
        fields = ['id', 'name', 'location', 'location_name', 'description']