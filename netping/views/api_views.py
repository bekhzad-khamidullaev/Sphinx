from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from .models import NetPingDevice
from django.conf import settings
from .serializers import DeviceSerializer
from rest_framework import viewsets
from rest_framework.views import APIView

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