from loguru import logger
import caliblibX
import os, json, time, argparse
import matplotlib.pyplot as plt
import termplotlib as tpl
import numpy as np

# * --- Set up script information ---------------------------------------------
script_id_str       = os.path.basename(__file__).split('.')[0]
script_version_str  = '1.2'
script_folder       = os.path.dirname(__file__)
script_info_str = "-- " + script_id_str + " (v" + script_version_str + ")"
while len(script_info_str) < 73:
    script_info_str += "-"
print(script_info_str)
print("------------------------------------------------------------------------")

# * --- Read command line arguments -------------------------------------------
parser = argparse.ArgumentParser(description='IO delay scan for HGCROC')
parser.add_argument('-i', '--i2c', type=str, help='Path to the I2C settings JSON file')
parser.add_argument('-c', '--config', type=str, help='Path to the common settings JSON file')
parser.add_argument('-t', '--target', type=int, help='Target ToA threshold (in DAC units)')
parser.add_argument('-a', '--asic', type=int, help='ASIC number to scan')
parser.add_argument('-o', '--output', type=str, help='Output folder name')

# analog settings
parser.add_argument('--rf', type=int, help='Feedback resistor setting (0-15)', default=0x08)
parser.add_argument('--cf', type=int, help='Feedback capacitor setting (0-15)', default=0x0a)
parser.add_argument('--cc', type=int, help='Current conveyor gain setting (0-15)', default=0x04)
parser.add_argument('--cfcomp', type=int, help='Feedback capacitor compensation setting (0-15)', default=0x0a)

# scan settings
parser.add_argument('--scan-pack', type=int, help='Number of channels to scan in parallel', default=8)
parser.add_argument('--scan-chn', type=int, help='Number of channels to scan per ASIC', default=72)

# ui update
parser.add_argument('--ui', type=bool, help='Enable UI updates during scan', default=False, nargs='?', const=True)
args = parser.parse_args()

# * --- Load configuration file -----------------------------------------------
output_dump_folder, output_config_path = caliblibX.output_path_setup(script_id_str, time.strftime('%Y%m%d_%H%M%S'), os.path.dirname(__file__))
output_config_json = {}

# * --- Load udp settings from config file ------------------------------------
udp_target = caliblibX.udp_target('10.1.2.207', 11000, 11001, '10.1.2.208', 11000)
if args.config:
    udp_target.load_udp_json_file(args.config)
udp_target.load_pool_json_file(os.path.join(script_folder, 'config', 'socket_pool_configX.json'))

print(f"- UDP from {args.config if args.config else 'default settings'}:")
print(f"-- PC IP: {udp_target.pc_ip}, Port: {udp_target.pc_port_cmd}/{udp_target.pc_port_data}")
print(f"-- Board IP: {udp_target.board_ip}, Port: {udp_target.board_port}")

udp_target.connect_to_pool(timeout=0.1)

# * --- Set running parameters ------------------------------------------------
total_asic = 2
if args.asic is not None:
    total_asic = int(args.asic)

# * --- Load I2C settings from file -------------------------------------------
i2c_settings = {}
if args.i2c:
    i2c_files = args.i2c.split(',')
if len(i2c_files) != total_asic and len(i2c_files) != 1:
    print(f"Error: Number of I2C files provided ({len(i2c_files)}) does not match number of ASICs to scan ({total_asic}).")
    exit()

# * --- Create base I2C settings ----------------------------------------------
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

# * --- Set running parameters ------------------------------------------------
target_toa = 50
if args.target is not None:
    target_toa = int(args.target)

print(f"- Target ToA threshold: {target_toa} DAC")

# - generator settings
i2c_retry                   = 30
i2c_fragment_life           = 3
machine_gun                 = 7
phase_setting               = 11
gen_nr_cycle                = 1
gen_interval_value          = 1000
expected_event_number       = gen_nr_cycle * (machine_gun + 1)
gen_pre_interval_value      = 15
gen_fcmd_internal_injection = 0b00101101
gen_fcmd_L1A                = 0b01001011

