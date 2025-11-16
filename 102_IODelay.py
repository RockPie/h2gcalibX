import packetlibX as packetlib
import numpy as np
import time
import json
import os, sys, uuid
import argparse
from loguru import logger
from tqdm import tqdm
import matplotlib.pyplot as plt
import caliblibX as caliblib

# * --- Set up script information -------------------------------------
script_id_str       = os.path.basename(__file__).split('.')[0]
script_version_str  = '1.4'

# Define a custom sink that uses tqdm to write log messages
class TqdmSink:
    def __init__(self):
        self.level = "DEBUG"

    def write(self, message):
        tqdm.write(message.rstrip())  # Remove the trailing newline

# Remove the default logger configuration
logger.remove()

# Add the custom tqdm sink with colored formatting for different levels
logger.add(
    TqdmSink(), 
    format="<green>{time:HH:mm:ss}</green> - "
           "<level>{level: <8}</level> - "
           "<level>{message}</level>",
    level="DEBUG",
    colorize=True,
    backtrace=True,
    diagnose=True,
)

# * --- Read command line arguments -----------------------------------
parser = argparse.ArgumentParser(description='IO delay scan for HGCROC')
parser.add_argument('-c', '--config', type=str, help='Path to the configuration file')
parser.add_argument('-r', '--reset', action='store_true', help='Enable reset before IO delay scan')
parser.add_argument('-t', '--trigger', action='store_true', help='Set trigger line delay')
parser.add_argument('-a', '--asic', type=int, help='ASIC number to scan')
parser.add_argument('-p', '--phase', type=int, default=12, help='Phase setting for the ASIC (default: 12)')
args = parser.parse_args()

# * --- Set up output folder -------------------------------------------
output_dump_path = 'dump'   # dump is for temporary files like config

output_folder_name      = f'{script_id_str}_data_{time.strftime("%Y%m%d_%H%M%S")}'
output_config_json_name = f'{script_id_str}_config_{time.strftime("%Y%m%d_%H%M%S")}.json'
output_config_json = {}

output_dump_folder = os.path.join(output_dump_path, output_folder_name)
output_config_path = os.path.join(output_dump_folder, output_config_json_name)

common_settings_json_path = "config/common_settings_4_11_208.json"
if args.config is not None:
    if os.path.exists(args.config):
        if args.config.endswith('.json'):
            common_settings_json_path = args.config
        else:
            logger.error(f"Configuration file must be a JSON file: {args.config}")
            exit()
    else:
        logger.error(f"Configuration file not found: {args.config}")
        exit()
is_common_settings_exist = False
try :
    with open(common_settings_json_path, 'r') as json_file:
        common_settings = json.load(json_file)
        is_common_settings_exist = True
except FileNotFoundError:
    logger.info(f"Common settings file not found: {common_settings_json_path}")

if not os.path.exists(output_dump_path):
    os.makedirs(output_dump_path)
if not os.path.exists(output_dump_folder):
    os.makedirs(output_dump_folder)

# * --- Load udp pool configuration file ------------------------------------------------
# * -------------------------------------------------------------------------------------
cfg_path = os.path.join(os.path.dirname(__file__), 'config/socket_pool_config.json')
with open(cfg_path, 'r') as f:
    cfg = json.load(f)

CONTROL_HOST = cfg['CONTROL_HOST']
CONTROL_PORT = cfg['CONTROL_PORT']
DATA_HOST    = cfg['DATA_HOST']
DATA_PORT    = cfg['DATA_PORT']
BUFFER_SIZE  = cfg['BUFFER_SIZE']

# * --- Set up socket -------------------------------------------------
h2gcroc_ip      = "10.1.2.208"
pc_ip           = "10.1.2.207"
h2gcroc_port    = 11000
pc_cmd_port     = 11000
pc_data_port    = 11001
timeout         = 1 # seconds
retry_time = 50

if is_common_settings_exist:
    try:
        udp_settings = common_settings['udp']
        h2gcroc_ip = udp_settings['h2gcroc_ip']
        pc_ip = udp_settings['pc_ip']
        h2gcroc_port = udp_settings['h2gcroc_port']
        pc_data_port = udp_settings['pc_data_port']
        pc_cmd_port = udp_settings['pc_cmd_port']
    except KeyError:
        logger.warning("Common settings file does not contain UDP settings")

