import packetlib, caliblib
import socket, json, time, os, sys, uuid, copy
import numpy as np
from matplotlib import pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from tqdm import tqdm
from loguru import logger
import argparse

script_id_str       = os.path.basename(__file__).split('.')[0]
script_version_str  = '1.0'

# Remove the default logger configuration
logger.remove()

class TqdmSink:
    def __init__(self):
        self.level = "DEBUG"

    def write(self, message):
        tqdm.write(message.rstrip())  # Remove the trailing newline

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

# * --- Read command line arguments -----------------------------------------------------
# * -------------------------------------------------------------------------------------
parser = argparse.ArgumentParser(description='IO delay scan for HGCROC')
parser.add_argument('-i', '--i2c', type=str, help='Path to the I2C settings JSON file')
parser.add_argument('-c', '--config', type=str, help='Path to the common settings JSON file')
parser.add_argument('-t', '--target', type=int, help='Target pedestal value')
parser.add_argument('-a', '--asic', type=int, help='ASIC number to scan')
parser.add_argument('-o', '--output', type=str, help='Output folder name')
args = parser.parse_args()

input_i2c_json_names = []
input_i2c_json_name_default = 'config/default_2024Aug_config.json'

total_asic              = 2
if args.asic is not None:
    logger.info(f"Setting total ASIC to {args.asic}")
    if args.asic >= 1 and args.asic <= 8:
        total_asic = args.asic
logger.info(f"Total ASIC: {total_asic}")

if args.i2c is not None:
    # if there is space in between the path, there are two files
    if ',' in args.i2c:
        i2c_file_names = args.i2c.split(',')
        if len(i2c_file_names) != total_asic:
            logger.error("Invalid I2C settings file")
            sys.exit(1)
        for i2c_file_name in i2c_file_names:
            if not i2c_file_name.endswith('.json'):
                logger.error("I2C settings file must be in JSON format")
                sys.exit(1)
            input_i2c_json_names.append(i2c_file_name)
    else:
        if os.path.exists(args.i2c):
            if not args.i2c.endswith('.json'):
                logger.error("I2C settings file must be in JSON format")
                sys.exit(1)
            input_i2c_json_names.append(args.i2c)
        else:
            logger.error(f"I2C settings file {args.i2c} does not exist")
            sys.exit(1)
else:
    exit()
    # input_i2c_json_names.append(input_i2c_json_name_default)

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

# * --- Set up output folder and config file --------------------------------------------
# * -------------------------------------------------------------------------------------
outputs            = caliblib.setup_output(script_id_str, args.output)
output_dump_folder = outputs['dump_folder']
output_config_path = outputs['config_path']
output_pedecalib_json_name = outputs['pedecalib_name']
output_config_json = outputs['config_json']
output_folder_name = outputs['output_folder']
output_config_json_name = outputs['output_config_json']
pdf_file           = outputs['pdf_file']

# -- Find UDP settings ----------------------------------------------
# -------------------------------------------------------------------
common_settings_json_path = "config/common_settings_3B.json"
if args.config is not None:
    if os.path.exists(args.config):
        if not args.config.endswith('.json'):
            logger.error("Common settings file must be in JSON format")
            sys.exit(1)
        common_settings_json_path = args.config
    else:
        logger.error(f"Common settings file {args.config} does not exist")
        sys.exit(1)

is_common_settings_exist  = False
try:
    with open(common_settings_json_path, 'r') as json_file:
        common_settings_json = json.load(json_file)
        is_common_settings_exist = True
except:
    logger.warning(f"Common settings file {common_settings_json_path} does not exist")
# -------------------------------------------------------------------

# -- Register values ------------------------------------------------
# -------------------------------------------------------------------
i2c_settings_json_path = "config/h2gcroc_1v4_r1.json"
reg_settings = packetlib.RegisterSettings(i2c_settings_json_path)
i2c_config = json.load(open(i2c_settings_json_path, 'r'))

i2c_dict = {}
for key in list(i2c_config['I2C_address'].keys()):
   i2c_dict[key] = i2c_config['I2C_address'][key]
# -------------------------------------------------------------------

# -- Default UDP settings -------------------------------------------
# -------------------------------------------------------------------
h2gcroc_ip      = "10.1.2.208"
pc_ip           = "10.1.2.207"
h2gcroc_port    = 11000
pc_cmd_port     = 11000
pc_data_port    = 11001
timeout         = 0.1 # seconds

if is_common_settings_exist:
    try:
        udp_settings    = common_settings_json['udp']
        h2gcroc_ip      = udp_settings['h2gcroc_ip']
        pc_ip           = udp_settings['pc_ip']
        h2gcroc_port    = udp_settings['h2gcroc_port']
        pc_data_port    = udp_settings['pc_data_port']
        pc_cmd_port     = udp_settings['pc_cmd_port']
    except:
        logger.warning("Failed to load common settings")
        is_common_settings_exist = False

logger.info(f"UDP settings: H2GCROC IP: {h2gcroc_ip}, PC IP: {pc_ip}, H2GCROC Port: {h2gcroc_port}")
logger.info(f"PC Data Port: {pc_data_port}, PC Command Port: {pc_cmd_port}")

fpga_address    = int(h2gcroc_ip.split('.')[-1]) - 208
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

output_pedecalib_json = {}  # output json for pedestal calibration

output_pedecalib_json['udp'] = {
    'h2gcroc_ip': h2gcroc_ip,
    'pc_ip': pc_ip,
    'h2gcroc_port': h2gcroc_port,
    'pc_data_port': pc_data_port,
    'pc_cmd_port': pc_cmd_port,
    'timeout': timeout
}
# -------------------------------------------------------------------

# -- DAQ settings ---------------------------------------------------
# -- (DNU) - do NOT change unless you know what you are doing -------
# -------------------------------------------------------------------

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

# ! --- Pedestal related settings -------------------------------------------------
# ! -------------------------------------------------------------------------------
target_pedestal = 80
if args.target is not None:
    target_pedestal = int(args.target)
target_global_scan = 150
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
# ! -------------------------------------------------------------------------------
# -------------------------------------------------------------------

# - channel_not_used: list of channels that are not used, here are the CM channels
# - dead_channel_list: list of dead channels
# channel_not_used    = [0, 19, 38, 57, 76, 95, 114, 133]
channel_not_used    = []
dead_channel_list   = []

final_ref_inv_values   = []
final_ref_noinv_values = []

fragment_life = 3

logger.debug(f"Channel not used: {channel_not_used}")
logger.debug(f"Dead channel list: {dead_channel_list}")

config_output_jsons = []

if len(input_i2c_json_names) == 0:
    logger.warning("No I2C settings file is provided, using the default settings")
    i2c_config = json.load(open(i2c_settings_json_path, 'r'))
elif len(input_i2c_json_names) == 1:
    logger.info(f"Using I2C settings file: {input_i2c_json_names[0]}")
    i2c_config = json.load(open(input_i2c_json_names[0], 'r'))
    for asic_index in range(total_asic):
        config_output_jsons.append(copy.deepcopy(i2c_config))
elif len(input_i2c_json_names) == total_asic:
    for input_i2c_json_index, input_i2c_json_name in enumerate(input_i2c_json_names):
        logger.info(f"Using I2C settings file for ASIC {input_i2c_json_index}: {input_i2c_json_name}")
        i2c_config = json.load(open(input_i2c_json_name, 'r'))
        config_output_jsons.append(copy.deepcopy(i2c_config))
else:
    logger.error("Number of I2C settings files does not match the number of ASICs")
    sys.exit(1)


