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

# * ---------------------------------------------------------------------------
# * - brief: print the adc mean and error values for selected to terminal
# * - param:
# * -   adc_values_mean: [asic_num * 76] measured adc mean values
# * -   adc_values_err: [asic_num * 76] measured adc error values
# * -   channel_nums: list of channel numbers (excluding common-mode and 
# * -                 calibration channels) to be printed; default to [3, 4, 5]
# * ---------------------------------------------------------------------------
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

    adc_values_mean_filtered = channel_list_remove_cm_calib(adc_values_mean)
    adc_values_err_filtered  = channel_list_remove_cm_calib(adc_values_err)

    for chn in channel_nums:
        if chn < 0 or chn >= 36:
            print(f"[clx visualize] Channel number {chn} is invalid! It should be between 0 and 35.")
            return
    
    for _asic in range(asic_num):
        str_print = f"--A{_asic}: "
        for _half in range(2):
            for _chn in channel_nums:
                idx = _asic * 72 + _half * 36 + _chn
                # fixed 4 digit int for mean and 2 digit int for err
                str_print += f"Ch{_chn+36*_half:02d} {int(adc_values_mean_filtered[idx]):3d} "
            str_print += " || "

        print(str_print)

# * ---------------------------------------------------------------------------
# * - brief: plot the adc mean values and highlight dead channels
# * - param:
# * -   adc_mean_list: [asic_num * 76] measured adc mean values
# * -   adc_err_list: [asic_num * 76] measured adc mean errors
# * -   info_str: string to be displayed on the plot
# * -   dead_channels: list of channel numbers (excluding common-mode and 
# *     calibration channels)
# * -   halves_target: list of target adc values for each half [asic_num * 2]
# * - return:
# * -   fig, ax: matplotlib figure and axis objects
# * ---------------------------------------------------------------------------
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
        ax.vlines(ch, -50, 1024, color='red', linestyle='--', label=f'Dead channel {ch}')

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

def Draw2DIM(_title, _x_label, _y_label, _total_asic, _data, _saving_path, _y_ticks=None, _turn_on_points=None, _data_saving_path=None, _image_saving_path=None):
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

    if _image_saving_path is not None:
        fig.savefig(_image_saving_path)

    return fig, ax
    