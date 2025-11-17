import packetlibX
import time, os, sys, socket, json, csv, uuid
import numpy as np
import pandas as pd
from matplotlib import pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from collections import deque
from collections import OrderedDict
import packetlib

color_list = ['#FF0000', '#0000FF', '#FFFF00', '#00FF00','#FF00FF', '#00FFFF', '#FFA500', '#800080', '#008080', '#FFC0CB']

def print_err(msg):
    print(f"[clx_calib] ERROR: {msg}", file=sys.stderr)
def print_info(msg):
    print(f"[clx_calib] INFO: {msg}", file=sys.stdout)
def print_warn(msg):
    print(f"[clx_calib] WARNING: {msg}", file=sys.stdout)

class udp_target:
    def __init__(self, pc_ip, pc_port_cmd, pc_port_data, board_ip, board_port):
        self.pc_ip         = pc_ip
        self.pc_port_cmd   = pc_port_cmd
        self.pc_port_data  = pc_port_data
        self.board_ip    = board_ip
        self.board_port  = board_port
        # extract board_id from ip by minus 208 from last octet
        self.board_id      = int(board_ip.split('.')[-1]) - 208

        self.pool_conn_setup = False

    def load_udp_json(self, json_dict):
        try:
            assert "pc_ip"         in json_dict
            assert "pc_cmd_port"   in json_dict
            assert "pc_data_port"  in json_dict
            assert "h2gcroc_ip"    in json_dict
            assert "h2gcroc_port"  in json_dict
        except AssertionError:
            print_err("JSON dictionary missing required UDP keys")
            return
        self.pc_ip         = json_dict["pc_ip"]
        self.pc_port_cmd   = json_dict["pc_cmd_port"]
        self.pc_port_data  = json_dict["pc_data_port"]
        self.board_ip    = json_dict["h2gcroc_ip"]
        self.board_port  = json_dict["h2gcroc_port"]
        self.board_id      = int(self.board_ip.split('.')[-1]) - 208

    def load_udp_json_file(self, json_path):
        try:
            with open(json_path, 'r') as f:
                json_dict = json.load(f)
                self.load_udp_json(json_dict.get('udp', {}))
        except Exception as e:
            print_err(f"Failed to load UDP settings from JSON file: {e}")

    def load_pool_json(self, json_dict):
        try:
            assert "control_host"  in json_dict
            assert "control_port"  in json_dict
            assert "data_host"     in json_dict
            assert "data_port"     in json_dict
            assert "buffer_size"   in json_dict
        except AssertionError:
            print_err("JSON dictionary missing required pool keys")
            return
        self.control_host = json_dict["control_host"]
        self.control_port = json_dict["control_port"]
        self.data_host    = json_dict["data_host"]
        self.data_port    = json_dict["data_port"]
        self.buffer_size  = json_dict["buffer_size"]

    def load_pool_json_file(self, json_path):
        try:
            with open(json_path, 'r') as f:
                json_dict = json.load(f)
                self.load_pool_json(json_dict.get('pool', {}))
        except Exception as e:
            print_err(f"Failed to load pool settings from JSON file: {e}")

    def connect_to_pool(self, timeout=2.0):
        self.worker_id = str(uuid.uuid4())
        try:
            self.ctrl_conn, self.data_cmd_conn, self.data_data_conn, self.cmd_outbound_conn, self.pool_do = init_worker_sockets(self.worker_id, self.board_ip, self.pc_ip, self.control_host, self.control_port, self.data_host, self.data_port, self.pc_port_cmd, self.pc_port_data, timeout)
        except Exception as e:
            print_err(f"Failed to connect to pool: {e}")

        self.pool_do("register", "cmd",  self.pc_port_cmd)
        self.pool_do("register", "data", self.pc_port_data)

        self.pool_conn_setup = True

    # make sure the connection is closed when the object is deleted
    def __del__(self):
        if self.pool_conn_setup:
            self.pool_do("unregister", "cmd",  self.pc_port_cmd)
            self.pool_do("unregister", "data", self.pc_port_data)
            try:
                self.ctrl_conn.close()
                self.data_cmd_conn.close()
                self.data_data_conn.close()
                self.cmd_outbound_conn.close()
            except Exception as e:
                print_err(f"Failed to close pool connections: {e}")

def UniChannelNum2RegKey(i2c_dict, channel_num):
    for _key in i2c_dict.keys():
        if "CM_" in _key or "Channel_" in _key or "CALIB_" in _key:
            _reverse_key = i2c_dict[_key]
            _key_full = _key
            if "Channel_" in _key_full:
                _key_index = int(_key_full.split("_")[-1])
                _key_full = f"Channel_{_key_index}"
            while len(_key_full) < 20:
                _key_full += " "
            # print (f"{_reverse_key} : {_key_full}")
            if _reverse_key == channel_num:
                return _key_full
    return "Not Found"

def TurnOnPoints(_val_list, _used_values, _threshold):
    _turn_on_points = [-1 for _ in range(len(_val_list[0]))]
    for _step in range(len(_val_list)):
        for _chn in range(len(_val_list[_step])):
            if _val_list[_step][_chn] > _threshold and _turn_on_points[_chn] == -1:
                if _step > 0:
                    if _step == len(_val_list) - 1:
                        _turn_on_points[_chn] = ( _used_values[_step] + _used_values[_step-1]) / 2
                    elif _val_list[_step+1][_chn] > _threshold:
                        _turn_on_points[_chn] = ( _used_values[_step] + _used_values[_step-1]) / 2
                else:
                    _turn_on_points[_chn] = _used_values[_step]
    # set still not turned on channels to the last value
    for _chn in range(len(_turn_on_points)):
        if _turn_on_points[_chn] == -1:
            _turn_on_points[_chn] = max(_used_values)
    return _turn_on_points

def find_true_sublists(bool_list, step_size):
    if bool_list is None:
        return []
    results = []
    start_index = None
    in_sequence = False
    print(f"Finding true sublists in: {bool_list} with step size {step_size}")

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

def send_reset_adj_calib(udp_target, asic_num, sw_hard_reset_sel=0x00, sw_hard_reset=0x00, sw_soft_reset_sel=0x00, sw_soft_reset=0x00, sw_i2c_reset_sel=0x00, sw_i2c_reset=0x00, reset_pack_counter=0x00, adjustable_start=0x00, verbose=False):
    return packetlibX.send_reset_adj(udp_target.cmd_outbound_conn, udp_target.board_ip, udp_target.board_port, asic_num=asic_num, fpga_addr=udp_target.board_id, sw_hard_reset_sel=sw_hard_reset_sel, sw_hard_reset=sw_hard_reset, sw_soft_reset_sel=sw_soft_reset_sel, sw_soft_reset=sw_soft_reset, sw_i2c_reset_sel=sw_i2c_reset_sel, sw_i2c_reset=sw_i2c_reset, reset_pack_counter=reset_pack_counter, adjustable_start=adjustable_start, verbose=verbose)

# packetlib.send_check_DAQ_gen_params(
#                               cmd_outbound_conn, data_cmd_conn, h2gcroc_ip, h2gcroc_port, fpga_addr=fpga_address,
#                               data_coll_en=0x00, trig_coll_en=0x00, 
#                               daq_fcmd=gen_fcmd_L1A, gen_pre_fcmd=0x00, gen_fcmd=gen_fcmd_L1A, 
#                               ext_trg_en=0x00, ext_trg_delay=0x00, ext_trg_deadtime=10000, 
#                               jumbo_en=0x00, 
#                               gen_preimp_en=0x00, gen_pre_interval=0x0010, gen_nr_of_cycle=gen_nr_cycle, 
#                               gen_interval=gen_interval_value, 
#                               daq_push_fcmd=gen_fcmd_L1A, machine_gun=machine_gun, 
#                               ext_trg_out_0_len=0x00, ext_trg_out_1_len=0x00, ext_trg_out_2_len=0x00, ext_trg_out_3_len=0x00, 
#                               asic0_collection=a0, asic1_collection=a1, asic2_collection=a2, asic3_collection=a3, 
#                               asic4_collection=a4, asic5_collection=a5, asic6_collection=a6, asic7_collection=a7, 
#                               verbose=True, readback=True):

def send_check_DAQ_gen_params_calib(udp_target, data_coll_en, trig_coll_en, daq_fcmd, gen_pre_fcmd, gen_fcmd, ext_trg_en, ext_trg_delay, ext_trg_deadtime, jumbo_en, gen_preimp_en, gen_pre_interval, gen_nr_of_cycle, gen_interval, daq_push_fcmd, machine_gun, 
ext_trg_out_0_len, ext_trg_out_1_len, ext_trg_out_2_len, ext_trg_out_3_len,
asic0_collection, asic1_collection, asic2_collection, asic3_collection, asic4_collection, asic5_collection, asic6_collection, asic7_collection, verbose=False, readback=True):
    return packetlibX.send_check_DAQ_gen_params(
        udp_target.cmd_outbound_conn, udp_target.data_cmd_conn, udp_target.board_ip, udp_target.board_port, fpga_addr=udp_target.board_id,
        data_coll_en=data_coll_en, trig_coll_en=trig_coll_en, 
        daq_fcmd=daq_fcmd, gen_pre_fcmd=gen_pre_fcmd, gen_fcmd=gen_fcmd, 
        ext_trg_en=ext_trg_en, ext_trg_delay=ext_trg_delay, ext_trg_deadtime=ext_trg_deadtime, 
        jumbo_en=jumbo_en, 
        gen_preimp_en=gen_preimp_en, gen_pre_interval=gen_pre_interval, gen_nr_of_cycle=gen_nr_of_cycle, 
        gen_interval=gen_interval, 
        daq_push_fcmd=daq_push_fcmd, machine_gun=machine_gun, 
        ext_trg_out_0_len=ext_trg_out_0_len, ext_trg_out_1_len=ext_trg_out_1_len, ext_trg_out_2_len=ext_trg_out_2_len, ext_trg_out_3_len=ext_trg_out_3_len,
        asic0_collection=asic0_collection, asic1_collection=asic1_collection, asic2_collection=asic2_collection, asic3_collection=asic3_collection, 
        asic4_collection=asic4_collection, asic5_collection=asic5_collection, asic6_collection=asic6_collection, asic7_collection=asic7_collection, 
        verbose=verbose, readback=readback)

def send_register_calib(udp_target, asic_index, reg_key, reg_value, retry=3, verbose=False):
    # If reg_value is a hex-string like "0A 1B 2C"
    if isinstance(reg_value, str):
        register_data = [int(x, 16) for x in reg_value.split()]
    # If reg_value is a list/bytes/etc.
    elif isinstance(reg_value, (list, tuple, bytes, bytearray)):
        register_data = list(reg_value)
    register_addr = packetlibX.get_register_address_by_key(reg_key)
    if register_addr is None:
        print_err(f"Invalid register key: {reg_key}")
        return False
    # print all parameters
    if verbose:
        print_info(f"Sending register calib: ASIC {asic_index}, Register Key: {reg_key}, Register Addr: 0x{register_addr:02X}, Data: {register_data}, Retry: {retry}")
    return packetlibX.send_check_i2c_wrapper(udp_target.cmd_outbound_conn, udp_target.data_cmd_conn, udp_target.board_ip, udp_target.board_port, asic_num=asic_index, fpga_addr=udp_target.board_id, sub_addr=register_addr, reg_addr=0x00, data=register_data, retry=retry, verbose=verbose)

def HalfTurnOnAverage(_turn_on_points, _unused_chn_list, _dead_chn_list, _asic_num):
    _half_on_points = [-1 for _ in range(38*_asic_num)]
    if len(_turn_on_points) != 76*_asic_num:
        print_err("Turn on points list does not match the number of channels")
        return
    for _half in range(2*_asic_num):
        _chn_list = []
        for _chn in range(38*_half, 38*(_half+1)):
            if _chn in _unused_chn_list or _chn in _dead_chn_list:
                continue
            _chn_list.append(_turn_on_points[_chn])
        _half_on_points[_half] = np.mean(_chn_list)
        # logger.debug(f"Half{_half}: {round(_half_on_points[_half], 2)}")
    return np.array(_half_on_points, dtype=float)

def setup_output(script_id_str, args_output=None, dump_root='dump'):
    """
    Sets up the output folders, config JSON stub, and PDF file for results.

    Args:
        script_id_str (str): Identifier derived from the script filename.
        args_output (str or None): User-specified base output folder.
        dump_root (str): Default root folder for dumps (temporary files).

    Returns:
        dict: {
            'dump_folder': path to created dump folder,
            'config_path': path to output config JSON,
            'config_json': empty dict for later population,
            'pedecalib_name': filename for pedestal calibration JSON,
            'pdf_path': full path to PDF,
            'pdf_file': PdfPages object
        }
    """
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_folder_name         = f'{script_id_str}_data_{timestamp}'
    output_config_json_name    = f'{script_id_str}_config_{timestamp}.json'
    output_pedecalib_json_name = f'{script_id_str}_pedecalib_{timestamp}.json'
    
    # Determine base folder
    base_folder = args_output if args_output and os.path.exists(args_output) else dump_root
    if args_output and not os.path.exists(args_output):
        # fallback warning could be logged by caller
        base_folder = dump_root
    
    dump_folder = os.path.join(base_folder, output_folder_name)
    os.makedirs(dump_folder, exist_ok=True)
    
    config_path = os.path.join(base_folder, output_config_json_name)
    pdf_path    = os.path.join(dump_folder, f'{script_id_str}_results_{timestamp}.pdf')
    pdf_file    = PdfPages(pdf_path)
    
    # Prepare stub config dict for later population
    config_json = {}
    
    return {
        'dump_folder': dump_folder,
        'config_path': config_path,
        'config_json': config_json,
        'pedecalib_name': output_pedecalib_json_name,
        'pdf_path': pdf_path,
        'pdf_file': pdf_file,
        'output_folder': output_folder_name,
        'output_config_json': output_config_json_name,
    }


def plot_channel_adc(adc_mean_list, adc_err_list, info_str, dead_channels=[]):
    fig, ax = plt.subplots(1, 1, figsize=(12, 9))

    # 1) draw four background bands
    regions = [
        (0,   38),
        (39,  76),
        (77,  114),
        (115, 152)
    ]
    colors = ['#DB9F9FFF', '#82C1DEFF', '#E7EBAEFF', '#B6E3AEFF']  # light grey, pale blue, pale red, pale green
    for (start, end), col in zip(regions, colors):
        ax.axvspan(start, end, facecolor=col, alpha=0.3, edgecolor='none')

    # 2) your existing errorbar + dead‐channel markers
    ax.errorbar(
        range(len(adc_mean_list)),
        adc_mean_list,
        yerr=adc_err_list,
        fmt='o',
        color='black',
        label='ADC mean value',
        markersize=2
    )
    for ch in dead_channels:
        ax.vlines(ch, -50, 1024, color='red', linestyle='--', label=f'Dead channel {ch}')

    ax.set_xlabel('Channel number')
    ax.set_ylabel('ADC mean value')
    ax.set_ylim(-50, 1024)
    ax.annotate(
        info_str,
        xy=(0.02, 0.95),
        xycoords='axes fraction',
        fontsize=17,
        color='#062B35FF',
        fontweight='bold'
    )
    return fig, ax

def init_worker_sockets(
    worker_id: str,
    h2gcroc_ip: str,
    pc_ip: str,
    CONTROL_HOST: str,
    CONTROL_PORT: int,
    DATA_HOST: str,
    DATA_PORT: int,
    pc_cmd_port: int,
    pc_data_port: int,
    timeout: float,
    logger = None
):
    """
    Initialize all worker sockets and registration function.

    Returns:
        ctrl_conn, data_cmd_conn, data_data_conn, cmd_outbound_conn, pool_do
    """
    # Create sockets
    ctrl_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    data_cmd_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    data_data_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    cmd_outbound_conn = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # Connect / bind
    ctrl_conn.connect((CONTROL_HOST, CONTROL_PORT))
    data_cmd_conn.connect((DATA_HOST, DATA_PORT))
    data_data_conn.connect((DATA_HOST, DATA_PORT))
    cmd_outbound_conn.bind((pc_ip, 0))

    # Set timeouts
    for s in (ctrl_conn, data_cmd_conn, data_data_conn, cmd_outbound_conn):
        s.settimeout(timeout)

    # Fetch assigned local ports
    ctrl_port    = ctrl_conn.getsockname()[1]
    cmd_data_port= data_cmd_conn.getsockname()[1]
    data_data_port = data_data_conn.getsockname()[1]

    # Log assignment
    print_info(
        f"Worker ID: {worker_id}, Control Port: {ctrl_port}")
    print_info(
        f"DataCMD Port: {cmd_data_port}, DataDATA Port: {data_data_port}"
    )

    # Send hello frames
    hello_data = {"action": "hello", "worker_id": worker_id, "direction": "data"}
    hello_cmd  = {"action": "hello", "worker_id": worker_id, "direction": "cmd"}

    data_cmd_conn.send(json.dumps(hello_cmd).encode())
    data_data_conn.send(json.dumps(hello_data).encode())

    # Define pool_do
    def pool_do(action: str, typ: str, do_port: int):
        msg = {
            "action":    action,
            "worker_id": worker_id,
            "type":      typ,
            "src_ip":    h2gcroc_ip,
            "port":      do_port
        }
        ctrl_conn.send(json.dumps(msg).encode())
        resp = json.loads(ctrl_conn.recv(1024).decode())
        # logger.debug(f"{action} {typ}@{h2gcroc_ip}:{do_port} → {resp}")
        return resp

    return ctrl_conn, data_cmd_conn, data_data_conn, cmd_outbound_conn, pool_do