# print out the global analog and reference voltage settings
logger.info(f"Global Analog 0 settings: {i2c_config['Register Settings']['Global_Analog_0     ']}")
logger.info(f"Global Analog 1 settings: {i2c_config['Register Settings']['Global_Analog_1     ']}")
logger.info(f"Reference Voltage 0 settings: {i2c_config['Register Settings']['Reference_Voltage_0 ']}")
logger.info(f"Reference Voltage 1 settings: {i2c_config['Register Settings']['Reference_Voltage_1 ']}")

# print out the copied config global analog and reference voltage settings
for asic_index in range(total_asic):
    logger.debug(f"Config {asic_index} Global Analog 0 settings: {config_output_jsons[asic_index]['Register Settings']['Global_Analog_0     ']}")
    logger.debug(f"Config {asic_index} Global Analog 1 settings: {config_output_jsons[asic_index]['Register Settings']['Global_Analog_1     ']}")
    logger.debug(f"Config {asic_index} Reference Voltage 0 settings: {config_output_jsons[asic_index]['Register Settings']['Reference_Voltage_0 ']}")
    logger.debug(f"Config {asic_index} Reference Voltage 1 settings: {config_output_jsons[asic_index]['Register Settings']['Reference_Voltage_1 ']}")

# add pedestal calib info
for asic_index in range(total_asic):
    config_output_jsons[asic_index]["PedestalCalib"] = {
        "script_name": script_id_str,
        "output_folder": output_folder_name,
        "output_config_json": output_config_json_name,
        "output_pedecalib_json": output_pedecalib_json_name,
        "phase_setting": phase_setting
    }

    config_output_jsons[asic_index]["Target ASIC"]["ASIC Address"] = asic_index
    config_output_jsons[asic_index]["Target ASIC"]["FPGA Address"] = int(h2gcroc_ip.split('.')[-1]) - 208

output_pedecalib_json['running_parameters'] = {
    'total_asic': total_asic,
    'fpga_address': fpga_address,
    'target_pedestal': target_pedestal,
    'fragment_life': i2c_fragment_life,
    'channel_not_used': channel_not_used,
    'dead_channels': dead_channel_list,
    'gen_nr_cycle': gen_nr_cycle,
    'gen_interval_value': gen_interval_value,
    'gen_fcmd_internal_injection': gen_fcmd_internal_injection,
    'gen_fcmd_L1A': gen_fcmd_L1A,
    'i2c_setting_verbose': False    # not used, just for compatibility
}

# * --- Set up register values ----------------------------------------------------------
# * -------------------------------------------------------------------------------------

# -- Top register ---------------------------------------------------
# -------------------------------------------------------------------
config_json = json.load(open(input_i2c_json_names[0], 'r'))
default_top_reg = config_json["Register Settings"]["Top                 "]
default_top_reg = [int(x, 16) for x in default_top_reg.split()]

top_reg_runLR    = default_top_reg.copy()
top_reg_runLR[0] = top_reg_runLR[0] | 0x03
top_reg_runLR    = top_reg_runLR[:8]

top_reg_offLR    = default_top_reg.copy()
top_reg_offLR[0] = top_reg_offLR[0] & 0xFC
top_reg_offLR    = top_reg_offLR[:8]

top_reg_runLR[7] = phase_setting & 0x0F
top_reg_offLR[7] = phase_setting & 0x0F

output_config_json["i2c"] = {}
output_config_json["i2c"]["top_reg_runLR"] = top_reg_runLR
output_config_json["i2c"]["top_reg_offLR"] = top_reg_offLR
# -------------------------------------------------------------------

# -- Global Analog, Channel Wise, Reference Voltage -----------------
# -------------------------------------------------------------------
default_channel_wise = config_json["Register Settings"]["Channel_36          "]
default_channel_wise = [int(x, 16) for x in default_channel_wise.split()]

default_global_analog_0 = config_json["Register Settings"]["Global_Analog_0     "]
default_global_analog_1 = config_json["Register Settings"]["Global_Analog_1     "]
default_global_analog_0 = [int(x, 16) for x in default_global_analog_0.split()]
default_global_analog_1 = [int(x, 16) for x in default_global_analog_1.split()]

# print out the global analog settings
logger.info(f"Global Analog 0 settings: {default_global_analog_0}")
logger.info(f"Global Analog 1 settings: {default_global_analog_1}")

default_reference_voltage_0 = config_json["Register Settings"]["Reference_Voltage_0 "]
default_reference_voltage_1 = config_json["Register Settings"]["Reference_Voltage_1 "]
default_reference_voltage_0 = [int(x, 16) for x in default_reference_voltage_0.split()]
default_reference_voltage_1 = [int(x, 16) for x in default_reference_voltage_1.split()]
# -------------------------------------------------------------------

# * --- Start Measurement ---------------------------------------------------------------
# * -------------------------------------------------------------------------------------
verbose_setup_gen = False

all_chn_value_0_array = np.zeros((expected_event_number+1, 76*total_asic))
all_chn_value_1_array = np.zeros((expected_event_number+1, 76*total_asic))
all_chn_value_2_array = np.zeros((expected_event_number+1, 76*total_asic))
hamming_code_array    = np.zeros((expected_event_number+1,  6*total_asic))

extracted_payloads_pool = []
event_fragment_pool     = []
fragment_life_dict      = {}

current_half_packet_num = 0
current_event_num = 0

result_adc_mean_lists = []
result_adc_err_lists  = []

verbose_setup_gen           = False
verbose_global_analog       = False
verbose_reference_voltage   = False
verbose_channel_wise        = False

