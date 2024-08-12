from pysnmp.hlapi import *
from pysnmp.smi import builder, view, compiler, rfc1902
from django.conf import settings

# Load MIB file
# Initialize the MIB Builder
mib_builder = builder.MibBuilder()
# settings.py
SNMP_MIB_DIRECTORY = 'C:/Users/atxmutb02/temp/mibs'  # Use the absolute path
SNMP_MIB_FILE = '72.1.RMB'  # Base name of the MIB file, without the .mib extension

# Add MIB Compiler
compiler.addMibCompiler(mib_builder, sources=[f'file://{settings.SNMP_MIB_DIRECTORY}'])

# # Compile MIB files
# mib_builder.loadModules(settings.SNMP_MIB_FILE)

# Initialize MIB View Controller
mib_view_controller = view.MibViewController(mib_builder)

def perform_snmpget_with_mib(ip, oid_name, community):
    try:
        # Translate the OID name to the corresponding OID
        object_identity = ObjectIdentity(oid_name).resolveWithMib(mib_view_controller)
        
        iterator = getCmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1),
            UdpTransportTarget((ip, 161), timeout=2, retries=2),
            ContextData(),
            ObjectType(object_identity)
        )

        errorIndication, errorStatus, errorIndex, varBinds = next(iterator)
        
        if errorIndication:
            print(f"Error: {errorIndication}")
        elif errorStatus:
            print(f"Error: {errorStatus.prettyPrint()} at {errorIndex and varBinds[int(errorIndex) - 1][0] or '?'}")
        else:
            snmp_response = []
            for varBind in varBinds:
                name, value = varBind
                snmp_response.append(f'{name.prettyPrint()} = {value.prettyPrint()}')
            return snmp_response
    except Exception as e:
        print(f"Exception: {e}")
        return []


def perform_snmpwalk(ip, oid, community):
    try:
        iterator = nextCmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1),  # SNMP v2c
            UdpTransportTarget((ip, 161), timeout=2, retries=2),
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
            lexicographicMode=False  # Ensures the walk is limited to the specified OID tree
        )

        snmp_response = []
        for (errorIndication, errorStatus, errorIndex, varBinds) in iterator:
            if errorIndication:
                print(f"Error: {errorIndication}")
                break
            elif errorStatus:
                print(f"Error: {errorStatus.prettyPrint()} at {errorIndex and varBinds[int(errorIndex) - 1][0] or '?'}")
                break
            else:
                for varBind in varBinds:
                    oid_str, value = varBind
                    snmp_response.append(int(value))  # Convert value to integer
        return snmp_response
    except Exception as e:
        print(f"Exception: {e}")
        return []
    

