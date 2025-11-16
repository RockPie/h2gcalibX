import packetlibX
import caliblibX
import argparse     # for input arguments
import os, json, time
import matplotlib.pyplot as plt

# * --- Set up script information -------------------------------------
script_id_str       = os.path.basename(__file__).split('.')[0]
script_version_str  = '1.1'
script_folder       = os.path.dirname(__file__)
print("-- "+ script_id_str + " (v" + script_version_str + ") ----------------")

# * --- Read command line arguments -----------------------------------
parser = argparse.ArgumentParser(description='IO delay scan for HGCROC')
parser.add_argument('-c', '--config', type=str, help='Path to the configuration file')
parser.add_argument('-r', '--reset', action='store_true', help='Enable reset before IO delay scan')
parser.add_argument('-t', '--trigger', action='store_true', help='Set trigger line delay')
parser.add_argument('-a', '--asic', type=int, help='ASIC number to scan')
parser.add_argument('-p', '--phase', type=int, default=12, help='Phase setting for the ASIC (default: 12)')
parser.add_argument('--plot', action='store_true', help='Enable plotting of results')
args = parser.parse_args()

# * --- Load configuration file ---------------------------------------
output_dump_folder, output_config_path = caliblibX.output_path_setup(script_id_str, time.strftime('%Y%m%d_%H%M%S'), os.path.dirname(__file__))
output_config_json = {}

# * --- Load udp settings from config file ----------------------------
udp_target = caliblibX.udp_target('10.1.2.207', 11000, 11001, '10.1.2.208', 11000)
if args.config:
    udp_target.load_udp_json_file(args.config)
udp_target.load_pool_json_file(os.path.join(script_folder, 'config', 'socket_pool_configX.json'))

print(f"- UDP from {args.config if args.config else 'default settings'}:")
print(f"-- PC IP: {udp_target.pc_ip}, Port: {udp_target.pc_port_cmd}/{udp_target.pc_port_data}")
print(f"-- Board IP: {udp_target.board_ip}, Port: {udp_target.board_port}")

udp_target.connect_to_pool(timeout=2.0)

# * --- Set running parameters --------------------------------------
total_asic = 2
if args.asic is not None:
    total_asic = int(args.asic)

asic_select = (1 << total_asic) - 1  # select all asics by default
io_dealy_scan_range = range(0, 512, 2)
locked_pattern = 0xaccccccc
enable_trigger_lines = args.trigger
reset_before_scan    = args.reset
phase_setting        = 12
if args.phase is not None:
    phase_setting = int(args.phase)

print(f"- Running parameters:")
print(f"-- Total ASIC: {total_asic}, ASIC Select: 0x{asic_select:02x}")
print(f"-- Locked Pattern: 0x{locked_pattern:08x}")
print(f"-- Trigger: {enable_trigger_lines}, Reset: {reset_before_scan}, Phase: {phase_setting}")

# * --- Reset ------------------------------------------------
if reset_before_scan:
    print(f"- Resetting HGCROC ASICs...")
    for _asic in range(total_asic):
        if not caliblibX.send_reset_adj_calib(udp_target, asic_num=total_asic, sw_hard_reset_sel=asic_select, sw_hard_reset=0x01):
            print(f"-- Failed to send reset command to ASIC {_asic}")
        time.sleep(0.1)

