import caliblibX
import argparse     # for input arguments
import os, json, time
from loguru import logger
import numpy as np

# * --- Set up script information -------------------------------------
script_id_str       = os.path.basename(__file__).split('.')[0]
script_version_str  = '1.1'
script_folder       = os.path.dirname(__file__)
print("-- "+ script_id_str + " (v" + script_version_str + ") ----------------")
print(f"---------------------------------------")

# * --- Read command line arguments -----------------------------------
parser = argparse.ArgumentParser(description='IO delay scan for HGCROC')
parser.add_argument('-i', '--i2c', type=str, help='Path to the I2C settings JSON file')
parser.add_argument('-c', '--config', type=str, help='Path to the common settings JSON file')
parser.add_argument('-t', '--target', type=int, help='Target pedestal value')
parser.add_argument('-a', '--asic', type=int, help='ASIC number to scan')
parser.add_argument('-o', '--output', type=str, help='Output folder name')
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

# * --- Load I2C settings from file ------------------------------------
i2c_settings = {}
if args.i2c:
    i2c_files = args.i2c.split(',')
if len(i2c_files) != total_asic and len(i2c_files) != 1:
    print(f"Error: Number of I2C files provided ({len(i2c_files)}) does not match number of ASICs to scan ({total_asic}).")
    exit()

# * --- Create base I2C settings ---------------------------------
register_settings_list = []
if len(i2c_files) == total_asic:
    for asic_idx in range(total_asic):
        try:
            new_i2c_settings = caliblibX.h2gcroc_registers_full()
            new_i2c_settings.load_from_json(i2c_files[asic_idx])
            if not new_i2c_settings.is_same_udp_settings(udp_target, asic_idx):
                raise ValueError(f"UDP settings in {i2c_files[asic_idx]} do not match the target UDP settings for ASIC {asic_idx}.")
            register_settings_list.append(new_i2c_settings)
        except Exception as e:
            print(f"Error loading I2C settings from {i2c_files[asic_idx]}: {e}")
            exit()
else:
    for asic_idx in range(total_asic):
        try:
            new_i2c_settings = caliblibX.h2gcroc_registers_full()
            new_i2c_settings.load_from_json(i2c_files[0])
            new_i2c_settings.sync_udp_settings(udp_target, asic_idx)
            register_settings_list.append(new_i2c_settings)
        except Exception as e:
            print(f"Error loading I2C settings from {i2c_files[0]}: {e}")
            exit()
    print("- Using the same I2C settings for all ASICs")




output_config_json["i2c"] = {}
# output_config_json["i2c"]["top_reg_runLR"] = top_reg_runLR
# output_config_json["i2c"]["top_reg_offLR"] = top_reg_offLR

# * --- Set running parameters --------------------------------------
target_pedestal = 100
if args.target is not None:
    target_pedestal = int(args.target)

print(f"- Target pedestal value: {target_pedestal}")

# - i2c_retry: number of retries for i2c communication
# - (DNU) i2c_fragment_life: number of fragments to wait for a complete event
i2c_retry               = 30
i2c_fragment_life       = 3

# - machine_gun: number of samples to take for every cycle, recommend to keep under 20,
#                0 means 1 sample per cycle
# - phase_setting: phase setting for the ASIC clock (0 - 15)
machine_gun             = 10
phase_setting           = 12

# - gen_nr_cycle: number of cycles to run the generator
# - (DNU) gen_interval_value: interval value for the generator
gen_nr_cycle            = 1
gen_interval_value      = 255
expected_event_number   = gen_nr_cycle * (machine_gun + 1)

# - (DNU) gen_fcmd_internal_injection: fast command for internal injection
# - (DNU) gen_fcmd_L1A: fast command for L1A request
gen_fcmd_internal_injection = 0b00101101
gen_fcmd_L1A                = 0b01001011

# - inv_vref_default: default value for the inverted reference voltage
# - noinv_vref_default: default value for the non-inverted reference voltage
inv_vref_default    = 512
noinv_vref_default  = 512
initial_inv_vref_list   = [inv_vref_default ]  * total_asic * 2
initial_noinv_vref_list = [noinv_vref_default] * total_asic * 2

