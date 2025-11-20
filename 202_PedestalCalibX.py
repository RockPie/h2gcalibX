import caliblibX
import os, json, time, argparse
import matplotlib.pyplot as plt
import termplotlib as tpl
import numpy as np

# * --- Set up script information -------------------------------------
script_id_str       = os.path.basename(__file__).split('.')[0]
script_version_str  = '1.4'
script_folder       = os.path.dirname(__file__)
print("-- "+ script_id_str + " (v" + script_version_str + ") ----------------")
print(f"---------------------------------------------")

# * --- Read command line arguments -----------------------------------
parser = argparse.ArgumentParser(description='IO delay scan for HGCROC')
parser.add_argument('-i', '--i2c', type=str, help='Path to the I2C settings JSON file')
parser.add_argument('-c', '--config', type=str, help='Path to the common settings JSON file')
parser.add_argument('-t', '--target', type=int, help='Target pedestal value')
parser.add_argument('-a', '--asic', type=int, help='ASIC number to scan')
parser.add_argument('-o', '--output', type=str, help='Output folder name')
args = parser.parse_args()

# * --- Load configuration file ---------------------------------------
output_dump_folder, output_config_path = caliblibX.output_path_setup(script_id_str, time.strftime('%Y%m%d_%H%M%S'), os.path.dirname(__file__))
output_config_json = {}

# * --- Load udp settings from config file ----------------------------
udp_target = caliblibX.udp_target('10.1.2.207', 11000, 11001, '10.1.2.208', 11000)
if args.config:
    udp_target.load_udp_json_file(args.config)
udp_target.load_pool_json_file(os.path.join(script_folder, 'config', 'socket_pool_configX.json'))

print(f"- UDP from {args.config if args.config else 'default settings'}:")
print(f"-- PC IP: {udp_target.pc_ip}, Port: {udp_target.pc_port_cmd}/{udp_target.pc_port_data}")
print(f"-- Board IP: {udp_target.board_ip}, Port: {udp_target.board_port}")

udp_target.connect_to_pool(timeout=0.1)

# * --- Set running parameters --------------------------------------
total_asic = 2
if args.asic is not None:
    total_asic = int(args.asic)

# * --- Load I2C settings from file ------------------------------------
i2c_settings = {}
if args.i2c:
    i2c_files = args.i2c.split(',')
if len(i2c_files) != total_asic and len(i2c_files) != 1:
    print(f"Error: Number of I2C files provided ({len(i2c_files)}) does not match number of ASICs to scan ({total_asic}).")
    exit()

# * --- Create base I2C settings ---------------------------------
register_settings_list = []
if len(i2c_files) == total_asic:
    for asic_idx in range(total_asic):
        try:
            new_i2c_settings = caliblibX.h2gcroc_registers_full()
            new_i2c_settings.load_from_json(i2c_files[asic_idx])
            print(f"- Loaded I2C settings from {i2c_files[asic_idx]} for ASIC {asic_idx}.")
            if not new_i2c_settings.is_same_udp_settings(udp_target, asic_idx):
                raise ValueError(f"UDP settings in {i2c_files[asic_idx]} do not match the target UDP settings for ASIC {asic_idx}.")
            register_settings_list.append(new_i2c_settings)
        except Exception as e:
            print(f"Error loading I2C settings from {i2c_files[asic_idx]}: {e}")
            exit()
else:
    for asic_idx in range(total_asic):
        try:
            new_i2c_settings = caliblibX.h2gcroc_registers_full()
            new_i2c_settings.load_from_json(i2c_files[0])
            new_i2c_settings.sync_udp_settings(udp_target, asic_idx)
            register_settings_list.append(new_i2c_settings)
        except Exception as e:
            print(f"Error loading I2C settings from {i2c_files[0]}: {e}")
            exit()
    print("- Using the same I2C settings for all ASICs")

# * --- Set running parameters --------------------------------------
target_pedestal = 100
if args.target is not None:
    target_pedestal = int(args.target)

print(f"- Target pedestal value: {target_pedestal}")

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

# - inv_vref_default: default value for the inverted reference voltage
# - noinv_vref_default: default value for the non-inverted reference voltage
inv_vref_default    = 512
noinv_vref_default  = 512