# * --- Set registers before IO delay scan ------------------------------
# top is the same
i2c_content_top = [0x08,0x0f,0x40,0x7f,0x00,0x07,0x05,0x00]
i2c_content_top[7] = phase_setting & 0x0F
# digital half is the same
i2c_content_digital_half_0 = [0x00,0x00,0x00,0x00,0x80,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x19,0x00,0x0a,0xcc,0xcc,0xcc,0x0c,0xcc,0xcc,0xcc,0xcc,0x0f,0x02,0x00]
i2c_content_digital_half_1 = [0x00,0x00,0x00,0x00,0x80,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x19,0x00,0x0a,0xcc,0xcc,0xcc,0x0c,0xcc,0xcc,0xcc,0xcc,0x0f,0x02,0x00]
# some register definations are different for HGCROC
i2c_content_global_analog_0 = [0x6f,0xdb,0x83,0x28,0x28,0x28,0x9a,0x9a,0xa8,0x8a,0x40,0x4a,0x4b,0x68]
i2c_content_global_analog_1 = [0x6f,0xdb,0x83,0x28,0x28,0x28,0x9a,0x9a,0xa8,0x8a,0x40,0x4a,0x4b,0x68]
# master TDC is the same
i2c_content_master_tdc_0 = [0x37,0xd4,0x54,0x80,0x0a,0xd4,0x03,0x00,0x80,0x80,0x0a,0x95,0x03,0x00,0x40,0x00]
i2c_content_master_tdc_1 = [0x37,0xd4,0x54,0x80,0x0a,0xd4,0x03,0x00,0x80,0x80,0x0a,0x95,0x03,0x00,0x40,0x00]
# some reference voltage register definations are different for HGCROC
i2c_content_reference_voltage_0 = [0xb4,0x0a,0xfa,0xfa,0xb8,0xd4,0xda,0x42,0x00,0x00]
i2c_content_reference_voltage_1 = [0xb4,0x0e,0xfa,0xfa,0xad,0xd4,0xda,0x42,0x00,0x00]
# no reg#14 for HGCROC
i2c_content_half_wise_0 = [0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00]
i2c_content_half_wise_1 = [0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00]

output_config_json['i2c_settings'] = {
    'Top': i2c_content_top,
    'Digital_Half_0': i2c_content_digital_half_0,
    'Digital_Half_1': i2c_content_digital_half_1,
    'Global_Analog_0': i2c_content_global_analog_0,
    'Global_Analog_1': i2c_content_global_analog_1,
    'Master_TDC_0': i2c_content_master_tdc_0,
    'Master_TDC_1': i2c_content_master_tdc_1,
    'Reference_Voltage_0': i2c_content_reference_voltage_0,
    'Reference_Voltage_1': i2c_content_reference_voltage_1,
    'HalfWise_0': i2c_content_half_wise_0,
    'HalfWise_1': i2c_content_half_wise_1
}

for _asic in range(total_asic):
    print(f"- Setting up ASIC {_asic} registers before IO delay scan...")
    for _key, _value in output_config_json['i2c_settings'].items():
        if not caliblibX.send_register_calib(udp_target, _asic, _key, _value):
            print(f"-- Failed to set {_key} for ASIC {_asic}")

# * --- Main script ----------------------------------------------
optimal_io_delay_values = []
io_delay_scan_results = {}
io_delay_scan_io_delay_values = {}
for _asic in range(total_asic):
    io_delay_scan_results[_asic] = []
    io_delay_scan_io_delay_values[_asic] = []

