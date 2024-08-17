from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from netping.models import NetPingDevice, Sensor, Problems, Comments
from netping.serializers import DeviceSerializer, SensorSerializer
from django.contrib.auth import get_user_model
User = get_user_model()



class DeviceViewSetTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.device_data = {
            'ip_address': '192.168.1.100',
            'location': 'Data Center',
            'hostname': 'netping-device-1',
            'snmp_community_ro': 'public',
            'snmp_community_rw': 'private',
            'status': True,
        }
        self.device = NetPingDevice.objects.create(**self.device_data)
        self.url = reverse('netpingdevice-list')

    def test_get_all_devices(self):
        response = self.client.get(self.url)
        devices = NetPingDevice.objects.all()
        serializer = DeviceSerializer(devices, many=True)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, serializer.data)

    def test_create_device(self):
        response = self.client.post(self.url, self.device_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(NetPingDevice.objects.count(), 2)
        self.assertEqual(NetPingDevice.objects.last().hostname, 'netping-device-1')


class NetPingDeviceCreateViewTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.device_data = {
            'ip_address': '192.168.1.101',
            'location': 'Server Room',
            'hostname': 'netping-device-2',
            'snmp_community_ro': 'public',
            'snmp_community_rw': 'private',
            'status': True,
        }
        self.url = reverse('netpingdevice-create')

    def test_create_device(self):
        response = self.client.post(self.url, self.device_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(NetPingDevice.objects.count(), 1)
        self.assertEqual(NetPingDevice.objects.last().hostname, 'netping-device-2')

    def test_create_device_invalid_data(self):
        invalid_data = self.device_data.copy()
        invalid_data['ip_address'] = 'invalid-ip'
        response = self.client.post(self.url, invalid_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(NetPingDevice.objects.count(), 0)


class UpdateSensorTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.device = NetPingDevice.objects.create(
            ip_address='192.168.1.102',
            location='Lab',
            hostname='netping-device-3',
            snmp_community_ro='public',
            snmp_community_rw='private',
            status=True,
        )
        self.url = reverse('update_sensor')
        self.sensor_data = {
            'sensor_id': 'sensor-123',
            'sensor_type': 'temperature',
            'sensor_name': 'Temperature Sensor',
            'value_current': 25.5,
            'device': self.device.pk,
        }

    def test_update_sensor(self):
        response = self.client.get(self.url, self.sensor_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        sensor = Sensor.objects.get(sensor_id='sensor-123')
        self.assertEqual(sensor.value_current, 25.5)

    def test_update_sensor_invalid_data(self):
        invalid_data = self.sensor_data.copy()
        invalid_data['device'] = '999'
        response = self.client.get(self.url, invalid_data)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class DeviceListViewTest(TestCase):

    def setUp(self):
        self.device = NetPingDevice.objects.create(
            ip_address='192.168.1.103',
            location='Office',
            hostname='netping-device-4',
            snmp_community_ro='public',
            snmp_community_rw='private',
            status=True,
        )
        self.url = reverse('device_list')

    def test_device_list(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, self.device.hostname)


class DeviceDetailViewTest(TestCase):

    def setUp(self):
        self.device = NetPingDevice.objects.create(
            ip_address='192.168.1.104',
            location='Warehouse',
            hostname='netping-device-5',
            snmp_community_ro='public',
            snmp_community_rw='private',
            status=True,
        )
        self.url = reverse('device_detail', kwargs={'pk': self.device.pk})

    def test_device_detail(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, self.device.hostname)

    def test_device_detail_not_found(self):
        response = self.client.get(reverse('device_detail', kwargs={'pk': 999}))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class CommentsListViewTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpassword')
        self.device = NetPingDevice.objects.create(
            ip_address='192.168.1.105',
            location='Headquarters',
            hostname='netping-device-6',
            snmp_community_ro='public',
            snmp_community_rw='private',
            status=True,
        )
        self.sensor = Sensor.objects.create(
            device=self.device,
            sensor_id='sensor-124',
            sensor_type='humidity',
            sensor_name='Humidity Sensor',
            value_current=40.0
        )
        self.problem = Problems.objects.create(
            host=self.device,
            sensor=self.sensor,
            problem_name='Humidity too high',
            problem_severity='high',
        )
        self.comment = Comments.objects.create(
            comment='This needs attention.',
            user=self.user,
            problem=self.problem,
        )
        self.url = reverse('comments_list', kwargs={'pk': self.problem.pk})

    def test_comments_list(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, self.comment.comment)


class ProblemsListViewTest(TestCase):

    def setUp(self):
        self.device = NetPingDevice.objects.create(
            ip_address='192.168.1.106',
            location='Remote Site',
            hostname='netping-device-7',
            snmp_community_ro='public',
            snmp_community_rw='private',
            status=True,
        )
        self.sensor = Sensor.objects.create(
            device=self.device,
            sensor_id='sensor-125',
            sensor_type='voltage_sensor',
            sensor_name='Voltage Sensor',
            value_current=220.0
        )
        self.problem = Problems.objects.create(
            host=self.device,
            sensor=self.sensor,
            problem_name='Voltage drop detected',
            problem_severity='warning',
        )
        self.url = reverse('problems_list', kwargs={'pk': self.device.pk})

    def test_problems_list(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, self.problem.problem_name)


class ProblemDetailViewTest(TestCase):

    def setUp(self):
        self.device = NetPingDevice.objects.create(
            ip_address='192.168.1.107',
            location='Branch Office',
            hostname='netping-device-8',
            snmp_community_ro='public',
            snmp_community_rw='private',
            status=True,
        )
        self.sensor = Sensor.objects.create(
            device=self.device,
            sensor_id='sensor-126',
            sensor_type='movement_detector',
            sensor_name='Motion Sensor',
            value_current=1.0
        )
        self.problem = Problems.objects.create(
            host=self.device,
            sensor=self.sensor,
            problem_name='Unauthorized movement detected',
            problem_severity='disaster',
        )
        self.url = reverse('problem_detail', kwargs={'pk': self.problem.pk})

    def test_problem_detail(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, self.problem.problem_name)

    def test_problem_detail_not_found(self):
        response = self.client.get(reverse('problem_detail', kwargs={'pk': 999}))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