# - inputdac_default: default value for the input DAC
# - pede_trim_default: default value for the pedestal trim
inputdac_default    = 0
pede_trim_default   = 31

input_dac_values = [inputdac_default] * 76 * total_asic

# - (DNU) global_scan_range: range for the step 1 - global scan
# - (DNU) dead_channel_scan_range: range for the step 2 - dead channel scan
# - (DNU) dead_channel_std_threshold: threshold to determine if a channel is dead
# global_scan_range           = range(0, 1024, 32)
global_scan_range           = range(200, 800, 60)
global_scan_fitting_range   = [100, 500]
zero_chn_threshold          = 1 # not implemented
dead_channel_scan_range     = range(0, 64, 8)
dead_channel_std_threshold  = 10


# - (DNU) inputdac_step_size: step size for the input DAC tunning
# - (DNU) inputdac_tolerance: tolerance for the input DAC tunning
inputdac_step_size  = 1
inputdac_tolerance  = 2

# - (DNU) pede_trim_step_size: step size for the pedestal trim tunning
# - (DNU) pede_tolerance: tolerance for the pedestal trim tunning
pede_trim_step_size = 4
pede_tolerance      = 2
pede_trim_attempt_number = 128 // pede_trim_step_size + 1
pede_trim_values         = [pede_trim_default] * 76 * total_asic

# - (DNU) ref_inv_scan_range: range for the inverted reference voltage scan
ref_inv_scan_range  = range(200, 800, 10)

for _asic in range(total_asic):
    print(f"- Setting I2C for ASIC {_asic}...")
    _asic_i2c_settings = register_settings_list[_asic]
    _asic_i2c_settings.set_phase(phase_setting)
    _asic_i2c_settings.turn_on_daq()
    _asic_i2c_settings.send_all_registers(udp_target)

asic_values = [0x30 if i < total_asic else 0x00 for i in range(8)]
a0, a1, a2, a3, a4, a5, a6, a7 = asic_values
if not caliblibX.send_check_DAQ_gen_params_calib(
    udp_target, 
    data_coll_en        = 0x00,
    trig_coll_en        = 0x00,
    daq_fcmd            = gen_fcmd_L1A,
    gen_pre_fcmd        = 0x00,
    gen_fcmd            = gen_fcmd_L1A,
    ext_trg_en          = 0x00,
    ext_trg_delay       = 0x00,
    ext_trg_deadtime    = 10000,
    jumbo_en            = 0x00,
    gen_preimp_en       = 0x00,
    gen_pre_interval    = 0x0010,
    gen_nr_of_cycle     = gen_nr_cycle,
    gen_interval        = gen_interval_value,
    daq_push_fcmd       = gen_fcmd_L1A,
    machine_gun         = machine_gun,
    ext_trg_out_0_len   = 0x00,
    ext_trg_out_1_len   = 0x00,
    ext_trg_out_2_len   = 0x00,
    ext_trg_out_3_len   = 0x00,
    asic0_collection    = a0,
    asic1_collection    = a1,
    asic2_collection    = a2,
    asic3_collection    = a3,
    asic4_collection    = a4,
    asic5_collection    = a5,
    asic6_collection    = a6,
    asic7_collection    = a7,
    verbose             = True,
    readback            = True
):
    print("-- Warning: Failed to set/check DAQ and generator parameters")

cmd_outbound_conn = udp_target.cmd_outbound_conn
data_data_conn    = udp_target.data_data_conn
h2gcroc_ip        = udp_target.board_ip
h2gcroc_port      = udp_target.board_port
fpga_address      = 0x00  # default FPGA address
fragment_life    = i2c_fragment_life
adc_mean_list, adc_err_list = caliblibX.measure_adc(cmd_outbound_conn, data_data_conn, h2gcroc_ip, h2gcroc_port, total_asic, fpga_address, expected_event_number, fragment_life, logger, i2c_retry)

print("- Measurement results after DAQ/Gen setup:")
print(adc_mean_list)
print(adc_err_list)