import socket, time, os
import numpy as np
from collections import deque

def print_warn(msg):
    print(f"[clx_data] WARNING: {msg}")
def print_info(msg):
    print(f"[clx_data] INFO: {msg}")
def print_err(msg):
    print(f"[clx_data] ERROR: {msg}")

# * ---------------------------------------------------------------------------
# * - brief: this function removes the common-mode channels and calibration
# * -        channels from the input channel value list
# * - param:
# * -   channel_value_list: list of channel values including common-mode
# * -                       and calibration channels
# * - return:
# * -   channel_list_filtered: list of channel values excluding common-mode
# * -                          and calibration channels
# * ---------------------------------------------------------------------------
def channel_list_remove_cm_calib(channel_value_list):
    # remove the channels with 0 and 19 mod 38
    channel_list_filtered = []
    for idx in range(len(channel_value_list)):
        chn_mod = idx % 38
        if chn_mod == 0 or chn_mod == 19:
            continue
        channel_list_filtered.append(channel_value_list[idx])
    return channel_list_filtered

# * ---------------------------------------------------------------------------
# * - brief: this function converts the channel index to the actual data
# * -        channel index
# * - param:
# * -   channel_index: index including common-mode and calibration channels
# * - return:
# * -   actual_channel_index: index after removing common-mode and
# * -                           calibration channels; returns -1 if the
# * -                           input index corresponds to a removed channel
# * ---------------------------------------------------------------------------
def single_channel_index_remove_cm_calib(channel_index):
    # convert the channel index to the index after removing channels 0 and 19 mod 38
    chn_mod = channel_index % 38
    if chn_mod == 0 or chn_mod == 19:
        return -1  # invalid index
    num_cm_before = channel_index // 19 + 1
    return channel_index - num_cm_before

# * ---------------------------------------------------------------------------
# * - brief: from the measured adc mean values, tune the channel trims settings
# * - param:
# * -   _best_chn_trim: [asic_num][72] current best channel trims settings
# * -   _adc_mean_list: [asic_num * 76] measured adc mean
# * -   _halves_target_adc: [asic_num * 2] target adc for each half
# * -   _adc_tolerance: tolerance within which no adjustment will be made
# * -   _adc_step: step size for each adjustment
# * ---------------------------------------------------------------------------
def tune_chn_trim_inv(_best_chn_trim, _adc_mean_list, _halves_target_adc, _adc_tolerance = 2, _adc_step = 4):
    if len(_best_chn_trim) * 2 != len(_halves_target_adc):
        print_err("Length of _best_chn_trim and _halves_target_adc do not match!")
        return False
    if len(_best_chn_trim) != len(_adc_mean_list) // 76:
        print_err("Length of _best_chn_trim and _adc_mean_list do not match!")
        return False
    
    _asic_num = len(_best_chn_trim)
    _adc_mean_list_filtered = channel_list_remove_cm_calib(_adc_mean_list)

    for _asic in range(_asic_num):
        _asic_adc_mean = _adc_mean_list_filtered[_asic * 72 : (_asic + 1) * 72]
        for _half in range(2):
            _half_target_adc = _halves_target_adc[_asic * 2 + _half]
            for _chn_in_half in range(36):
                _adc_diff = _half_target_adc - _asic_adc_mean[_half * 36 + _chn_in_half]
                if abs(_adc_diff) <= _adc_tolerance:
                    continue
                if _adc_diff > 0:
                    # need to increase adc value by decreasing trim
                    _best_chn_trim[_asic][_half * 36 + _chn_in_half] += _adc_step
                else:
                    # need to decrease adc value by increasing trim
                    _best_chn_trim[_asic][_half * 36 + _chn_in_half] -= _adc_step
                if _best_chn_trim[_asic][_half * 36 + _chn_in_half] < 0:
                    _best_chn_trim[_asic][_half * 36 + _chn_in_half] = 0
                if _best_chn_trim[_asic][_half * 36 + _chn_in_half] > 63:
                    _best_chn_trim[_asic][_half * 36 + _chn_in_half] = 63

