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