class h2gcroc_registers_full:
    def __init__(self):
        self.udp_settings       = OrderedDict()
        self.target_asic        = OrderedDict()
        self.register_settings  = OrderedDict()
        self._register_key_width = 20

    def send_register_from_key(self, udp_target, reg_key, retry=3, verbose=False):
        if reg_key not in self.register_settings:
            print_err(f"Register key {reg_key} not found in settings")
            return False
        register_data = self.register_settings[reg_key].copy()
        # if is top, get 0:8
        if "Top" in reg_key:
            register_data = register_data[0:8]
        return send_register_calib(udp_target, self.target_asic.get("ASIC Index", 0), reg_key, register_data, retry=retry, verbose=verbose)

    def send_top_register(self, udp_target, retry=3, verbose=False):
        return self.send_register_from_key(udp_target, "Top", retry=retry, verbose=verbose)
    
    def send_global_analog_0_register(self, udp_target, retry=3, verbose=False):
        return self.send_register_from_key(udp_target, "Global_Analog_0", retry=retry, verbose=verbose)
    
    def send_global_analog_1_register(self, udp_target, retry=3, verbose=False):
        return self.send_register_from_key(udp_target, "Global_Analog_1", retry=retry, verbose=verbose)
    
    def send_reference_voltage_0_register(self, udp_target, retry=3, verbose=False):
        return self.send_register_from_key(udp_target, "Reference_Voltage_0", retry=retry, verbose=verbose)
    
    def send_reference_voltage_1_register(self, udp_target, retry=3, verbose=False):
        return self.send_register_from_key(udp_target, "Reference_Voltage_1", retry=retry, verbose=verbose)
    
    def send_master_tdc_0_register(self, udp_target, retry=3, verbose=False):
        return self.send_register_from_key(udp_target, "Master_TDC_0", retry=retry, verbose=verbose)
    
    def send_master_tdc_1_register(self, udp_target, retry=3, verbose=False):
        return self.send_register_from_key(udp_target, "Master_TDC_1", retry=retry, verbose=verbose)
    
    def send_digital_half_0_register(self, udp_target, retry=3, verbose=False):
        return self.send_register_from_key(udp_target, "Digital_Half_0", retry=retry, verbose=verbose)
    
    def send_digital_half_1_register(self, udp_target, retry=3, verbose=False):
        return self.send_register_from_key(udp_target, "Digital_Half_1", retry=retry, verbose=verbose)
    
    def send_halfwise_0_register(self, udp_target, retry=3, verbose=False):
        return self.send_register_from_key(udp_target, "HalfWise_0", retry=retry, verbose=verbose)
    
    def send_halfwise_1_register(self, udp_target, retry=3, verbose=False):
        return self.send_register_from_key(udp_target, "HalfWise_1", retry=retry, verbose=verbose)
    
    def send_channel_register(self, udp_target, channel_index, retry=3, verbose=False):
        if channel_index < 0 or channel_index > 71:
            print_err("Channel index must be between 0 and 75")
            return False
        reg_key = "Channel_" + str(channel_index)
        return self.send_register_from_key(udp_target, reg_key, retry=retry, verbose=verbose)
    
    def send_cm_register(self, udp_target, cm_index, retry=3, verbose=False):
        if cm_index < 0 or cm_index > 3:
            print_err("CM index must be between 0 and 3")
            return False
        reg_key = "CM_" + str(cm_index)
        return self.send_register_from_key(udp_target, reg_key, retry=retry, verbose=verbose)
    
    def send_calib_register(self, udp_target, calib_index, retry=3, verbose=False):
        if calib_index < 0 or calib_index > 1:
            print_err("Calib index must be between 0 and 1")
            return False
        reg_key = "CALIB_" + str(calib_index)
        return self.send_register_from_key(udp_target, reg_key, retry=retry, verbose=verbose)

    def send_all_registers(self, udp_target, retry=3, verbose=False):
        for reg_key in self.register_settings.keys():
            if "HalfWise_" in reg_key:
                continue
            if not self.send_register_from_key(udp_target, reg_key, retry=retry, verbose=verbose):
                print_err(f"[clx_calib] Failed to send register {reg_key}")
        return True

    def sync_udp_settings(self, udp_target, asic_index=0):
        self.udp_settings["IP Address"]  = udp_target.board_ip
        self.udp_settings["Port"]        = udp_target.board_port
        self.target_asic["FPGA Address"] = udp_target.board_id
        self.target_asic["ASIC Index"]   = asic_index

    def is_same_udp_settings(self, udp_target, asic_index=0):
        return (self.udp_settings.get("IP Address") == udp_target.board_ip and
                self.udp_settings.get("Port")       == udp_target.board_port and
                self.target_asic.get("FPGA Address") == udp_target.board_id and
                self.target_asic.get("ASIC Index")   == asic_index)
    
    def set_phase(self, phase_value):
        if phase_value < 0 or phase_value > 15:
            print_err("Phase value must be between 0 and 255")
            return False
        try:
            top_reg = self.register_settings["Top"]
            top_reg[7] = phase_value & 0x0F
        except KeyError:
            print_err("Top register not found in settings")
            return False
        
    def set_inputdac_all(self, input_dac_value):
        if input_dac_value < 0 or input_dac_value > 63:
            print_err("Input DAC value must be between 0 and 63")
            return False
        for ch_index in range(72):
            reg_key = f"Channel_{ch_index}"
            try:
                ch_reg = self.register_settings[reg_key]
                ch_reg[0] = (ch_reg[0] & 0xc0) | (input_dac_value & 0x3F)
            except KeyError:
                print_err(f"Channel register {reg_key} not found in settings")
                return False
        return True
            
    def set_chn_trim_inv(self, channel_index, trim_value):
        if channel_index < 0 or channel_index > 71:
            print_err("Channel index must be between 0 and 71")
            return False
        if trim_value < 0 or trim_value > 63:
            print_err("Trim value must be between 0 and 63")
            return False
        reg_key = f"Channel_{channel_index}"
        try:
            ch_reg = self.register_settings[reg_key]
            ch_reg[1] = (ch_reg[1] & 0x03) | ((trim_value & 0x3F) << 2)
        except KeyError:
            print_err(f"Channel register {reg_key} not found in settings")
            return False
        return True
        
    def set_trim_inv_all(self, trim_value):
        if trim_value < 0 or trim_value > 63:
            print_err("Trim value must be between 0 and 63")
            return False
        for ch_index in range(72):
            reg_key = f"Channel_{ch_index}"
            try:
                ch_reg = self.register_settings[reg_key]
                ch_reg[1] = (ch_reg[1] & 0x03) | ((trim_value & 0x3F) << 2)
            except KeyError:
                print_err(f"Channel register {reg_key} not found in settings")
                return False
        return True
    
    def set_inv_vref(self, vref_value, half_index):
        if vref_value < 0 or vref_value > 1023:
            print_err("VREF value must be between 0 and 1023")
            return False
        if half_index not in [0, 1]:
            print_err("Half index must be 0 or 1")
            return False
        reg_key = f"Reference_Voltage_{half_index}"
        try:
            vref_reg = self.register_settings[reg_key]
            # bit 2-3 of reg#1
            vref_reg[1] = (vref_reg[0] & 0xF3) | (( vref_value & 0x03) << 2)
            # bit 0-7 of reg#4
            vref_reg[4] = (vref_reg[4] & 0x00) | ((vref_value & 0xFF) << 0)
        except KeyError:
            print_err(f"Reference Voltage register {reg_key} not found in settings")
            return False
        return True
    
    def set_noinv_vref(self, vref_value, half_index):
        if vref_value < 0 or vref_value > 1023:
            print_err("VREF value must be between 0 and 1023")
            return False
        if half_index not in [0, 1]:
            print_err("Half index must be 0 or 1")
            return False
        reg_key = f"Reference_Voltage_{half_index}"
        try:
            vref_reg = self.register_settings[reg_key]
            # bit 0-1 of reg#1
            vref_reg[1] = (vref_reg[0] & 0xFC) | (( vref_value & 0x03) << 0)
            # bit 0-7 of reg#5
            vref_reg[5] = (vref_reg[5] & 0x00) | ((vref_value & 0xFF) << 0)
        except KeyError:
            print_err(f"Reference Voltage register {reg_key} not found in settings")
            return False
        return True
        
    def turn_on_daq(self, enable=True):
        try:
            top_reg = self.register_settings["Top"]
            if enable:
                top_reg[0] = top_reg[0] | 0x03
            else:
                top_reg[0] = top_reg[0] & (~0x03)
        except KeyError:
            print_err("Top register not found in settings")
            return False
        return True
        
    def turn_off_daq(self, disable=True):
        return self.turn_on_daq(not disable)

    def load_from_json(self, json_file):
        try:
            with open(json_file, 'r') as f:
                json_dict = json.load(f, object_pairs_hook=OrderedDict)
        except Exception as e:
            print_err(f"Failed to load h2gcroc registers from JSON file: {e}")
            return False

        try:
            assert "UDP Settings"      in json_dict
            assert "Target ASIC"       in json_dict
            assert "Register Settings" in json_dict
        except AssertionError:
            print_err("JSON dictionary missing required h2gcroc register keys")
            return False

        self.udp_settings = json_dict["UDP Settings"]
        self.target_asic  = json_dict["Target ASIC"]

        raw_regs = json_dict["Register Settings"]

        if raw_regs:
            self._register_key_width = max(len(k) for k in raw_regs.keys())
        else:
            self._register_key_width = 0

        self.register_settings = OrderedDict()

        for raw_key, value in raw_regs.items():
            logical_key = raw_key.rstrip()   # "Channel_0           " -> "Channel_0"

            if isinstance(value, str):
                try:
                    if value.strip() == "":
                        ba = bytearray()
                    else:
                        ba = bytearray(int(tok, 16) for tok in value.split())
                except ValueError as e:
                    print_err(f"Invalid hex string for register {logical_key}: {e}")
                    continue
            elif isinstance(value, list):
                # 也支持 [0, 0, 0, 128, ...] 这样的列表
                try:
                    ba = bytearray(int(v) & 0xFF for v in value)
                except Exception as e:
                    print_err(f"Invalid list for register {logical_key}: {e}")
                    continue
            elif isinstance(value, (bytes, bytearray)):
                ba = bytearray(value)
            else:
                print_err(f"Unsupported register value type for {logical_key}: {type(value)}")
                continue

            self.register_settings[logical_key] = ba

        return True

    def save_to_json(self, json_file):
        # 计算写回时 key 的宽度
        if self.register_settings:
            max_logical = max(len(k) for k in self.register_settings.keys())
            width = max(self._register_key_width, max_logical)
        else:
            width = self._register_key_width or 0

        reg_out = OrderedDict()
        for logical_key, value in self.register_settings.items():
            padded_key = logical_key.ljust(width)

            # ---- 在这里把 bytearray 转回 "xx xx xx" 字符串 ----
            if isinstance(value, (bytes, bytearray)):
                hex_str = " ".join(f"{b:02x}" for b in value)  # 小写十六进制
            elif isinstance(value, list):
                hex_str = " ".join(f"{int(b) & 0xFF:02x}" for b in value)
            elif isinstance(value, str):
                # 已经是字符串就直接写，但不推荐
                hex_str = value
            else:
                print_err(f"Unsupported value type when saving {logical_key}: {type(value)}")
                continue

            reg_out[padded_key] = hex_str

        json_dict = OrderedDict({
            "UDP Settings":      self.udp_settings,
            "Target ASIC":       self.target_asic,
            "Register Settings": reg_out
        })

        try:
            with open(json_file, 'w') as f:
                json.dump(json_dict, f, indent=4)
            return True
        except Exception as e:
            print_err(f"Failed to save h2gcroc registers to JSON file: {e}")
            return False

# def measure_adc(_cmd_socket, _data_socket, _h2gcroc_ip, _h2gcroc_port, _total_asic_num, _fpga_addr, _total_event, _fragment_life, _logger, _retry=1, _verbose=False):
#     _retry_left = _retry
#     _all_events_received = False

#     n_channels = _total_asic_num * 76
#     n_halves   = _total_asic_num * 2

#     adc_mean_list = np.zeros(n_channels)
#     adc_err_list  = np.zeros(n_channels)

#     while _retry_left > 0 and not _all_events_received:
#         if _retry_left < _retry:
#             if _verbose:
#                 _logger.info(f"Retrying measurement, attempts left: {_retry_left}")
#             time.sleep(0.1)
#         _retry_left -= 1
        
#         try:
#             extracted_payloads_pool = deque()
#             event_fragment_pool     = []
#             fragment_life_dict      = {}

#             current_half_packet_num = 0
#             current_event_num       = 0
#             counter_daqh_incorrect  = 0

#             all_chn_value_0_array = np.zeros((_total_event, n_channels))
#             all_chn_value_1_array = np.zeros((_total_event, n_channels))
#             all_chn_value_2_array = np.zeros((_total_event, n_channels))
#             hamming_code_array    = np.zeros((_total_event, 3*n_halves))
#             daqh_good_array       = np.zeros((_total_event,   n_halves))

#             for i in range(_total_event):
#                 for j in range(n_halves):
#                     daqh_good_array[i][j] = True

#             if not packetlib.send_daq_gen_start_stop(_cmd_socket, _h2gcroc_ip, _h2gcroc_port, fpga_addr = _fpga_addr, daq_push=0x00, gen_start_stop=0, daq_start_stop=0xFF, verbose=False):
#                 _logger.warning("Failed to start the generator")
#             if not packetlib.send_daq_gen_start_stop(_cmd_socket, _h2gcroc_ip, _h2gcroc_port, fpga_addr = _fpga_addr, daq_push=0x00, gen_start_stop=1, daq_start_stop=0xFF, verbose=False):
#                 _logger.warning("Failed to start the generator")

#             if True:
#                 # ! Receive data
#                 try:
#                     try:
#                         for _ in range(100):
#                             if _verbose:
#                                 _logger.debug("--------------------------------------------------------------")
#                             # receive_start_time = time.perf_counter()
#                             data_packet, _ = _data_socket.recvfrom(8192)
#                             # _logger.debug(f'data length: {len(data_packet)}')
#                             # receive_end_time = time.perf_counter()
#                             # receive_time_us = (receive_end_time - receive_start_time) * 1e6
#                             # _logger.debug(f"-- Data received in {receive_time_us:.2f} us")

#                             # * Find the lines with fixed line pattern
#                             # payload_extraction_start_time = time.perf_counter()
#                             extracted_payloads_pool.extend(packetlib.extract_raw_payloads(data_packet))
#                             # payload_extraction_end_time = time.perf_counter()
#                             # payload_extraction_time_us = (payload_extraction_end_time - payload_extraction_start_time) * 1e6
#                             # _logger.debug(f"---- Payload extraction took {payload_extraction_time_us:.2f} us")
#                             # _logger.debug(f"---- Payloads in pool: {len(extracted_payloads_pool)}")
#                     except socket.timeout:
#                         if _verbose:
#                             _logger.warning("Socket timeout, no data received")

#                         if not packetlib.send_daq_gen_start_stop(_cmd_socket, _h2gcroc_ip, _h2gcroc_port, fpga_addr = _fpga_addr, daq_push=0x00, gen_start_stop=0, daq_start_stop=0x00, verbose=False):
#                             _logger.warning("Failed to stop the generator")

#                     # * Find 5-line packs (half asic data)
#                     # fragment_formatting_start_time = time.perf_counter()
#                     if len(extracted_payloads_pool) >= 5:
#                         candidate_packet_lines = [extracted_payloads_pool.popleft() for _ in range(5)]
#                         while len(extracted_payloads_pool) >= 1:
#                             is_packet_good, event_fragment = packetlib.check_event_fragment(candidate_packet_lines)
#                             if is_packet_good:
#                                 event_fragment_pool.append(event_fragment)
#                                 current_half_packet_num += 1
#                                 if len(extracted_payloads_pool) >= 5:
#                                     candidate_packet_lines = [extracted_payloads_pool.popleft() for _ in range(5)]
#                                 else:
#                                     break
#                             else:
#                                 # _logger.warning("Warning: Event fragment is not good")
#                                 # pop out the oldest line
#                                 candidate_packet_lines.pop(0)
#                                 candidate_packet_lines.append(extracted_payloads_pool.popleft())
#                     # fragment_formatting_end_time = time.perf_counter()
#                     # fragment_formatting_time_us = (fragment_formatting_end_time - fragment_formatting_start_time) * 1e6
#                     # _logger.debug(f"---- Fragment formatting took {fragment_formatting_time_us:.2f} us")
#                     # _logger.debug(f"---- Fragments in pool: {len(event_fragment_pool)}")

#                     # display the first 8 bytes for each fragment
#                     # for i in range(len(event_fragment_pool)):
#                     #     # print in hex
#                     #     _logger.debug(f"------ Fragment {i}: " + ' '.join([f"{x:02x}" for x in event_fragment_pool[i][0][:12]]))
#                     indices_to_delete = set()
#                     if len(event_fragment_pool) >= n_halves:
#                         event_fragment_pool = sorted(event_fragment_pool, key=lambda x: x[0][4:7])

