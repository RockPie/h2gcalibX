from matplotlib import pyplot as plt
import numpy as np
import pandas as pd
from .clx_data import channel_list_remove_cm_calib, single_channel_index_remove_cm_calib

# light background colors for at most 16 halves
halves_color_list = [
    '#FFCCCC', '#CCFFCC', '#CCCCFF', '#FFFFCC',
    '#CCFFFF', '#FFCCFF', '#F0E68C', '#E6E6FA',
    '#FFDAB9', '#E0FFFF', '#D8BFD8', '#FFE4E1',
    '#F5DEB3', '#D3DCDC', '#FFFACD', '#EEDD82'
]

def print_adc_to_terminal(adc_values_mean, adc_values_err, channel_nums = [3, 4, 5]):
    # only print the channel in channel_nums
    if len(adc_values_err) != len(adc_values_mean):
        print("[clx visualize] Length of adc_values_err and adc_values_mean do not match!")
        return
    asic_num = int(len(adc_values_mean) / 76)
    if len(channel_nums) == 0:
        print("[clx visualize] channel_nums is empty!")
        return
    # check if all the channel numbers are valid
    for chn in channel_nums:
        if chn < 0 or chn >= 38:
            print(f"[clx visualize] Channel number {chn} is invalid! It should be between 0 and 37.")
            return
    
    for _asic in range(asic_num):
        str_print = f"--A{_asic}: "
        for _half in range(2):
            for _chn in channel_nums:
                idx = _asic * 76 + _half * 38 + _chn
                # fixed 4 digit int for mean and 2 digit int for err
                str_print += f"Ch{_chn+38*_half:02d} {int(adc_values_mean[idx]):3d} "
            str_print += " || "

        print(str_print)

def calculate_half_average_adc(adc_values_mean, adc_values_err, asic_num, channel_ignore=[0, 19], channel_dead=[]):
    # calculate the average adc value for each half of each asic
    if len(adc_values_err) != len(adc_values_mean):
        print("[clx visualize] Length of adc_values_err and adc_values_mean do not match!")
        return [], []
    if len(adc_values_mean) != 76 * asic_num:
        print("[clx visualize] Length of adc_values_mean is not equal to 76 * total_asic!")
        return [], []
    for chn in channel_ignore:
        if chn < 0 or chn >= 38:
            print(f"[clx visualize] Channel number {chn} in channel_ignore is invalid! It should be between 0 and 37.")
            return [], []
    
    half_avg_list   = []
    half_error_list = []

    for _asic in range(asic_num):
        for _half in range(2):
            valid_channel_count = 0
            adc_sum = 0.0
            err_sum_sq = 0.0

            adc_list = []
            err_list = []

            for _chn in range(38):
                if _chn in channel_ignore:
                    continue
                if _chn in channel_dead:
                    continue
                idx = _asic * 76 + _half * 38 + _chn
                x   = adc_values_mean[idx]
                sx  = adc_values_err[idx]

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


def plot_channel_adc(adc_mean_list, adc_err_list, info_str, dead_channels=[], halves_target=[]):
    fig, ax = plt.subplots(1, 1, figsize=(12, 9))

    asic_num = int(len(adc_mean_list) / 76)
    regions = []
    for _asic in range(asic_num):
        for _half in range(2):
            start_ch = _asic * 72 + _half * 36 - 0.5
            end_ch   = start_ch + 35 + 1.0
            regions.append((start_ch, end_ch))
    for idx, (start, end) in enumerate(regions):
        ax.axvspan(start, end, facecolor=halves_color_list[idx % len(halves_color_list)], alpha=0.3, edgecolor='none')

    ax.errorbar(
        range(len(channel_list_remove_cm_calib(adc_mean_list))),
        channel_list_remove_cm_calib(adc_mean_list),
        yerr=channel_list_remove_cm_calib(adc_err_list),
        fmt='o',
        color='black',
        label='ADC mean value',
        markersize=2
    )

    for ch in dead_channels:
        ch_removed_cm = single_channel_index_remove_cm_calib(ch)
        if ch_removed_cm == -1:
            continue
        ax.vlines(ch_removed_cm, -50, 1024, color='red', linestyle='--', label=f'Dead channel {ch_removed_cm}')

    if len(halves_target) == asic_num * 2:
        for _half in range(asic_num * 2):
            start_ch = _half * 36 - 0.5
            end_ch   = start_ch + 35 + 1.0
            ax.hlines(
                halves_target[_half],
                start_ch,
                end_ch,
                colors='blue',
                linestyles='dotted',
                label=f'Target Half {_half} Pedestal' if _half < 2 else None
            )

    # draw y = 0 line
    ax.hlines(0, -0.5, asic_num * 72 - 0.5, colors='gray', linestyles='dashdot', label='ADC = 0')

    ax.set_xlabel('Channel number')
    ax.set_ylabel('ADC mean value')
    ax.set_ylim(-50, 1024)
    ax.set_xlim(-0.5, asic_num * 72 - 0.5)
    ax.annotate(
        info_str,
        xy=(0.02, 0.95),
        xycoords='axes fraction',
        fontsize=17,
        color='#062B35FF',
        fontweight='bold'
    )
    return fig, ax

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
    