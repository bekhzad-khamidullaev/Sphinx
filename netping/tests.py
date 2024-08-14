from django.test import TestCase
from .models import NetPingDevice

class NetPingDeviceTestCase(TestCase):
    def setUp(self):
        NetPingDevice.objects.create(ip_address="192.168.1.1", hostname="Test Device")

    def test_device_status(self):
        device = NetPingDevice.objects.get(ip_address="192.168.1.1")
        self.assertEqual(device.hostname, "Test Device")