logger.info(f"UDP settings: H2GCROC IP: {h2gcroc_ip}, PC IP: {pc_ip}, H2GCROC Port: {h2gcroc_port}")
logger.info(f"PC Data Port: {pc_data_port}, PC Command Port: {pc_cmd_port}")

output_config_json['udp'] = {
    'h2gcroc_ip': h2gcroc_ip,
    'pc_ip': pc_ip,
    'h2gcroc_port': h2gcroc_port,
    'pc_data_port': pc_data_port,
    'pc_cmd_port': pc_cmd_port,
    'timeout': timeout
}

worker_id       = str(uuid.uuid4())

try:
    ctrl_conn, data_cmd_conn, data_data_conn, cmd_outbound_conn, pool_do = caliblib.init_worker_sockets(
        worker_id, h2gcroc_ip, pc_ip,
        CONTROL_HOST, CONTROL_PORT, DATA_HOST, DATA_PORT,
        pc_cmd_port, pc_data_port,
        timeout, logger
    )
except Exception as e:
    logger.critical(f"Failed to initialize worker sockets: {e}")
    logger.critical("Please check the socket pool server and try again.")
    exit()

pool_do("register",   "data", pc_data_port)
pool_do("register",   "cmd",  pc_cmd_port)

# socket_cmd_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# socket_cmd_udp.bind((pc_ip, pc_cmd_port))
# socket_cmd_udp.settimeout(timeout)

# socket_data_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# socket_data_udp.bind((pc_ip, pc_data_port))
# socket_data_udp.settimeout(timeout)

# * --- Set running parameters ----------------------------------------
total_asic          = 2
if args.asic is not None:
    logger.info(f"Setting total ASIC to {args.asic}")
    if args.asic >= 1 and args.asic <= 8:
        total_asic = args.asic
logger.info(f"Total ASIC: {total_asic}")

asic_select         = (1 << total_asic) - 1
fpga_address        = int(h2gcroc_ip.split('.')[-1]) - 208
locked_output       = 0xaccccccc
sublist_min_len     = 10
sublist_extend      = 4
inter_step_sleep    = 0.05 # seconds
phase_setting       = 12
if args.phase is not None:
    if args.phase >= 0 and args.phase <= 15:
        phase_setting = args.phase
    else:
        logger.error(f"Phase setting must be between 0 and 15, got {args.phase}")
        exit()

enable_sublist          = True
enable_reset            = True
enable_trigger_delay    = False
if args.reset:
    enable_reset        = True
else:
    enable_reset        = False

if args.trigger:
    enable_trigger_delay = True
else:
    enable_trigger_delay = False

i2c_setting_verbose     = False
bitslip_verbose         = False
bitslip_debug_verbose   = False

output_config_json['running_parameters'] = {
    'total_asic': total_asic,
    'asic_select': asic_select,
    'fpga_address': fpga_address,
    'locked_output': locked_output,
    'sublist_min_len': sublist_min_len,
    'sublist_extend': sublist_extend,
    'inter_step_sleep': inter_step_sleep,
    'enable_sublist': enable_sublist,
    'enable_reset': enable_reset,
    'i2c_setting_verbose': i2c_setting_verbose,
    'bitslip_verbose': bitslip_verbose,
    'bitslip_debug_verbose': bitslip_debug_verbose
}

# * --- Useful functions ----------------------------------------------
def find_true_sublists(bool_list, step_size):
    if bool_list is None:
        return []
    results = []
    start_index = None
    in_sequence = False
    logger.debug(f"Finding true sublists in {bool_list}")

    for index, value in enumerate(bool_list):
        if value:
            if not in_sequence:
                # Starting a new sequence
                start_index = index * step_size
                in_sequence = True
        else:
            if in_sequence:
                # Ending a sequence
                results.append((start_index, index * step_size - start_index))
                in_sequence = False

    # Check if the last sequence extends to the end of the list
    if in_sequence:
        results.append((start_index, len(bool_list) * step_size - start_index))

    return results

