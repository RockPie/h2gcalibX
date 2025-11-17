from itertools import groupby

def extract_raw_payloads(data):
    # Constant values
    HEADER_SIZE = 12
    PAYLOAD_SIZE = 46  # Updated from 40 -> 46
    PAYLOAD_START_OPTIONS   = range(0xA0, 0xA3)  # 0xA0 to 0xA2
    SECOND_BYTE_OPTIONS     = range(0x00, 0x08)  # 0x00 to 0x07
    THIRD_BYTE_OPTIONS      = [0x24, 0x25]
    FOURTH_BYTE_OPTIONS     = range(0x00, 0x05)
    
    payloads = []

    # Skip the header to get to the payload
    payload_data = data[HEADER_SIZE:]

    # Check each possible start index in the payload data
    for i in range(len(payload_data) - PAYLOAD_SIZE + 1):
        if payload_data[i] in PAYLOAD_START_OPTIONS and \
           payload_data[i+1] in SECOND_BYTE_OPTIONS and \
           payload_data[i+2] in THIRD_BYTE_OPTIONS and \
           payload_data[i+3] in FOURTH_BYTE_OPTIONS:
            # Extract the 46-byte payload
            payload = payload_data[i:i + PAYLOAD_SIZE]
            payloads.append(payload)

    return payloads

def extract_raw_data(data):
    HEADER_SIZE = 14
    PAYLOAD_SIZE = 192
    PAYLOAD_START = b'\xAA\x5A'

    payloads = []
    payload_data = data[HEADER_SIZE:]

    i = 0
    while i <= len(payload_data) - PAYLOAD_SIZE:
        # Look for payload start marker
        if payload_data[i:i+2] == PAYLOAD_START:
            payload = payload_data[i:i+PAYLOAD_SIZE]
            payloads.append(payload)
            i += PAYLOAD_SIZE  # jump to next payload
        else:
            i += 1  # move forward one byte if not aligned yet

    return payloads


def sort_and_group_46bytes(data):
    # Sort/group by the same identifiers as before, but skip 6-byte padding
    def get_key(item):
        return item[0:3], item[4:7]  # (bytes 1–3, bytes 5–7)

    # Sort first for groupby to work correctly
    data_sorted = sorted(data, key=lambda x: (x[0:3], x[4:7], x[3]))

    grouped_data = []
    for ((bytes_1_3, bytes_5_7), items) in groupby(data_sorted, key=get_key):
        sub_group = sorted(list(items), key=lambda x: x[3])
        grouped_data.append(sub_group)

    return grouped_data


def assemble_data_from_46bytes(group, verbose=False):
    # Combine 5×46-byte chunks → 230-byte buffer
    data = bytearray()
    for pkt in group:
        data += pkt
    if len(data) != 230:
        if verbose:
            print('\033[33mError: Data length is not 230 bytes\033[0m')
        return None

    # Strip the 6-byte padding of each payload to rebuild the 200-byte core
    combined = bytearray()
    for i in range(0, 230, 46):
        combined += data[i + 6:i + 46]

    if len(combined) != 200:
        if verbose:
            print('\033[33mError: Unpadded data length is not 200 bytes\033[0m')
        return None

    _header      = combined[0]
    _fpga_addr   = combined[1]
    _packet_type = combined[2]
    _timestamp   = combined[4:7]

    _extraced_160_bytes  = combined[8:40]
    _extraced_160_bytes += combined[48:80]
    _extraced_160_bytes += combined[88:120]
    _extraced_160_bytes += combined[128:160]
    _extraced_160_bytes += combined[168:200]

    if verbose:
        print('\033[34m' + f"Header: {hex(_header)}" + '\033[0m')
        print('\033[34m' + f"FPGA Address: {hex(_fpga_addr)}" + '\033[0m')
        print('\033[34m' + f"Packet Type: {hex(_packet_type)}" + '\033[0m')
        print('\033[34m' + f"Timestamp: {hex(_timestamp[0])}{hex(_timestamp[1])}{hex(_timestamp[2])}" + '\033[0m')
        print('\033[34m' + "Data:" + '\033[0m')
        for i in range(0, 160, 16):
            print(' '.join([f"{x:02x}" for x in _extraced_160_bytes[i:i+16]]))

    return {
        "_header": _header,
        "_fpga_addr": _fpga_addr,
        "_packet_type": _packet_type,
        "_timestamp": _timestamp,
        "_extraced_160_bytes": _extraced_160_bytes
    }

