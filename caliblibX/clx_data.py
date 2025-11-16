import socket, time, os
import packetlibX
import numpy as np
from collections import deque

def print_warn(msg):
    print(f"[clx_data] WARNING: {msg}")
def print_info(msg):
    print(f"[clx_data] INFO: {msg}")
def print_err(msg):
    print(f"[clx_data] ERROR: {msg}")

# def measure_all_XR(_cmd_socket, _data_socket, _h2gcroc_ip, _h2gcroc_port, _total_asic_num, _fpga_addr, _machine_gun, _total_event, _fragment_life, _logger, _retry=1, _verbose=False, _focus_half=[]):

def measure_all_XR(udp_target, _total_asic_num, _machine_gun, _n_cycle, _fragment_life, _retry=1, _verbose=False, _focus_half=[]):
    _cmd_socket   = udp_target.data_cmd_conn
    _data_socket  = udp_target.data_data_conn
    _h2gcroc_ip   = udp_target.board_ip
    _h2gcroc_port = udp_target.board_port
    _fpga_addr    = udp_target.board_id
    
    _total_event = (_machine_gun + 1) * _n_cycle
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
                print_warn("Failed to start the generator")
            if not packetlibX.send_daq_gen_start_stop(_cmd_socket, _h2gcroc_ip, _h2gcroc_port, fpga_addr = _fpga_addr, daq_push=0x00, gen_start_stop=1, daq_start_stop=0xFF, verbose=False):
                print_warn("Failed to start the generator")

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
                            print_warn("Socket timeout, no data received")

                        if not packetlibX.send_daq_gen_start_stop(_cmd_socket, _h2gcroc_ip, _h2gcroc_port, fpga_addr = _fpga_addr, daq_push=0x00, gen_start_stop=0, daq_start_stop=0x00, verbose=False):
                            print_warn("Failed to stop the generator")

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
                                    print_warn("Socket timeout, no data received")

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
                            print_warn(f"Failed to extract chunk #{chunk_counter}")
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
                                    print_warn("Invalid event detected (hamming or DAQH error)")

                            else:
                                print_warn(f"Chunk timestamps mismatch: {timestamps}")

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

            if (current_event_num - counter_daqh_incorrect) < min(_total_event//2, 1):
                if _verbose:
                    print_warn("Not enough valid events received " + str(current_event_num) + "  " + str(_total_event))
                _all_events_received = False
                continue
            
            #_logger.debug(f"Event number: {current_event_num}")
            timestamps_pure = []
            for _timestamp_index in range(len(timestamps_events)):
                timestamps_pure.append(timestamps_events[_timestamp_index] - timestamps_events[0])
            #_logger.debug(f"Timestamps: {timestamps_pure}")
            if timestamps_pure[-1] != 164*(_machine_gun):
                print_warn(f"Machine gun {timestamps_pure[-1]} is not enough for {_machine_gun}")
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
                                print_warn(f"Machine gun {_current_machine_gun} exceeds {_machine_gun}")
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
                                    print_warn(f"Machine gun {_current_machine_gun} exceeds {_machine_gun}")
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
                print_warn("Failed to stop the generator")

        if _verbose:
            print_info(f"daqh bad events: {counter_daqh_incorrect} (expected: {_total_event}, received: {current_event_num})")

    if not _all_events_received:
        print_warn("Not enough valid events received")
        print_warn("Returning list of zeros")


    # if True:
    #     _logger.debug(f'Total events received: {current_event_num} / {_total_event}')
    #     _logger.debug(f'DaqH Bad events: {counter_daqh_incorrect}')

    return adc_mean_list, adc_err_list, tot_mean_list, tot_err_list, toa_mean_list, toa_err_list

def measure_all_X(udp_target, _total_asic_num, _machine_gun, _n_cycle, _fragment_life, _retry=1, _verbose=False, _focus_half=[]):
    _total_event  = _n_cycle * (_machine_gun + 1)

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
                print_info(f"Retrying measurement, attempts left: {_retry_left}")
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

            if not packetlibX.send_daq_gen_start_stop(udp_target.data_cmd_conn, udp_target.board_ip, udp_target.board_port, fpga_addr = udp_target.board_id, daq_push=0x00, gen_start_stop=0, daq_start_stop=0xFF, verbose=False):
                print_warn("Failed to start the generator")
            if not packetlibX.send_daq_gen_start_stop(udp_target.data_cmd_conn, udp_target.board_ip, udp_target.board_port, fpga_addr = udp_target.board_id, daq_push=0x00, gen_start_stop=1, daq_start_stop=0xFF, verbose=False):
                print_warn("Failed to start the generator")

            if True:
                try:
                    bytes_counter = 0
                    try:
                    # for _ in range(100):
                        data_packet, _ = udp_target.data_data_conn.recvfrom(8192)

                        # * Find the lines with fixed line pattern
                        if data_packet is not None:
                            print_info(f"Received data packet of size {len(data_packet)} bytes")
                        extracted_payloads_pool.extend(packetlibX.extract_raw_payloads(data_packet))
                        bytes_counter += len(data_packet)

                    except socket.timeout:
                        if _verbose:
                            print_warn("Socket timeout, no data received")

                        if not packetlibX.send_daq_gen_start_stop(udp_target.data_cmd_conn, udp_target.board_ip, udp_target.board_port, fpga_addr = udp_target.board_id, daq_push=0x00, gen_start_stop=0, daq_start_stop=0x00, verbose=False):
                            print_warn("Failed to stop the generator")

                        for _ in range(5):
                            try:

                                data_packet, _ = udp_target.data_data_conn.recvfrom(8192)

                                # * Find the lines with fixed line pattern
                                extracted_payloads_pool.extend(packetlibX.extract_raw_payloads(data_packet))
                                bytes_counter += len(data_packet)
                                if len(data_packet) > 0:
                                    break

                            except socket.timeout:
                                if _verbose:
                                    print_warn("Socket timeout, no data received")

                    half_packet_number = float(bytes_counter) / (5 * 40)
                    event_number = half_packet_number / 2 / _total_asic_num
                    half_packet_number = int(half_packet_number)
                    event_number = int(event_number)

                    print_info(f"Received {half_packet_number} half packets, {event_number} events")
                    print_info(f"Received {len(extracted_payloads_pool)} payloads")

                    if len(extracted_payloads_pool) >= 5:
                        candidate_packet_lines = [extracted_payloads_pool.popleft() for _ in range(5)]
                        while len(extracted_payloads_pool) > 0:
                            is_packet_good, event_fragment = packetlibX.check_event_fragment(candidate_packet_lines)
                            if is_packet_good:
                                event_fragment_pool.append(event_fragment)
                                current_half_packet_num += 1
                                if len(extracted_payloads_pool) >= 5:
                                    candidate_packet_lines = [extracted_payloads_pool.popleft() for _ in range(5)]
                                else:
                                    break
                            else:
                                print_warn("Warning: Event fragment is not good")
                                # pop out the oldest line
                                candidate_packet_lines.pop(0)
                                candidate_packet_lines.append(extracted_payloads_pool.popleft())

                    print_info(f"Current half packet number: {current_half_packet_num}")

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
                                extracted_data = packetlibX.assemble_data_from_40bytes(event_fragment_pool[counter_fragment+_half], verbose=False)
                                extracted_values = packetlibX.extract_values(extracted_data["_extraced_160_bytes"], verbose=False)
                                uni_chn_base = (extracted_data["_header"] - 0xA0) * 76 + (extracted_data["_packet_type"] - 0x24) * 38
                                for j in range(len(extracted_values["_extracted_values"])):
                                    all_chn_value_0_array[current_event_num][j+uni_chn_base] = extracted_values["_extracted_values"][j][1]
                                    all_chn_value_1_array[current_event_num][j+uni_chn_base] = extracted_values["_extracted_values"][j][2]
                                    all_chn_value_2_array[current_event_num][j+uni_chn_base] = extracted_values["_extracted_values"][j][3]
                                hamming_code_array[current_event_num][_half*3+0] =  packetlibX.DaqH_get_H1(extracted_values["_DaqH"])
                                hamming_code_array[current_event_num][_half*3+1] =  packetlibX.DaqH_get_H2(extracted_values["_DaqH"])
                                hamming_code_array[current_event_num][_half*3+2] =  packetlibX.DaqH_get_H3(extracted_values["_DaqH"])
                                daqh_good_array[current_event_num][_half] = packetlibX.DaqH_start_end_good(extracted_values["_DaqH"])
                            update_indices = []
                            for j in range(n_halves):
                                update_indices.append(counter_fragment+j)
                            indices_to_delete.update(update_indices)
                            if _verbose:
                                if not np.all(hamming_code_array[current_event_num] == 0):
                                    print_warn("Hamming code error detected!")
                                if not np.all(daqh_good_array[current_event_num] == True):
                                    print_warn("DAQH start/end error detected!")

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

                                if np.all(hamming_code_focus == 0) and np.all(daqh_good_focus == True):
                                    current_event_num += 1

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
                            print_info(f"Received enough events: {current_event_num} events (target: {_total_event} events)")
                        _all_events_received = True
                        # break;   

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

            if (current_event_num - counter_daqh_incorrect) < min(_total_event//2, 1):
                if _verbose:
                    print_warn("Not enough valid events received")
                _all_events_received = False
                continue
            
            # _logger.debug(f"Event number: {current_event_num}")
            timestamps_pure = []
            for _timestamp_index in range(len(timestamps_events)):
                timestamps_pure.append(timestamps_events[_timestamp_index] - timestamps_events[0])
            # _logger.debug(f"Timestamps: {timestamps_pure}")
            if timestamps_pure[-1] != 41*(_machine_gun-1):
                print_warn(f"Machine gun {timestamps_pure[-1]} is not enough")
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
                                print_warn(f"Machine gun {_current_machine_gun} exceeds {_machine_gun}")
                                continue

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
            if not packetlibX.send_daq_gen_start_stop(udp_target.data_cmd_conn, udp_target.board_ip, udp_target.board_port, fpga_addr = udp_target.board_id, daq_push=0x00, gen_start_stop=0, daq_start_stop=0x00, verbose=False):
                print_warn("Failed to stop the generator")

        if _verbose:
            print_info(f"daqh bad events: {counter_daqh_incorrect} (expected: {_total_event}, received: {current_event_num})")
    if not _all_events_received:
        print_warn("Not enough valid events received")
        print_warn("Returning list of zeros")

    return adc_mean_list, adc_err_list, tot_mean_list, tot_err_list, toa_mean_list, toa_err_list