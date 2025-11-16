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