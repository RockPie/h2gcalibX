import packetlibX
import time, os, sys, socket, json, csv, uuid
import numpy as np
import pandas as pd
from matplotlib import pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from collections import deque
from collections import OrderedDict
from .clx_calib import send_register_calib

def print_err(msg):
    print(f"[clx_h2g_set] ERROR: {msg}", file=sys.stderr)
def print_info(msg):
    print(f"[clx_h2g_set] INFO: {msg}", file=sys.stdout)
def print_warn(msg):
    print(f"[clx_h2g_set] WARNING: {msg}", file=sys.stdout)

class h2gcroc_registers_full:
    def __init__(self):
        self.udp_settings       = OrderedDict()
        self.target_asic        = OrderedDict()
        self.register_settings  = OrderedDict()
        self._register_key_width = 20

    def send_register_from_key(self, udp_target, reg_key, retry=3, verbose=False):
        if reg_key not in self.register_settings:
            print_err(f"Register key {reg_key} not found in settings")
            return False
        register_data = self.register_settings[reg_key].copy()
        # if is top, get 0:8
        if "Top" in reg_key:
            register_data = register_data[0:8]
        # print("sending to asic:", self.target_asic.get("ASIC Address", 0), " register:", reg_key.ljust(self._register_key_width), " data:", " ".join(f"{b:02x}" for b in register_data))
        return send_register_calib(udp_target, self.target_asic.get("ASIC Address", 0), reg_key, register_data, retry=retry, verbose=verbose)

    def send_top_register(self, udp_target, retry=3, verbose=False):
        return self.send_register_from_key(udp_target, "Top", retry=retry, verbose=verbose)
    
    def send_global_analog_0_register(self, udp_target, retry=3, verbose=False):
        return self.send_register_from_key(udp_target, "Global_Analog_0", retry=retry, verbose=verbose)
    
    def send_global_analog_1_register(self, udp_target, retry=3, verbose=False):
        return self.send_register_from_key(udp_target, "Global_Analog_1", retry=retry, verbose=verbose)
    
    def send_reference_voltage_0_register(self, udp_target, retry=3, verbose=False):
        return self.send_register_from_key(udp_target, "Reference_Voltage_0", retry=retry, verbose=verbose)
    
    def send_reference_voltage_1_register(self, udp_target, retry=3, verbose=False):
        return self.send_register_from_key(udp_target, "Reference_Voltage_1", retry=retry, verbose=verbose)
    
    def send_master_tdc_0_register(self, udp_target, retry=3, verbose=False):
        return self.send_register_from_key(udp_target, "Master_TDC_0", retry=retry, verbose=verbose)
    
    def send_master_tdc_1_register(self, udp_target, retry=3, verbose=False):
        return self.send_register_from_key(udp_target, "Master_TDC_1", retry=retry, verbose=verbose)
    
    def send_digital_half_0_register(self, udp_target, retry=3, verbose=False):
        return self.send_register_from_key(udp_target, "Digital_Half_0", retry=retry, verbose=verbose)
    
    def send_digital_half_1_register(self, udp_target, retry=3, verbose=False):
        return self.send_register_from_key(udp_target, "Digital_Half_1", retry=retry, verbose=verbose)
    
    def send_halfwise_0_register(self, udp_target, retry=3, verbose=False):
        return self.send_register_from_key(udp_target, "HalfWise_0", retry=retry, verbose=verbose)
    
    def send_halfwise_1_register(self, udp_target, retry=3, verbose=False):
        return self.send_register_from_key(udp_target, "HalfWise_1", retry=retry, verbose=verbose)
    
    def send_channel_register(self, udp_target, channel_index, retry=3, verbose=False):
        if channel_index < 0 or channel_index > 71:
            print_err("Channel index must be between 0 and 75")
            return False
        reg_key = "Channel_" + str(channel_index)
        return self.send_register_from_key(udp_target, reg_key, retry=retry, verbose=verbose)
    
    def send_all_channel_registers(self, udp_target, retry=3, verbose=False):
        for ch_index in range(72):
            if not self.send_channel_register(udp_target, ch_index, retry=retry, verbose=verbose):
                print_err(f"[clx_calib] Failed to send channel register {ch_index}")
                return False
        return True
    
    def send_cm_register(self, udp_target, cm_index, retry=3, verbose=False):
        if cm_index < 0 or cm_index > 3:
            print_err("CM index must be between 0 and 3")
            return False
        reg_key = "CM_" + str(cm_index)
        return self.send_register_from_key(udp_target, reg_key, retry=retry, verbose=verbose)
    
    def send_calib_register(self, udp_target, calib_index, retry=3, verbose=False):
        if calib_index < 0 or calib_index > 1:
            print_err("Calib index must be between 0 and 1")
            return False
        reg_key = "CALIB_" + str(calib_index)
        return self.send_register_from_key(udp_target, reg_key, retry=retry, verbose=verbose)

    def send_all_registers(self, udp_target, retry=3, verbose=False):
        for reg_key in self.register_settings.keys():
            if "HalfWise_" in reg_key:
                continue
            if not self.send_register_from_key(udp_target, reg_key, retry=retry, verbose=verbose):
                print_err(f"[clx_calib] Failed to send register {reg_key}")
        return True

    def sync_udp_settings(self, udp_target, asic_index=0):
        self.udp_settings["IP Address"]  = udp_target.board_ip
        self.udp_settings["Port"]        = udp_target.board_port
        self.target_asic["FPGA Address"] = udp_target.board_id
        self.target_asic["ASIC Address"]   = asic_index

    def is_same_udp_settings(self, udp_target, asic_index=0):
        return (self.udp_settings.get("IP Address") == udp_target.board_ip and
                int(self.udp_settings.get("Port")) == udp_target.board_port and
                self.target_asic.get("FPGA Address") == udp_target.board_id and
                self.target_asic.get("ASIC Address") == asic_index)

    # * --- Channel Settings --- *
    def set_inputdac_all(self, input_dac_value):
        if input_dac_value < 0 or input_dac_value > 63:
            print_err("Input DAC value must be between 0 and 63")
            return False
        for ch_index in range(72):
            reg_key = f"Channel_{ch_index}"
            try:
                ch_reg = self.register_settings[reg_key]
                ch_reg[0] = (ch_reg[0] & 0xc0) | (input_dac_value & 0x3F)
            except KeyError:
                print_err(f"Channel register {reg_key} not found in settings")
                return False
        return True
            
    def set_chn_trim_inv(self, channel_index, trim_value):
        if channel_index < 0 or channel_index > 71:
            print_err("Channel index must be between 0 and 71")
            return False
        if trim_value < 0 or trim_value > 63:
            print_err("Trim value must be between 0 and 63")
            return False
        reg_key = f"Channel_{channel_index}"
        try:
            ch_reg = self.register_settings[reg_key]
            ch_reg[3] = (ch_reg[3] & 0x03) | ((trim_value & 0x3F) << 2)
        except KeyError:
            print_err(f"Channel register {reg_key} not found in settings")
            return False
        return True
    
    def set_chn_trim_inv_all(self, trim_values):
        if len(trim_values) != 72:
            print_err("Trim values list must have exactly 72 elements")
            return False
        for ch_index in range(72):
            trim_value = trim_values[ch_index]
            if not self.set_chn_trim_inv(ch_index, trim_value):
                return False
        return True

    def set_chn_trim_toa(self, channel_index, trim_value):
        if channel_index < 0 or channel_index > 71:
            print_err("Channel index must be between 0 and 71")
            return False
        if trim_value < 0 or trim_value > 63:
            print_err("Trim value must be between 0 and 63")
            return False
        reg_key = f"Channel_{channel_index}"
        try:
            ch_reg = self.register_settings[reg_key]
            ch_reg[1] = (ch_reg[1] & 0x03) | ((trim_value & 0x3F) << 2)
        except KeyError:
            print_err(f"Channel register {reg_key} not found in settings")
            return False
        return True
    
    def set_chn_trim_tot(self, channel_index, trim_value):
        if channel_index < 0 or channel_index > 71:
            print_err("Channel index must be between 0 and 71")
            return False
        if trim_value < 0 or trim_value > 63:
            print_err("Trim value must be between 0 and 63")
            return False
        reg_key = f"Channel_{channel_index}"
        try:
            ch_reg = self.register_settings[reg_key]
            ch_reg[2] = (ch_reg[2] & 0x03) | ((trim_value & 0x3F) << 2)
        except KeyError:
            print_err(f"Channel register {reg_key} not found in settings")
            return False
        return True
    
    def set_chn_lowrange(self, channel_index, enable=True):
        if channel_index < 0 or channel_index > 71:
            print_err("Channel index must be between 0 and 71")
            return False
        reg_key = f"Channel_{channel_index}"
        try:
            ch_reg = self.register_settings[reg_key]
            if enable:
                ch_reg[4] = ch_reg[4] | 0x02
                # ch_reg[4] = ch_reg[4] & (~0x04)
            else:
                ch_reg[4] = ch_reg[4] & (~0x02)
                # ch_reg[4] = ch_reg[4] | 0x04
        except KeyError:
            print_err(f"Channel register {reg_key} not found in settings")
            return False
        return True
    
    def set_chn_highrange(self, channel_index, enable=True):
        if channel_index < 0 or channel_index > 71:
            print_err("Channel index must be between 0 and 71")
            return False
        reg_key = f"Channel_{channel_index}"
        try:
            ch_reg = self.register_settings[reg_key]
            if enable:
                ch_reg[4] = ch_reg[4] | 0x04
                # ch_reg[4] = ch_reg[4] & (~0x02)
            else:
                ch_reg[4] = ch_reg[4] & (~0x04)
                # ch_reg[4] = ch_reg[4] | 0x02
        except KeyError:
            print_err(f"Channel register {reg_key} not found in settings")
            return False
        return True
    
    def set_chn_sign_dac(self, channel_index, sign_dac_value=True):
        if channel_index < 0 or channel_index > 71:
            print_err("Channel index must be between 0 and 71")
            return False
        reg_key = f"Channel_{channel_index}"
        try:
            ch_reg = self.register_settings[reg_key]
            if sign_dac_value:
                ch_reg[14] = ch_reg[14] | 0x40
            else:
                ch_reg[14] = ch_reg[14] & (~0x40)
        except KeyError:
            print_err(f"Channel register {reg_key} not found in settings")
            return False
        return True
    
    def set_chn_gain_conv2(self, channel_index, gain_value=True):
        if channel_index < 0 or channel_index > 71:
            print_err("Channel index must be between 0 and 71")
            return False
        reg_key = f"Channel_{channel_index}"
        try:
            ch_reg = self.register_settings[reg_key]
            if gain_value:
                ch_reg[14] = ch_reg[14] | 0x80
            else:
                ch_reg[14] = ch_reg[14] & (~0x80)
        except KeyError:
            print_err(f"Channel register {reg_key} not found in settings")
            return False
        return True
    
    def set_chn_gain_conv1(self, channel_index, gain_value=True):
        # bit7 of reg#0
        if channel_index < 0 or channel_index > 71:
            print_err("Channel index must be between 0 and 71")
            return False
        reg_key = f"Channel_{channel_index}"
        try:
            ch_reg = self.register_settings[reg_key]
            if gain_value:
                ch_reg[0] = ch_reg[0] | 0x80
            else:
                ch_reg[0] = ch_reg[0] & (~0x80)
        except KeyError:
            print_err(f"Channel register {reg_key} not found in settings")
            return False
        return True
    
    def set_chn_gain_conv0(self, channel_index, gain_value=True):
        # bit6 of reg#0
        if channel_index < 0 or channel_index > 71:
            print_err("Channel index must be between 0 and 71")
            return False
        reg_key = f"Channel_{channel_index}"
        try:
            ch_reg = self.register_settings[reg_key]
            if gain_value:
                ch_reg[0] = ch_reg[0] | 0x40
            else:
                ch_reg[0] = ch_reg[0] & (~0x40)
        except KeyError:
            print_err(f"Channel register {reg_key} not found in settings")
            return False
        return True
    
    # * --- Reference Voltage Settings --- *
    def set_inv_vref(self, vref_value, half_index):
        if vref_value < 0 or vref_value > 1023:
            print_err("VREF value must be between 0 and 1023")
            return False
        if half_index not in [0, 1]:
            print_err("Half index must be 0 or 1")
            return False
        reg_key = f"Reference_Voltage_{half_index}"
        try:
            vref_reg = self.register_settings[reg_key]
            # bit 2-3 of reg#1
            vref_reg[1] = (vref_reg[0] & 0xF3) | (( vref_value & 0x03) << 2)
            # bit 0-7 of reg#4
            vref_reg[4] = (vref_reg[4] & 0x00) | ((vref_value >> 2) & 0xFF)
        except KeyError:
            print_err(f"Reference Voltage register {reg_key} not found in settings")
            return False
        return True
    
    def set_noinv_vref(self, vref_value, half_index):
        if vref_value < 0 or vref_value > 1023:
            print_err("VREF value must be between 0 and 1023")
            return False
        if half_index not in [0, 1]:
            print_err("Half index must be 0 or 1")
            return False
        reg_key = f"Reference_Voltage_{half_index}"
        try:
            vref_reg = self.register_settings[reg_key]
            # bit 0-1 of reg#1
            vref_reg[1] = (vref_reg[0] & 0xFC) | (( vref_value & 0x03) << 0)
            # bit 0-7 of reg#5
            vref_reg[5] = (vref_reg[5] & 0x00) | ((vref_value >> 2) & 0xFF)
        except KeyError:
            print_err(f"Reference Voltage register {reg_key} not found in settings")
            return False
        return True
    
    def set_toa_vref(self, vref_value, half_index):
        if vref_value < 0 or vref_value > 1023:
            print_err("VREF value must be between 0 and 1023")
            return False
        if half_index not in [0, 1]:
            print_err("Half index must be 0 or 1")
            return False
        reg_key = f"Reference_Voltage_{half_index}"
        try:
            vref_reg = self.register_settings[reg_key]
            # bit 9-2 in reg#3
            vref_reg[3] = (vref_value & 0xFC) >> 2
            # bit 1-0 in reg#1 bit 5-4
            vref_reg[1] = (vref_reg[1] & 0xCF) | ((vref_value & 0x03) << 4)
        except KeyError:
            print_err(f"Reference Voltage register {reg_key} not found in settings")
            return False
        return True
    
    def set_tot_vref(self, vref_value, half_index):
        if vref_value < 0 or vref_value > 1023:
            print_err("VREF value must be between 0 and 1023")
            return False
        if half_index not in [0, 1]:
            print_err("Half index must be 0 or 1")
            return False
        reg_key = f"Reference_Voltage_{half_index}"
        try:
            vref_reg = self.register_settings[reg_key]
            # bit 9-2 in reg#2
            vref_reg[2] = (vref_value & 0xFC) >> 2
            # bit 1-0 in reg#1 bit 7-6
            vref_reg[1] = (vref_reg[1] & 0x3F) | ((vref_value & 0x03) << 6)
        except KeyError:
            print_err(f"Reference Voltage register {reg_key} not found in settings")
            return False
        return True
    
    def set_12b_dac(self, dac_value, half_index):
        if dac_value < 0 or dac_value > 4095:
            print_err("12b DAC value must be between 0 and 4095")
            return False
        if half_index not in [0, 1]:
            print_err("Half index must be 0 or 1")
            return False
        reg_key = f"Reference_Voltage_{half_index}"
        try:
            reference_reg = self.register_settings[reg_key]
            # lower 8 bits to reg#6
            reference_reg[6] = dac_value & 0xFF
            # upper 4 bits to reg#7
            reference_reg[7] = (reference_reg[7] & 0xF0) | ((dac_value >> 8) & 0x0F)
        except KeyError:
            print_err(f"Reference Voltage register {reg_key} not found in settings")
            return False
        return True
    
    def set_12b_dac_2v5(self, dac_value, half_index):
        # 12-bit value, reg# 9 for bit7-0, reg#10 bit 3-0 for bit 11-8
        if dac_value < 0 or dac_value > 4095:
            print_err("12b DAC value must be between 0 and 4095")
            return False
        if half_index not in [0, 1]:
            print_err("Half index must be 0 or 1")
            return False
        reg_key = f"Reference_Voltage_{half_index}"
        try:
            reference_reg = self.register_settings[reg_key]
            # lower 8 bits to reg#9
            reference_reg[9] = dac_value & 0xFF
            # upper 4 bits to reg#10
            reference_reg[10] = (reference_reg[10] & 0xF0) | ((dac_value >> 8) & 0x0F)
        except KeyError:
            print_err(f"Reference Voltage register {reg_key} not found in settings")
            return False
        return True
    
    def set_intctest(self, enable, half_index):
        if half_index not in [0, 1]:
            print_err("Half index must be 0 or 1")
            return False
        reg_key = f"Reference_Voltage_{half_index}"
        try:
            reference_reg = self.register_settings[reg_key]
            if enable:
                reference_reg[7] = reference_reg[7] | 0x40
                reference_reg[7] = reference_reg[7] & (~0x80)
            else:
                reference_reg[7] = reference_reg[7] & (~0x40)
                reference_reg[7] = reference_reg[7] | 0x80
        except KeyError:
            print_err(f"Reference Voltage register {reg_key} not found in settings")
            return False
        return True
    
    def set_extctest(self, enable, half_index):
        self.set_intctest(not enable, half_index)

    def set_extctest_2v5(self, enable, half_index):
        if half_index not in [0, 1]:
            print_err("Half index must be 0 or 1")
            return False
        reg_key = f"Reference_Voltage_{half_index}"
        try:
            reference_reg = self.register_settings[reg_key]
            if enable:
                reference_reg[10] = reference_reg[10] | 0x20
            else:
                reference_reg[10] = reference_reg[10] & (~0x20)
        except KeyError:
            print_err(f"Reference Voltage register {reg_key} not found in settings")
            return False
        return True
    
    def set_choice_cinj(self, use_cinj, half_index):
        if half_index not in [0, 1]:
            print_err("Half index must be 0 or 1")
            return False
        reg_key = f"Reference_Voltage_{half_index}"
        try:
            reference_reg = self.register_settings[reg_key]
            if use_cinj:
                reference_reg[10] = reference_reg[10] | 0x40
            else:
                reference_reg[10] = reference_reg[10] & (~0x40)
        except KeyError:
            print_err(f"Reference Voltage register {reg_key} not found in settings")
            return False
        return True
    
    # * --- Global Analog Settings --- *

    def set_gain_conv3(self, gain_value, half_index):
        # 1-bit value, bit7 of reg#0
        if gain_value not in [0, 1]:
            print_err("Gain conv3 value must be 0 or 1")
            return False
        if half_index not in [0, 1]:
            print_err("Half index must be 0 or 1")
            return False
        reg_key = f"Global_Analog_{half_index}"
        try:
            ga_reg = self.register_settings[reg_key]
            if gain_value == 1:
                ga_reg[0] = ga_reg[0] | 0x80
            else:
                ga_reg[0] = ga_reg[0] & (~0x80)
        except KeyError:
            print_err(f"Global Analog register {reg_key} not found in settings")
            return False
        return True

    def set_cf_comp(self, comp_value, half_index):
        # 4-bit value
        if comp_value < 0 or comp_value > 15:
            print_err("Comp value must be between 0 and 15")
            return False
        if half_index not in [0, 1]:
            print_err("Half index must be 0 or 1")
            return False
        reg_key = f"Global_Analog_{half_index}"
        try:
            ga_reg = self.register_settings[reg_key]
            ga_reg[8] = (ga_reg[8] & 0x0F) | ((comp_value & 0x0F) << 4)
        except KeyError:
            print_err(f"Global Analog register {reg_key} not found in settings")
            return False
        return True
    
    def set_cf(self, cf_value, half_index):
        # 4-bit value
        if cf_value < 0 or cf_value > 15:
            print_err("CF value must be between 0 and 15")
            return False
        if half_index not in [0, 1]:
            print_err("Half index must be 0 or 1")
            return False
        reg_key = f"Global_Analog_{half_index}"
        try:
            ga_reg = self.register_settings[reg_key]
            ga_reg[9] = (ga_reg[9] & 0xF0) | (cf_value & 0x0F)
        except KeyError:
            print_err(f"Global Analog register {reg_key} not found in settings")
            return False
        return True
    
    def set_rf(self, rf_value, half_index):
        # 4-bit value
        if rf_value < 0 or rf_value > 15:
            print_err("RF value must be between 0 and 15")
            return False
        if half_index not in [0, 1]:
            print_err("Half index must be 0 or 1")
            return False
        reg_key = f"Global_Analog_{half_index}"
        try:
            ga_reg = self.register_settings[reg_key]
            ga_reg[9] = (ga_reg[9] & 0x0F) | ((rf_value & 0x0F) << 4)
        except KeyError:
            print_err(f"Global Analog register {reg_key} not found in settings")
            return False
        return True
    
    def set_s_sk(self, s_sk_value, half_index):
        # 3-bit value, bit 7-5 for reg#10
        if s_sk_value < 0 or s_sk_value > 7:
            print_err("S_sk value must be between 0 and 7")
            return False
        if half_index not in [0, 1]:
            print_err("Half index must be 0 or 1")
            return False
        reg_key = f"Global_Analog_{half_index}"
        try:
            ga_reg = self.register_settings[reg_key]
            ga_reg[10] = (ga_reg[10] & 0x1F) | ((s_sk_value & 0x07) << 5)
        except KeyError:
            print_err(f"Global Analog register {reg_key} not found in settings")
            return False
        return True
    
    def set_delay87(self, delay_value, half_index):
        # 3-bit value, bit 4-2 of reg#14
        if delay_value < 0 or delay_value > 7:
            print_err("Delay87 value must be between 0 and 7")
            return False
        if half_index not in [0, 1]:
            print_err("Half index must be 0 or 1")
            return False
        reg_key = f"Global_Analog_{half_index}"
        try:
            ga_reg = self.register_settings[reg_key]
            ga_reg[14] = (ga_reg[14] & 0xE3) | ((delay_value & 0x07) << 2)
        except KeyError:
            print_err(f"Global Analog register {reg_key} not found in settings")
            return False
        return True
    
    def set_delay9(self, delay_value, half_index):
        # 3-bit value, bit 7-5 of reg#14
        if delay_value < 0 or delay_value > 7:
            print_err("Delay9 value must be between 0 and 7")
            return False
        if half_index not in [0, 1]:
            print_err("Half index must be 0 or 1")
            return False
        reg_key = f"Global_Analog_{half_index}"
        try:
            ga_reg = self.register_settings[reg_key]
            ga_reg[14] = (ga_reg[14] & 0x1F) | ((delay_value & 0x07) << 5)
        except KeyError:
            print_err(f"Global Analog register {reg_key} not found in settings")
            return False
        return True
    

    # * --- Digital Half Settings --- *
    def set_bx_offset(self, bx_offset_value, half_index):
        # 12-bit value
        if bx_offset_value < 0 or bx_offset_value > 4095:
            print_err("BX offset value must be between 0 and 4095")
            return False
        try:
            dh_reg = self.register_settings[f"Digital_Half_{half_index}"]
            dh_reg[25] = bx_offset_value & 0xFF
            dh_reg[26] = (dh_reg[26] & 0xF0) | ((bx_offset_value >> 8) & 0x0F)
        except KeyError:
            print_err(f"Digital Half register Digital_Half_{half_index} not found in settings")
            return False
        return True
    
    def set_calibrationsc(self, calib_scale_value, half_index):
        # 1-bit value of bit 6 of register 4
        if calib_scale_value not in [0, 1]:
            print_err("Calibration scale value must be 0 or 1")
            return False
        try:
            dh_reg = self.register_settings[f"Digital_Half_{half_index}"]
            if calib_scale_value == 1:
                dh_reg[4] = dh_reg[4] | 0x40
            else:
                dh_reg[4] = dh_reg[4] & (~0x40)
        except KeyError:
            print_err(f"Digital Half register Digital_Half_{half_index} not found in settings")
            return False
        return True

    # * --- Top Settings --- *
    def turn_on_daq(self, enable=True):
        try:
            top_reg = self.register_settings["Top"]
            if enable:
                top_reg[0] = top_reg[0] | 0x03
            else:
                top_reg[0] = top_reg[0] & (~0x03)
        except KeyError:
            print_err("Top register not found in settings")
            return False
        return True
    
    def turn_off_daq(self, disable=True):
        return self.turn_on_daq(not disable)
    
    def set_phase(self, phase_value):
        if phase_value < 0 or phase_value > 15:
            print_err("Phase value must be between 0 and 255")
            return False
        try:
            top_reg = self.register_settings["Top"]
            top_reg[7] = phase_value & 0x0F
        except KeyError:
            print_err("Top register not found in settings")
            return False
        return True
    
    # * --- Combined Methods --- *
    def set_gain_conv(self, gain_value):
        # set bit0-3 to every channel   
        if gain_value < 0 or gain_value > 15:
            print_err("Gain value must be between 0 and 15")
            return False
        _gain_conv0 = (gain_value >> 0) & 0x01
        _gain_conv1 = (gain_value >> 1) & 0x01
        _gain_conv2 = (gain_value >> 2) & 0x01
        _gain_conv3 = (gain_value >> 3) & 0x01
        for ch_index in range(72):
            if not self.set_chn_gain_conv0(ch_index, _gain_conv0):
                return False
            if not self.set_chn_gain_conv1(ch_index, _gain_conv1):
                return False
            if not self.set_chn_gain_conv2(ch_index, _gain_conv2):
                return False
        for half_index in [0, 1]:
            if not self.set_gain_conv3(_gain_conv3, half_index):
                return False
        return True
    
    def print_reg(self, reg_key):
        if reg_key not in self.register_settings:
            print_err(f"Register key {reg_key} not found in settings")
            return
        register_data = self.register_settings[reg_key]
        hex_str = " ".join(f"{b:02x}" for b in register_data)
        print(f"Register {reg_key}: {hex_str}")
        

    def load_from_json(self, json_file):
        try:
            with open(json_file, 'r') as f:
                json_dict = json.load(f, object_pairs_hook=OrderedDict)
        except Exception as e:
            print_err(f"Failed to load h2gcroc registers from JSON file: {e}")
            return False

        try:
            assert "UDP Settings"      in json_dict
            assert "Target ASIC"       in json_dict
            assert "Register Settings" in json_dict
        except AssertionError:
            print_err("JSON dictionary missing required h2gcroc register keys")
            return False

        self.udp_settings = json_dict["UDP Settings"]
        self.target_asic  = json_dict["Target ASIC"]

        raw_regs = json_dict["Register Settings"]

        if raw_regs:
            self._register_key_width = max(len(k) for k in raw_regs.keys())
        else:
            self._register_key_width = 0

        self.register_settings = OrderedDict()

        for raw_key, value in raw_regs.items():
            logical_key = raw_key.rstrip()   # "Channel_0           " -> "Channel_0"

            if isinstance(value, str):
                try:
                    if value.strip() == "":
                        ba = bytearray()
                    else:
                        ba = bytearray(int(tok, 16) for tok in value.split())
                except ValueError as e:
                    print_err(f"Invalid hex string for register {logical_key}: {e}")
                    continue
            elif isinstance(value, list):
                # 也支持 [0, 0, 0, 128, ...] 这样的列表
                try:
                    ba = bytearray(int(v) & 0xFF for v in value)
                except Exception as e:
                    print_err(f"Invalid list for register {logical_key}: {e}")
                    continue
            elif isinstance(value, (bytes, bytearray)):
                ba = bytearray(value)
            else:
                print_err(f"Unsupported register value type for {logical_key}: {type(value)}")
                continue

            self.register_settings[logical_key] = ba

        return True

    def save_to_json(self, json_file):
        if self.register_settings:
            max_logical = max(len(k) for k in self.register_settings.keys())
            width = max(self._register_key_width, max_logical)
        else:
            width = self._register_key_width or 0

        reg_out = OrderedDict()
        for logical_key, value in self.register_settings.items():
            padded_key = logical_key.ljust(width)

            if isinstance(value, (bytes, bytearray)):
                hex_str = " ".join(f"{b:02x}" for b in value)
            elif isinstance(value, list):
                hex_str = " ".join(f"{int(b) & 0xFF:02x}" for b in value)
            elif isinstance(value, str):
                hex_str = value
            else:
                print_err(f"Unsupported value type when saving {logical_key}: {type(value)}")
                continue

            reg_out[padded_key] = hex_str

        self.udp_settings["Port"] = str(self.udp_settings.get("Port", 0))

        json_dict = OrderedDict({
            "UDP Settings":      self.udp_settings,
            "Target ASIC":       self.target_asic,
            "Register Settings": reg_out
        })

        try:
            with open(json_file, 'w') as f:
                json.dump(json_dict, f, indent=4)
            return True
        except Exception as e:
            print_err(f"Failed to save h2gcroc registers to JSON file: {e}")
            return False
