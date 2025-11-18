import socket, time, os
import numpy as np
from collections import deque

def print_warn(msg):
    print(f"[clx_data] WARNING: {msg}")
def print_info(msg):
    print(f"[clx_data] INFO: {msg}")
def print_err(msg):
    print(f"[clx_data] ERROR: {msg}")

def channel_list_remove_cm_calib(channel_value_list):
    # remove the channels with 0 and 19 mod 38
    channel_list_filtered = []
    for idx in range(len(channel_value_list)):
        chn_mod = idx % 38
        if chn_mod == 0 or chn_mod == 19:
            continue
        channel_list_filtered.append(channel_value_list[idx])
    return channel_list_filtered

def single_channel_index_remove_cm_calib(channel_index):
    # convert the channel index to the index after removing channels 0 and 19 mod 38
    chn_mod = channel_index % 38
    if chn_mod == 0 or chn_mod == 19:
        return -1  # invalid index
    num_cm_before = channel_index // 19 + 1
    return channel_index - num_cm_before


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
                