#                     # halves_search_start_time = time.perf_counter()
#                     counter_fragment = 0
#                     while counter_fragment <= len(event_fragment_pool) - n_halves:
#                         # _logger.debug(f"---- Searching for halves, current fragment: {counter_fragment}")
#                         timestamps = []
#                         for counter_half in range(n_halves):
#                             timestamps.append(event_fragment_pool[counter_fragment+counter_half][0][4] << 24 | event_fragment_pool[counter_fragment+counter_half][0][5] << 16 | event_fragment_pool[counter_fragment+counter_half][0][6] << 8 | event_fragment_pool[counter_fragment+counter_half][0][7])
#                         # print timestamp in hex
#                         # _logger.debug(f"---- Fragment {counter_fragment} timestamps: " + ' '.join([f"{x:08x}" for x in timestamps]))
#                         if len(set(timestamps)) == 1:
#                             for _half in range(n_halves):
#                                 extracted_data = packetlib.assemble_data_from_40bytes(event_fragment_pool[counter_fragment+_half], verbose=False)
#                                 extracted_values = packetlib.extract_values(extracted_data["_extraced_160_bytes"], verbose=False)
#                                 uni_chn_base = (extracted_data["_header"] - 0xA0) * 76 + (extracted_data["_packet_type"] - 0x24) * 38
#                                 for j in range(len(extracted_values["_extracted_values"])):
#                                     all_chn_value_0_array[current_event_num][j+uni_chn_base] = extracted_values["_extracted_values"][j][1]
#                                     all_chn_value_1_array[current_event_num][j+uni_chn_base] = extracted_values["_extracted_values"][j][2]
#                                     all_chn_value_2_array[current_event_num][j+uni_chn_base] = extracted_values["_extracted_values"][j][3]
#                                 hamming_code_array[current_event_num][_half*3+0] =  packetlib.DaqH_get_H1(extracted_values["_DaqH"])
#                                 hamming_code_array[current_event_num][_half*3+1] =  packetlib.DaqH_get_H2(extracted_values["_DaqH"])
#                                 hamming_code_array[current_event_num][_half*3+2] =  packetlib.DaqH_get_H3(extracted_values["_DaqH"])
#                                 # _logger.debug(f'DaqhH: ' + ' '.join([f"{x:02x}" for x in extracted_values["_DaqH"]]))
#                                 # print daqh in hex
#                                 # _logger.debug(f"---- Fragment {counter_fragment} daqh: " + ' '.join([f"{x:02x}" for x in extracted_values["_DaqH"]]))
#                                 daqh_good_array[current_event_num][_half] = packetlib.DaqH_start_end_good(extracted_values["_DaqH"])
#                             update_indices = []
#                             for j in range(n_halves):
#                                 update_indices.append(counter_fragment+j)
#                             indices_to_delete.update(update_indices)
#                             if _verbose:
#                                 if not np.all(hamming_code_array[current_event_num] == 0):
#                                     _logger.warning("Hamming code error detected!")
#                                 if not np.all(daqh_good_array[current_event_num] == True):
#                                     _logger.warning("DAQH start/end error detected!")
#                             current_event_num += 1
#                             counter_fragment += 1
#                             # _logger.debug(f'counter_event_num:{current_event_num}')
#                             # _logger.debug(f"-- Found a full event fragment, current event num: {current_event_num}")
#                         else:
#                             if timestamps[0] in fragment_life_dict:
#                                 if fragment_life_dict[timestamps[0]] >= _fragment_life - 1:
#                                     indices_to_delete.update([counter_fragment])
#                                     del fragment_life_dict[timestamps[0]]
#                                 else:
#                                     fragment_life_dict[timestamps[0]] += 1
#                             else:
#                                 fragment_life_dict[timestamps[0]] = 1
#                             counter_fragment += 1

                        
#                     # halves_search_end_time = time.perf_counter()
#                     # halves_search_time_us = (halves_search_end_time - halves_search_start_time) * 1e6
#                     # _logger.debug(f"---- Halves search took {halves_search_time_us:.2f} us")

#                     for index in sorted(indices_to_delete, reverse=True):
#                         del event_fragment_pool[index]
#                     if current_event_num >= _total_event - 2:
#                         if _verbose:
#                             _logger.debug(f"Received enough events: {current_event_num} events (target: {_total_event} events)")
#                         _all_events_received = True
#                         break;   
#                 except Exception as e:
#                     if _verbose:
#                         _logger.warning("Exception in receiving data")
#                         _logger.warning(e)
#                         _logger.warning('Halves received: ' + str(current_half_packet_num))
#                         _logger.warning('Halves expected: ' + str(_total_event * 2 * _total_asic_num))
#                         _logger.warning('left fragments:' + str(len(event_fragment_pool)))
#                         _logger.warning("current event num:" + str(current_event_num))
#                     _all_events_received = False
#                     break

#             for _event in range(current_event_num):
#                 if not np.all(daqh_good_array[_event] == True):
#                     counter_daqh_incorrect += 1

#             if (current_event_num - counter_daqh_incorrect) < min(_total_event//2, 1):
#                 if _verbose:
#                     _logger.warning(f"Not enough valid events received: {current_event_num - counter_daqh_incorrect} (expected: {_total_event}, received: {current_event_num})")
#                 _all_events_received = False
#                 continue

#             # avergae_calculation_start_time = time.perf_counter()
#             for _chn in range(n_channels):
#                 _candidate_values = []
#                 for _event in range(current_event_num):
#                     if np.all(hamming_code_array[_event] == 0) and np.all(daqh_good_array[_event] == True):
#                         # if all_chn_value_0_array[_event][_chn] != 0:
#                         _candidate_values.append(all_chn_value_0_array[_event][_chn])
#                 if len(_candidate_values) > 0:
#                     adc_mean_list[_chn] = np.mean(_candidate_values)
#                     adc_err_list[_chn]  = np.std(_candidate_values) / np.sqrt(len(_candidate_values))
#                 else:
#                     adc_mean_list[_chn] = 0
#                     adc_err_list[_chn]  = 0
#             # avergae_calculation_end_time = time.perf_counter()
#             # avergae_calculation_time_us = (avergae_calculation_end_time - avergae_calculation_start_time) * 1e6
#             # _logger.debug(f"---- Average calculation took {avergae_calculation_time_us:.2f} us")

#         finally:
#             if not packetlib.send_daq_gen_start_stop(_cmd_socket, _h2gcroc_ip, _h2gcroc_port, fpga_addr = _fpga_addr, daq_push=0x00, gen_start_stop=0, daq_start_stop=0x00, verbose=False):
#                 _logger.warning("Failed to stop the generator")
       
#         if _verbose:
#             _logger.info(f"daqh bad events: {counter_daqh_incorrect} (expected: {_total_event}, received: {current_event_num})")

#     if _verbose:
#         _logger.warning(f"Not enough events received: {current_event_num} (daqh bad: {counter_daqh_incorrect}, expected: {_total_event})")
#     return adc_mean_list, adc_err_list

# def measure_all(_cmd_socket, _data_socket, _h2gcroc_ip, _h2gcroc_port, _total_asic_num, _fpga_addr, _machine_gun, _total_event, _fragment_life, _logger, _retry=1, _verbose=False, _focus_half=[]):
#     _retry_left = _retry
#     _all_events_received = False

#     n_channels = _total_asic_num * 76
#     n_halves   = _total_asic_num * 2

#     adc_mean_list = np.zeros((_machine_gun+1, n_channels))
#     adc_err_list  = np.zeros((_machine_gun+1, n_channels))
#     tot_mean_list = np.zeros((_machine_gun+1, n_channels))
#     tot_err_list  = np.zeros((_machine_gun+1, n_channels))
#     toa_mean_list = np.zeros((_machine_gun+1, n_channels))
#     toa_err_list  = np.zeros((_machine_gun+1, n_channels))
    
#     while _retry_left > 0 and not _all_events_received:
#         if _retry_left < _retry:
#             if _verbose:
#                 _logger.info(f"Retrying measurement, attempts left: {_retry_left}")
#             time.sleep(0.1)
#         _retry_left -= 1

#         try:
#             extracted_payloads_pool = deque()
#             event_fragment_pool     = []
#             fragment_life_dict      = {}

#             timestamps_events = []

#             current_half_packet_num = 0
#             current_event_num       = 0
#             counter_daqh_incorrect  = 0

#             # Preallocate arrays for _event_num events.
#             # We will later process only the rows for which we received data.
#             all_chn_value_0_array = np.zeros((_total_event, n_channels))
#             all_chn_value_1_array = np.zeros((_total_event, n_channels))
#             all_chn_value_2_array = np.zeros((_total_event, n_channels))
#             hamming_code_array    = np.zeros((_total_event, 3*n_halves))
#             daqh_good_array       = np.zeros((_total_event,   n_halves))

#             for i in range(_total_event):
#                 for j in range(n_halves):
#                     daqh_good_array[i][j] = True

#             if not packetlibX.send_daq_gen_start_stop(_cmd_socket, _h2gcroc_ip, _h2gcroc_port, fpga_addr = _fpga_addr, daq_push=0x00, gen_start_stop=0, daq_start_stop=0xFF, verbose=False):
#                 print_warn("Failed to start the generator")
#             if not packetlibX.send_daq_gen_start_stop(_cmd_socket, _h2gcroc_ip, _h2gcroc_port, fpga_addr = _fpga_addr, daq_push=0x00, gen_start_stop=1, daq_start_stop=0xFF, verbose=False):
#                 print_warn("Failed to start the generator")

#             # packetlib.clean_socket(_socket_udp_data)

#             # if not packetlib.send_daq_gen_start_stop(
#             #         _socket_udp_cmd, _ip, _port,
#             #         fpga_addr=_fpga_address,
#             #         daq_push=0x00, gen_start_stop=1, daq_start_stop=0xFF,
#             #         verbose=False):
#             #     _logger.warning("Failed to start the generator")

#             # Main loop: try to receive data until we have enough events.
#             # while current_event_num < _total_event - 4:
#             if True:
#                 try:
#                     bytes_counter = 0
#                     try:
#                         for _ in range(100):
#                             data_packet, _ = _data_socket.recvfrom(8192)

#                             # * Find the lines with fixed line pattern
#                             extracted_payloads_pool.extend(packetlibX.extract_raw_payloads(data_packet))
#                             bytes_counter += len(data_packet)

#                     except socket.timeout:
#                         if _verbose:
#                             print_warn("Socket timeout, no data received")

#                         if not packetlibX.send_daq_gen_start_stop(_cmd_socket, _h2gcroc_ip, _h2gcroc_port, fpga_addr = _fpga_addr, daq_push=0x00, gen_start_stop=0, daq_start_stop=0x00, verbose=False):
#                             print_warn("Failed to stop the generator")

#                         for _ in range(5):
#                             try:

#                                 data_packet, _ = _data_socket.recvfrom(8192)

#                                 # * Find the lines with fixed line pattern
#                                 extracted_payloads_pool.extend(packetlibX.extract_raw_payloads(data_packet))
#                                 bytes_counter += len(data_packet)
#                                 if len(data_packet) > 0:
#                                     break

#                             except socket.timeout:
#                                 if _verbose:
#                                     print_warn("Socket timeout, no data received")


#                     # data_packet, _ = _data_socket.recvfrom(8192)
#                     # extracted_payloads_pool.extend(packetlib.extract_raw_payloads(data_packet))

#                     # logger.debug(f"Received {bytes_counter} bytes of data")
#                     half_packet_number = float(bytes_counter) / (5 * 40)
#                     event_number = half_packet_number / 2 / _total_asic_num
#                     half_packet_number = int(half_packet_number)
#                     event_number = int(event_number)

#                     logger.debug(f"Received {half_packet_number} half packets, {event_number} events")
#                     logger.debug(f"Received {len(extracted_payloads_pool)} payloads")

#                     if len(extracted_payloads_pool) >= 5:
#                         candidate_packet_lines = [extracted_payloads_pool.popleft() for _ in range(5)]
#                         while len(extracted_payloads_pool) > 0:
#                             is_packet_good, event_fragment = packetlib.check_event_fragment(candidate_packet_lines)
#                             if is_packet_good:
#                                 event_fragment_pool.append(event_fragment)
#                                 current_half_packet_num += 1
#                                 if len(extracted_payloads_pool) >= 5:
#                                     candidate_packet_lines = [extracted_payloads_pool.popleft() for _ in range(5)]
#                                 else:
#                                     break
#                             else:
#                                 _logger.warning("Warning: Event fragment is not good")
#                                 # pop out the oldest line
#                                 candidate_packet_lines.pop(0)
#                                 candidate_packet_lines.append(extracted_payloads_pool.popleft())

#                     logger.debug(f"Current half packet number: {current_half_packet_num}")

#                     indices_to_delete = set()
#                     if len(event_fragment_pool) >= n_halves:
#                         event_fragment_pool = sorted(event_fragment_pool, key=lambda x: x[0][4:7])

#                     counter_fragment = 0
#                     while counter_fragment <= len(event_fragment_pool) - n_halves:
#                         timestamps = []
#                         for counter_half in range(n_halves):
#                             timestamps.append(event_fragment_pool[counter_fragment+counter_half][0][4] << 24 | event_fragment_pool[counter_fragment+counter_half][0][5] << 16 | event_fragment_pool[counter_fragment+counter_half][0][6] << 8 | event_fragment_pool[counter_fragment+counter_half][0][7])
#                         if len(set(timestamps)) == 1:
#                             for _half in range(n_halves):
#                                 extracted_data = packetlib.assemble_data_from_40bytes(event_fragment_pool[counter_fragment+_half], verbose=False)
#                                 extracted_values = packetlib.extract_values(extracted_data["_extraced_160_bytes"], verbose=False)
#                                 uni_chn_base = (extracted_data["_header"] - 0xA0) * 76 + (extracted_data["_packet_type"] - 0x24) * 38
#                                 for j in range(len(extracted_values["_extracted_values"])):
#                                     all_chn_value_0_array[current_event_num][j+uni_chn_base] = extracted_values["_extracted_values"][j][1]
#                                     all_chn_value_1_array[current_event_num][j+uni_chn_base] = extracted_values["_extracted_values"][j][2]
#                                     all_chn_value_2_array[current_event_num][j+uni_chn_base] = extracted_values["_extracted_values"][j][3]
#                                 hamming_code_array[current_event_num][_half*3+0] =  packetlib.DaqH_get_H1(extracted_values["_DaqH"])
#                                 hamming_code_array[current_event_num][_half*3+1] =  packetlib.DaqH_get_H2(extracted_values["_DaqH"])
#                                 hamming_code_array[current_event_num][_half*3+2] =  packetlib.DaqH_get_H3(extracted_values["_DaqH"])
#                                 daqh_good_array[current_event_num][_half] = packetlib.DaqH_start_end_good(extracted_values["_DaqH"])
#                             update_indices = []
#                             for j in range(n_halves):
#                                 update_indices.append(counter_fragment+j)
#                             indices_to_delete.update(update_indices)
#                             if _verbose:
#                                 if not np.all(hamming_code_array[current_event_num] == 0):
#                                     _logger.warning("Hamming code error detected!")
#                                 if not np.all(daqh_good_array[current_event_num] == True):
#                                     _logger.warning("DAQH start/end error detected!")

#                             if len(_focus_half) == 0:
#                                 if np.all(hamming_code_array[current_event_num] == 0) and np.all(daqh_good_array[current_event_num] == True):
#                                     current_event_num += 1
#                                     timestamps_events.append(timestamps[0])
#                             else:
#                                 # only check the focus half daqh and hamming code
#                                 hamming_code_focus = []
#                                 daqh_good_focus  = []

#                                 for _half in range(n_halves):
#                                     if _half in _focus_half:
#                                         hamming_code_focus.append(int(hamming_code_array[current_event_num][_half*3+0]))
#                                         hamming_code_focus.append(int(hamming_code_array[current_event_num][_half*3+1]))
#                                         hamming_code_focus.append(int(hamming_code_array[current_event_num][_half*3+2]))
#                                         daqh_good_focus.append(bool(daqh_good_array[current_event_num][_half]))
#                                 hamming_code_focus = np.array(hamming_code_focus)
#                                 daqh_good_focus  = np.array(daqh_good_focus)
#                                 # _logger.debug(f"Focus half: {_half}, hamming code: {hamming_code_focus}, daqh good: {daqh_good_focus}")
#                                 # #     _logger.debug("if finished")
#                                 # # _logger.debug("for loop finished")
#                                 # # print the focus hamming code in hex
#                                 # _logger.debug(f"Focus hamming code: {hamming_code_focus} and is all zero: {np.all(hamming_code_focus == 0)}")
#                                 # # print the focus daqh in hex
#                                 # _logger.debug(f"Focus daqh: {daqh_good_focus} and is all True: {np.all(daqh_good_focus == True)}")
#                                 if np.all(hamming_code_focus == 0) and np.all(daqh_good_focus == True):
#                                     current_event_num += 1
#                                 #     _logger.debug(f"Event {current_event_num} is valid")
#                                 # else:
#                                 #     _logger.warning("Invalid event detected in focus half")


#                             counter_fragment += 1
#                             # _logger.debug(f"-- Found a full event fragment, current event num: {current_event_num}")
#                         else:
#                             if timestamps[0] in fragment_life_dict:
#                                 if fragment_life_dict[timestamps[0]] >= _fragment_life - 1:
#                                     indices_to_delete.update([counter_fragment])
#                                     del fragment_life_dict[timestamps[0]]
#                                 else:
#                                     fragment_life_dict[timestamps[0]] += 1
#                             else:
#                                 fragment_life_dict[timestamps[0]] = 1
#                             counter_fragment += 1
#                     for index in sorted(indices_to_delete, reverse=True):
#                         del event_fragment_pool[index]

#                     # Stop receiving if we have reached our target _event_num;
#                     # or if we have at least (_event_num - 4) events and an exception (e.g. timeout) occurs.
#                     if current_event_num >= _total_event - 4:
#                         if _verbose:
#                             _logger.debug(f"Received enough events: {current_event_num} events (target: {_total_event} events)")
#                         _all_events_received = True
#                         # break;   

#                 except Exception as e:
#                     if _verbose:
#                         _logger.warning("Exception in receiving data")
#                         _logger.warning(e)
#                         _logger.warning('Halves received: ' + str(current_half_packet_num))
#                         _logger.warning('Halves expected: ' + str(_total_event * 2 * _total_asic_num))
#                         _logger.warning('left fragments:' + str(len(event_fragment_pool)))
#                         _logger.warning("current event num:" + str(current_event_num))
#                     _all_events_received = False
#                     break
                
#             for _event in range(current_event_num):
#                 if not np.all(daqh_good_array[_event] == True):
#                     counter_daqh_incorrect += 1