# * --- I2C settings --------------------------------------------------
# i2c_content_top = [0x08,0x0f,0x40,0x7f,0x00,0x07,0x05,0x00]
# i2c_content_digital_half_0 = [0x00,0x00,0x00,0x00,0x80,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x19,0x00,0x0a,0xcc,0xcc,0xcc,0x0c,0xcc,0xcc,0xcc,0xcc,0x0f,0x02,0x00]
# i2c_content_digital_half_1 = [0x00,0x00,0x00,0x00,0x80,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x19,0x00,0x0a,0xcc,0xcc,0xcc,0x0c,0xcc,0xcc,0xcc,0xcc,0x0f,0x02,0x00]
# i2c_content_global_analog_0 =[0x6f,0xdb,0x83,0x28,0x28,0x28,0x9a,0x9a,0xa8,0x8a,0x40,0x4a,0x4b,0x68]
# i2c_content_global_analog_1 =[0x6f,0xdb,0x83,0x28,0x28,0x28,0x9a,0x9a,0xa8,0x8a,0x40,0x4a,0x4b,0x68]
# i2c_content_master_tdc_0 = [0x37,0xd4,0x54,0x80,0x0a,0xd4,0x03,0x00,0x80,0x80,0x0a,0x95,0x03,0x00,0x40,0x00]
# i2c_content_master_tdc_1 = [0x37,0xd4,0x54,0x80,0x0a,0xd4,0x03,0x00,0x80,0x80,0x0a,0x95,0x03,0x00,0x40,0x00]
# i2c_content_reference_voltage_0 = [0xb4,0x0a,0xfa,0xfa,0xb8,0xd4,0xda,0x42,0x00,0x00]
# i2c_content_reference_voltage_1 = [0xb4,0x0e,0xfa,0xfa,0xad,0xd4,0xda,0x42,0x00,0x00]
# i2c_content_half_wise_0 = [0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00]
# i2c_content_half_wise_1 = [0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00]

# * HGCROC register settings
# top is the same
i2c_content_top = [0x08,0x0f,0x40,0x7f,0x00,0x07,0x05,0x00]
i2c_content_top[7] = phase_setting & 0x0F
# digital half is the same
i2c_content_digital_half_0 = [0x00,0x00,0x00,0x00,0x80,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x19,0x00,0x0a,0xcc,0xcc,0xcc,0x0c,0xcc,0xcc,0xcc,0xcc,0x0f,0x02,0x00]
i2c_content_digital_half_1 = [0x00,0x00,0x00,0x00,0x80,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x19,0x00,0x0a,0xcc,0xcc,0xcc,0x0c,0xcc,0xcc,0xcc,0xcc,0x0f,0x02,0x00]
# some register definations are different for HGCROC
i2c_content_global_analog_0 =[0x6f,0xdb,0x83,0x28,0x28,0x28,0x9a,0x9a,0xa8,0x8a,0x40,0x4a,0x4b,0x68]
i2c_content_global_analog_1 =[0x6f,0xdb,0x83,0x28,0x28,0x28,0x9a,0x9a,0xa8,0x8a,0x40,0x4a,0x4b,0x68]
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
    'i2c_content_top': i2c_content_top,
    'i2c_content_digital_half_0': i2c_content_digital_half_0,
    'i2c_content_digital_half_1': i2c_content_digital_half_1,
    'i2c_content_global_analog_0': i2c_content_global_analog_0,
    'i2c_content_global_analog_1': i2c_content_global_analog_1,
    'i2c_content_master_tdc_0': i2c_content_master_tdc_0,
    'i2c_content_master_tdc_1': i2c_content_master_tdc_1,
    'i2c_content_reference_voltage_0': i2c_content_reference_voltage_0,
    'i2c_content_reference_voltage_1': i2c_content_reference_voltage_1,
    'i2c_content_half_wise_0': i2c_content_half_wise_0,
    'i2c_content_half_wise_1': i2c_content_half_wise_1
}

