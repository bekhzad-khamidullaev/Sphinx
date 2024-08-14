import logging
from pysnmp.hlapi import *
from pysnmp.smi import builder, view, compiler
from django.conf import settings
from pysnmp.smi.rfc1902 import ObjectIdentity, ObjectType

logging.basicConfig(level=logging.INFO)

# Initialize MIB builder and compiler
mib_builder = builder.MibBuilder()
compiler.addMibCompiler(mib_builder, sources=[f'file://{settings.SNMP_MIB_DIRECTORY}'])
logging.debug("MIB compiler added.")

# Load the MIB module
try:
    mib_builder.loadModules(settings.SNMP_MIB_FILE)
    logging.debug(f"MIB module {settings.SNMP_MIB_FILE} loaded successfully.")
except Exception as e:
    logging.error(f"Failed to load MIB module {settings.SNMP_MIB_FILE}: {e}")

# Initialize MIB view controller
mib_view_controller = view.MibViewController(mib_builder)

# Print loaded MIB modules for debugging
logging.debug("Loaded MIB modules:")
for name in mib_builder.mibSymbols:
    logging.debug(name)

def perform_snmpget_with_mib(ip, oid_name,obj, community):
    try:
        # Resolve the object identity using the MIB
        object_identity = ObjectIdentity('SNMPv2-MIB', oid_name, obj).resolveWithMib(mib_view_controller)
        logging.debug(f"Resolved object identity: {object_identity}")

        iterator = getCmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1),
            UdpTransportTarget((ip, 161), timeout=2, retries=2),
            ContextData(),
            ObjectType(object_identity)
        )

        errorIndication, errorStatus, errorIndex, varBinds = next(iterator)

        if errorIndication:
            logging.error(f"Error: {errorIndication}")
        elif errorStatus:
            logging.error(f"Error: {errorStatus.prettyPrint()} at {errorIndex and varBinds[int(errorIndex) - 1][0] or '?'}")
        else:
            snmp_response = []
            for varBind in varBinds:
                name, value = varBind
                snmp_response.append(f'{name.prettyPrint()} = {value.prettyPrint()}')
            return snmp_response
    except Exception as e:
        logging.error(f"Exception: {e}")
        return []

def perform_snmpwalk(ip, oid, community):
    try:
        iterator = nextCmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1),
            UdpTransportTarget((ip, 161), timeout=2, retries=2),
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
            lexicographicMode=False
        )

        snmp_response = []
        for (errorIndication, errorStatus, errorIndex, varBinds) in iterator:
            if errorIndication:
                logging.error(f"Error: {errorIndication}")
                break
            elif errorStatus:
                logging.error(f"Error: {errorStatus.prettyPrint()} at {errorIndex and varBinds[int(errorIndex) - 1][0] or '?'}")
                break
            else:
                for varBind in varBinds:
                    oid_str, value = varBind
                    snmp_response.append(int(value))

        return snmp_response
    except Exception as e:
        logging.error(f"Exception: {e}")
        return []
