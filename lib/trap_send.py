from pysnmp.hlapi import *

# Define the SNMP trap parameters
trap_receiver_ip = '127.0.0.1'
trap_receiver_port = 162

def send_snmp_trap(oid_values):
    # Create an SNMP Engine
    engine = SnmpEngine()

    # Create the trap message
    try:
        errorIndication, errorStatus, errorIndex, varBinds = next(
            sendNotification(
                engine,
                CommunityData('SWITCH', mpModel=0),  # Use your community string and model
                UdpTransportTarget((trap_receiver_ip, trap_receiver_port)),
                ContextData(),
                'trap',
                [ObjectType(ObjectIdentity(oid), value) for oid, value in oid_values]
            )
        )

        # Check for errors
        if errorIndication:
            print(f'Error: {errorIndication}')
        elif errorStatus:
            print(f'Error: {errorStatus.prettyPrint()} at {errorIndex}')
        else:
            print('Trap sent successfully!')
    except Exception as e:
        print(f'Exception occurred: {e}')

# Define OID values to send (replace with actual OIDs and values as needed)
oids_to_send = [
    ('1.3.6.1.2.1.1.3.0', Integer(2800687)),  # SysUpTime
    ('1.3.6.1.6.3.1.1.4.1.0', ObjectIdentifier('1.3.6.1.4.1.25728.8800.2.0.1')),  # Trap OID
    ('1.3.6.1.6.3.18.1.4.0', OctetString('SWITCH')),  # Trap source
    ('1.3.6.1.6.3.1.1.4.3.0', ObjectIdentifier('1.3.6.1.4.1.25728.8800.2')),  # Enterprise OID
    ('1.3.6.1.4.1.25728.8800.2.1.0', Integer(1)),  # Sensor ID or similar
    ('1.3.6.1.4.1.25728.8800.2.2.0', Integer(26)),  # Sensor value or status
    ('1.3.6.1.4.1.25728.8800.2.3.0', Integer(3)),  # Sensor type or ID
    ('1.3.6.1.4.1.25728.8800.2.4.0', Integer(10)),  # Additional sensor data
    ('1.3.6.1.4.1.25728.8800.2.5.0', Integer(20)),  # More sensor data
    ('1.3.6.1.4.1.25728.8800.2.6.0', OctetString('temperature')),  # Sensor type

    # Add door opened sensor trap
    ('1.3.6.1.4.1.25728.8800.3.1.0', Integer(1)),  # Example OID for door opened sensor
    ('1.3.6.1.4.1.25728.8800.3.2.0', OctetString('door_opened')),  # Example value for door opened event

    # Add movement sensor trap
    ('1.3.6.1.4.1.25728.8800.4.1.0', Integer(1)),  # Example OID for movement sensor
    ('1.3.6.1.4.1.25728.8800.4.2.0', OctetString('movement_detected')),  # Example value for movement detected event

    # Add voltage sensor trap
    ('1.3.6.1.4.1.25728.8800.5.1.0', Integer(1)),  # Example OID for voltage sensor
    ('1.3.6.1.4.1.25728.8800.5.2.0', Integer(230))  # Example value for voltage level (in volts)
]

# Send the trap
send_snmp_trap(oids_to_send)