for _asic in range(total_asic):
    print_result_array = []
    print(f"- Starting IO delay scan for ASIC {_asic}...")
    for _io_delay in io_dealy_scan_range:
        _is_locked = caliblibX.delay_test(udp_target.cmd_outbound_conn, udp_target.data_cmd_conn, udp_target.board_ip, udp_target.board_port, udp_target.board_id, _delay_setting=_io_delay, _asic_index=_asic, _asic_sel=asic_select, _locked_pattern=locked_pattern, _test_trigger_lines=enable_trigger_lines)
        # print(f"-- IO Delay: {_io_delay:03d}, Locked: {_is_locked}")
        io_delay_scan_io_delay_values[_asic].append(_io_delay)
        io_delay_scan_results[_asic].append(_is_locked)
        if _is_locked:
            print_result_array.append('L')
        else:
            print_result_array.append('U')
        if len(print_result_array) >= 32:
            print("---A" + str(_asic) + "- " + "".join(print_result_array))
            print_result_array = []

    # find the 3 longest locked segments
    top_segments = caliblibX.find_top_n_ones(io_delay_scan_io_delay_values[_asic], io_delay_scan_results[_asic], 3)

    for _segment_index, _segment in enumerate(top_segments):
        print(f"-- ASIC {_asic} Locked Segment: IO Delay {int(_segment[0])} to {int(_segment[1])} (Length: {int(_segment[1]-_segment[0]+1)})")

        # go though the segments to check if the length is over 20
        _segment_io_delay_values = []
        _segment_lock_status = []
        _segment_print_array = []
        for _io_delay in range(int(_segment[0]), int(_segment[1])):
            _is_locked = caliblibX.delay_test(udp_target.cmd_outbound_conn, udp_target.data_cmd_conn, udp_target.board_ip, udp_target.board_port, udp_target.board_id, _delay_setting=_io_delay, _asic_index=_asic, _asic_sel=asic_select, _locked_pattern=locked_pattern, _test_trigger_lines=enable_trigger_lines)
            _segment_io_delay_values.append(_io_delay)
            _segment_lock_status.append(_is_locked)
            if _is_locked:
                _segment_print_array.append('L')
            else:
                _segment_print_array.append('U')
            if len(_segment_print_array) >= 32:
                print("---A" + str(_asic) + "- " + "".join(_segment_print_array))
                _segment_print_array = []
        
        _segment_sub_top_segments = caliblibX.find_top_n_ones(_segment_io_delay_values, _segment_lock_status, 1)
        if _segment_sub_top_segments == []:
            if _segment_index == len(top_segments) - 1:
                optimal_io_delay_values.append(-1)
            else:
                continue
        _segment_sub_segment_length = int(_segment_sub_top_segments[0][1] - _segment_sub_top_segments[0][0] + 1)
        if _segment_sub_segment_length >= 20:
            _optimal_io_delay = int((_segment_sub_top_segments[0][0] + _segment_sub_top_segments[0][1]) / 2)
            optimal_io_delay_values.append(_optimal_io_delay)
            # print(f"*** Optimal IO Delay for ASIC {_asic} found: {_optimal_io_delay} ***")
            break
        elif _segment_index == len(top_segments) - 1:
            optimal_io_delay_values.append(-1)
            print(f" -- Warning: No valid optimal IO delay found for ASIC {_asic}!")

# load the optimal io delay settings to ASIC
for _asic in range(total_asic):
    _is_locked = caliblibX.delay_test(udp_target.cmd_outbound_conn, udp_target.data_cmd_conn, udp_target.board_ip, udp_target.board_port, udp_target.board_id, _delay_setting=optimal_io_delay_values[_asic], _asic_index=_asic, _asic_sel=asic_select, _locked_pattern=locked_pattern, _test_trigger_lines=enable_trigger_lines)
    if not _is_locked:
        print(f"*** Fatal Error: Optimal IO Delay {optimal_io_delay_values[_asic]} for ASIC {_asic} is not locked! ***")
        exit(1)
    if args.plot:
        plt.figure(figsize=(10, 5))
        plt.plot(io_delay_scan_io_delay_values[_asic], io_delay_scan_results[_asic], marker='o', linestyle='-', color='b')
        plt.title(f'IO Delay Scan Result for ASIC {_asic}')
        plt.xlabel('IO Delay Setting')
        plt.ylabel('Lock Status (1=Locked, 0=Not Locked)')
        plt.ylim(-0.1, 1.1)
        plt.grid(True)
        # draw the vertical line for optimal io delay
        plt.axvline(x=optimal_io_delay_values[_asic], color='r', linestyle='--', label='Optimal IO Delay')
        plt.legend()
        plt.savefig(os.path.join(output_dump_folder, f'io_delay_scan_asic_{_asic}.png'))
        plt.close()

print(f"- Optimal IO Delay Values: {optimal_io_delay_values}")

output_config_json['io_delay_scan'] = {
    'phase_setting': phase_setting,
    'io_delay_scan_results': io_delay_scan_results,
    'io_delay_scan_io_delay_values': io_delay_scan_io_delay_values,
    'optimal_io_delay_values': optimal_io_delay_values
}

with open(os.path.join(output_dump_folder, 'io_delay_scan_config.json'), 'w') as f:
    json.dump(output_config_json, f, indent=4)

del udp_target
print("-- End of Script ----------------------")