def assemble_data_from_192bytes(payload, verbose=False):
    """
    Assemble and parse a single 192-byte DAQ payload.

    Format:
    ----------------------------------------------------------------
    Bytes | Field
    ------|----------------------------------------------------------
    0–1   | Header (always 0xAA 0x5A)
    2     | 4-bit FPGA ID (high nibble) + 4-bit ASIC ID (low nibble)
    3     | Packet Type (8-bit)
    4–7   | Trigger In (32-bit)
    8–11  | Trigger Out (32-bit)
    12–15 | Event Counter (32-bit)
    16–23 | Timestamp (64-bit)
    24–31 | Spare (64-bit, currently unused)
    32–191| Data payload (160 bytes)
    ----------------------------------------------------------------
    """
    if len(payload) != 192:
        if verbose:
            print(f"\033[33mError: Payload length is {len(payload)}, expected 192 bytes\033[0m")
        return None

    # Header (should always be 0xAA 0x5A)
    header = payload[0:2]
    if header != b'\xAA\x5A' and verbose:
        print(f"\033[33mWarning: Invalid header {header.hex()}\033[0m")

    # IDs
    id_byte = payload[2]
    fpga_id = (id_byte & 0xF0) >> 4
    asic_id = id_byte & 0x0F

    # Other fields
    packet_type   = payload[3]
    trigger_in    = int.from_bytes(payload[4:8],  byteorder="big")
    trigger_out   = int.from_bytes(payload[8:12], byteorder="big")
    event_counter = int.from_bytes(payload[12:16], byteorder="big")
    timestamp     = int.from_bytes(payload[16:24], byteorder="big")
    spare         = int.from_bytes(payload[24:32], byteorder="big")
    extracted_160_bytes = payload[32:192]

    if verbose:
        print("\033[34m--- 192-byte payload ---\033[0m")
        print(f"\033[34mHeader:        {header.hex(' ')}\033[0m")
        print(f"\033[34mFPGA ID:       {fpga_id}   ASIC ID: {asic_id}\033[0m")
        print(f"\033[34mPacket Type:   0x{packet_type:02X}\033[0m")
        print(f"\033[34mTrigger In:    0x{trigger_in:08X}\033[0m")
        print(f"\033[34mTrigger Out:   0x{trigger_out:08X}\033[0m")
        print(f"\033[34mEvent Counter: 0x{event_counter:08X}\033[0m")
        print(f"\033[34mTimestamp:     0x{timestamp:016X}\033[0m")
        print(f"\033[34mSpare:         0x{spare:016X}\033[0m")
        print(f"\033[34mData (160 B):\033[0m")
        for i in range(0, 160, 16):
            print(' '.join(f"{x:02x}" for x in extracted_160_bytes[i:i+16]))

    return {
        "_header": header,
        "_fpga_id": fpga_id,
        "_asic_id": asic_id,
        "_packet_type": packet_type,
        "_trigger_in": trigger_in,
        "_trigger_out": trigger_out,
        "_event_counter": event_counter,
        "_timestamp": timestamp,
        "_spare": spare,
        "_extracted_160_bytes": extracted_160_bytes,
    }

def check_event_fragment(candidate_packet_lines):
    """Check if a group of 5 packets forms a valid event fragment."""
    if len(candidate_packet_lines) != 5:
        return False, None
    return True, candidate_packet_lines

