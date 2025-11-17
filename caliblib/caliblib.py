import packetlib
import time, os, sys, socket, json, csv
from loguru import logger
import numpy as np
import pandas as pd
from matplotlib import pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from collections import deque

color_list = ['#FF0000', '#0000FF', '#FFFF00', '#00FF00','#FF00FF', '#00FFFF', '#FFA500', '#800080', '#008080', '#FFC0CB']

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

def HalfTurnOnAverage(_turn_on_points, _unused_chn_list, _dead_chn_list, _asic_num):
    _half_on_points = [-1 for _ in range(38*_asic_num)]
    if len(_turn_on_points) != 76*_asic_num:
        logger.error("Turn on points list does not match the number of channels")
        return
    for _half in range(2*_asic_num):
        _chn_list = []
        for _chn in range(38*_half, 38*(_half+1)):
            if _chn in _unused_chn_list or _chn in _dead_chn_list:
                continue
            _chn_list.append(_turn_on_points[_chn])
        _half_on_points[_half] = np.mean(_chn_list)
        logger.debug(f"Half{_half}: {round(_half_on_points[_half], 2)}")
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
    logger
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
    logger.info(
        f"Worker ID: {worker_id}, Control Port: {ctrl_port}")
    logger.info(
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
        logger.debug(f"{action} {typ}@{h2gcroc_ip}:{do_port} → {resp}")
        return resp

    return ctrl_conn, data_cmd_conn, data_data_conn, cmd_outbound_conn, pool_do

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

            if not packetlib.send_daq_gen_start_stop(_cmd_socket, _h2gcroc_ip, _h2gcroc_port, fpga_addr = _fpga_addr, daq_push=0x00, gen_start_stop=0, daq_start_stop=0xFF, verbose=False):
                _logger.warning("Failed to start the generator")
            if not packetlib.send_daq_gen_start_stop(_cmd_socket, _h2gcroc_ip, _h2gcroc_port, fpga_addr = _fpga_addr, daq_push=0x00, gen_start_stop=1, daq_start_stop=0xFF, verbose=False):
                _logger.warning("Failed to start the generator")

            if True:
                try:
                    bytes_counter = 0
                    try:
                        for _ in range(100):
                            data_packet, _ = _data_socket.recvfrom(1358)

                            # * Find the lines with fixed line pattern
                            extracted_payloads_pool.extend(packetlib.extract_raw_data(data_packet))
                            bytes_counter += len(data_packet)

                    except socket.timeout:
                        if _verbose:
                            _logger.warning("Socket timeout, no data received")

                        if not packetlib.send_daq_gen_start_stop(_cmd_socket, _h2gcroc_ip, _h2gcroc_port, fpga_addr = _fpga_addr, daq_push=0x00, gen_start_stop=0, daq_start_stop=0x00, verbose=False):
                            _logger.warning("Failed to stop the generator")

                        for _ in range(10):
                            try:

                                data_packet, _ = _data_socket.recvfrom(1358)

                                # * Find the lines with fixed line pattern
                                extracted_payloads_pool.extend(packetlib.extract_raw_data(data_packet))
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

                        extracted_data = packetlib.extract_values_192(payload_192, verbose=False)
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

                                    hamming_code_array[current_event_num][_half*3 + 0] = packetlib.DaqH_get_H1(_DaqH)
                                    hamming_code_array[current_event_num][_half*3 + 1] = packetlib.DaqH_get_H2(_DaqH)
                                    hamming_code_array[current_event_num][_half*3 + 2] = packetlib.DaqH_get_H3(_DaqH)
                                    daqh_good_array[current_event_num][_half] = packetlib.DaqH_start_end_good(_DaqH)

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
            if not packetlib.send_daq_gen_start_stop(_cmd_socket, _h2gcroc_ip, _h2gcroc_port, fpga_addr = _fpga_addr, daq_push=0x00, gen_start_stop=0, daq_start_stop=0x00, verbose=False):
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

def measure_adc(_cmd_socket, _data_socket, _h2gcroc_ip, _h2gcroc_port, _total_asic_num, _fpga_addr, _total_event, _fragment_life, _logger, _retry=1, _verbose=False):
    adc_mean_list, adc_err_list, tot_mean_list, tot_err_list, toa_mean_list, toa_err_list = measure_all(_cmd_socket, _data_socket, _h2gcroc_ip, _h2gcroc_port, _total_asic_num, _fpga_addr, 10, _total_event, _fragment_life, _logger, _retry=_retry, _verbose=_verbose)
    
    return adc_mean_list[0], adc_err_list[0]

def Inj_2V5(_cmd_out_conn, _cmd_data_conn, _data_data_conn, _h2gcroc_ip, _h2gcroc_port, _fpga_address, _phase, _dac, _scan_chn_start, _scan_chn_number, _asic_num, _scan_chn_pack, _machine_gun, _expected_event_number, _fragment_life, _config, unused_chn_list, _dead_chn_list, _i2c_dict, _logger, _retry=1, _verbose=False):
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