# - inputdac_default: default value for the input DAC
# - pede_trim_default: default value for the pedestal trim
inputdac_default    = 0
pede_trim_default   = 31

# - (DNU) global_scan_range: range for the step 1 - global scan
# - (DNU) dead_channel_scan_range: range for the step 2 - dead channel scan
# - (DNU) dead_channel_std_threshold: threshold to determine if a channel is dead
# global_scan_range           = range(0, 1024, 32)
global_scan_range           = range(200, 800, 30)
dead_channel_scan_range     = range(0, 64, 8)
dead_channel_std_threshold  = 10

# - (DNU) pede_trim_step_size: step size for the pedestal trim tunning
# - (DNU) pede_tolerance: tolerance for the pedestal trim tunning
pede_trim_step_size = 4
pede_tolerance      = 2
pede_trim_attempt_number = 64 // pede_trim_step_size + 1
pede_trim_coarse_attempt_number = 16 // pede_trim_step_size + 1

# - target pedestal value for the global inverted reference voltage scan
global_coarse_scan_target = 150

# - delay time after setting i2c values before measurement
delay_after_setting_i2c = 0.1  # seconds


# - running result storage
dead_channels           = []
best_inv_vref_coarse    = []
best_chn_trim           = []
for _asic in range(total_asic):
    _asic_chn_trim = [pede_trim_default] * 72
    best_chn_trim.append(_asic_chn_trim)
best_inv_vref_fine   = []

for _asic in range(total_asic):
    print(f"- Setting I2C for ASIC {_asic}...")
    _asic_i2c_settings = register_settings_list[_asic]
    if not _asic_i2c_settings.set_inputdac_all(inputdac_default):
        print(f"Error: Failed to set Input DAC for ASIC {_asic}.")
    if not _asic_i2c_settings.set_chn_trim_inv_all(best_chn_trim[_asic]):
        print(f"Error: Failed to set Pedestal Trim for ASIC {_asic}.")
    if not _asic_i2c_settings.set_inv_vref(inv_vref_default, 0):
        print(f"Error: Failed to set Inverted Vref 0 for ASIC {_asic}.")
    if not _asic_i2c_settings.set_inv_vref(inv_vref_default, 1):
        print(f"Error: Failed to set Inverted Vref 1 for ASIC {_asic}.")
    if not _asic_i2c_settings.set_noinv_vref(noinv_vref_default, 0):
        print(f"Error: Failed to set Non-Inverted Vref 0 for ASIC {_asic}.")
    if not _asic_i2c_settings.set_noinv_vref(noinv_vref_default, 1):
        print(f"Error: Failed to set Non-Inverted Vref 1 for ASIC {_asic}.")
    _asic_i2c_settings.set_phase(phase_setting)
    _asic_i2c_settings.turn_on_daq()
    _asic_i2c_settings.send_all_registers(udp_target)

asic_values = [0x30 if i < total_asic else 0x00 for i in range(8)]
a0, a1, a2, a3, a4, a5, a6, a7 = asic_values

if not caliblibX.send_check_DAQ_gen_params_calib(
    udp_target, 
    data_coll_en        = 0x00, trig_coll_en        = 0x00,
    daq_fcmd            = gen_fcmd_L1A,
    gen_pre_fcmd        = gen_fcmd_internal_injection,
    gen_fcmd            = gen_fcmd_L1A,
    ext_trg_en          = 0x00, ext_trg_delay       = 0x00,
    ext_trg_deadtime    = 10000,
    jumbo_en            = 0x00,
    gen_preimp_en       = 0x00, gen_pre_interval    = 0x0010,
    gen_nr_of_cycle     = gen_nr_cycle,
    gen_interval        = gen_interval_value,
    daq_push_fcmd       = gen_fcmd_L1A,
    machine_gun         = machine_gun,
    ext_trg_out_0_len   = 0x00, ext_trg_out_1_len   = 0x00,
    ext_trg_out_2_len   = 0x00, ext_trg_out_3_len   = 0x00,
    asic0_collection    = a0,   asic1_collection    = a1,
    asic2_collection    = a2,   asic3_collection    = a3,
    asic4_collection    = a4,   asic5_collection    = a5,
    asic6_collection    = a6,   asic7_collection    = a7,
    verbose             = False,
    readback            = True
):
    print("-- Warning: Failed to set DAQ/Gen parameters.")