# - scan settings
scan_chn_pack               = 8
if args.scan_pack is not None:
    scan_chn_pack = int(args.scan_pack)
scan_asic_chn            = 76
if args.scan_chn is not None:
    scan_asic_chn = int(args.scan_chn)
scan_12b_range              = range(0, 160, 20)
scan_12b_fine_range         = range(max(int(target_toa - 27),0), int(target_toa + 27), 6)
scan_final_12b_range        = range(max(int(target_toa - 15),0), int(target_toa + 15), 3)

toa_global_threshold_ratio  = 0.4
tot_global_threshold_ratio  = 0.4

toa_channel_threshold_ratio = 0.4
tot_channel_threshold_ratio = 0.4

init_toa_global_threshold   = 140
init_tot_global_threshold   = 500

init_toa_threshold_trim     = 32
init_tot_threshold_trim     = 32

toa_turn_on_threshold = 0

dead_channel_list = []

toa_halves = [init_toa_global_threshold for _ in range(2*total_asic)]
tot_halves = [init_tot_global_threshold for _ in range(2*total_asic)]
toa_channel_trims = [init_toa_threshold_trim for _ in range(72 * total_asic)]
tot_channel_trims = [init_tot_threshold_trim for _ in range(72 * total_asic)]

_round_use_fine_scan = [False, False, True, True, True]
_round_enable_half_tuning = [True, True, False, False, False]
_round_enable_channel_tuning_reference_half = [False, True, True, False, False]
_round_enable_channel_tuning_reference_target = [False, False, False, True, True]

ui_total_steps = len(scan_12b_fine_range) * sum(_round_enable_half_tuning) + len(scan_12b_fine_range) * sum(_round_enable_channel_tuning_reference_half) + len(scan_final_12b_range) * sum(_round_enable_channel_tuning_reference_target)
ui_current_step = 0
if not args.ui:
    ui_total_steps = 0
    ui_current_step = 0

r_f_code = args.rf & 0x0F
c_f_code = args.cf & 0x0F
cc_gain_code = args.cc & 0x0F
c_f_comp_code = args.cfcomp & 0x0F