#             if (current_event_num - counter_daqh_incorrect) < min(_total_event//2, 1):
#                 if _verbose:
#                     _logger.warning("Not enough valid events received")
#                 _all_events_received = False
#                 continue
            
#             # _logger.debug(f"Event number: {current_event_num}")
#             timestamps_pure = []
#             for _timestamp_index in range(len(timestamps_events)):
#                 timestamps_pure.append(timestamps_events[_timestamp_index] - timestamps_events[0])
#             # _logger.debug(f"Timestamps: {timestamps_pure}")
#             if timestamps_pure[-1] != 41*(_machine_gun-1):
#                 _logger.warning(f"Machine gun {timestamps_pure[-1]} is not enough")
#                 _all_events_received = False
#                 continue
           
#             for _chn in range(n_channels):
#                 _candidate_adc_values = [[] for _ in range(_machine_gun + 1)]
#                 _candidate_tot_values = [[] for _ in range(_machine_gun + 1)]
#                 _candidate_toa_values = [[] for _ in range(_machine_gun + 1)]
#                 # _current_machine_gun = 0

#                 for _event in range(current_event_num):
#                     # if np.all(hamming_code_array[_event] == 0):
#                     if len(_focus_half) == 0:
#                         if np.all(hamming_code_array[_event] == 0) and np.all(daqh_good_array[_event] == True):
#                             _current_machine_gun = (timestamps_events[_event] - timestamps_events[0]) // 41
#                             if _current_machine_gun > _machine_gun:
#                                 _logger.warning(f"Machine gun {_current_machine_gun} exceeds {_machine_gun}")
#                                 continue
#                             # if _chn == 6:
#                             #     _logger.debug(f"Event {_event}, machine gun {_current_machine_gun}, channel {_chn}: ADC: {all_chn_value_0_array[_event][_chn]}, TOT: {all_chn_value_1_array[_event][_chn]}, ToA: {all_chn_value_2_array[_event][_chn]}")
#                             _candidate_adc_values[_current_machine_gun].append(all_chn_value_0_array[_event][_chn])
#                             _candidate_tot_values[_current_machine_gun].append(all_chn_value_1_array[_event][_chn])
#                             _candidate_toa_values[_current_machine_gun].append(all_chn_value_2_array[_event][_chn])
#                         # _current_machine_gun = (_current_machine_gun + 1) % (_machine_gun + 1)
#                     else:
#                         # only check the focus half daqh and hamming code
#                         hamming_code_focus = []
#                         daqh_good_focus  = []
#                         for _half in range(n_halves):
#                             if _half in _focus_half:
#                                 hamming_code_focus.append(hamming_code_array[_event][_half*3+0])
#                                 hamming_code_focus.append(hamming_code_array[_event][_half*3+1])
#                                 hamming_code_focus.append(hamming_code_array[_event][_half*3+2])
#                                 daqh_good_focus.append(daqh_good_array[_event][_half])
#                         hamming_code_focus = np.array(hamming_code_focus)
#                         daqh_good_focus  = np.array(daqh_good_focus)
#                         if np.all(hamming_code_focus == 0) and np.all(daqh_good_focus == True):
#                             _current_machine_gun = (timestamps_events[_event] - timestamps_events[0]) // 41
#                             # if _chn == 6:
#                             #     _logger.debug(f"Event {_event}, machine gun {_current_machine_gun}, channel {_chn}: ADC: {all_chn_value_0_array[_event][_chn]}, TOT: {all_chn_value_1_array[_event][_chn]}, ToA: {all_chn_value_2_array[_event][_chn]}")
#                             _candidate_adc_values[_current_machine_gun].append(all_chn_value_0_array[_event][_chn])
#                             _candidate_tot_values[_current_machine_gun].append(all_chn_value_1_array[_event][_chn])
#                             _candidate_toa_values[_current_machine_gun].append(all_chn_value_2_array[_event][_chn])
#                 event_short = 0
#                 if len(_candidate_adc_values) > 0:
#                     for _machine_gun_value in range(_machine_gun + 1):
#                         if len(_candidate_adc_values[_machine_gun_value]) > 0:
#                             _mean_adc = np.mean(_candidate_adc_values[_machine_gun_value])
#                             _err_adc  = np.std(_candidate_adc_values[_machine_gun_value]) / np.sqrt(len(_candidate_adc_values[_machine_gun_value]))
#                         else:
#                             _mean_adc = 0
#                             _err_adc  = 0
#                         if len(_candidate_tot_values[_machine_gun_value]) > 0:
#                             _mean_tot = np.mean(_candidate_tot_values[_machine_gun_value])
#                             _err_tot  = np.std(_candidate_tot_values[_machine_gun_value]) / np.sqrt(len(_candidate_tot_values[_machine_gun_value]))
#                         else:
#                             _mean_tot = 0
#                             _err_tot  = 0
#                         if len(_candidate_toa_values[_machine_gun_value]) > 0:
#                             _mean_toa = np.mean(_candidate_toa_values[_machine_gun_value])
#                             _err_toa  = np.std(_candidate_toa_values[_machine_gun_value]) / np.sqrt(len(_candidate_toa_values[_machine_gun_value]))
#                         else:
#                             _mean_toa = 0
#                             _err_toa  = 0

#                         # remove nan values
#                         if np.isnan(_mean_adc):
#                             _mean_adc = 0
#                         if np.isnan(_mean_tot):
#                             _mean_tot = 0
#                         if np.isnan(_mean_toa):
#                             _mean_toa = 0
#                         if np.isnan(_err_adc):
#                             _err_adc = 0
#                         if np.isnan(_err_tot):
#                             _err_tot = 0
#                         if np.isnan(_err_toa):
#                             _err_toa = 0

#                         _machine_gun_offset = _machine_gun_value + event_short
#                         if _machine_gun_offset > _machine_gun:
#                             _machine_gun_offset -= (_machine_gun + 1)   
#                         adc_mean_list[_machine_gun_offset][_chn] = _mean_adc
#                         adc_err_list[_machine_gun_offset][_chn]  = _err_adc
#                         tot_mean_list[_machine_gun_offset][_chn] = _mean_tot
#                         tot_err_list[_machine_gun_offset][_chn]  = _err_tot
#                         toa_mean_list[_machine_gun_offset][_chn] = _mean_toa
#                         toa_err_list[_machine_gun_offset][_chn]  = _err_toa
#                         # _logger.debug(f"Machine gun {_machine_gun}, channel {_chn}: ADC mean: {adc_mean_list[_machine_gun][_chn]}, ADC error: {adc_err_list[_machine_gun][_chn]}, TOT mean: {tot_mean_list[_machine_gun][_chn]}, TOT error: {tot_err_list[_machine_gun][_chn]}, ToA mean: {toa_mean_list[_machine_gun][_chn]}, ToA error: {toa_err_list[_machine_gun][_chn]}")
#                 else:
#                     for _machine_gun_value in range(_machine_gun + 1):
#                         _machine_gun_offset = _machine_gun_value + event_short
#                         if _machine_gun_offset > _machine_gun:
#                             _machine_gun_offset -= (_machine_gun + 1)   
#                         adc_mean_list[_machine_gun_offset][_chn] = 0
#                         adc_err_list[_machine_gun_offset][_chn]  = 0
#                         tot_mean_list[_machine_gun_offset][_chn] = 0
#                         tot_err_list[_machine_gun_offset][_chn]  = 0
#                         toa_mean_list[_machine_gun_offset][_chn] = 0
#                         toa_err_list[_machine_gun_offset][_chn]  = 0

#         finally:
#             if not packetlib.send_daq_gen_start_stop(_cmd_socket, _h2gcroc_ip, _h2gcroc_port, fpga_addr = _fpga_addr, daq_push=0x00, gen_start_stop=0, daq_start_stop=0x00, verbose=False):
#                 _logger.warning("Failed to stop the generator")

#         if _verbose:
#             _logger.info(f"daqh bad events: {counter_daqh_incorrect} (expected: {_total_event}, received: {current_event_num})")

#     if not _all_events_received:
#         _logger.warning("Not enough valid events received")
#         _logger.warning("Returning list of zeros")


#     # if True:
#     #     _logger.debug(f'Total events received: {current_event_num} / {_total_event}')
#     #     _logger.debug(f'DaqH Bad events: {counter_daqh_incorrect}')