try:
    for _asic in range(total_asic):
        # -- Set up global analog -----------------------------------
        # -----------------------------------------------------------
        _global_analog_0 = default_global_analog_0.copy()
        _global_analog_1 = default_global_analog_1.copy()

        if not packetlib.send_check_i2c_wrapper(cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, asic_num=_asic, fpga_addr = fpga_address, sub_addr=packetlib.subblock_address_dict["Global_Analog_0"], reg_addr=0x00, data=_global_analog_0, retry=i2c_retry, verbose=verbose_global_analog):
            logger.warning(f"Failed to set Global_Analog_0 settings for ASIC {_asic}")
        if not packetlib.send_check_i2c_wrapper(cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, asic_num=_asic, fpga_addr = fpga_address, sub_addr=packetlib.subblock_address_dict["Global_Analog_1"], reg_addr=0x00, data=_global_analog_1, retry=i2c_retry, verbose=verbose_global_analog):
            logger.warning(f"Failed to set Global_Analog_1 settings for ASIC {_asic}")
        # -----------------------------------------------------------

        # -- Set up reference voltage -------------------------------
        # -----------------------------------------------------------
        _ref_voltage_half0 = default_reference_voltage_0.copy()
        _ref_voltage_half1 = default_reference_voltage_1.copy()

        logger.info(f"preset ref voltage_0 {_ref_voltage_half0}, ref voltage_1 {_ref_voltage_half1}")

        _ref_voltage_half0[1] = ( _ref_voltage_half0[1] & 0xF0) | ((initial_inv_vref_list[_asic*2] & 0x03) << 2) | (initial_noinv_vref_list[_asic*2] & 0x03)
        _ref_voltage_half1[1] = ( _ref_voltage_half1[1] & 0xF0) | ((initial_inv_vref_list[_asic*2+1] & 0x03) << 2) | (initial_noinv_vref_list[_asic*2+1] & 0x03)

        _ref_voltage_half0[4] = initial_inv_vref_list[_asic*2] >> 2
        _ref_voltage_half1[4] = initial_inv_vref_list[_asic*2 + 1] >> 2
        _ref_voltage_half0[5] = initial_noinv_vref_list[_asic*2] >> 2
        _ref_voltage_half1[5] = initial_noinv_vref_list[_asic*2 + 1] >> 2

        _ref_voltage_half0[7] = 0x00
        _ref_voltage_half0[6] = 0x00
        _ref_voltage_half1[7] = 0x00
        _ref_voltage_half1[6] = 0x00

        _ref_voltage_half0[10] = 0x80
        _ref_voltage_half1[10] = 0x80

        logger.info(f"modified ref voltage_0 {_ref_voltage_half0}, ref voltage_1 {_ref_voltage_half1}")

        if not packetlib.send_check_i2c_wrapper(cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, asic_num=_asic, fpga_addr = fpga_address, sub_addr=packetlib.subblock_address_dict["Reference_Voltage_0"], reg_addr=0x00, data=_ref_voltage_half0, retry=i2c_retry, verbose=verbose_reference_voltage):
            logger.warning(f"Failed to set Reference_Voltage_Half_0 settings for ASIC {_asic}")
        if not packetlib.send_check_i2c_wrapper(cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, asic_num=_asic, fpga_addr = fpga_address, sub_addr=packetlib.subblock_address_dict["Reference_Voltage_1"], reg_addr=0x00, data=_ref_voltage_half1, retry=i2c_retry, verbose=verbose_reference_voltage):
            logger.warning(f"Failed to set Reference_Voltage_Half_1 settings for ASIC {_asic}")
        # -----------------------------------------------------------

        # -- Set up channel wise ------------------------------------
        # -----------------------------------------------------------
        _chn_wise = default_channel_wise.copy()
        _chn_wise[0] = inputdac_default & 0x3F
        _chn_wise[3] = (pede_trim_default << 2)  & 0xFC
        # _chn_wise[4] = 0x04
        # ! the halfwise readback is not the same as the write value
        packetlib.send_check_i2c_wrapper(cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, asic_num=_asic, fpga_addr = fpga_address, sub_addr=packetlib.subblock_address_dict["HalfWise_0"], reg_addr=0x00, data=_chn_wise, retry=1, verbose=verbose_channel_wise)
        packetlib.send_check_i2c_wrapper(cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, asic_num=_asic, fpga_addr = fpga_address, sub_addr=packetlib.subblock_address_dict["HalfWise_1"], reg_addr=0x00, data=_chn_wise, retry=1, verbose=verbose_channel_wise)
        # -----------------------------------------------------------

        # -- Turn on DAQ --------------------------------------------
        # -----------------------------------------------------------
        if not packetlib.send_check_i2c_wrapper(cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, asic_num=_asic, fpga_addr = fpga_address, sub_addr=packetlib.subblock_address_dict["Top"], reg_addr=0x00, data=top_reg_runLR, retry=i2c_retry, verbose=False):
            logger.warning(f"Failed to turn on LR for ASIC {_asic}")
        else:
            logger.info(f"Turned on LR for ASIC {_asic}")
        # -----------------------------------------------------------

    # -- Set up DAQ ------------------------------------------------
    # data_coll_en: 0x03, turn on data collection for ASIC 0 and 1
    # trig_coll_en: 0x00, turn off trigger collection
    # daq_fcmd:     0b01001011, L1A
    # gen_preimp_en:0, turn off pre-fcmd
    # ---------------------------------------------------------------
    asic_values = [0x30 if i < total_asic else 0x00 for i in range(8)]
    a0, a1, a2, a3, a4, a5, a6, a7 = asic_values
    if not packetlib.send_check_DAQ_gen_params(
                              cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, fpga_addr=fpga_address,
                              data_coll_en=0x00, trig_coll_en=0x00, 
                              daq_fcmd=gen_fcmd_L1A, gen_pre_fcmd=0x00, gen_fcmd=gen_fcmd_L1A, 
                              ext_trg_en=0x00, ext_trg_delay=0x00, ext_trg_deadtime=10000, 
                              jumbo_en=0x00, 
                              gen_preimp_en=0x00, gen_pre_interval=0x0010, gen_nr_of_cycle=gen_nr_cycle, 
                              gen_interval=gen_interval_value, 
                              daq_push_fcmd=gen_fcmd_L1A, machine_gun=machine_gun, 
                              ext_trg_out_0_len=0x00, ext_trg_out_1_len=0x00, ext_trg_out_2_len=0x00, ext_trg_out_3_len=0x00, 
                              asic0_collection=a0, asic1_collection=a1, asic2_collection=a2, asic3_collection=a3, 
                              asic4_collection=a4, asic5_collection=a5, asic6_collection=a6, asic7_collection=a7, 
                              verbose=True, readback=True):

        logger.warning("Failed to set up generator")
    else:
        logger.info("Generator set up successfully")
    
    logger.info("Starting measurement...")
    adc_mean_list, adc_err_list = caliblib.measure_adc(cmd_outbound_conn, data_data_conn, h2gcroc_ip, h2gcroc_port, total_asic, fpga_address, expected_event_number, fragment_life, logger, i2c_retry)
    logger.info("Measurement done")
    
    fig, ax = caliblib.plot_channel_adc(
        adc_mean_list,
        adc_err_list,
        'Initial pedestal values'
    )
    pdf_file.savefig(fig)
    plt.close(fig)

    # * --- Step 1: Global scan ---------------------------------------------------------
    # * ---------------------------------------------------------------------------------
    corase_scan_ref_values    = [] # < scans
    corase_scan_noinv_values  = []
    average_pedestals         = [[] for _ in range(2*total_asic)]   # < halves < scans
    average_pedestals_err     = [[] for _ in range(2*total_asic)]   # < halves < scans
    channel_scan_adcs         = [[] for _ in range(76*total_asic)]  # < channels < scans

    _ref_noinv = noinv_vref_default
    for _ref_inv in tqdm(global_scan_range, desc="Global Scan"):
        for _asic in range(total_asic):
            _ref_voltage_half0 = default_reference_voltage_0.copy()
            _ref_voltage_half1 = default_reference_voltage_1.copy()

            _ref_voltage_half0[1] = ( _ref_voltage_half0[1] & 0xF0) | ((_ref_inv & 0x03) << 2) | (_ref_noinv & 0x03)
            _ref_voltage_half1[1] = ( _ref_voltage_half1[1] & 0xF0) | ((_ref_inv & 0x03) << 2) | (_ref_noinv & 0x03)

            _ref_voltage_half0[4] = _ref_inv >> 2
            _ref_voltage_half1[4] = _ref_inv >> 2
            _ref_voltage_half0[5] = _ref_noinv >> 2
            _ref_voltage_half1[5] = _ref_noinv >> 2

            if not packetlib.send_check_i2c_wrapper(cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, asic_num=_asic, fpga_addr = fpga_address, sub_addr=packetlib.subblock_address_dict["Reference_Voltage_0"], reg_addr=0x00, data=_ref_voltage_half0, retry=i2c_retry, verbose=verbose_reference_voltage):
                logger.warning(f"Failed to set Reference_Voltage_Half_0 settings for ASIC {_asic}")
            if not packetlib.send_check_i2c_wrapper(cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, asic_num=_asic, fpga_addr = fpga_address, sub_addr=packetlib.subblock_address_dict["Reference_Voltage_1"], reg_addr=0x00, data=_ref_voltage_half1, retry=i2c_retry, verbose=verbose_reference_voltage):
                logger.warning(f"Failed to set Reference_Voltage_Half_1 settings for ASIC {_asic}")

            time.sleep(0.1)

        adc_mean_list, adc_err_list = caliblib.measure_adc(cmd_outbound_conn, data_data_conn, h2gcroc_ip, h2gcroc_port, total_asic, fpga_address, expected_event_number, fragment_life, logger, i2c_retry)
        print(adc_mean_list)

        corase_scan_ref_values.append(_ref_inv)
        corase_scan_noinv_values.append(_ref_noinv)

        for _chn in range(76 * total_asic):
            channel_scan_adcs[_chn].append(adc_mean_list[_chn])


    #  -- Calculate average pedestal values, dead channels and max pedestal values ------
    global_scan_half_chn_sums = [[0 for _ in range(len(corase_scan_ref_values))] for _ in range(2*total_asic)]
    global_scan_half_chn_nums = [[0 for _ in range(len(corase_scan_ref_values))] for _ in range(2*total_asic)]
    global_scan_half_chn_diff_square_sums = [[0 for _ in range(len(corase_scan_ref_values))] for _ in range(2*total_asic)]
    channel_pedestal_stds = [0 for _ in range(76 * total_asic)]

    maximum_chn_pedestal_index_list = []
    minimum_chn_pedestal_index_list = []
    # find the maximum pedestal channel index for each scan
    for _scan in range(len(corase_scan_ref_values)):
        maximum_chn_pedestal_index = 0
        minimum_chn_pedestal_index = 0
        for _chn in range(76 * total_asic):
            if _chn in channel_not_used:
                continue
            if _chn in dead_channel_list:
                continue
            if channel_scan_adcs[_chn][_scan] > channel_scan_adcs[maximum_chn_pedestal_index][_scan]:
                maximum_chn_pedestal_index = _chn
            if channel_scan_adcs[_chn][_scan] < channel_scan_adcs[minimum_chn_pedestal_index][_scan]:
                minimum_chn_pedestal_index = _chn
        maximum_chn_pedestal_index_list.append(maximum_chn_pedestal_index)
        minimum_chn_pedestal_index_list.append(minimum_chn_pedestal_index)

    for _chn in range(76 * total_asic):
        if _chn in channel_not_used:
            continue
        if _chn in dead_channel_list:
            continue
        _chn_half_index = _chn // 38
        _chn_pedestal_std = np.std(channel_scan_adcs[_chn])
        channel_pedestal_stds[_chn] = _chn_pedestal_std
        if _chn_pedestal_std < dead_channel_std_threshold:
            dead_channel_list.append(_chn)
            logger.warning(f"Channel {_chn} is dead, std: {round(_chn_pedestal_std, 2)}")
        else:
            for _scan in range(len(corase_scan_ref_values)):
                # exclude the max and min pedestal values
                if _chn == maximum_chn_pedestal_index_list[_scan] or _chn == minimum_chn_pedestal_index_list[_scan]:
                    continue
                global_scan_half_chn_sums[_chn_half_index][_scan] += channel_scan_adcs[_chn][_scan]
                global_scan_half_chn_nums[_chn_half_index][_scan] += 1

    for _half in range(2*total_asic):
        for _scan in range(len(corase_scan_ref_values)):
            if global_scan_half_chn_nums[_half][_scan] > 0:
                average_pedestals[_half].append(global_scan_half_chn_sums[_half][_scan] / global_scan_half_chn_nums[_half][_scan])
            else:
                average_pedestals[_half].append(target_pedestal)

    for _half in range(2*total_asic):
        global_scan_half_chn_nums[_half] = [0 for _ in range(len(corase_scan_ref_values))]

    for _chn in range(76 * total_asic):
        if _chn in channel_not_used:
            continue
        if _chn in dead_channel_list:
            continue
        _chn_half_index = _chn // 38
        for _scan in range(len(corase_scan_ref_values)):
            global_scan_half_chn_diff_square_sums[_chn_half_index][_scan] += (channel_scan_adcs[_chn][_scan] - average_pedestals[_chn_half_index][_scan]) ** 2

    for _half in range(2*total_asic):
        for _scan in range(len(corase_scan_ref_values)):
            if global_scan_half_chn_nums[_half][_scan] > 0:
                average_pedestals_err[_half].append(np.sqrt(global_scan_half_chn_diff_square_sums[_half][_scan] / (global_scan_half_chn_nums[_half][_scan] - 1)) / np.sqrt(global_scan_half_chn_nums[_half][_scan]))
            else:
                average_pedestals_err[_half].append(target_pedestal)

    del global_scan_half_chn_sums
    del global_scan_half_chn_nums
    del global_scan_half_chn_diff_square_sums
    del channel_scan_adcs
    # -----------------------------------------------------------------------------------

    # draw the std distribution
    fig, ax = plt.subplots(1, 1, figsize=(12, 9))
    ax.hist(channel_pedestal_stds, bins=int(max(channel_pedestal_stds) - min(channel_pedestal_stds)), color='blue', alpha=0.7)
    ax.axvline(x=dead_channel_std_threshold, color='red', linestyle='--', label='Dead Channel Threshold')
    ax.set_xlabel('Pedestal Std [ADC]')
    ax.set_ylabel('Number of Channels')
    ax.set_ylim(0, 19 * total_asic)
    ax.annotate('Pedestal Std Distribution', xy=(0.02, 0.95), xycoords='axes fraction', fontsize=17, color='#062B35FF', fontweight='bold')
    ax.legend()
    pdf_file.savefig(fig)
    plt.close(fig)

    dist_global_scan_target     = [1024 for _ in range(2*total_asic)]
    dist_minimal_ref_values     = [0 for _ in range(2*total_asic)]
    dist_global_scan_peak_found = [False for _ in range(2*total_asic)]
    for _half in range(2*total_asic):
        average_pedestals[_half] = [round(x, 2) for x in average_pedestals[_half]]
        logger.info(f"Average pedestals for half {_half}: {average_pedestals[_half]}")
        if max(average_pedestals[_half]) < target_global_scan:
            logger.warning(f"Pedestal values are too low for half {_half}")
        for _ref_index in range(len(corase_scan_ref_values)):
            if not dist_global_scan_peak_found[_half] and _ref_index < len(corase_scan_ref_values) - 1:
                if average_pedestals[_half][_ref_index] > average_pedestals[_half][_ref_index + 1] + 30:
                    dist_global_scan_peak_found[_half] = True
            if abs(average_pedestals[_half][_ref_index] - target_global_scan) < dist_global_scan_target[_half] and dist_global_scan_peak_found[_half]:
                dist_global_scan_target[_half] = abs(average_pedestals[_half][_ref_index] - target_global_scan)
                dist_minimal_ref_values[_half] = corase_scan_ref_values[_ref_index]

    global_ref_inv_values   = []
    global_ref_noinv_values = []

    fig, ax = plt.subplots(1, 1, figsize=(12, 9))
    for _half in range(2*total_asic):
        ax.errorbar(corase_scan_ref_values, average_pedestals[_half], yerr=average_pedestals_err[_half], label=f"Half {_half}", marker='o', markersize=2, color=caliblib.color_list[_half])
        ax.axvline(x=dist_minimal_ref_values[_half], color=caliblib.color_list[_half], linestyle='--', label=f"Target {_half}")
    ax.set_xlabel('Reference Voltage Value')
    ax.set_ylabel('Pedestal Value [ADC]')
    ax.set_ylim(-50, 1024)
    ax.annotate('Pedestal vs. Global Reference', xy=(0.02, 0.95), xycoords='axes fraction', fontsize=17, color='#062B35FF', fontweight='bold')
    ax.legend()
    pdf_file.savefig(fig)
    plt.close(fig)

    time.sleep(0.1)

    # -- Set up global analog -----------------------------------
    # -----------------------------------------------------------
    for _asic in range(total_asic):
        for _half in range(2):
            global_ref_inv_values.append(dist_minimal_ref_values[_asic*2 + _half])
            global_ref_noinv_values.append(noinv_vref_default)

    for _asic in range(total_asic):
        _ref_voltage_half0 = default_reference_voltage_0.copy()
        _ref_voltage_half1 = default_reference_voltage_1.copy()

        _ref_voltage_half0[1] = ( _ref_voltage_half0[1] & 0xF0) | ((global_ref_inv_values[_asic*2] & 0x03) << 2) | (global_ref_noinv_values[_asic*2] & 0x03)
        _ref_voltage_half1[1] = ( _ref_voltage_half1[1] & 0xF0) | ((global_ref_inv_values[_asic*2+1] & 0x03) << 2) | (global_ref_noinv_values[_asic*2+1] & 0x03)

        _ref_voltage_half0[4] = global_ref_inv_values[_asic*2] >> 2
        _ref_voltage_half1[4] = global_ref_inv_values[_asic*2 + 1] >> 2
        _ref_voltage_half0[5] = global_ref_noinv_values[_asic*2] >> 2
        _ref_voltage_half1[5] = global_ref_noinv_values[_asic*2 + 1] >> 2

        if not packetlib.send_check_i2c_wrapper(cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, asic_num=_asic, fpga_addr = fpga_address, sub_addr=packetlib.subblock_address_dict["Reference_Voltage_0"], reg_addr=0x00, data=_ref_voltage_half0, retry=i2c_retry, verbose=verbose_reference_voltage):
            logger.warning(f"Failed to set Reference_Voltage_Half_0 settings for ASIC {_asic}")
        if not packetlib.send_check_i2c_wrapper(cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, asic_num=_asic, fpga_addr = fpga_address, sub_addr=packetlib.subblock_address_dict["Reference_Voltage_1"], reg_addr=0x00, data=_ref_voltage_half1, retry=i2c_retry, verbose=verbose_reference_voltage):
            logger.warning(f"Failed to set Reference_Voltage_Half_1 settings for ASIC {_asic}")

        time.sleep(0.1)

    adc_mean_list, adc_err_list = caliblib.measure_adc(cmd_outbound_conn, data_data_conn, h2gcroc_ip, h2gcroc_port, total_asic, fpga_address, expected_event_number, fragment_life, logger, i2c_retry)

    maximum_pedestals         = [0 for _ in range(2*total_asic)]   # < halves < scans
    second_maximum_pedestals  = [0 for _ in range(2*total_asic)]   # < halves < scans
    pedestal_sum_list        = [0 for _ in range(2*total_asic)]   # < halves < scans
    pedestal_num_list        = [0 for _ in range(2*total_asic)]   # < halves < scans
    for _chn_index in range(76 * total_asic):
        if _chn_index in channel_not_used:
            continue
        if _chn_index in dead_channel_list:
            continue
        _chn_half_index = _chn_index // 38
        if adc_mean_list[_chn_index] > maximum_pedestals[_chn_half_index]:
            second_maximum_pedestals[_chn_half_index] = maximum_pedestals[_chn_half_index]
            maximum_pedestals[_chn_half_index] = adc_mean_list[_chn_index]
        pedestal_sum_list[_chn_half_index] += adc_mean_list[_chn_index]
        pedestal_num_list[_chn_half_index] += 1

    for _half in range(2*total_asic):
        if pedestal_num_list[_half] == 0:
            maximum_pedestals[_half] = target_pedestal
        else:
            maximum_pedestals[_half] = pedestal_sum_list[_half] / pedestal_num_list[_half]
        # maximum_pedestals[_half] = min(maximum_pedestals[_half], second_maximum_pedestals[_half] + 20)
        # if maximum_pedestals[_half] - second_maximum_pedestals[_half] > 200:
        #     maximum_pedestals[_half] = second_maximum_pedestals[_half] + 50
        #     logger.warning(f"Pedestal values are too high for half {_half}, set to {maximum_pedestals[_half]}")

    del second_maximum_pedestals

    fig, ax = caliblib.plot_channel_adc(
        adc_mean_list,
        adc_err_list,
        'Global scan results',
        dead_channels=dead_channel_list
    )
    for _half in range(2 * total_asic):
        normalized_xmin = (_half * 38 - ax.get_xlim()[0]) / (ax.get_xlim()[1] - ax.get_xlim()[0])
        normalized_xmax = ((_half + 1) * 38 - ax.get_xlim()[0]) / (ax.get_xlim()[1] - ax.get_xlim()[0])
        ax.axhline(
            y=maximum_pedestals[_half],
            xmin=normalized_xmin,
            xmax=normalized_xmax,
            color=caliblib.color_list[_half],
            linestyle='--',
            label=f"Max {_half}"
        )
    ax.legend()
    pdf_file.savefig(fig)
    plt.close(fig)

    # * --- Step 2: Coarse channel wise trimming ----------------------------------------
    # * ---------------------------------------------------------------------------------
    coarse_chn_trimming_attempt_number = 4

    # make the maximum_pedestals integer
    for _half in range(2*total_asic):
        maximum_pedestals[_half] = round(maximum_pedestals[_half])

    logger.debug(f"adc_mean_list: {adc_mean_list}")
    logger.debug(f"maximum_pedestals: {maximum_pedestals}")

    for _attempt in tqdm(range(coarse_chn_trimming_attempt_number), desc="Coarse Channel Wise Trimming"):
        _changed_chn_cnt = 0
        for _chn in range(76 * total_asic):
            if _chn not in channel_not_used and _chn not in dead_channel_list:
                _half_index = _chn // 38
                if adc_mean_list[_chn] < maximum_pedestals[_half_index] - pede_tolerance:
                    pede_trim_values[_chn] += pede_trim_step_size
                    if pede_trim_values[_chn] > 63:
                        pede_trim_values[_chn] = 63
                    _chn_wise = default_channel_wise.copy()
                    _chn_wise[0] = input_dac_values[_chn] & 0x3F
                    _chn_wise[3] = (pede_trim_values[_chn] << 2) & 0xFC

                    if not packetlib.send_check_i2c_wrapper(cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, asic_num=_chn // 76, fpga_addr = fpga_address, sub_addr=packetlib.uni_chn_to_subblock_list[_chn%76], reg_addr=0x00, data=_chn_wise, retry=i2c_retry, verbose=verbose_channel_wise):
                        logger.warning(f"Failed to set Channel_{_chn} settings for ASIC {_chn // 76}")

                    _changed_chn_cnt += 1

                elif adc_mean_list[_chn] > maximum_pedestals[_half_index] + pede_tolerance:
                    pede_trim_values[_chn] -= pede_trim_step_size
                    if pede_trim_values[_chn] < 0:
                        pede_trim_values[_chn] = 0
                    _chn_wise = default_channel_wise.copy()
                    _chn_wise[0] = input_dac_values[_chn] & 0x3F
                    _chn_wise[3] = (pede_trim_values[_chn] << 2) & 0xFC

                    if not packetlib.send_check_i2c_wrapper(cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, asic_num=_chn // 76, fpga_addr = fpga_address, sub_addr=packetlib.uni_chn_to_subblock_list[_chn%76], reg_addr=0x00, data=_chn_wise, retry=i2c_retry, verbose=verbose_channel_wise):
                        logger.warning(f"Failed to set Channel_{_chn} settings for ASIC {_chn // 76}")

                    _changed_chn_cnt += 1

        logger.info(f"Attempt {_attempt + 1}: {pede_trim_values}")

        if _changed_chn_cnt == 0:
            logger.info(f"No channel changed in attempt {_attempt + 1}, stop trimming")
            break

        adc_mean_list, adc_err_list = caliblib.measure_adc(cmd_outbound_conn, data_data_conn, h2gcroc_ip, h2gcroc_port, total_asic, fpga_address, expected_event_number, fragment_life, logger, i2c_retry)

    fig, ax = caliblib.plot_channel_adc(
        adc_mean_list,
        adc_err_list,
        f'Coarse channel wise trimming attempt {_attempt + 1}',
        dead_channels=dead_channel_list
    )
    for _half in range(2 * total_asic):
        normalized_xmin = (_half * 38 - ax.get_xlim()[0]) / (ax.get_xlim()[1] - ax.get_xlim()[0])
        normalized_xmax = ((_half + 1) * 38 - ax.get_xlim()[0]) / (ax.get_xlim()[1] - ax.get_xlim()[0])
        ax.axhline(
            y=maximum_pedestals[_half],
            xmin=normalized_xmin,
            xmax=normalized_xmax,
            color=caliblib.color_list[_half],
            linestyle='--',
            label=f"Max {_half}"
        )
    ax.legend()
    pdf_file.savefig(fig)
    plt.close(fig)

    # * --- Step 3: Fine Reference inv scan ---------------------------------------------
    # * ---------------------------------------------------------------------------------
    corase_scan_ref_values    = [] # < scans
    corase_scan_noinv_values  = []
    average_pedestals         = [[] for _ in range(2*total_asic)]   # < halves < scans
    average_pedestals_err     = [[] for _ in range(2*total_asic)]   # < halves < scans
    channel_scan_adcs         = [[] for _ in range(76*total_asic)]  # < channels < scans

    _ref_noinv = noinv_vref_default
    for _ref_inv in tqdm(ref_inv_scan_range, desc="Ref_Inv Scan"):
        for _asic in range(total_asic):
            _ref_voltage_half0 = default_reference_voltage_0.copy()
            _ref_voltage_half1 = default_reference_voltage_1.copy()

            _ref_voltage_half0[1] = ( _ref_voltage_half0[1] & 0xF0) | ((_ref_inv & 0x03) << 2) | (global_ref_noinv_values[_asic*2] & 0x03)
            _ref_voltage_half1[1] = ( _ref_voltage_half1[1] & 0xF0) | ((_ref_inv & 0x03) << 2) | (global_ref_noinv_values[_asic*2+1] & 0x03)

            _ref_voltage_half0[4] = _ref_inv >> 2
            _ref_voltage_half1[4] = _ref_inv >> 2
            _ref_voltage_half0[5] = _ref_noinv >> 2
            _ref_voltage_half1[5] = _ref_noinv >> 2

            if not packetlib.send_check_i2c_wrapper(cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, asic_num=_asic, fpga_addr = fpga_address, sub_addr=packetlib.subblock_address_dict["Reference_Voltage_0"], reg_addr=0x00, data=_ref_voltage_half0, retry=i2c_retry, verbose=verbose_reference_voltage):
                logger.warning(f"Failed to set Reference_Voltage_Half_0 settings for ASIC {_asic}")
            if not packetlib.send_check_i2c_wrapper(cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, asic_num=_asic, fpga_addr = fpga_address, sub_addr=packetlib.subblock_address_dict["Reference_Voltage_1"], reg_addr=0x00, data=_ref_voltage_half1, retry=i2c_retry, verbose=verbose_reference_voltage):
                logger.warning(f"Failed to set Reference_Voltage_Half_1 settings for ASIC {_asic}")

        adc_mean_list, adc_err_list = caliblib.measure_adc(cmd_outbound_conn, data_data_conn, h2gcroc_ip, h2gcroc_port, total_asic, fpga_address, expected_event_number, fragment_life, logger, i2c_retry)
        corase_scan_ref_values.append(_ref_inv)
        corase_scan_noinv_values.append(_ref_noinv)

        for _chn in range(76 * total_asic):
            channel_scan_adcs[_chn].append(adc_mean_list[_chn])

    #  -- Calculate average pedestal values, dead channels and max pedestal values ------
    global_scan_half_chn_sums = [[0 for _ in range(len(corase_scan_ref_values))] for _ in range(2*total_asic)]
    global_scan_half_chn_nums = [[0 for _ in range(len(corase_scan_ref_values))] for _ in range(2*total_asic)]
    global_scan_half_chn_diff_square_sums = [[0 for _ in range(len(corase_scan_ref_values))] for _ in range(2*total_asic)]
    channel_pedestal_stds = [0 for _ in range(76 * total_asic)]
    for _chn in range(76 * total_asic):
        if _chn in channel_not_used:
            continue
        if _chn in dead_channel_list:
            continue
        _chn_half_index = _chn // 38
        _chn_pedestal_std = np.std(channel_scan_adcs[_chn])
        channel_pedestal_stds[_chn] = _chn_pedestal_std
        if _chn_pedestal_std < dead_channel_std_threshold:
            dead_channel_list.append(_chn)
            logger.warning(f"Channel {_chn} is dead, std: {round(_chn_pedestal_std, 2)}")
        else:
            for _scan in range(len(corase_scan_ref_values)):
                global_scan_half_chn_sums[_chn_half_index][_scan] += channel_scan_adcs[_chn][_scan]
                global_scan_half_chn_nums[_chn_half_index][_scan] += 1

    for _half in range(2*total_asic):
        for _scan in range(len(corase_scan_ref_values)):
            if global_scan_half_chn_nums[_half][_scan] > 0:
                average_pedestals[_half].append(global_scan_half_chn_sums[_half][_scan] / global_scan_half_chn_nums[_half][_scan])
            else:
                average_pedestals[_half].append(target_pedestal)

    for _half in range(2*total_asic):
        global_scan_half_chn_nums[_half] = [0 for _ in range(len(corase_scan_ref_values))]

    maximum_chn_pedestal_index_list = []
    minimum_chn_pedestal_index_list = []

    # find the maximum pedestal channel index for each scan
    for _scan in range(len(corase_scan_ref_values)):
        maximum_chn_pedestal_index = 0
        minimum_chn_pedestal_index = 0
        for _chn in range(76 * total_asic):
            if _chn in channel_not_used:
                continue
            if _chn in dead_channel_list:
                continue
            if channel_scan_adcs[_chn][_scan] > channel_scan_adcs[maximum_chn_pedestal_index][_scan]:
                maximum_chn_pedestal_index = _chn
            if channel_scan_adcs[_chn][_scan] < channel_scan_adcs[minimum_chn_pedestal_index][_scan]:
                minimum_chn_pedestal_index = _chn
        maximum_chn_pedestal_index_list.append(maximum_chn_pedestal_index)
        minimum_chn_pedestal_index_list.append(minimum_chn_pedestal_index)

    for _chn in range(76 * total_asic):
        if _chn in channel_not_used:
            continue
        if _chn in dead_channel_list:
            continue
        _chn_half_index = _chn // 38
        for _scan in range(len(corase_scan_ref_values)):
            # exclude the max and min pedestal values
            if _chn == maximum_chn_pedestal_index_list[_scan] or _chn == minimum_chn_pedestal_index_list[_scan]:
                continue
            global_scan_half_chn_diff_square_sums[_chn_half_index][_scan] += (channel_scan_adcs[_chn][_scan] - average_pedestals[_chn_half_index][_scan]) ** 2
            global_scan_half_chn_nums[_chn_half_index][_scan] += 1

    for _half in range(2*total_asic):
        for _scan in range(len(corase_scan_ref_values)):
            if global_scan_half_chn_nums[_half][_scan] > 0:
                average_pedestals_err[_half].append(np.sqrt(global_scan_half_chn_diff_square_sums[_half][_scan] / (global_scan_half_chn_nums[_half][_scan] - 1)) / np.sqrt(global_scan_half_chn_nums[_half][_scan]))
            else:
                average_pedestals_err[_half].append(0)

    del global_scan_half_chn_sums
    del global_scan_half_chn_nums
    del global_scan_half_chn_diff_square_sums

    dist_global_scan_peak_found = [False for _ in range(2*total_asic)]
    dist_minimal_ref_values     = [0 for _ in range(2*total_asic)]
    dist_global_scan_target     = [1024 for _ in range(2*total_asic)]

    for _half in range(2*total_asic):
        average_pedestals[_half] = [round(x, 2) for x in average_pedestals[_half]]
        logger.info(f"Average pedestals for half {_half}: {average_pedestals[_half]}")
        if max(average_pedestals[_half]) < target_pedestal:
            logger.warning(f"Pedestal values are too low for half {_half}")
        for _ref_index in range(len(corase_scan_ref_values)):
            if not dist_global_scan_peak_found[_half] and _ref_index < len(corase_scan_ref_values) - 1:
                if average_pedestals[_half][_ref_index] > average_pedestals[_half][_ref_index + 1] + 1:
                    dist_global_scan_peak_found[_half] = True
            if abs(average_pedestals[_half][_ref_index] - target_pedestal) < dist_global_scan_target[_half] and dist_global_scan_peak_found[_half]:
                dist_global_scan_target[_half] = abs(average_pedestals[_half][_ref_index] - target_pedestal)
                dist_minimal_ref_values[_half] = corase_scan_ref_values[_ref_index]

    # draw the pedestal vs. ref_inv
    fig, ax = plt.subplots(1, 1, figsize=(12, 9))
    for _half in range(2*total_asic):
        ax.errorbar(corase_scan_ref_values, average_pedestals[_half], yerr=average_pedestals_err[_half], label=f"Half {_half}", marker='o', markersize=2, color=caliblib.color_list[_half])
        ax.axvline(x=dist_minimal_ref_values[_half], color=caliblib.color_list[_half], linestyle='--', label=f"Target {_half}")
    ax.set_xlabel('Reference Voltage Value')
    ax.set_ylabel('Pedestal Value [ADC]')
    ax.set_ylim(-50, 1024)
    ax.annotate('Pedestal vs. Reference Inv', xy=(0.02, 0.95), xycoords='axes fraction', fontsize=17, color='#062B35FF', fontweight='bold')
    ax.legend(loc='upper right')
    pdf_file.savefig(fig)
    plt.close(fig)

    global_ref_inv_values   = []
    global_ref_noinv_values = []
    for _half in range(2*total_asic):
        global_ref_inv_values.append(dist_minimal_ref_values[_half])
        global_ref_noinv_values.append(noinv_vref_default)
    for _half in range(2*total_asic):
        if global_ref_inv_values[_half] < 0:
            global_ref_inv_values[_half] = 0
        if global_ref_inv_values[_half] > 1023:
            global_ref_inv_values[_half] = 1023
        logger.info(f"Global reference inv value for half {_half}: {global_ref_inv_values[_half]}")


    # -- Set up global analog -----------------------------------
    # -----------------------------------------------------------
    for _asic in range(total_asic):
        final_ref_inv_values.append(global_ref_inv_values[_asic*2])
        final_ref_noinv_values.append(global_ref_noinv_values[_asic*2])

        final_ref_inv_values.append(global_ref_inv_values[_asic*2+1])
        final_ref_noinv_values.append(global_ref_noinv_values[_asic*2+1])

        _ref_voltage_half0 = default_reference_voltage_0.copy()
        _ref_voltage_half1 = default_reference_voltage_1.copy()

        _ref_voltage_half0[1] = ( _ref_voltage_half0[1] & 0xF0) | ((global_ref_inv_values[_asic*2] & 0x03) << 2) | (global_ref_noinv_values[_asic*2] & 0x03)
        _ref_voltage_half1[1] = ( _ref_voltage_half1[1] & 0xF0) | ((global_ref_inv_values[_asic*2+1] & 0x03) << 2) | (global_ref_noinv_values[_asic*2+1] & 0x03)

        _ref_voltage_half0[4] = global_ref_inv_values[_asic*2] >> 2
        _ref_voltage_half1[4] = global_ref_inv_values[_asic*2 + 1] >> 2
        _ref_voltage_half0[5] = global_ref_noinv_values[_asic*2] >> 2
        _ref_voltage_half1[5] = global_ref_noinv_values[_asic*2 + 1] >> 2

        

        if not packetlib.send_check_i2c_wrapper(cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, asic_num=_asic, fpga_addr = fpga_address, sub_addr=packetlib.subblock_address_dict["Reference_Voltage_0"], reg_addr=0x00, data=_ref_voltage_half0, retry=i2c_retry, verbose=verbose_reference_voltage):
            logger.warning(f"Failed to set Reference_Voltage_Half_0 settings for ASIC {_asic}")
        if not packetlib.send_check_i2c_wrapper(cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, asic_num=_asic, fpga_addr = fpga_address, sub_addr=packetlib.subblock_address_dict["Reference_Voltage_1"], reg_addr=0x00, data=_ref_voltage_half1, retry=i2c_retry, verbose=verbose_reference_voltage):
            logger.warning(f"Failed to set Reference_Voltage_Half_1 settings for ASIC {_asic}")

        time.sleep(0.1)

    adc_mean_list, adc_err_list = caliblib.measure_adc(cmd_outbound_conn, data_data_conn, h2gcroc_ip, h2gcroc_port, total_asic, fpga_address, expected_event_number, fragment_life, logger, i2c_retry)

    fig, ax = caliblib.plot_channel_adc(
        adc_mean_list,
        adc_err_list,
        'Fine reference inv scan results',
        dead_channels=dead_channel_list
    )
    normalized_xmin = (0 - ax.get_xlim()[0]) / (ax.get_xlim()[1] - ax.get_xlim()[0])
    normalized_xmax = (152 - ax.get_xlim()[0]) / (ax.get_xlim()[1] - ax.get_xlim()[0])
    ax.axhline(
        y=target_pedestal,
        xmin=normalized_xmin,
        xmax=normalized_xmax,
        color=caliblib.color_list[_half],
        linestyle='--',
        label=f"Target Pedestal: {target_pedestal}"
    )
    ax.legend()

    pdf_file.savefig(fig)
    plt.close(fig)

    # * --- Step 4: Fine channel wise trimming ------------------------------------------
    # * ---------------------------------------------------------------------------------
    fine_chn_trimming_attempt_number = 16

    for _attempt in tqdm(range(fine_chn_trimming_attempt_number), desc="Fine Channel Wise Trimming"):
        _changed_chn_cnt = 0
        _underflow_chn_list = []
        _overflow_chn_list = []
        for _chn in range(76 * total_asic):
            if _chn not in channel_not_used and _chn not in dead_channel_list:
                _half_index = _chn // 38
                if adc_mean_list[_chn] < target_pedestal - pede_tolerance:
                    pede_trim_values[_chn] += pede_trim_step_size // 2
                    if pede_trim_values[_chn] > 63:
                        _overflow_chn_list.append(_chn)
                        pede_trim_values[_chn] = 63
                    _chn_wise = default_channel_wise.copy()
                    _chn_wise[0] = input_dac_values[_chn] & 0x3F
                    _chn_wise[3] = (pede_trim_values[_chn] << 2) & 0xFC

                    if not packetlib.send_check_i2c_wrapper(cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, asic_num=_chn // 76, fpga_addr = fpga_address, sub_addr=packetlib.uni_chn_to_subblock_list[_chn%76], reg_addr=0x00, data=_chn_wise, retry=i2c_retry, verbose=verbose_channel_wise):
                        logger.warning(f"Failed to set Channel_{_chn} settings for ASIC {_chn // 76}")

                    _changed_chn_cnt += 1
                elif adc_mean_list[_chn] > target_pedestal + pede_tolerance:
                    pede_trim_values[_chn] -= pede_trim_step_size // 2
                    if pede_trim_values[_chn] < 0:
                        _underflow_chn_list.append(_chn)
                        pede_trim_values[_chn] = 0
                    _chn_wise = default_channel_wise.copy()
                    _chn_wise[0] = input_dac_values[_chn] & 0x3F
                    _chn_wise[3] = (pede_trim_values[_chn] << 2) & 0xFC

                    if not packetlib.send_check_i2c_wrapper(cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, asic_num=_chn // 76, fpga_addr = fpga_address, sub_addr=packetlib.uni_chn_to_subblock_list[_chn%76], reg_addr=0x00, data=_chn_wise, retry=i2c_retry, verbose=verbose_channel_wise):
                        logger.warning(f"Failed to set Channel_{_chn} settings for ASIC {_chn // 76}")
        if len(_underflow_chn_list) > 0:
            logger.info(f"Underflow channels: {_underflow_chn_list}")
        if len(_overflow_chn_list) > 0:
            logger.info(f"Overflow channels: {_overflow_chn_list}")

        logger.info(f"Attempt {_attempt + 1}: {pede_trim_values}")

        if _changed_chn_cnt == 0:
            logger.info(f"No channel changed in attempt {_attempt + 1}, stop trimming")
            break

        adc_mean_list, adc_err_list = caliblib.measure_adc(cmd_outbound_conn, data_data_conn, h2gcroc_ip, h2gcroc_port, total_asic, fpga_address, expected_event_number, fragment_life, logger, i2c_retry)

    fig, ax = caliblib.plot_channel_adc(
        adc_mean_list,
        adc_err_list,
        f'Fine channel wise trimming attempt {_attempt + 1}',
        dead_channels=dead_channel_list
    )
    normalized_xmin = (0 - ax.get_xlim()[0]) / (ax.get_xlim()[1] - ax.get_xlim()[0])
    normalized_xmax = (152 - ax.get_xlim()[0]) / (ax.get_xlim()[1] - ax.get_xlim()[0])
    ax.axhline(
        y=target_pedestal,
        xmin=normalized_xmin,
        xmax=normalized_xmax,
        color=caliblib.color_list[_half],
        linestyle='--',
        label=f"Target Pedestal: {target_pedestal}"
    )
    ax.legend()
    pdf_file.savefig(fig)
    plt.close(fig)

    for _asic in range(total_asic):
        # -- Turn off DAQ --------------------------------------------
        # -----------------------------------------------------------
        if not packetlib.send_check_i2c_wrapper(cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, asic_num=_asic, fpga_addr = fpga_address, sub_addr=packetlib.subblock_address_dict["Top"], reg_addr=0x00, data=top_reg_offLR, retry=i2c_retry, verbose=False):
            logger.warning(f"Failed to turn off LR for ASIC {_asic}")
        else:
            logger.info(f"Turned off LR for ASIC {_asic}")
        # -----------------------------------------------------------
    
finally:
    pool_do("unregister", "data", pc_data_port)
    pool_do("unregister", "cmd", pc_cmd_port)
    data_cmd_conn.close()
    data_data_conn.close()
    cmd_outbound_conn.close()
    ctrl_conn.close()

# * --- Save results to pdf plots -------------------------------------------------------
# * -------------------------------------------------------------------------------------
pdf_file.close()

# * --- Save the results ----------------------------------------------------------------
# * -------------------------------------------------------------------------------------
output_config_json["common_settings_pede"]    = common_settings_json_path
output_config_json["input_i2c_settings_pede"] = input_i2c_json_names

# -- Save the results to a json file --------------------------------
# -------------------------------------------------------------------
output_pedecalib_json["inv_vref_list"]          = final_ref_inv_values
output_pedecalib_json["noinv_vref_list"]        = final_ref_noinv_values
output_pedecalib_json["chn_trim_settings"]      = pede_trim_values
output_pedecalib_json["chn_inputdac_settings"]  = input_dac_values
output_pedecalib_json["dead_channels"]          = dead_channel_list
output_pedecalib_json["channel_not_used"]       = channel_not_used
output_pedecalib_json["pede_values"]            = list(adc_mean_list)
output_pedecalib_json["pede_errors"]            = list(adc_err_list)
output_pedecalib_json["phase_setting"]          = phase_setting

output_pedecalib_json_path = os.path.join(output_dump_folder, output_pedecalib_json_name)
with open(output_pedecalib_json_path, 'w') as f:
    json.dump(output_pedecalib_json, f, indent=4)

# -- Save the register settings -------------------------------------
# -------------------------------------------------------------------
for _chn in range(total_asic * 76):
     if _chn not in channel_not_used and _chn not in dead_channel_list:
        _asic_num = _chn // 76
        _chn_num  = _chn % 76
        _sub_addr = packetlib.uni_chn_to_subblock_list[_chn_num]

        _chn_wise = default_channel_wise.copy()
        _chn_wise[0] = input_dac_values[_chn] & 0x3F
        _chn_wise[3] = (pede_trim_values[_chn] << 2) & 0xFC

        chn_key = caliblib.UniChannelNum2RegKey(i2c_dict, _sub_addr)
        # print(f"Channel register key: {chn_key} for chn {_chn} in asic {_asic_num} with sub addr {_sub_addr}")
        config_output_jsons[_asic_num]["Register Settings"][chn_key] = ' '.join([f"{x:02X}" for x in _chn_wise])


for _asic in range(total_asic):
    _ref_voltage_half0 = default_reference_voltage_0.copy()
    _ref_voltage_half1 = default_reference_voltage_1.copy()

    _ref_voltage_half0[1] = ( _ref_voltage_half0[1] & 0xF0) | ((final_ref_inv_values[_asic*2] & 0x03) << 2) | (final_ref_noinv_values[_asic*2] & 0x03)
    _ref_voltage_half1[1] = ( _ref_voltage_half1[1] & 0xF0) | ((final_ref_inv_values[_asic*2+1] & 0x03) << 2) | (final_ref_noinv_values[_asic*2+1] & 0x03)

    _ref_voltage_half0[4] = final_ref_inv_values[_asic*2] >> 2
    _ref_voltage_half1[4] = final_ref_inv_values[_asic*2 + 1] >> 2

    _ref_voltage_half0[5] = final_ref_noinv_values[_asic*2] >> 2
    _ref_voltage_half1[5] = final_ref_noinv_values[_asic*2 + 1] >> 2

    config_output_jsons[_asic]["Register Settings"]["Reference_Voltage_0 "] = ' '.join([f"{x:02X}" for x in _ref_voltage_half0])
    config_output_jsons[_asic]["Register Settings"]["Reference_Voltage_1 "] = ' '.join([f"{x:02X}" for x in _ref_voltage_half1])

for _asic in range(total_asic):
    config_output_jsons[_asic]["PedestalCalib"]["DeadChannels"] = dead_channel_list
    config_output_jsons[_asic]["PedestalCalib"]["ChannelNotUsed"] = channel_not_used
    config_output_jsons[_asic]["UDP Settings"]["IP Address"] = h2gcroc_ip
    config_output_jsons[_asic]["UDP Settings"]["Port"] = str(h2gcroc_port)

config_saving_time = time.strftime("%Y%m%d_%H%M%S", time.localtime())
config_files = []

for _asic in range(total_asic):
    config_name = f'config_pede_a{_asic}_' + config_saving_time + '.json'
    config_output_json_path = os.path.join(output_dump_folder, config_name)
    with open(config_output_json_path, 'w') as f:
        json.dump(config_output_jsons[_asic], f, indent=4)
    config_files.append(config_output_json_path)

output_info = {
    "output_folder": output_dump_folder,
    "config_files": config_files
}

print("OUTPUT_INFO_103: " + json.dumps(output_info))