for _asic in range(total_asic):
    print(f"- Setting I2C for ASIC {_asic}...")
    _asic_i2c_settings = register_settings_list[_asic]
    try:
        if not _asic_i2c_settings.set_cf(c_f_code, 0):
            raise ValueError("Failed to set CF 0x0a to 0")
        if not _asic_i2c_settings.set_cf(c_f_code, 1):
            raise ValueError("Failed to set CF 0x0a to 1")
        if not _asic_i2c_settings.set_cf_comp(c_f_comp_code, 0):
            raise ValueError("Failed to set CF_COMP 0x0a to 0")
        if not _asic_i2c_settings.set_cf_comp(c_f_comp_code, 1):
            raise ValueError("Failed to set CF_COMP 0x0a to 1")
        if not _asic_i2c_settings.set_rf(r_f_code, 0):
            raise ValueError("Failed to set RF 0x0c to 0")
        if not _asic_i2c_settings.set_rf(r_f_code, 1):
            raise ValueError("Failed to set RF 0x0c to 1")
        if not _asic_i2c_settings.set_s_sk(0x02, 0):
            raise ValueError("Failed to set S_SK 0x02 to 0")
        if not _asic_i2c_settings.set_s_sk(0x02, 1):
            raise ValueError("Failed to set S_SK 0x02 to 1")
        if not _asic_i2c_settings.set_delay87(0x03, 0):
            raise ValueError("Failed to set DELAY87 0x03 to 0")
        if not _asic_i2c_settings.set_delay87(0x03, 1):
            raise ValueError("Failed to set DELAY87 0x03 to 1")
        if not _asic_i2c_settings.set_delay9(0x03, 0):
            raise ValueError("Failed to set DELAY9 0x03 to 0")
        if not _asic_i2c_settings.set_delay9(0x03, 1):
            raise ValueError("Failed to set DELAY9 0x03 to 1")
        if not _asic_i2c_settings.set_12b_dac(0, 0):
            raise ValueError("Failed to set 12B_DAC 0 to 0")
        if not _asic_i2c_settings.set_12b_dac(0, 1):
            raise ValueError("Failed to set 12B_DAC 0 to 1")

        if not _asic_i2c_settings.set_calibrationsc(1, 0):
            raise ValueError("Failed to set CALIBRATIONS_C 1 to 0")
        if not _asic_i2c_settings.set_calibrationsc(1, 1):
            raise ValueError("Failed to set CALIBRATIONS_C 1 to 1")
        if not _asic_i2c_settings.set_bx_offset(2, 0):
            raise ValueError("Failed to set BX_OFFSET 2 to 0")
        if not _asic_i2c_settings.set_bx_offset(2, 1):
            raise ValueError("Failed to set BX_OFFSET 2 to 1")
        
        _asic_i2c_settings.set_gain_conv(cc_gain_code)
        
        if not _asic_i2c_settings.set_phase(phase_setting):
            raise ValueError("Failed to set phase")
        _asic_i2c_settings.turn_on_daq(True)
        # _asic_i2c_settings.send_top_register(udp_target)
        # _asic_i2c_settings.print_reg("Reference_Voltage_0")
        # _asic_i2c_settings.print_reg("Reference_Voltage_1")
        # _asic_i2c_settings.print_reg("Global_Analog_0")
        # _asic_i2c_settings.print_reg("Global_Analog_1")
        _asic_i2c_settings.send_all_registers(udp_target)
    except Exception as e:
        print(f"Error setting I2C for ASIC {_asic}: {e}")

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
    gen_preimp_en       = 0x01, 
    gen_pre_interval    = gen_pre_interval_value,
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