def extract_values(bytes_input, verbose=False):
    """Extract data values from a 160-byte payload."""
    if len(bytes_input) != 160:
        if verbose:
            print('\033[33m' + "Error: Data length is not 160 bytes" + '\033[0m')
        return None

    _DaqH = bytes_input[0:4]
    _extracted_values = []

    for i in range(4, 152, 4):
        _value = int.from_bytes(bytes_input[i:i+4], byteorder='big', signed=False)
        if verbose:
            print('\033[34m' + "Value: " + hex(_value) + '\033[0m')
        _val0  = (_value >> 20) & 0x3FF
        _val1  = (_value >> 10) & 0x3FF
        _val2  = (_value >>  0) & 0x3FF
        _tctp  = (_value >> 30) & 0x3
        _extracted_values.append([_tctp, _val0, _val1, _val2])

    if verbose:
        print('\033[34m' + "DaqH: " + ' '.join([f"{x:02x}" for x in _DaqH]) + '\033[0m')
        print('\033[34m' + "Extracted Values:" + '\033[0m')
        for i in range(len(_extracted_values)):
            print(' '.join([f"{x:04x}" for x in _extracted_values[i]]))

    return {
        "_DaqH": _DaqH,
        "_extracted_values": _extracted_values
    }

def extract_values_192(bytes_input, verbose=False):
    """Extract data values from a 192-byte payload (32B header + 160B data)."""
    if len(bytes_input) != 192:
        if verbose:
            print('\033[33m' + f"Error: Data length is {len(bytes_input)} bytes (expected 192)" + '\033[0m')
        return None

    timestamp_bytes = bytes_input[16:24]
    timestamp = int.from_bytes(timestamp_bytes, byteorder='big', signed=False)
    address_id = bytes_input[2]
    packet_id = bytes_input[3]

    # Skip the first 32 bytes
    data_160 = bytes_input[32:192]
    if len(data_160) != 160:
        if verbose:
            print('\033[33m' + "Error: Extracted payload is not 160 bytes" + '\033[0m')
        return None

    _DaqH = data_160[0:4]
    _extracted_values = []

    for i in range(4, 152, 4):
        _value = int.from_bytes(data_160[i:i+4], byteorder='big', signed=False)
        if verbose:
            print('\033[34m' + "Value: " + hex(_value) + '\033[0m')

        _val0 = (_value >> 20) & 0x3FF
        _val1 = (_value >> 10) & 0x3FF
        _val2 = (_value >>  0) & 0x3FF
        _tctp = (_value >> 30) & 0x3
        _extracted_values.append([_tctp, _val0, _val1, _val2])

    if verbose:
        print('\033[34m' + "DaqH: " + ' '.join([f"{x:02x}" for x in _DaqH]) + '\033[0m')
        print('\033[34m' + "Extracted Values:" + '\033[0m')
        for v in _extracted_values:
            print(' '.join([f"{x:04x}" for x in v]))

    return {
        "_timestamp": timestamp,
        "_address_id": address_id,
        "_packet_id": packet_id,
        "_DaqH": _DaqH,
        "_extracted_values": _extracted_values
    }

def DaqH_get_H1(_daqh):
    if len(_daqh) != 4:
        return None
    value = int(_daqh[-1])
    return (value & 0x40) >> 6


def DaqH_get_H2(_daqh):
    if len(_daqh) != 4:
        return None
    value = int(_daqh[-1])
    return (value & 0x20) >> 5


def DaqH_get_H3(_daqh):
    if len(_daqh) != 4:
        return None
    value = int(_daqh[-1])
    return (value & 0x10) >> 4

def DaqH_start_end_good(_daqh):
    # return ((_daqh[-1] & 0x0F) == 0x05)
    return ((_daqh[0] >> 4) == 0x0F or (_daqh[0] >> 4) == 0x05 or (_daqh[0] >> 4) == 0x02) and ((_daqh[-1] & 0x0F) == 0x05 or (_daqh[-1] & 0x0F) == 0x02)