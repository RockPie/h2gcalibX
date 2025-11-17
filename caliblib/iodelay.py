import packetlib
import time
import numpy as np

def delay_test(_cmd_out_conn, _cmd_in_conn, _h2gcroc_ip, _h2gcroc_port, _fpga_addr, _delay_setting, _asic_index, _asic_sel, _locked_pattern = 0xaccccccc,_test_trigger_lines=False, _test_cycles=50, _verbose=False):
 
 
    if not packetlib.set_bitslip(_cmd_out_conn, _cmd_in_conn, _h2gcroc_ip, _h2gcroc_port, fpga_addr=_fpga_addr, asic_num=_asic_index, io_dly_sel=_asic_sel, a0_io_dly_val_fclk=0x000, a0_io_dly_val_fcmd=0x400, a1_io_dly_val_fclk=0x000, a1_io_dly_val_fcmd=0x400, a0_io_dly_val_tr0=_delay_setting, a0_io_dly_val_tr1=_delay_setting, a0_io_dly_val_tr2=_delay_setting, a0_io_dly_val_tr3=_delay_setting, a0_io_dly_val_dq0=_delay_setting, a0_io_dly_val_dq1=_delay_setting, a1_io_dly_val_tr0=_delay_setting, a1_io_dly_val_tr1=_delay_setting, a1_io_dly_val_tr2=_delay_setting, a1_io_dly_val_tr3=_delay_setting, a1_io_dly_val_dq0=_delay_setting, a1_io_dly_val_dq1=_delay_setting, verbose=False):
        print('\033[33m' + "Warning in setting bitslip 0" + '\033[0m')
    if not packetlib.send_reset_adj(_cmd_out_conn, _h2gcroc_ip, _h2gcroc_port,fpga_addr=_fpga_addr, asic_num=_asic_index, sw_hard_reset_sel=0x00, sw_hard_reset=0x00,sw_soft_reset_sel=0x00, sw_soft_reset=0x00, sw_i2c_reset_sel=0x00,sw_i2c_reset=0x00, reset_pack_counter=0x00, adjustable_start=_asic_sel, verbose=False):
        print('\033[33m' + "Warning in sending reset_adj" + '\033[0m')

    # time.sleep(0.05)

    _all_lines_locked = True

    for _cycle in range(_test_cycles):
        _debug_info = packetlib.get_debug_data(_cmd_out_conn, _cmd_in_conn, _h2gcroc_ip, _h2gcroc_port, fpga_addr=_fpga_addr, asic_num=_asic_index, verbose=False)

        _str_info = "Delay " + "{:03}".format(_delay_setting) + " : "
        if _debug_info["data0_value"] == _locked_pattern:
            _str_info += '\033[32m' + "D0 " + '\033[0m'
        else:
            _str_info += '\033[31m' + "D0 " + '\033[0m'
            _all_lines_locked = False
        if _debug_info["data1_value"] == _locked_pattern:
            _str_info += '\033[32m' + "D1 " + '\033[0m'
        else:
            _str_info += '\033[31m' + "D1 " + '\033[0m'
            _all_lines_locked = False
        
        if _test_trigger_lines:
            if _debug_info["trg0_value"] == _locked_pattern:
                _str_info += '\033[32m' + "T0 " + '\033[0m'
            else:
                _str_info += '\033[31m' + "T0 " + '\033[0m'
                _all_lines_locked = False
            if _debug_info["trg1_value"] == _locked_pattern:
                _str_info += '\033[32m' + "T1 " + '\033[0m'
            else:
                _str_info += '\033[31m' + "T1 " + '\033[0m'
                _all_lines_locked = False
            if _debug_info["trg2_value"] == _locked_pattern:
                _str_info += '\033[32m' + "T2 " + '\033[0m'
            else:
                _str_info += '\033[31m' + "T2 " + '\033[0m'
                _all_lines_locked = False
            if _debug_info["trg3_value"] == _locked_pattern:
                _str_info += '\033[32m' + "T3 " + '\033[0m'
            else:
                _str_info += '\033[31m' + "T3 " + '\033[0m'
                _all_lines_locked = False
        
        if not _all_lines_locked:
            break
    
    if _verbose:
        print(_str_info)

    return _all_lines_locked

def quick_iodelay_setting(_cmd_out_conn, _cmd_in_conn, _h2gcroc_ip, _h2gcroc_port, _fpga_addr, _asic_num, _good_setting_window_len=20, _locked_pattern = 0xaccccccc,_test_trigger_lines=False, _test_cycles=50, _verbose=False):
    """
    This function is used to set the iodelay of the ASICs very quickly.
    It will not be the global optimal setting, but usually good enough for calibration.
    """ 
    _good_settings = []
    _asic_sel = (1 << _asic_num) - 1
    for _asic_index in range(_asic_num):
        
        _tested_results = np.zeros(_good_setting_window_len, dtype=bool)
        for _delay_setting in range(0, 512, 1):
            _all_lines_locked = delay_test(_cmd_out_conn, _cmd_in_conn, _h2gcroc_ip, _h2gcroc_port, _fpga_addr, _delay_setting, _asic_index, _asic_sel, _locked_pattern=_locked_pattern,_test_trigger_lines=_test_trigger_lines, _test_cycles=_test_cycles, _verbose=_verbose)
            # pop the oldest result and push the new result
            _tested_results = np.roll(_tested_results, -1)
            _tested_results[-1] = _all_lines_locked
            # print(_tested_results)
            # check if all are true
            if np.all(_tested_results):
                # if all are true, set the iodelay to the middle of the window
                _good_setting = _delay_setting - int(_good_setting_window_len/2)
                _last_tested_result = delay_test(_cmd_out_conn, _cmd_in_conn, _h2gcroc_ip, _h2gcroc_port, _fpga_addr, _good_setting, _asic_index, 0x00, _locked_pattern=_locked_pattern,_test_trigger_lines=_test_trigger_lines, _test_cycles=_test_cycles, _verbose=_verbose)
                if _last_tested_result:
                    if _verbose:
                        print("Good setting found: " + str(_good_setting))
                    _good_settings.append(_good_setting)
                    break
                else:
                    _tested_results[-1] = False

        # if no good setting found, return -1
        if len(_good_settings) < _asic_index + 1:
            if _verbose:
                print("No good setting found for ASIC " + str(_asic_index))
            _good_settings.append(-1)

    return _good_settings