for _scan_round in range(len(_round_use_fine_scan)):
    _round_scan_range = scan_12b_fine_range if _round_use_fine_scan[_scan_round] else scan_12b_range

    print(f"- Starting scan round {_scan_round}...")
    used_scan_values, scan_adc_list, scan_adc_error_list, scan_tot_list, scan_tot_error_list, scan_toa_list, scan_toa_error_list, ui_current_step = caliblibX.Scan_12b(
        udp_target, _round_scan_range, total_asic, scan_chn_pack, scan_asic_chn,machine_gun, expected_event_number, i2c_fragment_life, dead_channel_list, register_settings_list, toa_halves, tot_halves, toa_channel_trims, tot_channel_trims, i2c_retry, _total_steps = ui_total_steps, _current_step = ui_current_step
    )

    if scan_adc_list is None:
        print(f"Error: Scan failed for ASIC {_asic}.")

    scan_adc_list_np = np.array(scan_adc_list).transpose().transpose()
    scan_tot_list_np = np.array(scan_tot_list).transpose().transpose()
    scan_toa_list_np = np.array(scan_toa_list).transpose().transpose()

    toa_turn_on  = caliblibX.TurnOnPoints(scan_toa_list_np, used_scan_values, toa_turn_on_threshold)
    half_turn_on = caliblibX.HalfTurnOnAverage(toa_turn_on, [], dead_channel_list, total_asic)
    half_turn_on[np.isnan(half_turn_on)] = target_toa

    if args.ui:
        for _asic in range(total_asic):
            toa_turn_on_asic = toa_turn_on[_asic*76:(_asic+1)*76]
            toa_turn_on_asic_valid = caliblibX.channel_list_remove_cm_calib(toa_turn_on_asic)
            print(f"ui_asic{_asic}: " + " ".join([f"{int(x):3d}" for x in toa_turn_on_asic_valid]))

    fig_adc, ax_adc = caliblibX.Draw2DIM("ADC Values", "Channel Number", "12b DAC Value", total_asic, scan_adc_list_np, os.path.join(output_dump_folder, f"scan{_scan_round}_val0.pdf"), [str(x) for x in used_scan_values], _data_saving_path = os.path.join(output_dump_folder, f"scan{_scan_round}_val0.csv"), _image_saving_path = os.path.join(output_dump_folder, f"scan{_scan_round}_val0.png"))
    plt.close(fig_adc)
    fig_tot, ax_tot = caliblibX .Draw2DIM("ToT Values", "Channel Number", "12b DAC Value", total_asic, scan_tot_list_np, os.path.join(output_dump_folder, f"scan{_scan_round}_val1.pdf"), [str(x) for x in used_scan_values], _data_saving_path = os.path.join(output_dump_folder, f"scan{_scan_round}_val1.csv"), _image_saving_path = os.path.join(output_dump_folder, f"scan{_scan_round}_val1.png"))
    plt.close(fig_tot)
    fig_toa, ax_toa = caliblibX.Draw2DIM("ToA Values", "Channel Number", "12b DAC Value", total_asic, scan_toa_list_np, os.path.join(output_dump_folder, f"scan{_scan_round}_val2.pdf"), [str(x) for x in used_scan_values], _data_saving_path = os.path.join(output_dump_folder, f"scan{_scan_round}_val2.csv"), _turn_on_points=toa_turn_on, _image_saving_path = os.path.join(output_dump_folder, f"scan{_scan_round}_val2.png"))
    plt.close(fig_toa)

    # * Update the half-wise ToA thresholds
    if _round_enable_half_tuning[_scan_round]:
        for _half in range(total_asic * 2):
            toa_halves[_half] += int(toa_global_threshold_ratio * (target_toa - half_turn_on[_half]))
            if toa_halves[_half] < 0:
                toa_halves[_half] = 0
            elif toa_halves[_half] > 1023:
                toa_halves[_half] = 1023

    # * Update the channel-wise ToA trims
    if _round_enable_channel_tuning_reference_half[_scan_round]:
        for _asic in range(total_asic):
            for _chn in range(76):
                _chn_valid = caliblibX.single_channel_index_remove_cm_calib(_chn)
                if _chn_valid == -1 or _chn_valid in dead_channel_list:
                    continue
                toa_channel_trims[_asic * 72 + _chn_valid] += int(toa_channel_threshold_ratio * (toa_turn_on[_asic*76 + _chn] - half_turn_on[_asic*2 + (_chn // 38)]))
                if toa_channel_trims[_asic * 72 + _chn_valid] < 0:
                    toa_channel_trims[_asic * 72 + _chn_valid] = 0
                elif toa_channel_trims[_asic * 72 + _chn_valid] > 63:
                    toa_channel_trims[_asic * 72 + _chn_valid] = 63

    if _round_enable_channel_tuning_reference_target[_scan_round]:
        for _asic in range(total_asic):
            for _chn in range(76):
                _chn_valid = caliblibX.single_channel_index_remove_cm_calib(_chn)
                if _chn_valid == -1 or _chn_valid in dead_channel_list:
                    continue
                toa_channel_trims[_asic * 72 + _chn_valid] += int(toa_channel_threshold_ratio * (toa_turn_on[_asic*76 + _chn] - target_toa))
                if toa_channel_trims[_asic * 72 + _chn_valid] < 0:
                    toa_channel_trims[_asic * 72 + _chn_valid] = 0
                elif toa_channel_trims[_asic * 72 + _chn_valid] > 63:
                    toa_channel_trims[_asic * 72 + _chn_valid] = 63

# show the final scan result
used_scan_values, scan_adc_list, scan_adc_error_list, scan_tot_list, scan_tot_error_list, scan_toa_list, scan_toa_error_list, ui_current_step = caliblibX.Scan_12b(
    udp_target, scan_12b_fine_range, total_asic, scan_chn_pack, scan_asic_chn, machine_gun, expected_event_number, i2c_fragment_life, dead_channel_list, register_settings_list, toa_halves, tot_halves, toa_channel_trims, tot_channel_trims, i2c_retry, _total_steps = ui_total_steps, _current_step = ui_current_step
)

if scan_adc_list is None:
    print(f"Error: Final scan failed for ASIC {_asic}.")

scan_adc_list_np = np.array(scan_adc_list).transpose().transpose()
scan_tot_list_np = np.array(scan_tot_list).transpose().transpose()
scan_toa_list_np = np.array(scan_toa_list).transpose().transpose()

half_turn_on = caliblibX.HalfTurnOnAverage(caliblibX.TurnOnPoints(scan_toa_list_np, used_scan_values, toa_turn_on_threshold), [], dead_channel_list, total_asic)
half_turn_on[np.isnan(half_turn_on)] = target_toa

if args.ui:
    for _asic in range(total_asic):
        toa_turn_on_asic = caliblibX.TurnOnPoints(scan_toa_list_np, used_scan_values, toa_turn_on_threshold)[_asic*76:(_asic+1)*76]
        toa_turn_on_asic_valid = caliblibX.channel_list_remove_cm_calib(toa_turn_on_asic)
        print(f"ui_asic{_asic}: " + " ".join([f"{int(x):3d}" for x in toa_turn_on_asic_valid]))

fig_adc, ax_adc = caliblibX.Draw2DIM("Final ADC Values", "Channel Number", "12b DAC Value", total_asic, scan_adc_list_np, os.path.join(output_dump_folder, f"final_scan_val0.pdf"), [str(x) for x in used_scan_values], _data_saving_path = os.path.join(output_dump_folder, f"final_scan_val0.csv"), _image_saving_path = os.path.join(output_dump_folder, f"final_scan_val0.png"))
plt.close(fig_adc)
fig_tot, ax_tot = caliblibX.Draw2DIM("Final ToT Values", "Channel Number", "12b DAC Value", total_asic, scan_tot_list_np, os.path.join(output_dump_folder, f"final_scan_val1.pdf"), [str(x) for x in used_scan_values], _data_saving_path = os.path.join(output_dump_folder, f"final_scan_val1.csv"), _image_saving_path = os.path.join(output_dump_folder, f"final_scan_val1.png"))
plt.close(fig_tot)
fig_toa, ax_toa = caliblibX.Draw2DIM("Final ToA Values", "Channel Number", "12b DAC Value", total_asic, scan_toa_list_np, os.path.join(output_dump_folder, f"final_scan_val2.pdf"), [str(x) for x in used_scan_values], _data_saving_path = os.path.join(output_dump_folder, f"final_scan_val2.csv"), _turn_on_points=caliblibX.TurnOnPoints(scan_toa_list_np, used_scan_values, toa_turn_on_threshold), _image_saving_path = os.path.join(output_dump_folder, f"final_scan_val2.png"))
plt.close(fig_toa)

# * --- Save final calibration settings ---------------------------------------
for _asic in range(total_asic):
    final_i2c_settings = register_settings_list[_asic]
    for _half in range(2):
        final_i2c_settings.set_toa_vref(toa_halves[_asic*2 + _half], _half)
        final_i2c_settings.set_tot_vref(tot_halves[_asic*2 + _half], _half)
    for _chn in range(72):
        final_i2c_settings.set_chn_trim_toa(_chn, toa_channel_trims[_asic*72 + _chn])
        final_i2c_settings.set_chn_trim_tot(_chn, tot_channel_trims[_asic*72 + _chn])
    final_i2c_settings.save_to_json(os.path.join(output_dump_folder, f"asic{_asic}_final_calib_i2c.json"))
    json_full_path = os.path.join(output_dump_folder, f"asic{_asic}_final_calib_i2c.json")
    print(f"- Saved final I2C settings for ASIC {_asic} to {json_full_path}")

if args.ui:
    print("ui_progress:100")