import packetlibX
import caliblibX
import uuid, os, json
from loguru import logger

h2gcroc_ip   = "10.1.2.208"
pc_ip        = "10.1.2.207"
pc_cmd_port  = 11000
pc_data_port = 11001
h2gcroc_port = 11000
fpga_address = 0x00
timeout = 2.0
i2c_retry = 3

cfg_path = os.path.join(os.path.dirname(__file__), 'config/socket_pool_config.json')
with open(cfg_path, 'r') as f:
    cfg = json.load(f)

CONTROL_HOST = cfg['CONTROL_HOST']
CONTROL_PORT = cfg['CONTROL_PORT']
DATA_HOST    = cfg['DATA_HOST']
DATA_PORT    = cfg['DATA_PORT']
BUFFER_SIZE  = cfg['BUFFER_SIZE']

default_i2c_path = os.path.join(os.path.dirname(__file__), 'config/default_2024Aug_config.json')
default_i2c_config = json.load(open(default_i2c_path, 'r'))
default_i2c_registers = {}
for _key in default_i2c_config["Register Settings"].keys():
    _raw_key = _key.replace(' ', '')
    _reg_values_str = default_i2c_config["Register Settings"][_key]
    _reg_values_list = [int(x, 16) for x in _reg_values_str.split()]
    default_i2c_registers[_raw_key] = _reg_values_list

_global_analog_0 = default_i2c_registers["Global_Analog_0"]

worker_id    = str(uuid.uuid4())

try:
    ctrl_conn, data_cmd_conn, data_data_conn, cmd_outbound_conn, pool_do = caliblibX.init_worker_sockets(
        worker_id, h2gcroc_ip, pc_ip,
        CONTROL_HOST, CONTROL_PORT, DATA_HOST, DATA_PORT,
        pc_cmd_port, pc_data_port,
        timeout, logger
    )
except Exception as e:
    print(f"Failed to initialize worker sockets: {e}")
    print("Please check the socket pool server and try again.")
    exit()

pool_do("register",   "data", pc_data_port)
pool_do("register",   "cmd",  pc_cmd_port)

for _asic in range(2):
    if not packetlibX.send_check_i2c_wrapper(cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, asic_num=_asic, fpga_addr = fpga_address, sub_addr=packetlibX.subblock_address_dict["Global_Analog_0"], reg_addr=0x00, data=_global_analog_0, retry=i2c_retry, verbose=True):
        print(f"Failed to set Global_Analog_0 settings for ASIC {_asic}")