# * ---------------------------------------------------------------------------
# * - brief: calculate the average adc value for each half of each asic,
# * -        excluding specified ignored and dead channels
# * - param:
# * -   adc_values_mean: [asic_num * 76] measured adc mean values
# * -   adc_values_err: [asic_num * 76] measured adc mean errors
# * -   asic_num: total number of asics
# * -   channel_dead: list of dead channel numbers (72 max)
# * - return:
# * -   half_avg_list: [asic_num * 2] average adc values for each half
# * -   half_error_list: [asic_num * 2] errors of average adc values for 
# *                      each half
# * ---------------------------------------------------------------------------
def calculate_half_average_adc(adc_values_mean, adc_values_err, asic_num, channel_dead=[]):
    # calculate the average adc value for each half of each asic
    if len(adc_values_err) != len(adc_values_mean):
        print("[clx visualize] Length of adc_values_err and adc_values_mean do not match!")
        return [], []
    if len(adc_values_mean) != 76 * asic_num:
        print("[clx visualize] Length of adc_values_mean is not equal to 76 * total_asic!")
        return [], []
    
    adc_values_mean_filtered = channel_list_remove_cm_calib(adc_values_mean)
    adc_values_err_filtered  = channel_list_remove_cm_calib(adc_values_err)
    
    half_avg_list   = []
    half_error_list = []

    for _asic in range(asic_num):
        for _half in range(2):
            valid_channel_count = 0
            adc_sum = 0.0
            err_sum_sq = 0.0

            adc_list = []
            err_list = []

            for _chn in range(36):
                if _asic * 72 + _half * 36 + _chn in channel_dead:
                    continue
                idx = _asic * 72 + _half * 36 + _chn
                x   = adc_values_mean_filtered[idx]
                sx  = adc_values_err_filtered[idx]

                adc_sum    += x
                err_sum_sq += sx ** 2
                valid_channel_count += 1

                adc_list.append(x)
                err_list.append(sx)

            if valid_channel_count == 0:
                half_avg_list.append(0.0)
                half_error_list.append(0.0)
                continue

            N = valid_channel_count

            half_avg = adc_sum / N
            half_avg_list.append(half_avg)

            half_err_meas = (err_sum_sq ** 0.5) / N

            if N > 1:
                spread_sum_sq = 0.0
                for x in adc_list:
                    spread_sum_sq += (x - half_avg) ** 2

                # sigma_spread_for_mean = sqrt( sum (xi - mean)^2 / (N * (N - 1)) )
                half_err_spread = (spread_sum_sq / (N * (N - 1))) ** 0.5
            else:
                half_err_spread = 0.0

            half_error = (half_err_meas ** 2 + half_err_spread ** 2) ** 0.5
            half_error_list.append(half_error)

    return half_avg_list, half_error_list

# * ---------------------------------------------------------------------------
# * - brief: discriminate dead channels based on inv_ref scan
# * - param:
# * -   _adc_mean_scan_array: [half][channel][scan_point] adc mean values from 
# * -                         inv_ref scan np array
# * -   _dead_chn_threshold: RMS threshold below which a channel is dead
# * - return:
# * -   _dead_chn_list: [dead_channel_num] dead channel indexes (72 max)
# * -   _chn_rms_list: [half][channel] channel RMS values from the scan
# * ---------------------------------------------------------------------------
def dead_chn_discrimination(_adc_mean_scan_array, _dead_chn_threshold = 20):
    _dead_chn_list = []
    _chn_rms_list = []
    half_num = _adc_mean_scan_array.shape[0]
    chn_num  = _adc_mean_scan_array.shape[1]
    scan_num = _adc_mean_scan_array.shape[2]
    if scan_num < 2:
        print_err("Not enough scan points for dead channel discrimination!")
        return _dead_chn_list
    if chn_num != 36:
        print_err("Channel number mismatch for dead channel discrimination!")
        return _dead_chn_list
    for _half in range(half_num):
        _chn_base = _half * 36
        for _chn in range(chn_num):
            _adc_values = _adc_mean_scan_array[_half, _chn, :]
            _adc_rms = np.std(_adc_values)
            _chn_rms_list.append(_adc_rms)
            if _adc_rms < _dead_chn_threshold:
                _dead_chn_list.append(_chn_base + _chn)

    return _dead_chn_list, _chn_rms_list