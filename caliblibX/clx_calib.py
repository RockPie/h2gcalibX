import packetlibX
import time, os, sys, socket, json, csv, uuid
import numpy as np
import pandas as pd
from matplotlib import pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from collections import deque
from collections import OrderedDict
from .clx_udp import udp_target
from .clx_data import single_channel_index_remove_cm_calib
import copy

color_list = ['#FF0000', '#0000FF', '#FFFF00', '#00FF00','#FF00FF', '#00FFFF', '#FFA500', '#800080', '#008080', '#FFC0CB']

def print_err(msg):
    print(f"[clx_calib] ERROR: {msg}", file=sys.stderr)
def print_info(msg):
    print(f"[clx_calib] INFO: {msg}", file=sys.stdout)
def print_warn(msg):
    print(f"[clx_calib] WARNING: {msg}", file=sys.stdout)

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

def measure_all(_udp_target, _total_asic_num, _machine_gun, _total_event, _fragment_life, _retry=1, _verbose=False, _focus_half=[]):
    _cmd_socket  = _udp_target.cmd_outbound_conn
    _data_socket = _udp_target.data_data_conn
    _h2gcroc_ip  = _udp_target.board_ip
    _h2gcroc_port= _udp_target.board_port
    _fpga_addr   = _udp_target.board_id

    _retry_left = _retry
    _all_events_received = False

    n_channels = _total_asic_num * 76
    n_halves   = _total_asic_num * 2
    chunks_per_event = n_halves

    BC_PER_SHOT = 164  # bunch crossings per machine-gun shot

    adc_mean_list = np.zeros((_machine_gun + 1, n_channels))
    adc_err_list  = np.zeros((_machine_gun + 1, n_channels))
    tot_mean_list = np.zeros((_machine_gun + 1, n_channels))
    tot_err_list  = np.zeros((_machine_gun + 1, n_channels))
    toa_mean_list = np.zeros((_machine_gun + 1, n_channels))
    toa_err_list  = np.zeros((_machine_gun + 1, n_channels))
    
    while _retry_left > 0 and not _all_events_received:
        if _retry_left < _retry:
            if _verbose:
                print_info(f"Retrying measurement, attempts left: {_retry_left}")
            time.sleep(0.1)
        _retry_left -= 1

        try:
            extracted_payloads_pool = deque()
            event_fragment_pool     = []

            timestamps_events = []

            current_half_packet_num = 0
            current_event_num       = 0
            counter_daqh_incorrect  = 0

            all_chn_value_0_array = np.zeros((_total_event, n_channels))
            all_chn_value_1_array = np.zeros((_total_event, n_channels))
            all_chn_value_2_array = np.zeros((_total_event, n_channels))
            hamming_code_array    = np.zeros((_total_event, 3 * n_halves), dtype=np.uint8)
            daqh_good_array       = np.ones((_total_event,   n_halves), dtype=bool)

            if not packetlibX.send_daq_gen_start_stop(
                _cmd_socket, _h2gcroc_ip, _h2gcroc_port,
                fpga_addr=_fpga_addr, daq_push=0x00,
                gen_start_stop=0, daq_start_stop=0xFF, verbose=False
            ):
                print_warn("Failed to start the generator")
            if not packetlibX.send_daq_gen_start_stop(
                _cmd_socket, _h2gcroc_ip, _h2gcroc_port,
                fpga_addr=_fpga_addr, daq_push=0x00,
                gen_start_stop=1, daq_start_stop=0xFF, verbose=False
            ):
                print_warn("Failed to start the generator")

            if True:
                try:
                    bytes_counter = 0
                    try:
                        for _ in range(100):
                            data_packet, _ = _data_socket.recvfrom(1358)
                            extracted_payloads_pool.extend(
                                packetlibX.extract_raw_data(data_packet)
                            )
                            bytes_counter += len(data_packet)

                    except socket.timeout:
                        if _verbose:
                            print_warn("Socket timeout, no data received")

                        if not packetlibX.send_daq_gen_start_stop(
                            _cmd_socket, _h2gcroc_ip, _h2gcroc_port,
                            fpga_addr=_fpga_addr, daq_push=0x00,
                            gen_start_stop=0, daq_start_stop=0x00, verbose=False
                        ):
                            print_warn("Failed to stop the generator")

                        for _ in range(10):
                            try:
                                data_packet, _ = _data_socket.recvfrom(1358)
                                extracted_payloads_pool.extend(
                                    packetlibX.extract_raw_data(data_packet)
                                )
                                bytes_counter += len(data_packet)
                                if len(data_packet) > 0:
                                    break
                            except socket.timeout:
                                if _verbose:
                                    print_warn("Socket timeout, no data received")

                    num_packets = bytes_counter // 1358
                    half_packet_number = (bytes_counter - num_packets * 14) // 192
                    event_number = half_packet_number // (2 * _total_asic_num)

                    half_packet_number = int(half_packet_number)
                    event_number = int(event_number)

                    chunk_counter = 0
                    event_chunk_buffer = []

                    while len(extracted_payloads_pool) > 0:
                        payload_192 = extracted_payloads_pool.popleft()
                        chunk_counter += 1

                        extracted_data = packetlibX.extract_values_192(
                            payload_192, verbose=False
                        )
                        if extracted_data is None:
                            print_warn(f"Failed to extract chunk #{chunk_counter}")
                            continue

                        event_chunk_buffer.append(extracted_data)

                        if len(event_chunk_buffer) == chunks_per_event:
                            timestamps = [c["_timestamp"] for c in event_chunk_buffer]
                            
                            if len(set(timestamps)) == 1:
                                for _half, chunk in enumerate(event_chunk_buffer):
                                    _DaqH = chunk["_DaqH"]
                                    extracted_values = chunk["_extracted_values"]
                                    byte3 = chunk["_address_id"]
                                    byte4 = chunk["_packet_id"]
                                    asic_id = byte3 & 0x0F
                                    packet_id = byte4

                                    uni_chn_base = asic_id * 76 + (packet_id - 0x24) * 38     

                                    for j, vals in enumerate(extracted_values):
                                        channel_id = uni_chn_base + j
                                        all_chn_value_0_array[current_event_num, channel_id] = vals[1]
                                        all_chn_value_1_array[current_event_num, channel_id] = vals[2]
                                        all_chn_value_2_array[current_event_num, channel_id] = vals[3]

                                    hamming_code_array[current_event_num, _half*3 + 0] = packetlibX.DaqH_get_H1(_DaqH)
                                    hamming_code_array[current_event_num, _half*3 + 1] = packetlibX.DaqH_get_H2(_DaqH)
                                    hamming_code_array[current_event_num, _half*3 + 2] = packetlibX.DaqH_get_H3(_DaqH)
                                    daqh_good_array[current_event_num, _half] = packetlibX.DaqH_start_end_good(_DaqH)

                                if np.all(hamming_code_array[current_event_num] == 0) and np.all(daqh_good_array[current_event_num]):
                                    timestamps_events.append(timestamps[0])
                                    current_event_num += 1
                                else:
                                    print_warn("Invalid event detected (hamming or DAQH error)")
                            else:
                                print_warn(f"Chunk timestamps mismatch: {timestamps}")

                            event_chunk_buffer.clear()

                        if current_event_num >= _total_event:
                            _all_events_received = True
                            break

                except Exception as e:
                    if _verbose:
                        print_warn("Exception in receiving data")
                        print_warn(e)
                        print_warn('Halves received: ' + str(current_half_packet_num))
                        print_warn('Halves expected: ' + str(_total_event * 2 * _total_asic_num))
                        print_warn('left fragments:' + str(len(event_fragment_pool)))
                        print_warn("current event num:" + str(current_event_num))
                    _all_events_received = False
                    break
                
            for _event in range(current_event_num):
                if not np.all(daqh_good_array[_event] == True):
                    counter_daqh_incorrect += 1

            valid_events = current_event_num - counter_daqh_incorrect
            min_valid_needed = max(_total_event // 2, 1)
            if valid_events < min_valid_needed:
                if _verbose:
                    print_warn(
                        f"Not enough valid events received "
                        f"(valid={valid_events}, total={current_event_num}, expected={_total_event})"
                    )
                _all_events_received = False
                continue
            
            if current_event_num == 0 or len(timestamps_events) == 0:
                if _verbose:
                    print_warn("No valid events with timestamps")
                _all_events_received = False
                continue

            timestamps_events_arr = np.array(timestamps_events[:current_event_num], dtype=np.int64)
            timestamps_pure = timestamps_events_arr - timestamps_events_arr[0]

            if timestamps_pure[-1] != BC_PER_SHOT * _machine_gun:
                if _verbose:
                    print_warn(
                        f"Machine gun coverage not enough: "
                        f"last_delta={timestamps_pure[-1]} expected={BC_PER_SHOT * _machine_gun}"
                    )
                _all_events_received = False
                continue

            # ---------- vectorized statistics over events x channels ----------

            # select only the rows actually filled
            all_chn_value_0_valid = all_chn_value_0_array[:current_event_num, :]
            all_chn_value_1_valid = all_chn_value_1_array[:current_event_num, :]
            all_chn_value_2_valid = all_chn_value_2_array[:current_event_num, :]

            # event-good mask (global or focus-only)
            if len(_focus_half) == 0:
                event_good = (hamming_code_array[:current_event_num] == 0).all(axis=1) & \
                             daqh_good_array[:current_event_num].all(axis=1)
            else:
                focus_halves = np.array(_focus_half, dtype=int)
                hc_reshaped = hamming_code_array[:current_event_num].reshape(current_event_num, n_halves, 3)
                hc_focus = hc_reshaped[:, focus_halves, :]          # shape: (events, n_focus, 3)
                daqh_focus = daqh_good_array[:current_event_num, :][:, focus_halves]  # (events, n_focus)

                cond_hc = (hc_focus == 0).all(axis=(1, 2))
                cond_daqh = daqh_focus.all(axis=1)
                event_good = cond_hc & cond_daqh

            mg_index = timestamps_pure // BC_PER_SHOT
            mg_index = mg_index.astype(int)
            mg_index[mg_index < 0] = -1  # safety

            valid_mg = (mg_index >= 0) & (mg_index <= _machine_gun)

            # combined mask per-event that will be used for grouping
            base_mask = event_good & valid_mg

            # precompute per-bin statistics
            event_short = 0  # kept for interface compatibility

            for mg in range(_machine_gun + 1):
                mask_mg = (mg_index == mg) & base_mask
                n_e = int(mask_mg.sum())
                if n_e > 0:
                    vals_adc = all_chn_value_0_valid[mask_mg, :]  # shape: (n_e, n_channels)
                    vals_tot = all_chn_value_1_valid[mask_mg, :]
                    vals_toa = all_chn_value_2_valid[mask_mg, :]

                    mean_adc = vals_adc.mean(axis=0)
                    mean_tot = vals_tot.mean(axis=0)
                    mean_toa = vals_toa.mean(axis=0)

                    std_adc = vals_adc.std(axis=0, ddof=0)
                    std_tot = vals_tot.std(axis=0, ddof=0)
                    std_toa = vals_toa.std(axis=0, ddof=0)

                    err_adc = std_adc / np.sqrt(n_e)
                    err_tot = std_tot / np.sqrt(n_e)
                    err_toa = std_toa / np.sqrt(n_e)
                else:
                    mean_adc = np.zeros(n_channels, dtype=float)
                    mean_tot = np.zeros(n_channels, dtype=float)
                    mean_toa = np.zeros(n_channels, dtype=float)
                    err_adc  = np.zeros(n_channels, dtype=float)
                    err_tot  = np.zeros(n_channels, dtype=float)
                    err_toa  = np.zeros(n_channels, dtype=float)

                mg_offset = mg + event_short
                if mg_offset > _machine_gun:
                    mg_offset -= (_machine_gun + 1)

                adc_mean_list[mg_offset, :] = mean_adc
                adc_err_list[mg_offset, :]  = err_adc
                tot_mean_list[mg_offset, :] = mean_tot
                tot_err_list[mg_offset, :]  = err_tot
                toa_mean_list[mg_offset, :] = mean_toa
                toa_err_list[mg_offset, :]  = err_toa

        finally:
            if not packetlibX.send_daq_gen_start_stop(
                _cmd_socket, _h2gcroc_ip, _h2gcroc_port,
                fpga_addr=_fpga_addr, daq_push=0x00,
                gen_start_stop=0, daq_start_stop=0x00, verbose=False
            ):
                print_warn("Failed to stop the generator")

        if _verbose:
            print_info(
                f"daqh bad events: {counter_daqh_incorrect} "
                f"(expected: {_total_event}, received: {current_event_num})"
            )

    if not _all_events_received:
        print_warn("Not enough valid events received")
        print_warn("Returning list of zeros")
        # arrays are already initialized as zeros

    return adc_mean_list, adc_err_list, tot_mean_list, tot_err_list, toa_mean_list, toa_err_list

def measure_adc(_udp_target, _total_asic_num, _machine_gun, _total_event, _fragment_life, _logger, _retry=1, _verbose=False):
    adc_mean_list, adc_err_list, _, _, _, _ = measure_all(_udp_target, _total_asic_num, _machine_gun, _total_event, _fragment_life, _retry=_retry, _verbose=_verbose)
    
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

def Scan_12b(_udp_target, _progress_bar, _asic_num, _scan_chn_pack, _scan_asic_chn, _machine_gun, _expected_event_number, _fragment_life, _dead_chn_list, _asic_settings, _toa_halves, _tot_halves, _toa_channels, _tot_channels, _retry, _toa_setting=True, _verbose=False, _total_steps=0, _current_step=0):
    if _asic_num != len(_asic_settings):
        print_err("Number of ASICs does not match the number of configurations")
        return
    
    if len(_toa_halves) != 2*_asic_num or len(_tot_halves) != 2*_asic_num:
        print_err("Length of TOA/ToT halves does not match the number of ASICs")
        return
    
    if len(_toa_channels) != 72*_asic_num or len(_tot_channels) != 72*_asic_num:
        print_err("Length of TOA/ToT channels does not match the number of ASICs")
        return
    
    if _scan_chn_pack > 76 or _scan_chn_pack < 1:
        print_err("Invalid scan channel pack number")
        return
    _used_scan_values = []
    _copied_asic_settings = [copy.deepcopy(_asic_settings[i]) for i in range(_asic_num)]

    _scan_val0_list     = []
    _scan_val0_list     = []
    _scan_val0_err_list = []
    _scan_val1_list     = []
    _scan_val1_err_list = []
    _scan_val2_list     = []
    _scan_val2_err_list = []

    for _12b_dac_value in _progress_bar:
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
            _asic_setting = _copied_asic_settings[_asic_index]
            if not _asic_setting.set_12b_dac(_12b_dac_value, half_index=0):
                print_err(f"Failed to set 12b DAC for ASIC {_asic_index} half 0")
            if not _asic_setting.set_12b_dac(_12b_dac_value, half_index=1):
                print_err(f"Failed to set 12b DAC for ASIC {_asic_index} half 1")
            if not _asic_setting.set_intctest(True, half_index=0):
                print_err(f"Failed to set IntCTest for ASIC {_asic_index} half 0")
            if not _asic_setting.set_intctest(True, half_index=1):
                print_err(f"Failed to set IntCTest for ASIC {_asic_index} half 1")
            if _toa_setting:
                if not _asic_setting.set_toa_vref(vref_value=_toa_halves[2*_asic_index], half_index=0):
                    print_err(f"Failed to set TOA Vref for ASIC {_asic_index} half 0")
                if not _asic_setting.set_toa_vref(vref_value=_toa_halves[2*_asic_index + 1], half_index=1):
                    print_err(f"Failed to set TOA Vref for ASIC {_asic_index} half 1")
            if not _asic_setting.set_tot_vref(vref_value=_tot_halves[2*_asic_index], half_index=0):
                print_err(f"Failed to set TOT Vref for ASIC {_asic_index} half 0")
            if not _asic_setting.set_tot_vref(vref_value=_tot_halves[2*_asic_index + 1], half_index=1):
                print_err(f"Failed to set TOT Vref for ASIC {_asic_index} half 1")

            if not _asic_setting.set_choice_cinj(True, half_index=0):
                print_err(f"Failed to set Choice_Cinj for ASIC {_asic_index} half 0")   
            if not _asic_setting.set_choice_cinj(True, half_index=1):
                print_err(f"Failed to set Choice_Cinj for ASIC {_asic_index} half 1")
            if not _asic_setting.set_extctest_2v5(False, half_index=0):
                print_err(f"Failed to set ExtCTest 2v5 for ASIC {_asic_index} half 0")
            if not _asic_setting.set_extctest_2v5(False, half_index=1):
                print_err(f"Failed to set ExtCTest 2v5 for ASIC {_asic_index} half 1")

            # _asic_setting.print_reg("Reference_Voltage_0")
            # _asic_setting.print_reg("Reference_Voltage_1")
            if not _asic_setting.send_reference_voltage_0_register(_udp_target):
                print_err(f"Failed to send Reference Voltage 0 register for ASIC {_asic_index}")
            if not _asic_setting.send_reference_voltage_1_register(_udp_target):
                print_err(f"Failed to send Reference Voltage 1 register for ASIC {_asic_index}")

        # -- Set up channel wise registers ----------------------
        # -------------------------------------------------------
        flag_all_channels_feed = False
        max_chn_half = 38
        current_chn_half = 0
        while not flag_all_channels_feed:
            _pack_channels = [] # this is 72 channel indexing
            _pack_channels_raw = [] # this is 76 channel indexing

            while len(_pack_channels) < _scan_chn_pack and not flag_all_channels_feed:
                for _half in range(2):
                    _chn_index = current_chn_half + _half*38
                    if _chn_index < _scan_asic_chn:
                        _chn_valid = single_channel_index_remove_cm_calib(_chn_index)
                        _pack_channels_raw.append(_chn_index)
                        if _chn_valid != -1:
                            _pack_channels.append(_chn_valid)
                current_chn_half +=1
                if current_chn_half >= max_chn_half:
                    flag_all_channels_feed = True
                    break

            for _asic in range(_asic_num):
                _asic_setting = _copied_asic_settings[_asic]
                for _chn in _pack_channels:
                    if _asic*72 + _chn in _dead_chn_list:
                        continue
                    _chn_toa = _toa_channels[_asic*72 + _chn]
                    _chn_tot = _tot_channels[_asic*72 + _chn]

                    if _toa_setting:
                        if not _asic_setting.set_chn_trim_toa(_chn, _chn_toa):
                            print_err(f"Failed to set TOA trim for ASIC {_asic} channel {_chn}")
                    if not _asic_setting.set_chn_trim_tot(_chn, _chn_tot):
                        print_err(f"Failed to set TOT trim for ASIC {_asic} channel {_chn}")
                    if not _asic_setting.set_chn_highrange(_chn, True):
                        print_err(f"Failed to set high range for ASIC {_asic} channel {_chn}")
                    if not _asic_setting.set_chn_lowrange(_chn, False):
                        print_err(f"Failed to set low range for ASIC {_asic} channel {_chn}")
                    if not _asic_setting.set_chn_sign_dac(_chn):
                        print_err(f"Failed to set sign DAC for ASIC {_asic} channel {_chn}")
                    if not _asic_setting.set_chn_gain_conv2(_chn):
                        print_err(f"Failed to set gain conv2 for ASIC {_asic} channel {_chn}")

                    # _asic_setting.print_reg("Channel_" + str(_chn))
                    if not _asic_setting.send_channel_register(_udp_target, _chn):
                        print_err(f"Failed to send channel register for ASIC {_asic} channel {_chn}")

            v0_list, v0_err, v1_list, v1_err, v2_list, v2_err = measure_all(_udp_target, _asic_num, _machine_gun, _expected_event_number, _fragment_life, _retry, _focus_half=[])
            # two digit channel index
            channel_str = ', '.join([f"{ch:02d}" for ch in _pack_channels])
            print(f"-- 12b DAC {_12b_dac_value:04d}, channels {channel_str}")
            # for _asic in range(_asic_num):
            #     _pack_channels_to_check = _pack_channels_raw.copy()
            #     for _chn_index in range(len(_pack_channels_to_check)):
            #         _pack_channels_to_check[_chn_index] += _asic*76
                # append the two next channels
                # _pack_channels_to_check.append(_pack_channels_to_check[-1] + 1)
                # _pack_channels_to_check.append(_pack_channels_to_check[-1] + 1)
                # print(f" ASIC {_asic}, channels {_pack_channels_to_check}:")
                # for _mg in range(_machine_gun+1):
                #     print(f"  MG {_mg}: V0 {v0_list[_mg][_pack_channels_to_check]}, V1 {v1_list[_mg][_pack_channels_to_check]}, V2 {v2_list[_mg][_pack_channels_to_check]}")

            for _asic in range(_asic_num):
                _asic_setting = _copied_asic_settings[_asic]
                for _chn in _pack_channels:
                    if _asic*72 + _chn in _dead_chn_list:
                        continue

                    if not _asic_setting.set_chn_highrange(_chn, False):
                        print_err(f"Failed to set high range for ASIC {_asic} channel {_chn}")
                    if not _asic_setting.set_chn_lowrange(_chn, False):
                        print_err(f"Failed to set low range for ASIC {_asic} channel {_chn}")

                    if not _asic_setting.send_channel_register(_udp_target, _chn):
                        print_err(f"Failed to send channel register for ASIC {_asic} channel {_chn}")

            for _asic in range(_asic_num):
                for _chn in _pack_channels_raw:
                    _chn_v0_list, _chn_v1_list, _chn_v2_list = [], [], []
                    _chn_v0_err,  _chn_v1_err,  _chn_v2_err  = [], [], []

                    for _machine_gun_index in range(_machine_gun+1):
                        _chn_v0_list.append(v0_list[_machine_gun_index][_chn + _asic*76])
                        _chn_v0_err.append(v0_err[_machine_gun_index][_chn + _asic*76])
                        _chn_v1_list.append(v1_list[_machine_gun_index][_chn + _asic*76])
                        _chn_v1_err.append(v1_err[_machine_gun_index][_chn + _asic*76])
                        _chn_v2_list.append(v2_list[_machine_gun_index][_chn + _asic*76])
                        _chn_v2_err.append(v2_err[_machine_gun_index][_chn + _asic*76])

                    val0_list_assembled[_chn + _asic*76]     = np.max(_chn_v0_list)
                    val0_err_list_assembled[_chn + _asic*76] = _chn_v0_err[np.argmax(_chn_v0_list)]
                    val1_list_assembled[_chn + _asic*76]     = np.max(_chn_v1_list)
                    val1_err_list_assembled[_chn + _asic*76] = _chn_v1_err[np.argmax(_chn_v1_list)]
                    val2_list_assembled[_chn + _asic*76]     = np.max(_chn_v2_list)
                    val2_err_list_assembled[_chn + _asic*76] = _chn_v2_err[np.argmax(_chn_v2_list)]

        _scan_val0_list.append(val0_list_assembled)
        _scan_val0_err_list.append(val0_err_list_assembled)
        _scan_val1_list.append(val1_list_assembled)
        _scan_val1_err_list.append(val1_err_list_assembled)
        _scan_val2_list.append(val2_list_assembled)
        _scan_val2_err_list.append(val2_err_list_assembled)

        if _total_steps > 0:
            _current_step += 1
            print(f"ui_progress:{int(100*_current_step/_total_steps)}")

    return _used_scan_values, _scan_val0_list, _scan_val0_err_list, _scan_val1_list, _scan_val1_err_list, _scan_val2_list, _scan_val2_err_list, _current_step
# * -------------------------------------------------------------------------------------