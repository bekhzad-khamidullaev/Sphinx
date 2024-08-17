from pysnmp.entity import engine, config
from pysnmp.carrier.asyncore.dgram import udp
from pysnmp.entity.rfc3413 import ntfrcv
import logging
from django.core.management.base import BaseCommand
from netping.models import NetPingDevice, Sensor
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SNMPTrapReceiver:
    def __init__(self, trap_agent_address='0.0.0.0', port=162):
        self.snmpEngine = engine.SnmpEngine()
        self.trap_agent_address = trap_agent_address
        self.port = port
        self.community_ro = "SWITCH"
        self.community_rw = "SWITCH"
        self._setup_transport()
        self._setup_snmp_engine()

    def _setup_transport(self):
        """Setup UDP transport for SNMP traps."""
        config.addTransport(
            self.snmpEngine,
            udp.domainName + (1,),
            udp.UdpTransport().openServerMode((self.trap_agent_address, self.port))
        )

    def _setup_snmp_engine(self):
        """Configure SNMP engine with default communities."""
        config.addV1System(self.snmpEngine, self.community_ro, self.community_rw)

    def start(self):
        """Start SNMP trap listener."""
        ntfrcv.NotificationReceiver(self.snmpEngine, self._process_trap)
        self.snmpEngine.transportDispatcher.jobStarted(1)
        try:
            self.snmpEngine.transportDispatcher.runDispatcher()
        except:
            self.snmpEngine.transportDispatcher.closeDispatcher()
            raise

    def convert_uptime_to_human_readable(self, uptime_in_hundredths):
        total_seconds = int(uptime_in_hundredths) / 100.0
        days = total_seconds // (24 * 3600)
        hours = (total_seconds % (24 * 3600)) // 3600
        return f"{int(days)} days, {int(hours)} hours"

    def _process_trap(self, snmpEngine, stateReference, contextEngineId, contextName, varBinds, cbCtx):
        device_ip = None

        for name, val in varBinds:
            oid = name.prettyPrint()
            value = val.prettyPrint()

            if oid == '1.3.6.1.6.3.18.1.3.0':
                device_ip = value
                logger.info(f"Received trap from device IP: {device_ip}")

            if device_ip:
                self._handle_device(device_ip, oid, value)

    def _handle_device(self, device_ip, oid, value):
        """Handle SNMP traps by updating the corresponding device and sensors."""
        try:
            device, created = NetPingDevice.objects.get_or_create(ip_address=device_ip)
            device.status = True

            try:
                sensor, created = Sensor.objects.get_or_create(
                    device=device,
                    defaults={
                        'value_current': None,
                        'value_high_trshld': None,
                        'value_low_trshld': None,
                        'status': None,
                        'sensor_id': None,
                        'sensor_name': None
                    }
                )

            except MultipleObjectsReturned:
                logger.error(f"Multiple sensors found for device {device_ip}.")
                return
            except ObjectDoesNotExist:
                logger.error(f"No sensor found for device {device_ip}.")
                return

            # Process the OIDs and update the sensor accordingly
            self._update_sensor(sensor, oid, value)
            sensor.save()
            device.save()
            logger.info(f"Updated sensor for device IP: {device_ip}")
            
        except ObjectDoesNotExist as e:
            logger.error(f"Error fetching device or sensor: {e}")

    def _update_sensor(self, sensor, oid, value):
        """Update sensor attributes based on the received OID."""
        print(f'oid: {oid} ::: value: {value}')

        if oid == '1.3.6.1.2.1.1.3.0':
            sensor.uptime = self.convert_uptime_to_human_readable(value)
            print(sensor.uptime)
        
        elif oid == '1.3.6.1.4.1.25728.8800.2.2.0':
            sensor.value_current = value
        elif oid == '1.3.6.1.4.1.25728.8800.2.5.0':
            sensor.value_high_trshld = int(value)
        elif oid == '1.3.6.1.4.1.25728.8800.2.4.0':
            sensor.value_low_trshld = int(value)
        elif oid == '1.3.6.1.4.1.25728.8800.2.3.0':
            sensor.status = int(value)
        elif oid == '1.3.6.1.4.1.25728.8800.2.1.0':
            sensor.sensor_id = value
        elif oid == '1.3.6.1.4.1.25728.8800.2.6.0':
            sensor.sensor_name = value

        elif oid == '1.3.6.1.4.1.25728.8900.2.2.0':
            sensor.value_current = int(value)
        elif oid == '1.3.6.1.4.1.25728.8900.2.7.0':
            sensor.status = int(value)
        elif oid == '1.3.6.1.4.1.25728.8900.2.1.0':
            sensor.sensor_id = value
        elif oid == '1.3.6.1.4.1.25728.8900.2.6.0':
            sensor.sensor_name = value

        ### Humidity sensor
        elif oid == '1.3.6.1.4.1.25728.8400.3.7.0':
            sensor.value_high_trshld = int(value)
        elif oid == '1.3.6.1.4.1.25728.8400.3.8.0':
            sensor.value_low_trshld = int(value)
        elif oid == '1.3.6.1.4.1.25728.8400.3.2.0':
            sensor.value_current = int(value)
        elif oid == '1.3.6.1.4.1.25728.8400.3.4.0':
            sensor.status = int(value)
        elif oid == '1.3.6.1.4.1.25728.8400.3.1.0':
            sensor.sensor_id = value
        elif oid == '1.3.6.1.4.1.25728.8400.3.6.0':
            sensor.sensor_name = value


class Command(BaseCommand):
    help = 'Start the SNMP Trap Receiver'

    def handle(self, *args, **kwargs):
        trap_receiver = SNMPTrapReceiver()
        trap_receiver.start()
