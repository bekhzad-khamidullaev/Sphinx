from pysnmp.smi import builder, view, compiler, rfc1902
from pysnmp.entity import engine, config
from pysnmp.carrier.asyncore.dgram import udp
from pysnmp.entity.rfc3413 import ntfrcv
import logging
from django.core.management.base import BaseCommand
from netping.models import NetPingDevice, Sensor
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.conf import settings

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mib_path=settings.SNMP_MIB_DIRECTORY

class SNMPTrapReceiver:
    def __init__(self, trap_agent_address='0.0.0.0', port=162, mib_path):
        self.snmpEngine = engine.SnmpEngine()
        self.trap_agent_address = trap_agent_address
        self.port = port
        self.community_ro = "SWITCH"
        self.community_rw = "SWITCH"
        self.mibBuilder = builder.MibBuilder()
        self.mibViewController = view.MibViewController(self.mibBuilder)

        # Load the precompiled MIBs
        self.mibBuilder.setMibPath(mib_path)
        compiler.addMibCompiler(self.mibBuilder, sources=['file://' + mib_path])
        self.mibBuilder.loadModules()

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

    def _resolve_oid(self, oid):
        """Resolve OID to a human-readable name and value using MIBs."""
        oid_obj = rfc1902.ObjectIdentity(oid)
        oid_obj.resolveWithMib(self.mibViewController)
        return oid_obj.prettyPrint()

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
                        'sensor_id': None,  # This should be handled appropriately
                        'sensor_name': None
                    }
                )

            except MultipleObjectsReturned:
                logger.error(f"Multiple sensors found for device {device_ip}.")
                return
            except ObjectDoesNotExist:
                logger.error(f"No sensor found for device {device_ip}.")
                return

            # Resolve the OID to a human-readable name
            resolved_oid = self._resolve_oid(oid)
            logger.info(f"Resolved OID: {resolved_oid} - Value: {value}")

            # Process the OIDs and update the sensor accordingly
            self._update_sensor(sensor, resolved_oid, value)
            sensor.save()
            device.save()
            
        except ObjectDoesNotExist as e:
            logger.error(f"Error fetching device or sensor: {e}")

    def _update_sensor(self, sensor, resolved_oid, value):
        """Update sensor attributes based on the resolved OID."""
        print(f'Resolved OID: {resolved_oid} ::: Value: {value}')

        if 'sysUpTimeInstance' in resolved_oid:
            sensor.uptime = self.convert_uptime_to_human_readable(value)
            print(sensor.uptime)
        
        elif 'value_current' in resolved_oid:
            sensor.value_current = float(value)
        elif 'value_high_trshld' in resolved_oid:
            sensor.value_high_trshld = int(value)
        elif 'value_low_trshld' in resolved_oid:
            sensor.value_low_trshld = int(value)
        elif 'status' in resolved_oid:
            sensor.status = int(value)
        elif 'sensor_id' in resolved_oid:
            sensor.sensor_id = value
        elif 'sensor_name' in resolved_oid:
            sensor.sensor_name = value


class Command(BaseCommand):
    help = 'Start the SNMP Trap Receiver'

    def handle(self, *args, **kwargs):
        trap_receiver = SNMPTrapReceiver()
        trap_receiver.start()