# * --- Global scan of inverted reference voltage ------------------------------
scan_global_inv_ref_adc_avg = np.zeros((2*total_asic, len(global_scan_range)), dtype=float)
scan_global_inv_ref_adc_err = np.zeros((2*total_asic, len(global_scan_range)), dtype=float)

scan_global_inv_ref_chn_adc_avg = np.zeros((2*total_asic, 36, len(global_scan_range)), dtype=float)

for _ref_inv in global_scan_range:
    print(f"- Setting Inverted Vref to {_ref_inv}")
    for _asic in range(total_asic):
        _asic_i2c_settings = register_settings_list[_asic]
        if not _asic_i2c_settings.set_inv_vref(_ref_inv, 0):
            print(f"Error: Failed to set Inverted Vref 0 for ASIC {_asic}.")
        if not _asic_i2c_settings.set_inv_vref(_ref_inv, 1):
            print(f"Error: Failed to set Inverted Vref 1 for ASIC {_asic}.")

        _asic_i2c_settings.send_reference_voltage_0_register(udp_target)
        _asic_i2c_settings.send_reference_voltage_1_register(udp_target)

    time.sleep(delay_after_setting_i2c)
    adc_mean_list, adc_err_list = caliblibX.measure_adc(udp_target, total_asic, machine_gun, expected_event_number, i2c_fragment_life, i2c_retry, _verbose=False)
    adc_mean_list_filtered = caliblibX.channel_list_remove_cm_calib(adc_mean_list)
    for _asic in range(total_asic):
        for _chn in range(72):
            scan_global_inv_ref_chn_adc_avg[2*_asic + (_chn // 36), _chn % 36, global_scan_range.index(_ref_inv)] = adc_mean_list_filtered[_asic * 72 + _chn]

    caliblibX.print_adc_to_terminal(adc_mean_list, adc_err_list)
    half_avg_list, half_err_list = caliblibX.calculate_half_average_adc(adc_mean_list, adc_err_list, total_asic, dead_channels)
    for _half in range(2*total_asic):
        scan_global_inv_ref_adc_avg[_half, global_scan_range.index(_ref_inv)] = half_avg_list[_half]
        scan_global_inv_ref_adc_err[_half, global_scan_range.index(_ref_inv)] = half_err_list[_half]

for _half in range(2*total_asic):
    adc_values = scan_global_inv_ref_adc_avg[_half, :]
    diffs = np.abs(adc_values - global_coarse_scan_target)
    best_index = np.argmin(diffs)
    best_inv_vref = list(global_scan_range)[best_index]
    best_inv_vref_coarse.append(best_inv_vref)
    print(f"-- Half {_half}: Best Inverted Vref = {best_inv_vref}, Achieved Pedestal = {adc_values[best_index]:.2f}")

fig_global_inv_coarse, axs_global_inv_coarse = plt.subplots(1, 1, figsize=(10, 6))
for _half in range(2*total_asic):
    axs_global_inv_coarse.errorbar(
        list(global_scan_range),
        scan_global_inv_ref_adc_avg[_half, :],
        yerr=scan_global_inv_ref_adc_err[_half, :],
        label=f'Half {_half}'
    )
    # draw the best point as a vertical line
    best_inv_vref = best_inv_vref_coarse[_half]
    axs_global_inv_coarse.axvline(x=best_inv_vref, color='r', linestyle='--', alpha=0.5)
axs_global_inv_coarse.set_title('Global Scan of Inverted Reference Voltage')
axs_global_inv_coarse.set_xlabel('Inverted Reference Voltage Setting')
axs_global_inv_coarse.set_ylabel('Average ADC Value')
axs_global_inv_coarse.legend()
fig_global_inv_coarse.tight_layout()
fig_global_inv_coarse_path = os.path.join(output_dump_folder, '00_global_inv_ref_scan.png')
fig_global_inv_coarse.savefig(fig_global_inv_coarse_path)
print(f"- Saved global inverted reference voltage scan plot to {fig_global_inv_coarse_path}")

# find dead channels
dead_channels, channel_rms_values = caliblibX.dead_chn_discrimination(scan_global_inv_ref_chn_adc_avg, dead_channel_std_threshold)
# draw a hist of the rms values
fig_dead_chn_rms, ax_dead_chn_rms = plt.subplots(1, 1, figsize=(8, 5))
ax_dead_chn_rms.hist(channel_rms_values, bins=50, color='blue', alpha=0.7)
ax_dead_chn_rms.axvline(x=dead_channel_std_threshold, color='r', linestyle='--', label='Dead Channel Threshold')
ax_dead_chn_rms.set_title('Channel RMS Distribution from Inverted Vref Scan')
ax_dead_chn_rms.set_xlabel('Channel RMS')
ax_dead_chn_rms.set_ylabel('Number of Channels')
ax_dead_chn_rms.legend()
fig_dead_chn_rms_path = os.path.join(output_dump_folder, '01_dead_channel_rms.png')
fig_dead_chn_rms.savefig(fig_dead_chn_rms_path)
print(f"- Saved dead channel RMS distribution plot to {fig_dead_chn_rms_path}")

if dead_channels is not []:
    print(f"-- Detected dead channels: {dead_channels}")

# set the best inverted reference voltage found
for _asic in range(total_asic):
    _asic_i2c_settings = register_settings_list[_asic]
    best_inv_vref_0 = best_inv_vref_coarse[2*_asic]
    best_inv_vref_1 = best_inv_vref_coarse[2*_asic + 1]
    if not _asic_i2c_settings.set_inv_vref(best_inv_vref_0, 0):
        print(f"Error: Failed to set Inverted Vref 0 for ASIC {_asic}.")
    if not _asic_i2c_settings.set_inv_vref(best_inv_vref_1, 1):
        print(f"Error: Failed to set Inverted Vref 1 for ASIC {_asic}.")

    _asic_i2c_settings.send_reference_voltage_0_register(udp_target)
    _asic_i2c_settings.send_reference_voltage_1_register(udp_target)

time.sleep(delay_after_setting_i2c)

adc_mean_list, adc_err_list = caliblibX.measure_adc(udp_target, total_asic, machine_gun, expected_event_number, i2c_fragment_life, i2c_retry, _verbose=False)

caliblibX.print_adc_to_terminal(adc_mean_list, adc_err_list)
half_avg_list, half_err_list = caliblibX.calculate_half_average_adc(adc_mean_list, adc_err_list, total_asic, dead_channels)

fig_pede_after_global_inv, ax_pede_after_global_inv = caliblibX.plot_channel_adc(adc_mean_list, adc_err_list, 'Coarse Global Inverted Reference Voltage Scan', dead_channels, half_avg_list)
fig_pede_after_global_inv.savefig(os.path.join(output_dump_folder, '02_pede_after_global_inv_scan.png'))
print(f"- Saved pedestal plot after global inverted reference voltage scan to {os.path.join(output_dump_folder, '02_pede_after_global_inv_scan.png')}")
# * --- Coarse pedestal trim tuning with inverted reference voltage -------------

caliblibX.tune_chn_trim_inv(best_chn_trim, adc_mean_list, half_avg_list, pede_tolerance, pede_trim_step_size)

for _tune_attempt in range(pede_trim_coarse_attempt_number):

    print(f"- Tune Attempt {_tune_attempt + 1} / {pede_trim_coarse_attempt_number}:")

    for _asic in range(total_asic):
        _asic_i2c_settings = register_settings_list[_asic]
        if not _asic_i2c_settings.set_chn_trim_inv_all(best_chn_trim[_asic]):
            print(f"Error: Failed to set Pedestal Trim for ASIC {_asic}.")
        _asic_i2c_settings.send_all_channel_registers(udp_target)

    time.sleep(delay_after_setting_i2c)

    adc_mean_list, adc_err_list = caliblibX.measure_adc(udp_target, total_asic, machine_gun, expected_event_number, i2c_fragment_life, i2c_retry, _verbose=False)

    caliblibX.print_adc_to_terminal(adc_mean_list, adc_err_list)
    half_avg_list, half_err_list = caliblibX.calculate_half_average_adc(adc_mean_list, adc_err_list, total_asic, dead_channels)

    if _tune_attempt < pede_trim_coarse_attempt_number - 1:
        caliblibX.tune_chn_trim_inv(best_chn_trim, adc_mean_list, half_avg_list, pede_tolerance, pede_trim_step_size)
    else:
        fig_pede_after_global_inv, ax_pede_after_global_inv = caliblibX.plot_channel_adc(adc_mean_list, adc_err_list, 'Coarse Pedestal Trim', dead_channels, half_avg_list)
        fig_pede_after_global_inv.savefig(os.path.join(output_dump_folder, '03_coarse_pede_trim.png'))
        print(f"- Saved pedestal plot after global inverted reference voltage scan to {os.path.join(output_dump_folder, '03_coarse_pede_trim.png')}")

# * --- Fine inv_vref scan ---------------------------------------------------
global_inv_scan_range_min = min(best_inv_vref_coarse) - 20
global_inv_scan_range_max = max(best_inv_vref_coarse) + 100
if global_inv_scan_range_min < 0:
    global_inv_scan_range_min = 0
if global_inv_scan_range_max > 1023:
    global_inv_scan_range_max = 1023
global_scan_fine = range(global_inv_scan_range_min, global_inv_scan_range_max, 5)
scan_global_inv_ref_adc_avg_fine = np.zeros((2*total_asic, len(global_scan_fine)), dtype=float)
scan_global_inv_ref_adc_err_fine = np.zeros((2*total_asic, len(global_scan_fine)), dtype=float)

for _ref_inv in global_scan_fine:
    print(f"- Setting Inverted Vref to {_ref_inv}")
    for _asic in range(total_asic):
        _asic_i2c_settings = register_settings_list[_asic]
        if not _asic_i2c_settings.set_inv_vref(_ref_inv, 0):
            print(f"Error: Failed to set Inverted Vref 0 for ASIC {_asic}.")
        if not _asic_i2c_settings.set_inv_vref(_ref_inv, 1):
            print(f"Error: Failed to set Inverted Vref 1 for ASIC {_asic}.")

        _asic_i2c_settings.send_reference_voltage_0_register(udp_target)
        _asic_i2c_settings.send_reference_voltage_1_register(udp_target)

    time.sleep(delay_after_setting_i2c)
    adc_mean_list, adc_err_list = caliblibX.measure_adc(udp_target, total_asic, machine_gun, expected_event_number, i2c_fragment_life, i2c_retry, _verbose=False)

    caliblibX.print_adc_to_terminal(adc_mean_list, adc_err_list)
    half_avg_list, half_err_list = caliblibX.calculate_half_average_adc(adc_mean_list, adc_err_list, total_asic, dead_channels)
    for _half in range(2*total_asic):
        scan_global_inv_ref_adc_avg_fine[_half, global_scan_fine.index(_ref_inv)] = half_avg_list[_half]
        scan_global_inv_ref_adc_err_fine[_half, global_scan_fine.index(_ref_inv)] = half_err_list[_half]

for _half in range(2*total_asic):
    adc_values = scan_global_inv_ref_adc_avg_fine[_half, :]
    diffs = np.abs(adc_values - target_pedestal)
    best_index = np.argmin(diffs)
    best_inv_vref = list(global_scan_fine)[best_index]
    best_inv_vref_fine.append(best_inv_vref)
    print(f"-- Half {_half}: Best Inverted Vref = {best_inv_vref}, Achieved Pedestal = {adc_values[best_index]:.2f}")

fig_global_inv_fine, axs_global_inv_fine = plt.subplots(1, 1, figsize=(10, 6))
for _half in range(2*total_asic):
    axs_global_inv_fine.errorbar(
        list(global_scan_fine),
        scan_global_inv_ref_adc_avg_fine[_half, :],
        yerr=scan_global_inv_ref_adc_err_fine[_half, :],
        label=f'Half {_half}'
    )
    # draw the best point as a vertical line
    best_inv_vref = best_inv_vref_fine[_half]
    axs_global_inv_fine.axvline(x=best_inv_vref, color='r', linestyle='--', alpha=0.5)
axs_global_inv_fine.set_title('Fine Scan of Inverted Reference Voltage')
axs_global_inv_fine.set_xlabel('Inverted Reference Voltage Setting')
axs_global_inv_fine.set_ylabel('Average ADC Value')
axs_global_inv_fine.legend()
fig_global_inv_fine.tight_layout()
fig_global_inv_fine_path = os.path.join(output_dump_folder, '04_global_inv_ref_scan_fine.png')
fig_global_inv_fine.savefig(fig_global_inv_fine_path)
print(f"- Saved fine global inverted reference voltage scan plot to {fig_global_inv_fine_path}")

# set the best inverted reference voltage found
for _asic in range(total_asic):
    _asic_i2c_settings = register_settings_list[_asic]
    best_inv_vref_0 = best_inv_vref_fine[2*_asic]
    best_inv_vref_1 = best_inv_vref_fine[2*_asic + 1]
    if not _asic_i2c_settings.set_inv_vref(best_inv_vref_0, 0):
        print(f"Error: Failed to set Inverted Vref 0 for ASIC {_asic}.")
    if not _asic_i2c_settings.set_inv_vref(best_inv_vref_1, 1):
        print(f"Error: Failed to set Inverted Vref 1 for ASIC {_asic}.")

    _asic_i2c_settings.send_reference_voltage_0_register(udp_target)
    _asic_i2c_settings.send_reference_voltage_1_register(udp_target)

time.sleep(delay_after_setting_i2c)

adc_mean_list, adc_err_list = caliblibX.measure_adc(udp_target, total_asic, machine_gun, expected_event_number, i2c_fragment_life, i2c_retry, _verbose=False)

caliblibX.print_adc_to_terminal(adc_mean_list, adc_err_list)
halves_target_list = [target_pedestal] * 2 * total_asic

fig_pede_after_global_inv, ax_pede_after_global_inv = caliblibX.plot_channel_adc(adc_mean_list, adc_err_list, 'Fine Inverted Reference Voltage Scan', dead_channels, halves_target_list)
fig_pede_after_global_inv.savefig(os.path.join(output_dump_folder, '05_fine_inv_vref_scan.png'))
print(f"- Saved pedestal plot after fine inverted reference voltage scan to {os.path.join(output_dump_folder, '05_fine_inv_vref_scan.png')}")

# * --- Final fine tune of pedestal trim with inverted reference voltage -----
caliblibX.tune_chn_trim_inv(best_chn_trim, adc_mean_list, halves_target_list, pede_tolerance//2, pede_trim_step_size//2)

for _tune_attempt in range(pede_trim_attempt_number):
    
    print(f"- Final Tune Attempt {_tune_attempt + 1} / {pede_trim_attempt_number}:")

    for _asic in range(total_asic):
        _asic_i2c_settings = register_settings_list[_asic]
        if not _asic_i2c_settings.set_chn_trim_inv_all(best_chn_trim[_asic]):
            print(f"Error: Failed to set Pedestal Trim for ASIC {_asic}.")
        _asic_i2c_settings.send_all_channel_registers(udp_target)

    time.sleep(delay_after_setting_i2c)

    adc_mean_list, adc_err_list = caliblibX.measure_adc(udp_target, total_asic, machine_gun, expected_event_number, i2c_fragment_life, i2c_retry, _verbose=False)

    caliblibX.print_adc_to_terminal(adc_mean_list, adc_err_list)
    half_avg_list, half_err_list = caliblibX.calculate_half_average_adc(adc_mean_list, adc_err_list, total_asic, dead_channels)

    if _tune_attempt < pede_trim_attempt_number - 1:
        caliblibX.tune_chn_trim_inv(best_chn_trim, adc_mean_list, halves_target_list, pede_tolerance//2, pede_trim_step_size//2)
    else:
        fig_pede_after_global_inv, ax_pede_after_global_inv = caliblibX.plot_channel_adc(adc_mean_list, adc_err_list, 'Final Fine Pedestal Trim', dead_channels, halves_target_list)
        fig_pede_after_global_inv.savefig(os.path.join(output_dump_folder, '06_final_fine_pede_trim.png'))
        print(f"- Saved pedestal plot after final fine pedestal trim to {os.path.join(output_dump_folder, '06_final_fine_pede_trim.png')}")

# * --- Save final settings -----------------------------------------------
for _asic in range(total_asic):
    _asic_i2c_settings = register_settings_list[_asic]
    output_i2c_path = os.path.join(output_dump_folder, f'asic_{_asic}_final_i2c_settings.json')
    _asic_i2c_settings.save_to_json(output_i2c_path)
    print(f"- Saved final I2C settings for ASIC {_asic} to {output_i2c_path}")