#     return adc_mean_list, adc_err_list, tot_mean_list, tot_err_list, toa_mean_list, toa_err_list
def measure_all(_cmd_socket, _data_socket, _h2gcroc_ip, _h2gcroc_port, _total_asic_num, _fpga_addr, _machine_gun, _total_event, _fragment_life, _logger, _retry=1, _verbose=False, _focus_half=[]):
    _retry_left = _retry
    _all_events_received = False

    n_channels = _total_asic_num * 76
    n_halves   = _total_asic_num * 2

    adc_mean_list = np.zeros((_machine_gun+1, n_channels))
    adc_err_list  = np.zeros((_machine_gun+1, n_channels))
    tot_mean_list = np.zeros((_machine_gun+1, n_channels))
    tot_err_list  = np.zeros((_machine_gun+1, n_channels))
    toa_mean_list = np.zeros((_machine_gun+1, n_channels))
    toa_err_list  = np.zeros((_machine_gun+1, n_channels))
    
    while _retry_left > 0 and not _all_events_received:
        if _retry_left < _retry:
            if _verbose:
                _logger.info(f"Retrying measurement, attempts left: {_retry_left}")
            time.sleep(0.1)
        _retry_left -= 1

        try:
            extracted_payloads_pool = deque()
            event_fragment_pool     = []

            timestamps_events = []

            current_half_packet_num = 0
            current_event_num       = 0
            counter_daqh_incorrect  = 0

            # Preallocate arrays for _event_num events.
            # We will later process only the rows for which we received data.
            all_chn_value_0_array = np.zeros((_total_event, n_channels))
            all_chn_value_1_array = np.zeros((_total_event, n_channels))
            all_chn_value_2_array = np.zeros((_total_event, n_channels))
            hamming_code_array    = np.zeros((_total_event, 3*n_halves))
            daqh_good_array       = np.zeros((_total_event,   n_halves))

            for i in range(_total_event):
                for j in range(n_halves):
                    daqh_good_array[i][j] = True

            if not packetlibX.send_daq_gen_start_stop(_cmd_socket, _h2gcroc_ip, _h2gcroc_port, fpga_addr = _fpga_addr, daq_push=0x00, gen_start_stop=0, daq_start_stop=0xFF, verbose=False):
                _logger.warning("Failed to start the generator")
            if not packetlibX.send_daq_gen_start_stop(_cmd_socket, _h2gcroc_ip, _h2gcroc_port, fpga_addr = _fpga_addr, daq_push=0x00, gen_start_stop=1, daq_start_stop=0xFF, verbose=False):
                _logger.warning("Failed to start the generator")

            if True:
                try:
                    bytes_counter = 0
                    try:
                        for _ in range(100):
                            data_packet, _ = _data_socket.recvfrom(1358)

                            # * Find the lines with fixed line pattern
                            extracted_payloads_pool.extend(packetlibX.extract_raw_data(data_packet))
                            bytes_counter += len(data_packet)

                    except socket.timeout:
                        if _verbose:
                            _logger.warning("Socket timeout, no data received")

                        if not packetlibX.send_daq_gen_start_stop(_cmd_socket, _h2gcroc_ip, _h2gcroc_port, fpga_addr = _fpga_addr, daq_push=0x00, gen_start_stop=0, daq_start_stop=0x00, verbose=False):
                            _logger.warning("Failed to stop the generator")

                        for _ in range(10):
                            try:

                                data_packet, _ = _data_socket.recvfrom(1358)

                                # * Find the lines with fixed line pattern
                                extracted_payloads_pool.extend(packetlibX.extract_raw_data(data_packet))
                                bytes_counter += len(data_packet)
                                if len(data_packet) > 0:
                                    break

                            except socket.timeout:
                                if _verbose:
                                    _logger.warning("Socket timeout, no data received")

                    # logger.debug(f"Received {bytes_counter} bytes of data")
                    num_packets = bytes_counter / 1358
                    half_packet_number = (bytes_counter - num_packets * 14) / 192
                    event_number = half_packet_number / 2 / _total_asic_num
                    half_packet_number = int(half_packet_number)
                    event_number = int(event_number)

                    #logger.debug(f"Received {num_packets} packets, {half_packet_number} half packets, {event_number} events")
                    #logger.debug(f"Received {len(extracted_payloads_pool)} payloads")

                    #_logger.debug(f"Starting processing loop with {len(extracted_payloads_pool)} payloads")

                    chunk_counter = 0
                    event_chunk_buffer = []

                    while len(extracted_payloads_pool) > 0:
                        payload_192 = extracted_payloads_pool.popleft()
                        chunk_counter += 1

                        extracted_data = packetlibX.extract_values_192(payload_192, verbose=False)
                        if extracted_data is None:
                            _logger.warning(f"Failed to extract chunk #{chunk_counter}")
                            continue

                        event_chunk_buffer.append(extracted_data)
                        # When we have 4 chunks, we can assemble a full event
                        if len(event_chunk_buffer) == 4:
                            # Combine or verify that these 4 belong together (same timestamp, etc.)
                            timestamps = [c["_timestamp"] for c in event_chunk_buffer]
                            
                            if len(set(timestamps)) == 1:
                                # ✅ All 4 chunks belong to the same event
                                for _half, chunk in enumerate(event_chunk_buffer):
                                    _DaqH = chunk["_DaqH"]
                                    extracted_values = chunk["_extracted_values"]
                                    # Extract ASIC and packet ID
                                    byte3 = chunk["_address_id"]  # 3rd byte
                                    byte4 = chunk["_packet_id"]  # 4th byte
                                    asic_id = byte3 & 0x0F   # upper 4 bits of 3rd byte
                                    #logger.debug(asic_id)
                                    packet_id = byte4               # full 4th byte
                                    # Determine base channel ID for this chunk
                                    uni_chn_base = asic_id * 76 + (packet_id - 0x24) * 38     

                                    # Fill arrays, same as before
                                    for j, vals in enumerate(extracted_values):
                                        channel_id = uni_chn_base + j  # correct unique channel ID
                                        all_chn_value_0_array[current_event_num][channel_id] = vals[1]
                                        all_chn_value_1_array[current_event_num][channel_id] = vals[2]
                                        all_chn_value_2_array[current_event_num][channel_id] = vals[3]

                                    hamming_code_array[current_event_num][_half*3 + 0] = packetlibX.DaqH_get_H1(_DaqH)
                                    hamming_code_array[current_event_num][_half*3 + 1] = packetlibX.DaqH_get_H2(_DaqH)
                                    hamming_code_array[current_event_num][_half*3 + 2] = packetlibX.DaqH_get_H3(_DaqH)
                                    daqh_good_array[current_event_num][_half] = packetlibX.DaqH_start_end_good(_DaqH)

                                # After processing all 4 halves → count 1 event
                                if np.all(hamming_code_array[current_event_num] == 0) and np.all(daqh_good_array[current_event_num]):
                                    timestamps_events.append(timestamps[0])
                                    current_event_num += 1
                                else:
                                    _logger.warning("Invalid event detected (hamming or DAQH error)")

                            else:
                                _logger.warning(f"Chunk timestamps mismatch: {timestamps}")

                            # Clear buffer for next event
                            event_chunk_buffer.clear()

                        # Stop when all events collected
                        if current_event_num >= _total_event:
                            #_logger.debug(f"Received enough events: {current_event_num}/{_total_event}")
                            _all_events_received = True
                            break

                    #_logger.debug(f"Loop finished — processed {chunk_counter} chunks, built {current_event_num} full events")


                except Exception as e:
                    if _verbose:
                        _logger.warning("Exception in receiving data")
                        _logger.warning(e)
                        _logger.warning('Halves received: ' + str(current_half_packet_num))
                        _logger.warning('Halves expected: ' + str(_total_event * 2 * _total_asic_num))
                        _logger.warning('left fragments:' + str(len(event_fragment_pool)))
                        _logger.warning("current event num:" + str(current_event_num))
                    _all_events_received = False
                    break
                
            for _event in range(current_event_num):
                if not np.all(daqh_good_array[_event] == True):
                    counter_daqh_incorrect += 1

            if (current_event_num - counter_daqh_incorrect) < min(_total_event//2, 1):
                if _verbose:
                    _logger.warning("Not enough valid events received " + str(current_event_num) + "  " + str(_total_event))
                _all_events_received = False
                continue
            
            #_logger.debug(f"Event number: {current_event_num}")
            timestamps_pure = []
            for _timestamp_index in range(len(timestamps_events)):
                timestamps_pure.append(timestamps_events[_timestamp_index] - timestamps_events[0])
            #_logger.debug(f"Timestamps: {timestamps_pure}")
            if timestamps_pure[-1] != 164*(_machine_gun):
                _logger.warning(f"Machine gun {timestamps_pure[-1]} is not enough for {_machine_gun}")
                _all_events_received = False
                continue
            
            for _chn in range(n_channels):
                _candidate_adc_values = [[] for _ in range(_machine_gun + 1)]
                _candidate_tot_values = [[] for _ in range(_machine_gun + 1)]
                _candidate_toa_values = [[] for _ in range(_machine_gun + 1)]
                # _current_machine_gun = 0

                for _event in range(current_event_num):
                    # if np.all(hamming_code_array[_event] == 0):
                    if len(_focus_half) == 0:
                        if np.all(hamming_code_array[_event] == 0) and np.all(daqh_good_array[_event] == True):
                            _current_machine_gun = (timestamps_events[_event] - timestamps_events[0]) // 164
                            if _current_machine_gun > _machine_gun:
                                _logger.warning(f"Machine gun {_current_machine_gun} exceeds {_machine_gun}")
                                continue
                            # if _chn == 6:
                            #     _logger.debug(f"Event {_event}, machine gun {_current_machine_gun}, channel {_chn}: ADC: {all_chn_value_0_array[_event][_chn]}, TOT: {all_chn_value_1_array[_event][_chn]}, ToA: {all_chn_value_2_array[_event][_chn]}")
                            _candidate_adc_values[_current_machine_gun].append(all_chn_value_0_array[_event][_chn])
                            _candidate_tot_values[_current_machine_gun].append(all_chn_value_1_array[_event][_chn])
                            _candidate_toa_values[_current_machine_gun].append(all_chn_value_2_array[_event][_chn])
                        # _current_machine_gun = (_current_machine_gun + 1) % (_machine_gun + 1)
                    else:
                        # only check the focus half daqh and hamming code
                        hamming_code_focus = []
                        daqh_good_focus  = []
                        for _half in range(n_halves):
                            if _half in _focus_half:
                                hamming_code_focus.append(hamming_code_array[_event][_half*3+0])
                                hamming_code_focus.append(hamming_code_array[_event][_half*3+1])
                                hamming_code_focus.append(hamming_code_array[_event][_half*3+2])
                                daqh_good_focus.append(daqh_good_array[_event][_half])
                        hamming_code_focus = np.array(hamming_code_focus)
                        daqh_good_focus  = np.array(daqh_good_focus)
                        if np.all(hamming_code_focus == 0) and np.all(daqh_good_focus == True):
                            _current_machine_gun = (timestamps_events[_event] - timestamps_events[0]) // 41
                            # if _chn == 6:
                            #     _logger.debug(f"Event {_event}, machine gun {_current_machine_gun}, channel {_chn}: ADC: {all_chn_value_0_array[_event][_chn]}, TOT: {all_chn_value_1_array[_event][_chn]}, ToA: {all_chn_value_2_array[_event][_chn]}")
                            _candidate_adc_values[_current_machine_gun].append(all_chn_value_0_array[_event][_chn])
                            _candidate_tot_values[_current_machine_gun].append(all_chn_value_1_array[_event][_chn])
                            _candidate_toa_values[_current_machine_gun].append(all_chn_value_2_array[_event][_chn])
                event_short = 0
                if len(_candidate_adc_values) > 0:
                    for _machine_gun_value in range(_machine_gun + 1):
                        if len(_candidate_adc_values[_machine_gun_value]) > 0:
                            _mean_adc = np.mean(_candidate_adc_values[_machine_gun_value])
                            _err_adc  = np.std(_candidate_adc_values[_machine_gun_value]) / np.sqrt(len(_candidate_adc_values[_machine_gun_value]))
                        else:
                            _mean_adc = 0
                            _err_adc  = 0
                        if len(_candidate_tot_values[_machine_gun_value]) > 0:
                            _mean_tot = np.mean(_candidate_tot_values[_machine_gun_value])
                            _err_tot  = np.std(_candidate_tot_values[_machine_gun_value]) / np.sqrt(len(_candidate_tot_values[_machine_gun_value]))
                        else:
                            _mean_tot = 0
                            _err_tot  = 0
                        if len(_candidate_toa_values[_machine_gun_value]) > 0:
                            _mean_toa = np.mean(_candidate_toa_values[_machine_gun_value])
                            _err_toa  = np.std(_candidate_toa_values[_machine_gun_value]) / np.sqrt(len(_candidate_toa_values[_machine_gun_value]))
                        else:
                            _mean_toa = 0
                            _err_toa  = 0

                        # remove nan values
                        if np.isnan(_mean_adc):
                            _mean_adc = 0
                        if np.isnan(_mean_tot):
                            _mean_tot = 0
                        if np.isnan(_mean_toa):
                            _mean_toa = 0
                        if np.isnan(_err_adc):
                            _err_adc = 0
                        if np.isnan(_err_tot):
                            _err_tot = 0
                        if np.isnan(_err_toa):
                            _err_toa = 0

                        _machine_gun_offset = _machine_gun_value + event_short
                        if _machine_gun_offset > _machine_gun:
                            _machine_gun_offset -= (_machine_gun + 1)   
                        adc_mean_list[_machine_gun_offset][_chn] = _mean_adc
                        adc_err_list[_machine_gun_offset][_chn]  = _err_adc
                        tot_mean_list[_machine_gun_offset][_chn] = _mean_tot
                        tot_err_list[_machine_gun_offset][_chn]  = _err_tot
                        toa_mean_list[_machine_gun_offset][_chn] = _mean_toa
                        toa_err_list[_machine_gun_offset][_chn]  = _err_toa
                        # _logger.debug(f"Machine gun {_machine_gun}, channel {_chn}: ADC mean: {adc_mean_list[_machine_gun][_chn]}, ADC error: {adc_err_list[_machine_gun][_chn]}, TOT mean: {tot_mean_list[_machine_gun][_chn]}, TOT error: {tot_err_list[_machine_gun][_chn]}, ToA mean: {toa_mean_list[_machine_gun][_chn]}, ToA error: {toa_err_list[_machine_gun][_chn]}")
                else:
                    for _machine_gun_value in range(_machine_gun + 1):
                        _machine_gun_offset = _machine_gun_value + event_short
                        if _machine_gun_offset > _machine_gun:
                            _machine_gun_offset -= (_machine_gun + 1)   
                        adc_mean_list[_machine_gun_offset][_chn] = 0
                        adc_err_list[_machine_gun_offset][_chn]  = 0
                        tot_mean_list[_machine_gun_offset][_chn] = 0
                        tot_err_list[_machine_gun_offset][_chn]  = 0
                        toa_mean_list[_machine_gun_offset][_chn] = 0
                        toa_err_list[_machine_gun_offset][_chn]  = 0
            #exit()
            if 0:
                for _chn in range(n_channels):
                    _candidate_adc_values = [[] for _ in range(_machine_gun + 1)]
                    _candidate_tot_values = [[] for _ in range(_machine_gun + 1)]
                    _candidate_toa_values = [[] for _ in range(_machine_gun + 1)]
                    # _current_machine_gun = 0

                    for _event in range(current_event_num):
                        # if np.all(hamming_code_array[_event] == 0):
                        if len(_focus_half) == 0:
                            if np.all(hamming_code_array[_event] == 0) and np.all(daqh_good_array[_event] == True):
                                _current_machine_gun = (timestamps_events[_event] - timestamps_events[0]) // 41
                                if _current_machine_gun > _machine_gun:
                                    _logger.warning(f"Machine gun {_current_machine_gun} exceeds {_machine_gun}")
                                    continue
                                # if _chn == 6:
                                #     _logger.debug(f"Event {_event}, machine gun {_current_machine_gun}, channel {_chn}: ADC: {all_chn_value_0_array[_event][_chn]}, TOT: {all_chn_value_1_array[_event][_chn]}, ToA: {all_chn_value_2_array[_event][_chn]}")
                                _candidate_adc_values[_current_machine_gun].append(all_chn_value_0_array[_event][_chn])
                                _candidate_tot_values[_current_machine_gun].append(all_chn_value_1_array[_event][_chn])
                                _candidate_toa_values[_current_machine_gun].append(all_chn_value_2_array[_event][_chn])
                            # _current_machine_gun = (_current_machine_gun + 1) % (_machine_gun + 1)
                        else:
                            # only check the focus half daqh and hamming code
                            hamming_code_focus = []
                            daqh_good_focus  = []
                            for _half in range(n_halves):
                                if _half in _focus_half:
                                    hamming_code_focus.append(hamming_code_array[_event][_half*3+0])
                                    hamming_code_focus.append(hamming_code_array[_event][_half*3+1])
                                    hamming_code_focus.append(hamming_code_array[_event][_half*3+2])
                                    daqh_good_focus.append(daqh_good_array[_event][_half])
                            hamming_code_focus = np.array(hamming_code_focus)
                            daqh_good_focus  = np.array(daqh_good_focus)
                            if np.all(hamming_code_focus == 0) and np.all(daqh_good_focus == True):
                                _current_machine_gun = (timestamps_events[_event] - timestamps_events[0]) // 41
                                # if _chn == 6:
                                #     _logger.debug(f"Event {_event}, machine gun {_current_machine_gun}, channel {_chn}: ADC: {all_chn_value_0_array[_event][_chn]}, TOT: {all_chn_value_1_array[_event][_chn]}, ToA: {all_chn_value_2_array[_event][_chn]}")
                                _candidate_adc_values[_current_machine_gun].append(all_chn_value_0_array[_event][_chn])
                                _candidate_tot_values[_current_machine_gun].append(all_chn_value_1_array[_event][_chn])
                                _candidate_toa_values[_current_machine_gun].append(all_chn_value_2_array[_event][_chn])
                    event_short = 0
                    if len(_candidate_adc_values) > 0:
                        for _machine_gun_value in range(_machine_gun + 1):
                            if len(_candidate_adc_values[_machine_gun_value]) > 0:
                                _mean_adc = np.mean(_candidate_adc_values[_machine_gun_value])
                                _err_adc  = np.std(_candidate_adc_values[_machine_gun_value]) / np.sqrt(len(_candidate_adc_values[_machine_gun_value]))
                            else:
                                _mean_adc = 0
                                _err_adc  = 0
                            if len(_candidate_tot_values[_machine_gun_value]) > 0:
                                _mean_tot = np.mean(_candidate_tot_values[_machine_gun_value])
                                _err_tot  = np.std(_candidate_tot_values[_machine_gun_value]) / np.sqrt(len(_candidate_tot_values[_machine_gun_value]))
                            else:
                                _mean_tot = 0
                                _err_tot  = 0
                            if len(_candidate_toa_values[_machine_gun_value]) > 0:
                                _mean_toa = np.mean(_candidate_toa_values[_machine_gun_value])
                                _err_toa  = np.std(_candidate_toa_values[_machine_gun_value]) / np.sqrt(len(_candidate_toa_values[_machine_gun_value]))
                            else:
                                _mean_toa = 0
                                _err_toa  = 0

                            # remove nan values
                            if np.isnan(_mean_adc):
                                _mean_adc = 0
                            if np.isnan(_mean_tot):
                                _mean_tot = 0
                            if np.isnan(_mean_toa):
                                _mean_toa = 0
                            if np.isnan(_err_adc):
                                _err_adc = 0
                            if np.isnan(_err_tot):
                                _err_tot = 0
                            if np.isnan(_err_toa):
                                _err_toa = 0

                            _machine_gun_offset = _machine_gun_value + event_short
                            if _machine_gun_offset > _machine_gun:
                                _machine_gun_offset -= (_machine_gun + 1)   
                            adc_mean_list[_machine_gun_offset][_chn] = _mean_adc
                            adc_err_list[_machine_gun_offset][_chn]  = _err_adc
                            tot_mean_list[_machine_gun_offset][_chn] = _mean_tot
                            tot_err_list[_machine_gun_offset][_chn]  = _err_tot
                            toa_mean_list[_machine_gun_offset][_chn] = _mean_toa
                            toa_err_list[_machine_gun_offset][_chn]  = _err_toa
                            # _logger.debug(f"Machine gun {_machine_gun}, channel {_chn}: ADC mean: {adc_mean_list[_machine_gun][_chn]}, ADC error: {adc_err_list[_machine_gun][_chn]}, TOT mean: {tot_mean_list[_machine_gun][_chn]}, TOT error: {tot_err_list[_machine_gun][_chn]}, ToA mean: {toa_mean_list[_machine_gun][_chn]}, ToA error: {toa_err_list[_machine_gun][_chn]}")
                    else:
                        for _machine_gun_value in range(_machine_gun + 1):
                            _machine_gun_offset = _machine_gun_value + event_short
                            if _machine_gun_offset > _machine_gun:
                                _machine_gun_offset -= (_machine_gun + 1)   
                            adc_mean_list[_machine_gun_offset][_chn] = 0
                            adc_err_list[_machine_gun_offset][_chn]  = 0
                            tot_mean_list[_machine_gun_offset][_chn] = 0
                            tot_err_list[_machine_gun_offset][_chn]  = 0
                            toa_mean_list[_machine_gun_offset][_chn] = 0
                            toa_err_list[_machine_gun_offset][_chn]  = 0

        finally:
            if not packetlibX.send_daq_gen_start_stop(_cmd_socket, _h2gcroc_ip, _h2gcroc_port, fpga_addr = _fpga_addr, daq_push=0x00, gen_start_stop=0, daq_start_stop=0x00, verbose=False):
                _logger.warning("Failed to stop the generator")

        if _verbose:
            _logger.info(f"daqh bad events: {counter_daqh_incorrect} (expected: {_total_event}, received: {current_event_num})")

    if not _all_events_received:
        _logger.warning("Not enough valid events received")
        _logger.warning("Returning list of zeros")


    # if True:
    #     _logger.debug(f'Total events received: {current_event_num} / {_total_event}')
    #     _logger.debug(f'DaqH Bad events: {counter_daqh_incorrect}')

    return adc_mean_list, adc_err_list, tot_mean_list, tot_err_list, toa_mean_list, toa_err_list

def measure_all_pede(_cmd_socket, _data_socket, _h2gcroc_ip, _h2gcroc_port, _total_asic_num, _fpga_addr, _machine_gun, _total_event, _fragment_life, _logger, _retry=1, _verbose=False, _focus_half=[]):
    _retry_left = _retry
    _all_events_received = False

    n_channels = _total_asic_num * 76
    n_halves   = _total_asic_num * 2

    adc_mean_list = np.zeros((_machine_gun+1, n_channels))
    adc_err_list  = np.zeros((_machine_gun+1, n_channels))
    tot_mean_list = np.zeros((_machine_gun+1, n_channels))
    tot_err_list  = np.zeros((_machine_gun+1, n_channels))
    toa_mean_list = np.zeros((_machine_gun+1, n_channels))
    toa_err_list  = np.zeros((_machine_gun+1, n_channels))
    
    while _retry_left > 0 and not _all_events_received:
        if _retry_left < _retry:
            if _verbose:
                _logger.info(f"Retrying measurement, attempts left: {_retry_left}")
            time.sleep(0.1)
        _retry_left -= 1

        try:
            extracted_payloads_pool = deque()
            event_fragment_pool     = []
            fragment_life_dict      = {}

            timestamps_events = []

            current_half_packet_num = 0
            current_event_num       = 0
            counter_daqh_incorrect  = 0

            # Preallocate arrays for _event_num events.
            # We will later process only the rows for which we received data.
            all_chn_value_0_array = np.zeros((_total_event, n_channels))
            all_chn_value_1_array = np.zeros((_total_event, n_channels))
            all_chn_value_2_array = np.zeros((_total_event, n_channels))
            hamming_code_array    = np.zeros((_total_event, 3*n_halves))
            daqh_good_array       = np.zeros((_total_event,   n_halves))

            for i in range(_total_event):
                for j in range(n_halves):
                    daqh_good_array[i][j] = True

            if not packetlib.send_daq_gen_start_stop(_cmd_socket, _h2gcroc_ip, _h2gcroc_port, fpga_addr = _fpga_addr, daq_push=0x00, gen_start_stop=0, daq_start_stop=0xFF, verbose=False):
                _logger.warning("Failed to start the generator")
            if not packetlib.send_daq_gen_start_stop(_cmd_socket, _h2gcroc_ip, _h2gcroc_port, fpga_addr = _fpga_addr, daq_push=0x00, gen_start_stop=1, daq_start_stop=0xFF, verbose=False):
                _logger.warning("Failed to start the generator")

            # packetlib.clean_socket(_socket_udp_data)

            # if not packetlib.send_daq_gen_start_stop(
            #         _socket_udp_cmd, _ip, _port,
            #         fpga_addr=_fpga_address,
            #         daq_push=0x00, gen_start_stop=1, daq_start_stop=0xFF,
            #         verbose=False):
            #     _logger.warning("Failed to start the generator")

            # Main loop: try to receive data until we have enough events.
            # while current_event_num < _total_event - 4:
            if True:
                try:
                    bytes_counter = 0
                    try:
                        for _ in range(100):
                            data_packet, _ = _data_socket.recvfrom(8192)

                            # * Find the lines with fixed line pattern
                            extracted_payloads_pool.extend(packetlib.extract_raw_payloads(data_packet))
                            # _logger.debug(f'data length: {len(data_packet)}')
                            bytes_counter += len(data_packet)

                    except socket.timeout:
                        if _verbose:
                            _logger.warning("Socket timeout, no data received")

                        if not packetlib.send_daq_gen_start_stop(_cmd_socket, _h2gcroc_ip, _h2gcroc_port, fpga_addr = _fpga_addr, daq_push=0x00, gen_start_stop=0, daq_start_stop=0x00, verbose=False):
                            _logger.warning("Failed to stop the generator")

                        for _ in range(5):
                            try:

                                data_packet, _ = _data_socket.recvfrom(8192)

                                # * Find the lines with fixed line pattern
                                extracted_payloads_pool.extend(packetlib.extract_raw_payloads(data_packet))
                                # _logger.debug(f'data length: {len(data_packet)}')
                                bytes_counter += len(data_packet)
                                if len(data_packet) > 0:
                                    break

                            except socket.timeout:
                                if _verbose:
                                    _logger.warning("Socket timeout, no data received")


                    # data_packet, _ = _data_socket.recvfrom(8192)
                    # extracted_payloads_pool.extend(packetlib.extract_raw_payloads(data_packet))

                    # logger.debug(f"Received {bytes_counter} bytes of data")
                    half_packet_number = float(bytes_counter) / (5 * 40)
                    event_number = half_packet_number / 2 / _total_asic_num
                    half_packet_number = int(half_packet_number)
                    event_number = int(event_number)

                    logger.debug(f"Received {half_packet_number} half packets, {event_number} events")
                    logger.debug(f"Received {len(extracted_payloads_pool)} payloads")

                    if len(extracted_payloads_pool) >= 5:
                        candidate_packet_lines = [extracted_payloads_pool.popleft() for _ in range(5)]
                        while len(extracted_payloads_pool) > 0:
                            is_packet_good, event_fragment = packetlib.check_event_fragment(candidate_packet_lines)
                            if is_packet_good:
                                event_fragment_pool.append(event_fragment)
                                current_half_packet_num += 1
                                if len(extracted_payloads_pool) >= 5:
                                    candidate_packet_lines = [extracted_payloads_pool.popleft() for _ in range(5)]
                                else:
                                    break
                            else:
                                _logger.warning("Warning: Event fragment is not good")
                                # pop out the oldest line
                                candidate_packet_lines.pop(0)
                                candidate_packet_lines.append(extracted_payloads_pool.popleft())

                    logger.debug(f"Current half packet number: {current_half_packet_num}")

                    indices_to_delete = set()
                    if len(event_fragment_pool) >= n_halves:
                        event_fragment_pool = sorted(event_fragment_pool, key=lambda x: x[0][4:7])

                    counter_fragment = 0
                    while counter_fragment <= len(event_fragment_pool) - n_halves:
                        timestamps = []
                        for counter_half in range(n_halves):
                            timestamps.append(event_fragment_pool[counter_fragment+counter_half][0][4] << 24 | event_fragment_pool[counter_fragment+counter_half][0][5] << 16 | event_fragment_pool[counter_fragment+counter_half][0][6] << 8 | event_fragment_pool[counter_fragment+counter_half][0][7])
                        if len(set(timestamps)) == 1:
                            for _half in range(n_halves):
                                extracted_data = packetlib.assemble_data_from_40bytes(event_fragment_pool[counter_fragment+_half], verbose=False)
                                extracted_values = packetlib.extract_values(extracted_data["_extraced_160_bytes"], verbose=False)
                                uni_chn_base = (extracted_data["_header"] - 0xA0) * 76 + (extracted_data["_packet_type"] - 0x24) * 38
                                for j in range(len(extracted_values["_extracted_values"])):
                                    all_chn_value_0_array[current_event_num][j+uni_chn_base] = extracted_values["_extracted_values"][j][1]
                                    all_chn_value_1_array[current_event_num][j+uni_chn_base] = extracted_values["_extracted_values"][j][2]
                                    all_chn_value_2_array[current_event_num][j+uni_chn_base] = extracted_values["_extracted_values"][j][3]
                                hamming_code_array[current_event_num][_half*3+0] =  packetlib.DaqH_get_H1(extracted_values["_DaqH"])
                                hamming_code_array[current_event_num][_half*3+1] =  packetlib.DaqH_get_H2(extracted_values["_DaqH"])
                                hamming_code_array[current_event_num][_half*3+2] =  packetlib.DaqH_get_H3(extracted_values["_DaqH"])
                                daqh_good_array[current_event_num][_half] = packetlib.DaqH_start_end_good(extracted_values["_DaqH"])
                            update_indices = []
                            for j in range(n_halves):
                                update_indices.append(counter_fragment+j)
                            indices_to_delete.update(update_indices)
                            if _verbose:
                                if not np.all(hamming_code_array[current_event_num] == 0):
                                    _logger.warning("Hamming code error detected!")
                                if not np.all(daqh_good_array[current_event_num] == True):
                                    _logger.warning("DAQH start/end error detected!")

                            if len(_focus_half) == 0:
                                if np.all(hamming_code_array[current_event_num] == 0) and np.all(daqh_good_array[current_event_num] == True):
                                    current_event_num += 1
                                    timestamps_events.append(timestamps[0])
                            else:
                                # only check the focus half daqh and hamming code
                                hamming_code_focus = []
                                daqh_good_focus  = []

                                for _half in range(n_halves):
                                    if _half in _focus_half:
                                        hamming_code_focus.append(int(hamming_code_array[current_event_num][_half*3+0]))
                                        hamming_code_focus.append(int(hamming_code_array[current_event_num][_half*3+1]))
                                        hamming_code_focus.append(int(hamming_code_array[current_event_num][_half*3+2]))
                                        daqh_good_focus.append(bool(daqh_good_array[current_event_num][_half]))
                                hamming_code_focus = np.array(hamming_code_focus)
                                daqh_good_focus  = np.array(daqh_good_focus)
                                # _logger.debug(f"Focus half: {_half}, hamming code: {hamming_code_focus}, daqh good: {daqh_good_focus}")
                                # #     _logger.debug("if finished")
                                # # _logger.debug("for loop finished")
                                # # print the focus hamming code in hex
                                # _logger.debug(f"Focus hamming code: {hamming_code_focus} and is all zero: {np.all(hamming_code_focus == 0)}")
                                # # print the focus daqh in hex
                                # _logger.debug(f"Focus daqh: {daqh_good_focus} and is all True: {np.all(daqh_good_focus == True)}")
                                if np.all(hamming_code_focus == 0) and np.all(daqh_good_focus == True):
                                    current_event_num += 1
                                #     _logger.debug(f"Event {current_event_num} is valid")
                                # else:
                                #     _logger.warning("Invalid event detected in focus half")


                            counter_fragment += 1
                            # _logger.debug(f"-- Found a full event fragment, current event num: {current_event_num}")
                        else:
                            if timestamps[0] in fragment_life_dict:
                                if fragment_life_dict[timestamps[0]] >= _fragment_life - 1:
                                    indices_to_delete.update([counter_fragment])
                                    del fragment_life_dict[timestamps[0]]
                                else:
                                    fragment_life_dict[timestamps[0]] += 1
                            else:
                                fragment_life_dict[timestamps[0]] = 1
                            counter_fragment += 1
                    for index in sorted(indices_to_delete, reverse=True):
                        del event_fragment_pool[index]

                    # Stop receiving if we have reached our target _event_num;
                    # or if we have at least (_event_num - 4) events and an exception (e.g. timeout) occurs.
                    if current_event_num >= _total_event - 4:
                        if _verbose:
                            _logger.debug(f"Received enough events: {current_event_num} events (target: {_total_event} events)")
                        _all_events_received = True
                        # break;   

                except Exception as e:
                    if _verbose:
                        _logger.warning("Exception in receiving data")
                        _logger.warning(e)
                        _logger.warning('Halves received: ' + str(current_half_packet_num))
                        _logger.warning('Halves expected: ' + str(_total_event * 2 * _total_asic_num))
                        _logger.warning('left fragments:' + str(len(event_fragment_pool)))
                        _logger.warning("current event num:" + str(current_event_num))
                    _all_events_received = False
                    break
                
            for _event in range(current_event_num):
                if not np.all(daqh_good_array[_event] == True):
                    counter_daqh_incorrect += 1

            if (current_event_num - counter_daqh_incorrect) < min(_total_event//2, 1):
                if _verbose:
                    _logger.warning("Not enough valid events received")
                _all_events_received = False
                continue
            
            # _logger.debug(f"Event number: {current_event_num}")
            timestamps_pure = []
            for _timestamp_index in range(len(timestamps_events)):
                timestamps_pure.append(timestamps_events[_timestamp_index] - timestamps_events[0])
            # _logger.debug(f"Timestamps: {timestamps_pure}")
            if timestamps_pure[-1] != 41*(_machine_gun-1):
                _logger.warning(f"Machine gun {timestamps_pure[-1]} is not enough")
                _all_events_received = False
                continue
           
            for _chn in range(n_channels):
                _candidate_adc_values = [[] for _ in range(_machine_gun + 1)]
                _candidate_tot_values = [[] for _ in range(_machine_gun + 1)]
                _candidate_toa_values = [[] for _ in range(_machine_gun + 1)]
                # _current_machine_gun = 0

                for _event in range(current_event_num):
                    # if np.all(hamming_code_array[_event] == 0):
                    if len(_focus_half) == 0:
                        if np.all(hamming_code_array[_event] == 0) and np.all(daqh_good_array[_event] == True):
                            _current_machine_gun = (timestamps_events[_event] - timestamps_events[0]) // 41
                            if _current_machine_gun > _machine_gun:
                                _logger.warning(f"Machine gun {_current_machine_gun} exceeds {_machine_gun}")
                                continue
                            # if _chn == 6:
                            #     _logger.debug(f"Event {_event}, machine gun {_current_machine_gun}, channel {_chn}: ADC: {all_chn_value_0_array[_event][_chn]}, TOT: {all_chn_value_1_array[_event][_chn]}, ToA: {all_chn_value_2_array[_event][_chn]}")
                            _candidate_adc_values[_current_machine_gun].append(all_chn_value_0_array[_event][_chn])
                            _candidate_tot_values[_current_machine_gun].append(all_chn_value_1_array[_event][_chn])
                            _candidate_toa_values[_current_machine_gun].append(all_chn_value_2_array[_event][_chn])
                        # _current_machine_gun = (_current_machine_gun + 1) % (_machine_gun + 1)
                    else:
                        # only check the focus half daqh and hamming code
                        hamming_code_focus = []
                        daqh_good_focus  = []
                        for _half in range(n_halves):
                            if _half in _focus_half:
                                hamming_code_focus.append(hamming_code_array[_event][_half*3+0])
                                hamming_code_focus.append(hamming_code_array[_event][_half*3+1])
                                hamming_code_focus.append(hamming_code_array[_event][_half*3+2])
                                daqh_good_focus.append(daqh_good_array[_event][_half])
                        hamming_code_focus = np.array(hamming_code_focus)
                        daqh_good_focus  = np.array(daqh_good_focus)
                        if np.all(hamming_code_focus == 0) and np.all(daqh_good_focus == True):
                            _current_machine_gun = (timestamps_events[_event] - timestamps_events[0]) // 41
                            # if _chn == 6:
                            #     _logger.debug(f"Event {_event}, machine gun {_current_machine_gun}, channel {_chn}: ADC: {all_chn_value_0_array[_event][_chn]}, TOT: {all_chn_value_1_array[_event][_chn]}, ToA: {all_chn_value_2_array[_event][_chn]}")
                            _candidate_adc_values[_current_machine_gun].append(all_chn_value_0_array[_event][_chn])
                            _candidate_tot_values[_current_machine_gun].append(all_chn_value_1_array[_event][_chn])
                            _candidate_toa_values[_current_machine_gun].append(all_chn_value_2_array[_event][_chn])
                event_short = 0
                if len(_candidate_adc_values) > 0:
                    for _machine_gun_value in range(_machine_gun + 1):
                        if len(_candidate_adc_values[_machine_gun_value]) > 0:
                            _mean_adc = np.mean(_candidate_adc_values[_machine_gun_value])
                            _err_adc  = np.std(_candidate_adc_values[_machine_gun_value]) / np.sqrt(len(_candidate_adc_values[_machine_gun_value]))
                        else:
                            _mean_adc = 0
                            _err_adc  = 0
                        if len(_candidate_tot_values[_machine_gun_value]) > 0:
                            _mean_tot = np.mean(_candidate_tot_values[_machine_gun_value])
                            _err_tot  = np.std(_candidate_tot_values[_machine_gun_value]) / np.sqrt(len(_candidate_tot_values[_machine_gun_value]))
                        else:
                            _mean_tot = 0
                            _err_tot  = 0
                        if len(_candidate_toa_values[_machine_gun_value]) > 0:
                            _mean_toa = np.mean(_candidate_toa_values[_machine_gun_value])
                            _err_toa  = np.std(_candidate_toa_values[_machine_gun_value]) / np.sqrt(len(_candidate_toa_values[_machine_gun_value]))
                        else:
                            _mean_toa = 0
                            _err_toa  = 0

                        # remove nan values
                        if np.isnan(_mean_adc):
                            _mean_adc = 0
                        if np.isnan(_mean_tot):
                            _mean_tot = 0
                        if np.isnan(_mean_toa):
                            _mean_toa = 0
                        if np.isnan(_err_adc):
                            _err_adc = 0
                        if np.isnan(_err_tot):
                            _err_tot = 0
                        if np.isnan(_err_toa):
                            _err_toa = 0

                        _machine_gun_offset = _machine_gun_value + event_short
                        if _machine_gun_offset > _machine_gun:
                            _machine_gun_offset -= (_machine_gun + 1)   
                        adc_mean_list[_machine_gun_offset][_chn] = _mean_adc
                        adc_err_list[_machine_gun_offset][_chn]  = _err_adc
                        tot_mean_list[_machine_gun_offset][_chn] = _mean_tot
                        tot_err_list[_machine_gun_offset][_chn]  = _err_tot
                        toa_mean_list[_machine_gun_offset][_chn] = _mean_toa
                        toa_err_list[_machine_gun_offset][_chn]  = _err_toa
                        # _logger.debug(f"Machine gun {_machine_gun}, channel {_chn}: ADC mean: {adc_mean_list[_machine_gun][_chn]}, ADC error: {adc_err_list[_machine_gun][_chn]}, TOT mean: {tot_mean_list[_machine_gun][_chn]}, TOT error: {tot_err_list[_machine_gun][_chn]}, ToA mean: {toa_mean_list[_machine_gun][_chn]}, ToA error: {toa_err_list[_machine_gun][_chn]}")
                else:
                    for _machine_gun_value in range(_machine_gun + 1):
                        _machine_gun_offset = _machine_gun_value + event_short
                        if _machine_gun_offset > _machine_gun:
                            _machine_gun_offset -= (_machine_gun + 1)   
                        adc_mean_list[_machine_gun_offset][_chn] = 0
                        adc_err_list[_machine_gun_offset][_chn]  = 0
                        tot_mean_list[_machine_gun_offset][_chn] = 0
                        tot_err_list[_machine_gun_offset][_chn]  = 0
                        toa_mean_list[_machine_gun_offset][_chn] = 0
                        toa_err_list[_machine_gun_offset][_chn]  = 0

        finally:
            if not packetlib.send_daq_gen_start_stop(_cmd_socket, _h2gcroc_ip, _h2gcroc_port, fpga_addr = _fpga_addr, daq_push=0x00, gen_start_stop=0, daq_start_stop=0x00, verbose=False):
                _logger.warning("Failed to stop the generator")

        if _verbose:
            _logger.info(f"daqh bad events: {counter_daqh_incorrect} (expected: {_total_event}, received: {current_event_num})")

    if not _all_events_received:
        _logger.warning("Not enough valid events received")
        _logger.warning("Returning list of zeros")

# def measure_adc(_cmd_socket, _data_socket, _h2gcroc_ip, _h2gcroc_port, _total_asic_num, _fpga_addr, _total_event, _fragment_life, _logger, _retry=1, _verbose=False):
#     adc_mean_list, adc_err_list, tot_mean_list, tot_err_list, toa_mean_list, toa_err_list = measure_all(_cmd_socket, _data_socket, _h2gcroc_ip, _h2gcroc_port, _total_asic_num, _fpga_addr, 10, _total_event, _fragment_life, _logger, _retry=_retry, _verbose=_verbose)
    
#     return adc_mean_list[0], adc_err_list[0]

def measure_adc(_cmd_socket, _data_socket, _h2gcroc_ip, _h2gcroc_port, _total_asic_num, _fpga_addr, _total_event, _fragment_life, _logger, _retry=1, _verbose=False):
    adc_mean_list, adc_err_list, tot_mean_list, tot_err_list, toa_mean_list, toa_err_list = measure_all(_cmd_socket, _data_socket, _h2gcroc_ip, _h2gcroc_port, _total_asic_num, _fpga_addr, 10, _total_event, _fragment_life, _logger, _retry=_retry, _verbose=_verbose)
    
    return adc_mean_list[0], adc_err_list[0]

def Inj_2V5(_cmd_out_conn, _cmd_data_conn, _data_data_conn, _h2gcroc_ip, _h2gcroc_port, _fpga_address, _phase, _dac, _scan_chn_start, _scan_chn_number, _asic_num, _scan_chn_pack, _machine_gun, _expected_event_number, _fragment_life, _config, unused_chn_list, _dead_chn_list, _i2c_dict, _logger, _retry=1, _verbose=False, _cancell_flag=None, _stop_event=None):
    if _asic_num != len(_config):
        _logger.error("Number of ASICs does not match the number of configurations")
        return
    
    if _scan_chn_pack > 76 or _scan_chn_pack < 1:
        _logger.error("Invalid scan channel pack number")
        return
    
    val0_list_assembled     = np.zeros((76*_asic_num, _machine_gun+1), dtype=np.int16)
    val0_err_list_assembled = np.zeros((76*_asic_num, _machine_gun+1), dtype=np.int16)
    val1_list_assembled     = np.zeros((76*_asic_num, _machine_gun+1), dtype=np.int16)
    val1_err_list_assembled = np.zeros((76*_asic_num, _machine_gun+1), dtype=np.int16)
    val2_list_assembled     = np.zeros((76*_asic_num, _machine_gun+1), dtype=np.int16)
    val2_err_list_assembled = np.zeros((76*_asic_num, _machine_gun+1), dtype=np.int16)

    for _asic_index in range(_asic_num):
        # -- Set up reference voltage ---------------------------
        # -------------------------------------------------------
        _asic_config = _config[_asic_index]
        _ref_content_half_0 = _asic_config["ref_voltage_0"]
        _ref_content_half_1 = _asic_config["ref_voltage_1"]
        # _toa_global_threshold = _asic_config["toa_global_threshold"]
        # _tot_global_threshold = _asic_config["tot_global_threshold"]

        # _ref_content_half_0[7] = 0x40 | _dac >> 8
        # _ref_content_half_0[6] = _dac & 0xFF  
        # _ref_content_half_1[7] = 0x40 | _dac >> 8
        # _ref_content_half_1[6] = _dac & 0xFF

        _ref_content_half_0[7] = 0x00
        _ref_content_half_0[6] = 0x00
        _ref_content_half_1[7] = 0x00
        _ref_content_half_1[6] = 0x00

        _ref_content_half_0[10] = 0x80 | _dac >> 8
        _ref_content_half_0[9] = _dac & 0xFF
        _ref_content_half_1[10] = 0x80 | _dac >> 8
        _ref_content_half_1[9] = _dac & 0xFF

        # _ref_content_half_0[3] = _toa_global_threshold[0] >> 2
        # _ref_content_half_1[3] = _toa_global_threshold[1] >> 2
        # _ref_content_half_0[2] = _tot_global_threshold[0] >> 2
        # _ref_content_half_1[2] = _tot_global_threshold[1] >> 2

        # _ref_content_half_0[10]= 0x40
        # _ref_content_half_1[10]= 0x40

        # _ref_content_half_0[1] = (_ref_content_half_0[1] & 0x0F) | ((_toa_global_threshold[0] & 0x03) << 4) | ((_tot_global_threshold[0] & 0x03) << 6)
        # _ref_content_half_1[1] = (_ref_content_half_1[1] & 0x0F) | ((_toa_global_threshold[1] & 0x03) << 4) | ((_tot_global_threshold[1] & 0x03) << 6)

        if not packetlib.send_check_i2c_wrapper(_cmd_out_conn, _cmd_data_conn, _h2gcroc_ip, _h2gcroc_port, asic_num=_asic_index, fpga_addr = _fpga_address, sub_addr=packetlib.subblock_address_dict["Reference_Voltage_0"], reg_addr=0x00, data=_ref_content_half_0, retry=_retry, verbose=_verbose):
            logger.warning(f"Failed to set Reference_Voltage_0 settings for ASIC {_asic_index}")

        if not packetlib.send_check_i2c_wrapper(_cmd_out_conn, _cmd_data_conn, _h2gcroc_ip, _h2gcroc_port, asic_num=_asic_index, fpga_addr = _fpga_address, sub_addr=packetlib.subblock_address_dict["Reference_Voltage_1"], reg_addr=0x00, data=_ref_content_half_1, retry=_retry, verbose=_verbose):
            logger.warning(f"Failed to set Reference_Voltage_1 settings for ASIC {_asic_index}")
        # -------------------------------------------------------

    # -- Set up channel wise registers ----------------------
    # -------------------------------------------------------
    for _chn_pack_pos in range(_scan_chn_start, _scan_chn_start + _scan_chn_number, _scan_chn_pack):
        # check stop flag
        if _stop_event is not None and _stop_event.is_set():
            if _verbose:
                _logger.info("Stop event is set, exiting Inj_2V5")
            if _cancell_flag is not None:
                _cancell_flag = True
            return val0_list_assembled, val0_err_list_assembled, val1_list_assembled, val1_err_list_assembled, val2_list_assembled, val2_err_list_assembled
        _pack_channels = []
        _half_focus = []
        for _i in range(_scan_chn_pack):
            if _chn_pack_pos + _i < 76:
                _pack_channels.append(_chn_pack_pos + _i)
                _chn_half = (_chn_pack_pos + _i) // 38
                # if _chn_half not in _half_focus:
                #     _half_focus.append(_chn_half)
        # _logger.debug(f"Channel pack: {_pack_channels}")
        for _chn in _pack_channels:
            _sub_addr = packetlib.uni_chn_to_subblock_list[_chn]
            _reg_key  = UniChannelNum2RegKey(_i2c_dict, _sub_addr)
            for _asic_index in range(_asic_num):
                if _chn + 76*_asic_index in unused_chn_list or _chn + 76*_asic_index in _dead_chn_list:
                    continue
                _current_config = _config[_asic_index]
                _reg_str        = _current_config["config"]["Register Settings"][_reg_key]
                _reg_val        = [int(x, 16) for x in _reg_str.split()]
                _reg_val[4]     = _reg_val[4] & 0xFD | 0x04 # ! enable high range injection
                _reg_val[14]    = 0xC0
                # _reg_val[2]     = (_current_config["tot_chn_threshold"][_chn] & 0x3F) << 2
                # _reg_val[1]     = (_current_config["toa_chn_threshold"][_chn] & 0x3F) << 2
                if not packetlib.send_check_i2c_wrapper(_cmd_out_conn, _cmd_data_conn, _h2gcroc_ip, _h2gcroc_port, asic_num=_asic_index, fpga_addr = _fpga_address, sub_addr=_sub_addr, reg_addr=0x00, data=_reg_val, retry=_retry, verbose=_verbose):
                    logger.warning(f"Failed to set Channel Wise Register {_reg_key} for ASIC {_asic_index}")

        # time.sleep(0.1)

        v0_list, v0_err, v1_list, v1_err, v2_list, v2_err = measure_all(_cmd_out_conn, _data_data_conn, _h2gcroc_ip, _h2gcroc_port, _asic_num, _fpga_address, _machine_gun, _expected_event_number, _fragment_life, _logger, _retry, _focus_half=_half_focus)

        # _logger.info(f"12b DAC: {_dac}, channel pack: {_pack_channels}")
        # _logger.info(f"v0: {v0_list}")
        # _logger.info(f"v0_err: {v0_err}")
        # _logger.info(f"v1: {v1_list}")
        # _logger.info(f"v1_err: {v1_err}")
        # _logger.info(f"v2: {v2_list}")
        # _logger.info(f"v2_err: {v2_err}")

        # display_chn = 6
        # display_samples = []

        for _chn in _pack_channels:
            _sub_addr = packetlib.uni_chn_to_subblock_list[_chn]
            _reg_key  = UniChannelNum2RegKey(_i2c_dict, _sub_addr)
            for _asic_index in range(_asic_num):    # turn off the high range injection
                if _chn + 76*_asic_index in unused_chn_list or _chn + 76*_asic_index in _dead_chn_list:
                    continue
                _current_config = _config[_asic_index]
                _reg_str    = _current_config["config"]["Register Settings"][_reg_key]
                _reg_val    = [int(x, 16) for x in _reg_str.split()]
                _reg_val[4] = _reg_val[4] & 0xFD
                _reg_val[14]= 0xC0
                # _reg_val[2] = (_current_config["tot_chn_threshold"][_chn] & 0x3F) << 2
                # _reg_val[1] = (_current_config["toa_chn_threshold"][_chn] & 0x3F) << 2
                if not packetlib.send_check_i2c_wrapper(_cmd_out_conn, _cmd_data_conn, _h2gcroc_ip, _h2gcroc_port, asic_num=_asic_index, fpga_addr = _fpga_address, sub_addr=_sub_addr, reg_addr=0x00, data=_reg_val, retry=_retry, verbose=_verbose):
                    logger.warning(f"Failed to set Channel Wise Register {_reg_key} for ASIC {_asic_index}")

                _chn_v0_list = np.zeros(((_machine_gun+1), 76*_asic_num), dtype=np.int16)
                _chn_v1_list = np.zeros(((_machine_gun+1), 76*_asic_num), dtype=np.int16)
                _chn_v2_list = np.zeros(((_machine_gun+1), 76*_asic_num), dtype=np.int16)
                _chn_v0_err  = np.zeros(((_machine_gun+1), 76*_asic_num), dtype=np.int16)
                _chn_v1_err  = np.zeros(((_machine_gun+1), 76*_asic_num), dtype=np.int16)
                _chn_v2_err  = np.zeros(((_machine_gun+1), 76*_asic_num), dtype=np.int16)

                for _machine_gun_index in range(_machine_gun+1):
                    # _chn_v0_list.append(v0_list[_machine_gun_index][_chn + _asic_index*76])
                    # _chn_v0_err.append(v0_err[_machine_gun_index][_chn + _asic_index*76])
                    # _chn_v1_list.append(v1_list[_machine_gun_index][_chn + _asic_index*76])
                    # _chn_v1_err.append(v1_err[_machine_gun_index][_chn + _asic_index*76])
                    # _chn_v2_list.append(v2_list[_machine_gun_index][_chn + _asic_index*76])
                    # _chn_v2_err.append(v2_err[_machine_gun_index][_chn + _asic_index*76])

                    # if _chn + 76*_asic_index == display_chn:
                    #     display_samples.append(_chn_v0_list[-1])
                    _chn_v0_err[_machine_gun_index][_chn + _asic_index*76] = v0_err[_machine_gun_index][_chn + _asic_index*76]
                    _chn_v1_err[_machine_gun_index][_chn + _asic_index*76] = v1_err[_machine_gun_index][_chn + _asic_index*76]
                    _chn_v2_err[_machine_gun_index][_chn + _asic_index*76] = v2_err[_machine_gun_index][_chn + _asic_index*76]
                    _chn_v0_list[_machine_gun_index][_chn + _asic_index*76] = v0_list[_machine_gun_index][_chn + _asic_index*76]
                    _chn_v1_list[_machine_gun_index][_chn + _asic_index*76] = v1_list[_machine_gun_index][_chn + _asic_index*76]
                    _chn_v2_list[_machine_gun_index][_chn + _asic_index*76] = v2_list[_machine_gun_index][_chn + _asic_index*76]


                # transpose the list
                #  print(f'index: {_chn + _asic_index*76}')
                for _machine_gun_index in range(_machine_gun+1):
                    val0_list_assembled[_chn + _asic_index*76][_machine_gun_index] = _chn_v0_list[_machine_gun_index][_chn + _asic_index*76]
                    val0_err_list_assembled[_chn + _asic_index*76][_machine_gun_index] = _chn_v0_err[_machine_gun_index][_chn + _asic_index*76]
                    val1_list_assembled[_chn + _asic_index*76][_machine_gun_index] = _chn_v1_list[_machine_gun_index][_chn + _asic_index*76]
                    val1_err_list_assembled[_chn + _asic_index*76][_machine_gun_index] = _chn_v1_err[_machine_gun_index][_chn + _asic_index*76]
                    val2_list_assembled[_chn + _asic_index*76][_machine_gun_index] = _chn_v2_list[_machine_gun_index][_chn + _asic_index*76]
                    val2_err_list_assembled[_chn + _asic_index*76][_machine_gun_index] = _chn_v2_err[_machine_gun_index][_chn + _asic_index*76]

    return val0_list_assembled, val0_err_list_assembled, val1_list_assembled, val1_err_list_assembled, val2_list_assembled, val2_err_list_assembled

def Inj_Normal(_cmd_out_conn, _cmd_data_conn, _data_data_conn, _h2gcroc_ip, _h2gcroc_port, _fpga_address, _phase, _dac, _scan_chn_start, _scan_chn_number, _asic_num, _scan_chn_pack, _machine_gun, _expected_event_number, _fragment_life, _config, unused_chn_list, _dead_chn_list, _i2c_dict, _logger, _retry=1, _verbose=False, _range_mode="Low Range", _cancell_flag=None, _stop_event=None):
    if _asic_num != len(_config):
        _logger.error("Number of ASICs does not match the number of configurations")
        return
    
    if _scan_chn_pack > 76 or _scan_chn_pack < 1:
        _logger.error("Invalid scan channel pack number")
        return
    
    val0_list_assembled     = np.zeros((76*_asic_num, _machine_gun+1), dtype=np.int16)
    val0_err_list_assembled = np.zeros((76*_asic_num, _machine_gun+1), dtype=np.int16)
    val1_list_assembled     = np.zeros((76*_asic_num, _machine_gun+1), dtype=np.int16)
    val1_err_list_assembled = np.zeros((76*_asic_num, _machine_gun+1), dtype=np.int16)
    val2_list_assembled     = np.zeros((76*_asic_num, _machine_gun+1), dtype=np.int16)
    val2_err_list_assembled = np.zeros((76*_asic_num, _machine_gun+1), dtype=np.int16)

    for _asic_index in range(_asic_num):
        # -- Set up reference voltage ---------------------------
        # -------------------------------------------------------
        _asic_config = _config[_asic_index]
        _ref_content_half_0 = _asic_config["ref_voltage_0"]
        _ref_content_half_1 = _asic_config["ref_voltage_1"]
        # _toa_global_threshold = _asic_config["toa_global_threshold"]
        # _tot_global_threshold = _asic_config["tot_global_threshold"]

        _ref_content_half_0[7] = 0x40 | _dac >> 8
        _ref_content_half_0[6] = _dac & 0xFF  
        _ref_content_half_1[7] = 0x40 | _dac >> 8
        _ref_content_half_1[6] = _dac & 0xFF

        # _ref_content_half_0[7] = 0x00
        # _ref_content_half_0[6] = 0x00
        # _ref_content_half_1[7] = 0x00
        # _ref_content_half_1[6] = 0x00

        # _ref_content_half_0[10] = 0xC0 | _dac >> 8
        # _ref_content_half_0[9] = _dac & 0xFF
        # _ref_content_half_1[10] = 0xC0 | _dac >> 8
        # _ref_content_half_1[9] = _dac & 0xFF

        # _ref_content_half_0[3] = _toa_global_threshold[0] >> 2
        # _ref_content_half_1[3] = _toa_global_threshold[1] >> 2
        # _ref_content_half_0[2] = _tot_global_threshold[0] >> 2
        # _ref_content_half_1[2] = _tot_global_threshold[1] >> 2

        _ref_content_half_0[10]= 0x40
        _ref_content_half_1[10]= 0x40

        # _ref_content_half_0[1] = (_ref_content_half_0[1] & 0x0F) | ((_toa_global_threshold[0] & 0x03) << 4) | ((_tot_global_threshold[0] & 0x03) << 6)
        # _ref_content_half_1[1] = (_ref_content_half_1[1] & 0x0F) | ((_toa_global_threshold[1] & 0x03) << 4) | ((_tot_global_threshold[1] & 0x03) << 6)

        if not packetlib.send_check_i2c_wrapper(_cmd_out_conn, _cmd_data_conn, _h2gcroc_ip, _h2gcroc_port, asic_num=_asic_index, fpga_addr = _fpga_address, sub_addr=packetlib.subblock_address_dict["Reference_Voltage_0"], reg_addr=0x00, data=_ref_content_half_0, retry=_retry, verbose=_verbose):
            logger.warning(f"Failed to set Reference_Voltage_0 settings for ASIC {_asic_index}")

        if not packetlib.send_check_i2c_wrapper(_cmd_out_conn, _cmd_data_conn, _h2gcroc_ip, _h2gcroc_port, asic_num=_asic_index, fpga_addr = _fpga_address, sub_addr=packetlib.subblock_address_dict["Reference_Voltage_1"], reg_addr=0x00, data=_ref_content_half_1, retry=_retry, verbose=_verbose):
            logger.warning(f"Failed to set Reference_Voltage_1 settings for ASIC {_asic_index}")
        # -------------------------------------------------------

    # -- Set up channel wise registers ----------------------
    # -------------------------------------------------------
    for _chn_pack_pos in range(_scan_chn_start, _scan_chn_start + _scan_chn_number, _scan_chn_pack):
        if _stop_event is not None and _stop_event.is_set():
            if _verbose:
                _logger.info("Stop event is set, exiting Inj_2V5")
            if _cancell_flag is not None:
                _cancell_flag = True
            return val0_list_assembled, val0_err_list_assembled, val1_list_assembled, val1_err_list_assembled, val2_list_assembled, val2_err_list_assembled
        _pack_channels = []
        _half_focus = []
        for _i in range(_scan_chn_pack):
            if _chn_pack_pos + _i < 76:
                _pack_channels.append(_chn_pack_pos + _i)
                _chn_half = (_chn_pack_pos + _i) // 38
                # if _chn_half not in _half_focus:
                #     _half_focus.append(_chn_half)
        # _logger.debug(f"Channel pack: {_pack_channels}")
        for _chn in _pack_channels:
            _sub_addr = packetlib.uni_chn_to_subblock_list[_chn]
            _reg_key  = UniChannelNum2RegKey(_i2c_dict, _sub_addr)
            for _asic_index in range(_asic_num):
                if _chn + 76*_asic_index in unused_chn_list or _chn + 76*_asic_index in _dead_chn_list:
                    continue
                _current_config = _config[_asic_index]
                _reg_str        = _current_config["config"]["Register Settings"][_reg_key]
                _reg_val        = [int(x, 16) for x in _reg_str.split()]
                if _range_mode == "High Range":
                    _reg_val[4]     = _reg_val[4] & 0xF9 | 0x04 # ! enable high range injection
                    logger.debug(f"Channel {_chn} set to High Range injection")
                elif _range_mode == "Low Range":
                    _reg_val[4]     = _reg_val[4] & 0xF9 | 0x02
                    logger.debug(f"Channel {_chn} set to Low Range injection")
                else:
                    _logger.error("Invalid range mode, should be 'High Range' or 'Low Range'")
                _reg_val[14]    = 0xC0
                # _reg_val[2]     = (_current_config["tot_chn_threshold"][_chn] & 0x3F) << 2
                # _reg_val[1]     = (_current_config["toa_chn_threshold"][_chn] & 0x3F) << 2
                if not packetlib.send_check_i2c_wrapper(_cmd_out_conn, _cmd_data_conn, _h2gcroc_ip, _h2gcroc_port, asic_num=_asic_index, fpga_addr = _fpga_address, sub_addr=_sub_addr, reg_addr=0x00, data=_reg_val, retry=_retry, verbose=_verbose):
                    logger.warning(f"Failed to set Channel Wise Register {_reg_key} for ASIC {_asic_index}")

        # time.sleep(0.1)

        v0_list, v0_err, v1_list, v1_err, v2_list, v2_err = measure_all(_cmd_out_conn, _data_data_conn, _h2gcroc_ip, _h2gcroc_port, _asic_num, _fpga_address, _machine_gun, _expected_event_number, _fragment_life, _logger, _retry, _focus_half=_half_focus)

        # _logger.info(f"12b DAC: {_dac}, channel pack: {_pack_channels}")
        # _logger.info(f"v0: {v0_list}")
        # _logger.info(f"v0_err: {v0_err}")
        # _logger.info(f"v1: {v1_list}")
        # _logger.info(f"v1_err: {v1_err}")
        # _logger.info(f"v2: {v2_list}")
        # _logger.info(f"v2_err: {v2_err}")

        # display_chn = 6
        # display_samples = []

        for _chn in _pack_channels:
            _sub_addr = packetlib.uni_chn_to_subblock_list[_chn]
            _reg_key  = UniChannelNum2RegKey(_i2c_dict, _sub_addr)
            for _asic_index in range(_asic_num):    # turn off the high range injection
                if _chn + 76*_asic_index in unused_chn_list or _chn + 76*_asic_index in _dead_chn_list:
                    continue
                _current_config = _config[_asic_index]
                _reg_str    = _current_config["config"]["Register Settings"][_reg_key]
                _reg_val    = [int(x, 16) for x in _reg_str.split()]
                _reg_val[4] = _reg_val[4] & 0xF9
                _reg_val[14]= 0xC0
                # _reg_val[2] = (_current_config["tot_chn_threshold"][_chn] & 0x3F) << 2
                # _reg_val[1] = (_current_config["toa_chn_threshold"][_chn] & 0x3F) << 2
                if not packetlib.send_check_i2c_wrapper(_cmd_out_conn, _cmd_data_conn, _h2gcroc_ip, _h2gcroc_port, asic_num=_asic_index, fpga_addr = _fpga_address, sub_addr=_sub_addr, reg_addr=0x00, data=_reg_val, retry=_retry, verbose=_verbose):
                    logger.warning(f"Failed to set Channel Wise Register {_reg_key} for ASIC {_asic_index}")

                _chn_v0_list = np.zeros(((_machine_gun+1), 76*_asic_num), dtype=np.int16)
                _chn_v1_list = np.zeros(((_machine_gun+1), 76*_asic_num), dtype=np.int16)
                _chn_v2_list = np.zeros(((_machine_gun+1), 76*_asic_num), dtype=np.int16)
                _chn_v0_err  = np.zeros(((_machine_gun+1), 76*_asic_num), dtype=np.int16)
                _chn_v1_err  = np.zeros(((_machine_gun+1), 76*_asic_num), dtype=np.int16)
                _chn_v2_err  = np.zeros(((_machine_gun+1), 76*_asic_num), dtype=np.int16)

                for _machine_gun_index in range(_machine_gun+1):
                    # _chn_v0_list.append(v0_list[_machine_gun_index][_chn + _asic_index*76])
                    # _chn_v0_err.append(v0_err[_machine_gun_index][_chn + _asic_index*76])
                    # _chn_v1_list.append(v1_list[_machine_gun_index][_chn + _asic_index*76])
                    # _chn_v1_err.append(v1_err[_machine_gun_index][_chn + _asic_index*76])
                    # _chn_v2_list.append(v2_list[_machine_gun_index][_chn + _asic_index*76])
                    # _chn_v2_err.append(v2_err[_machine_gun_index][_chn + _asic_index*76])

                    # if _chn + 76*_asic_index == display_chn:
                    #     display_samples.append(_chn_v0_list[-1])
                    _chn_v0_err[_machine_gun_index][_chn + _asic_index*76] = v0_err[_machine_gun_index][_chn + _asic_index*76]
                    _chn_v1_err[_machine_gun_index][_chn + _asic_index*76] = v1_err[_machine_gun_index][_chn + _asic_index*76]
                    _chn_v2_err[_machine_gun_index][_chn + _asic_index*76] = v2_err[_machine_gun_index][_chn + _asic_index*76]
                    _chn_v0_list[_machine_gun_index][_chn + _asic_index*76] = v0_list[_machine_gun_index][_chn + _asic_index*76]
                    _chn_v1_list[_machine_gun_index][_chn + _asic_index*76] = v1_list[_machine_gun_index][_chn + _asic_index*76]
                    _chn_v2_list[_machine_gun_index][_chn + _asic_index*76] = v2_list[_machine_gun_index][_chn + _asic_index*76]


                # transpose the list
                #  print(f'index: {_chn + _asic_index*76}')
                for _machine_gun_index in range(_machine_gun+1):
                    val0_list_assembled[_chn + _asic_index*76][_machine_gun_index] = _chn_v0_list[_machine_gun_index][_chn + _asic_index*76]
                    val0_err_list_assembled[_chn + _asic_index*76][_machine_gun_index] = _chn_v0_err[_machine_gun_index][_chn + _asic_index*76]
                    val1_list_assembled[_chn + _asic_index*76][_machine_gun_index] = _chn_v1_list[_machine_gun_index][_chn + _asic_index*76]
                    val1_err_list_assembled[_chn + _asic_index*76][_machine_gun_index] = _chn_v1_err[_machine_gun_index][_chn + _asic_index*76]
                    val2_list_assembled[_chn + _asic_index*76][_machine_gun_index] = _chn_v2_list[_machine_gun_index][_chn + _asic_index*76]
                    val2_err_list_assembled[_chn + _asic_index*76][_machine_gun_index] = _chn_v2_err[_machine_gun_index][_chn + _asic_index*76]

    return val0_list_assembled, val0_err_list_assembled, val1_list_assembled, val1_err_list_assembled, val2_list_assembled, val2_err_list_assembled

def Scan_12b(_cmd_out_conn, _cmd_data_conn, _data_data_conn, _h2gcroc_ip, _h2gcroc_port, _fpga_address, _progress_bar, _asic_num, _scan_chn_pack, _machine_gun, _expected_event_number, _fragment_life, _config, unused_chn_list, _dead_chn_list, _i2c_dict, _logger, _retry, _toa_setting=True, _verbose=False):
    if _asic_num != len(_config):
        _logger.error("Number of ASICs does not match the number of configurations")
        return
    
    if _scan_chn_pack > 76 or _scan_chn_pack < 1:
        _logger.error("Invalid scan channel pack number")
        return
    
    _used_scan_values = []

    _scan_val0_list     = []
    _scan_val0_err_list = []
    _scan_val1_list     = []
    _scan_val1_err_list = []
    _scan_val2_list     = []
    _scan_val2_err_list = []

    for _12b_dac_value in _progress_bar:
        # _progress_bar.set_description(f"12b DAC: {_12b_dac_value}")
        # _logger.debug(f"12b DAC: {_12b_dac_value}")
        _used_scan_values.append(_12b_dac_value)

        val0_list_assembled     = np.zeros(76*_asic_num, dtype=np.int16)
        val0_err_list_assembled = np.zeros(76*_asic_num, dtype=np.int16)
        val1_list_assembled     = np.zeros(76*_asic_num, dtype=np.int16)
        val1_err_list_assembled = np.zeros(76*_asic_num, dtype=np.int16)
        val2_list_assembled     = np.zeros(76*_asic_num, dtype=np.int16)
        val2_err_list_assembled = np.zeros(76*_asic_num, dtype=np.int16)

        for _asic_index in range(_asic_num):
            # -- Set up reference voltage ---------------------------
            # -------------------------------------------------------
            _asic_config = _config[_asic_index]
            _ref_content_half_0 = _asic_config["ref_voltage_0"]
            _ref_content_half_1 = _asic_config["ref_voltage_1"]
            _toa_global_threshold = _asic_config["toa_global_threshold"]
            _tot_global_threshold = _asic_config["tot_global_threshold"]

            _ref_content_half_0[7] = 0x40 | _12b_dac_value >> 8
            _ref_content_half_0[6] = _12b_dac_value & 0xFF  
            _ref_content_half_1[7] = 0x40 | _12b_dac_value >> 8
            _ref_content_half_1[6] = _12b_dac_value & 0xFF

            if _toa_setting:
                _ref_content_half_0[3] = _toa_global_threshold[0] >> 2
                _ref_content_half_1[3] = _toa_global_threshold[1] >> 2
            _ref_content_half_0[2] = _tot_global_threshold[0] >> 2
            _ref_content_half_1[2] = _tot_global_threshold[1] >> 2

            _ref_content_half_0[10]= 0x40
            _ref_content_half_1[10]= 0x40

            if _toa_setting:
                _ref_content_half_0[1] = (_ref_content_half_0[1] & 0x0F) | ((_toa_global_threshold[0] & 0x03) << 4) | ((_tot_global_threshold[0] & 0x03) << 6)
                _ref_content_half_1[1] = (_ref_content_half_1[1] & 0x0F) | ((_toa_global_threshold[1] & 0x03) << 4) | ((_tot_global_threshold[1] & 0x03) << 6)
            else:
                _ref_content_half_0[1] = (_ref_content_half_0[1] & 0x3F) | ((_tot_global_threshold[0] & 0x03) << 6)
                _ref_content_half_1[1] = (_ref_content_half_1[1] & 0x3F) | ((_tot_global_threshold[1] & 0x03) << 6)

            if not packetlib.send_check_i2c_wrapper(_cmd_out_conn, _cmd_data_conn, _h2gcroc_ip, _h2gcroc_port, asic_num=_asic_index, fpga_addr = _fpga_address, sub_addr=packetlib.subblock_address_dict["Reference_Voltage_0"], reg_addr=0x00, data=_ref_content_half_0, retry=_retry, verbose=_verbose):
                logger.warning(f"Failed to set Reference_Voltage_0 settings for ASIC {_asic_index}")

            if not packetlib.send_check_i2c_wrapper(_cmd_out_conn, _cmd_data_conn, _h2gcroc_ip, _h2gcroc_port, asic_num=_asic_index, fpga_addr = _fpga_address, sub_addr=packetlib.subblock_address_dict["Reference_Voltage_1"], reg_addr=0x00, data=_ref_content_half_1, retry=_retry, verbose=_verbose):
                logger.warning(f"Failed to set Reference_Voltage_1 settings for ASIC {_asic_index}")
            # -------------------------------------------------------

        # -- Set up channel wise registers ----------------------
        # -------------------------------------------------------
        for _chn_pack_pos in range(0, 76, _scan_chn_pack):
            _pack_channels = []
            _half_focus = []
            for _i in range(_scan_chn_pack):
                if _chn_pack_pos + _i < 76:
                    _pack_channels.append(_chn_pack_pos + _i)
                    _chn_half = (_chn_pack_pos + _i) // 38
                    # if _chn_half not in _half_focus:
                    #     _half_focus.append(_chn_half)
            # _logger.debug(f"Channel pack: {_pack_channels}")
            for _chn in _pack_channels:
                _sub_addr = packetlib.uni_chn_to_subblock_list[_chn]
                _reg_key  = UniChannelNum2RegKey(_i2c_dict, _sub_addr)
                for _asic_index in range(_asic_num):
                    if _chn + 76*_asic_index in unused_chn_list or _chn + 76*_asic_index in _dead_chn_list:
                        continue
                    _current_config = _config[_asic_index]
                    _reg_str        = _current_config["config"]["Register Settings"][_reg_key]
                    _reg_val        = [int(x, 16) for x in _reg_str.split()]
                    _reg_val[4]     = _reg_val[4] & 0xFD | 0x04 # ! enable high range injection
                    _reg_val[14]    = 0xC0
                    _reg_val[2]     = (_current_config["tot_chn_threshold"][_chn] & 0x3F) << 2
                    if _toa_setting:
                        _reg_val[1]     = (_current_config["toa_chn_threshold"][_chn] & 0x3F) << 2
                    if not packetlib.send_check_i2c_wrapper(_cmd_out_conn, _cmd_data_conn, _h2gcroc_ip, _h2gcroc_port, asic_num=_asic_index, fpga_addr = _fpga_address, sub_addr=_sub_addr, reg_addr=0x00, data=_reg_val, retry=_retry, verbose=_verbose):
                        logger.warning(f"Failed to set Channel Wise Register {_reg_key} for ASIC {_asic_index}")

            # time.sleep(0.1)

            v0_list, v0_err, v1_list, v1_err, v2_list, v2_err = measure_all(_cmd_out_conn, _data_data_conn, _h2gcroc_ip, _h2gcroc_port, _asic_num, _fpga_address, _machine_gun, _expected_event_number, _fragment_life, _logger, _retry, _focus_half=_half_focus)

            # _logger.info(f"12b DAC: {_12b_dac_value}, channel pack: {_pack_channels}")
            # _logger.info(f"v0: {v0_list}")
            # _logger.info(f"v0_err: {v0_err}")
            # _logger.info(f"v1: {v1_list}")
            # _logger.info(f"v1_err: {v1_err}")
            # _logger.info(f"v2: {v2_list}")
            # _logger.info(f"v2_err: {v2_err}")

            # display_chn = 6
            # display_samples = []

            for _chn in _pack_channels:
                _sub_addr = packetlib.uni_chn_to_subblock_list[_chn]
                _reg_key  = UniChannelNum2RegKey(_i2c_dict, _sub_addr)
                for _asic_index in range(_asic_num):    # turn off the high range injection
                    if _chn + 76*_asic_index in unused_chn_list or _chn + 76*_asic_index in _dead_chn_list:
                        continue
                    _current_config = _config[_asic_index]
                    _reg_str    = _current_config["config"]["Register Settings"][_reg_key]
                    _reg_val    = [int(x, 16) for x in _reg_str.split()]
                    _reg_val[4] = _reg_val[4] & 0xFD
                    _reg_val[14]= 0xC0
                    _reg_val[2] = (_current_config["tot_chn_threshold"][_chn] & 0x3F) << 2
                    if _toa_setting:
                        _reg_val[1] = (_current_config["toa_chn_threshold"][_chn] & 0x3F) << 2
                    if not packetlib.send_check_i2c_wrapper(_cmd_out_conn, _cmd_data_conn, _h2gcroc_ip, _h2gcroc_port, asic_num=_asic_index, fpga_addr = _fpga_address, sub_addr=_sub_addr, reg_addr=0x00, data=_reg_val, retry=_retry, verbose=_verbose):
                        logger.warning(f"Failed to set Channel Wise Register {_reg_key} for ASIC {_asic_index}")

                    _chn_v0_list = []
                    _chn_v1_list = []
                    _chn_v2_list = []
                    _chn_v0_err  = []
                    _chn_v1_err  = []
                    _chn_v2_err  = []

                    for _machine_gun_index in range(_machine_gun+1):
                        _chn_v0_list.append(v0_list[_machine_gun_index][_chn + _asic_index*76])
                        _chn_v0_err.append(v0_err[_machine_gun_index][_chn + _asic_index*76])
                        _chn_v1_list.append(v1_list[_machine_gun_index][_chn + _asic_index*76])
                        _chn_v1_err.append(v1_err[_machine_gun_index][_chn + _asic_index*76])
                        _chn_v2_list.append(v2_list[_machine_gun_index][_chn + _asic_index*76])
                        _chn_v2_err.append(v2_err[_machine_gun_index][_chn + _asic_index*76])

                        # if _chn + 76*_asic_index == display_chn:
                        #     display_samples.append(_chn_v0_list[-1])

                    # transpose the list
                    #  print(f'index: {_chn + _asic_index*76}')
                    val0_list_assembled[_chn + _asic_index*76]     = np.max(_chn_v0_list)
                    val0_err_list_assembled[_chn + _asic_index*76] = _chn_v0_err[np.argmax(_chn_v0_list)]
                    val1_list_assembled[_chn + _asic_index*76]     = np.max(_chn_v1_list)
                    val1_err_list_assembled[_chn + _asic_index*76] = _chn_v1_err[np.argmax(_chn_v1_list)]
                    val2_list_assembled[_chn + _asic_index*76]     = np.max(_chn_v2_list)
                    val2_err_list_assembled[_chn + _asic_index*76] = _chn_v2_err[np.argmax(_chn_v2_list)]
            
            # if display_chn in _pack_channels:
            #     _logger.debug(f"12b DAC: {_12b_dac_value}, channel samples: {display_samples}")
            # -------------------------------------------------------

        _scan_val0_list.append(val0_list_assembled)
        _scan_val0_err_list.append(val0_err_list_assembled)
        _scan_val1_list.append(val1_list_assembled)
        _scan_val1_err_list.append(val1_err_list_assembled)
        _scan_val2_list.append(val2_list_assembled)
        _scan_val2_err_list.append(val2_err_list_assembled)

    return _used_scan_values, _scan_val0_list, _scan_val0_err_list, _scan_val1_list, _scan_val1_err_list, _scan_val2_list, _scan_val2_err_list
# * -------------------------------------------------------------------------------------

def Draw2DIM(_title, _x_label, _y_label, _total_asic, _data, _saving_path, _y_ticks=None, _turn_on_points=None, _data_saving_path=None):
    if _data_saving_path is not None:
        pd.DataFrame(_data).to_csv(_data_saving_path, index=False, header=False)

    fig, ax = plt.subplots(figsize=(10, 6))
    cax = ax.imshow(_data, aspect='auto', cmap='viridis', interpolation='nearest')
    fig.colorbar(cax, ax=ax)

    ax.set_xlabel(_x_label)
    ax.set_ylabel(_y_label)
    ax.set_xticks(np.arange(0, 2*_total_asic, step=19))

    if _y_ticks is not None:
        ax.set_yticks(np.arange(0, len(_data), step=len(_data)//len(_y_ticks)))
        ax.set_yticklabels(_y_ticks)
    else:
        ax.set_yticks(np.arange(0, len(_data), step=len(_data)//10))

    if _turn_on_points is not None:
        for _index, _point in enumerate(_turn_on_points):
            if _point == -1:
                continue
            if _y_ticks is not None:
                _y_ticks_int = [int(_y_tick) for _y_tick in _y_ticks]
                y_min = min(_y_ticks_int)
                y_max = max(_y_ticks_int)
                _point_scaled = (_point - y_min) / (y_max - y_min) * (len(_data) - 1)
            else:
                _point_scaled = _point

            ax.plot([_index - 0.5, _index + 0.5], [_point_scaled, _point_scaled], 'r')

    ax.text(0.02, 0.96, _title, transform=ax.transAxes, fontsize=18,
            verticalalignment='top', weight='bold', color='white')

    return fig, ax