try:
    if enable_reset:
        for _asic in range(total_asic):
            if not packetlib.send_reset_adj(cmd_outbound_conn, h2gcroc_ip, h2gcroc_port,fpga_addr=fpga_address, asic_num=_asic, sw_hard_reset_sel=0x03, sw_hard_reset=0x01,sw_soft_reset_sel=0x00, sw_soft_reset=0x00, sw_i2c_reset_sel=0x00,sw_i2c_reset=0x00, reset_pack_counter=0x00, adjustable_start=0x00,verbose=False):
                logger.critical("Error in resetting ASIC " + str(_asic))
                exit()

    for _asic in range(total_asic):
        logger.info(f"Setting I2C for ASIC {_asic} ...")
        if not packetlib.send_check_i2c_wrapper(cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, asic_num=_asic, fpga_addr = fpga_address, sub_addr=packetlib.subblock_address_dict["Top"], reg_addr=0x00, data=i2c_content_top,retry=retry_time, verbose=i2c_setting_verbose):
            logger.warning(f"Readback mismatch for ASIC {_asic} Top")
        if not packetlib.send_check_i2c_wrapper(cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, asic_num=_asic, fpga_addr = fpga_address, sub_addr=packetlib.subblock_address_dict["Digital_Half_0"], reg_addr=0x00, data=i2c_content_digital_half_0,retry=retry_time, verbose=i2c_setting_verbose):
            logger.warning(f"Readback mismatch for ASIC {_asic} Digital_Half_0")
        if not packetlib.send_check_i2c_wrapper(cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, asic_num=_asic, fpga_addr = fpga_address, sub_addr=packetlib.subblock_address_dict["Digital_Half_1"], reg_addr=0x00, data=i2c_content_digital_half_1,retry=retry_time, verbose=i2c_setting_verbose):
            logger.warning(f"Readback mismatch for ASIC {_asic} Digital_Half_1")
        if not packetlib.send_check_i2c_wrapper(cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, asic_num=_asic, fpga_addr = fpga_address, sub_addr=packetlib.subblock_address_dict["Global_Analog_0"], reg_addr=0x00, data=i2c_content_global_analog_0,retry=retry_time, verbose=i2c_setting_verbose):
            logger.warning(f"Readback mismatch for ASIC {_asic} Global_Analog_0")
        if not packetlib.send_check_i2c_wrapper(cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, asic_num=_asic, fpga_addr = fpga_address, sub_addr=packetlib.subblock_address_dict["Global_Analog_1"], reg_addr=0x00, data=i2c_content_global_analog_1,retry=retry_time, verbose=i2c_setting_verbose):
            logger.warning(f"Readback mismatch for ASIC {_asic} Global_Analog_1")
        if not packetlib.send_check_i2c_wrapper(cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, asic_num=_asic, fpga_addr = fpga_address, sub_addr=packetlib.subblock_address_dict["Master_TDC_0"], reg_addr=0x00, data=i2c_content_master_tdc_0,retry=retry_time, verbose=i2c_setting_verbose):
            logger.warning(f"Readback mismatch for ASIC {_asic} Master_TDC_0")
        if not packetlib.send_check_i2c_wrapper(cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, asic_num=_asic, fpga_addr = fpga_address, sub_addr=packetlib.subblock_address_dict["Master_TDC_1"], reg_addr=0x00, data=i2c_content_master_tdc_1,retry=retry_time, verbose=i2c_setting_verbose):
            logger.warning(f"Readback mismatch for ASIC {_asic} Master_TDC_1")
        if not packetlib.send_check_i2c_wrapper(cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, asic_num=_asic, fpga_addr = fpga_address, sub_addr=packetlib.subblock_address_dict["Reference_Voltage_0"], reg_addr=0x00, data=i2c_content_reference_voltage_0,retry=retry_time, verbose=i2c_setting_verbose):
            logger.warning(f"Readback mismatch for ASIC {_asic} Reference_Voltage_0")
        if not packetlib.send_check_i2c_wrapper(cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, asic_num=_asic, fpga_addr = fpga_address, sub_addr=packetlib.subblock_address_dict["Reference_Voltage_1"], reg_addr=0x00, data=i2c_content_reference_voltage_1,retry=retry_time, verbose=i2c_setting_verbose):
            logger.warning(f"Readback mismatch for ASIC {_asic} Reference_Voltage_1")
        # ! HalfWise will not read back correctly
        packetlib.send_check_i2c_wrapper(cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, asic_num=_asic, fpga_addr = fpga_address, sub_addr=packetlib.subblock_address_dict["HalfWise_0"], reg_addr=0x00, data=i2c_content_half_wise_0,retry=retry_time, verbose=i2c_setting_verbose)
        packetlib.send_check_i2c_wrapper(cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, asic_num=_asic, fpga_addr = fpga_address, sub_addr=packetlib.subblock_address_dict["HalfWise_1"], reg_addr=0x00, data=i2c_content_half_wise_1,retry=retry_time, verbose=i2c_setting_verbose)

# * --- Main script ---------------------------------------------------
    
    
    best_values = []
    # quick_iodelay_settings = caliblib.quick_iodelay_setting(cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, _fpga_addr=fpga_address, _asic_num=total_asic, _good_setting_window_len=20, _locked_pattern=locked_output, _test_trigger_lines=enable_trigger_delay, _test_cycles=50, _verbose=False)
    # logger.info(f"Quick IO delay settings: {quick_iodelay_settings}")
    for _asic in range(total_asic):
        locked_flag_array  = []
        logger.info(f"Setting bitslip for ASIC {_asic}")
        progress_bar_local = range(0, 512, 2)
        delay_value_array = []
        delay_locked_array = []
        for _delay in progress_bar_local:
            # if _delay == 320: # Skip 320 because it is cursed
            #     continue
            # progress_bar_local.set_description(f"Delay " + "{:03}".format(_delay))
            # _locked = test_delay(_delay, _asic, verbose=False)
            # time.sleep(0.01)
            _locked = caliblib.delay_test(cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, _fpga_addr=fpga_address, _delay_setting=_delay, _asic_index=_asic, _asic_sel = asic_select ,_locked_pattern=locked_output, _test_trigger_lines=enable_trigger_delay, _verbose=False)
            locked_flag_array.append(_locked)
            delay_locked_array.append(_locked)
            delay_value_array.append(_delay)
        valid_sublists = []
        try:
            valid_sublists = find_true_sublists(locked_flag_array, 2)
        except:
            logger.error('No valid IO delay found for ASIC ' + str(_asic))
            continue
        if len(valid_sublists) == 0:
            logger.error('No valid IO delay found for ASIC ' + str(_asic))
            continue

        sorted_sublists = sorted(valid_sublists, key=lambda x: x[1], reverse=True)
        _valid_sublist_found = False
        _best_delay = 0
        logger.info(f"Searching for best IO delay for ASIC {_asic}")
        for _sublist_index in range(len(sorted_sublists)):
            _sublist = sorted_sublists[_sublist_index]
            # logger.info(f"Sublist start index: {_sublist[0]}, length: {_sublist[1]}")
            if len(_sublist) != 2:
                logger.warning(f"Abnormal sublist data format for ASIC {_asic}")
                break
            _start_index = _sublist[0]
            _sublist_len = _sublist[1]
            if _sublist_len < sublist_min_len:
                _best_delay = _start_index + _sublist_len // 2
                _valid_sublist_found = True
                logger.warning('No best IO delay found for ASIC ' + str(_asic)+ ' using coarse delay ' + str(_best_delay))
                break
            if not enable_sublist:
                _best_delay = _start_index + _sublist_len // 2
                _valid_sublist_found = True
                break
            else:
                _subscan_start = max(0, _start_index - sublist_extend)
                _subscan_end = min(511, _start_index + _sublist_len + sublist_extend)

            valid_subsublists = []
            locked_flag_sublist = []
            locked_delay_sublist = []
            progress_bar_sublocal = range(_subscan_start, _subscan_end, 1)
            for _subdelay in progress_bar_sublocal:
                # if _subdelay == 320:
                #     continue
                #progress_bar_sublocal.set_description(f"Delay " + "{:03}".format(_subdelay))
                #locked_flag_sublist.append(test_delay(_subdelay, _asic, verbose=False))
                locked_flag_sublist.append(caliblib.delay_test(cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, _fpga_addr=fpga_address, _delay_setting=_subdelay, _asic_index=_asic, _asic_sel = asic_select ,_locked_pattern=locked_output, _test_trigger_lines=enable_trigger_delay, _verbose=False))
                locked_delay_sublist.append(_subdelay)
            try:
                valid_subsublists = find_true_sublists(locked_flag_sublist, 1)
            except:
                continue
                # _best_delay = _start_index + _sublist_len // 2
                # _valid_sublist_found = True
                # logger.warning('No best IO delay found for ASIC ' + str(_asic)+ ' using coarse delay ' + str(_best_delay) + ' (E1)')
                # break
            if len(valid_subsublists) == 0:
                continue
                # _best_delay = _start_index + _sublist_len // 2
                # _valid_sublist_found = True
                # logger.warning('No best IO delay found for ASIC ' + str(_asic)+ ' using coarse delay ' + str(_best_delay) + ' (E2)')
                # break
            sorted_subsublists = sorted(valid_subsublists, key=lambda x: x[1], reverse=True)
            # logger.info(sorted_subsublists)
            try:
                best_sublist = sorted_subsublists[0]
            except:
                continue
            if best_sublist[1] > sublist_min_len:
                _best_delay = best_sublist[0] + best_sublist[1] // 2 + _subscan_start
                _valid_sublist_found = True
                break
            else:
                if _sublist_index == len(sorted_sublists) - 1:
                    _best_delay = _start_index + _sublist_len // 2
                    _valid_sublist_found = True
                    logger.warning('No best IO delay found for ASIC ' + str(_asic)+ ' using coarse delay ' + str(_best_delay) + ' (E4)')
                    break
                else:
                    continue
        if not _valid_sublist_found:
            logger.error('No valid IO delay found for ASIC ' + str(_asic))
            continue
        if not caliblib.delay_test(cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, _fpga_addr=fpga_address, _delay_setting=_best_delay, _asic_index=_asic, _asic_sel = asic_select ,_locked_pattern=locked_output, _test_trigger_lines=enable_trigger_delay, _verbose=False):
            logger.error(f"Best IO delay candidate for ASIC {_asic} is not locked")
            continue
        # if not test_delay(_best_delay, _asic, verbose=False):
        #     logger.error(f"Best IO delay candidate for ASIC {_asic} is not locked")
        #     continue
        else:
            logger.info(f"Best IO delay for ASIC {_asic}: {_best_delay}")
            best_values.append(_best_delay)


        # draw the plot
        fig = plt.figure(figsize=(15, 6))
        ax = fig.add_subplot(111)
        ax.plot(delay_value_array, delay_locked_array)
        # draw every sublist
        for _sublist in valid_sublists:
            _start_index = _sublist[0]
            _end_index = _start_index + _sublist[1]
            ax.axvspan(_start_index, _end_index, color='gray', alpha=0.5)
            ax.annotate(f"{_sublist[0]}", (_start_index + _sublist[1] // 2, 0.5), ha='center')
        ax.axvline(_best_delay, color='red', linestyle='--')
        ax.set_xlabel("IO Delay Value")
        ax.set_ylabel("Locked Status")
        ax.set_title(f"ASIC {_asic} IO Delay Scan")
        plt.savefig(os.path.join(output_dump_folder, f"asic{_asic}_io_delay_scan.pdf"), bbox_inches='tight')
        plt.close(fig)        

finally:
    pool_do("unregister", "data", pc_data_port)
    pool_do("unregister", "cmd", pc_cmd_port)
    data_cmd_conn.close()
    data_data_conn.close()
    cmd_outbound_conn.close()
    ctrl_conn.close()

output_config_json['best_values'] = best_values

output_config_json['common_settings_iodelay'] = common_settings_json_path

with open(output_config_path, 'w') as json_file:
    json.dump(output_config_json, json_file, indent=4)

logger.info(f"Configuration saved to {output_config_path}")