# https://sentry.io/answers/print-colored-text-to-terminal-with-python/




# -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# Import
# -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
import socket
import binascii
import time



# -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# NumberOfASIC = 2
# ASIC_SELECT  = 3

NumberOfASIC = 2
ASIC_SELECT  = 15

ASIC0_IODly  = 16
ASIC1_IODly  = 48
ASIC2_IODly  = 25
ASIC3_IODly  = 42
ASIC4_IODly  = 32
ASIC5_IODly  = 32
ASIC6_IODly  = 32
ASIC7_IODly  = 32

SocketTimeOut = 5

# -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# Global Things
# -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

BOARD_ADDRESS = 0
HOST   ="10.1.2.207"
UDP_IP ="10.1.2.208"

# BOARD_ADDRESS = 1
# HOST   ="10.1.2.206"
# UDP_IP ="10.1.2.209"

PORT   =11000


# -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# Start...
# -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
print("")
print("-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------")
print(">>>                                                         Test Script for Aligning - 003_10G_Test_Align.py                                                                                                                                  <<<")
print("-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------")
print("")

RED     = '\033[31m'
GREEN   = '\033[32m'
YELLOW  = '\033[33m'
BLUE    = '\033[34m'
MAGENTA = '\033[35m'
CYAN    = '\033[36m'
WHITE   = '\033[37m'
RESET   = '\033[0m' # called to return to standard terminal text color




# -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# Socket Init...
# -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM , 0)
s.bind((HOST,PORT))

s.settimeout(SocketTimeOut) # Sets the socket to timeout after "SocketTimeOut" second of no activity




# -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# GetStatus, Check the communication
# -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# Position:       -6   -5   -4   -3   -2   -1   00   01   02   03   04   05   06   07   08   09   10   11   12   13   14   15   16   17   18   19   20   21   22   23   24   25   26   27   28   29   30   31   32   33   34   35   36   37   38   39")
# Position:      [   UDP COUNTER   ]  IP  PORT  00   01   02   03   04   05   06   07   08   09   10   11   12   13   14   15   16   17   18   19   20   21   22   23   24   25   26   27   28   29   30   31   32   33   34   35   36   37   38   39")
MesGetStatus   =[0x00,0x00,0x00,0x00,0x00,0x00,0xa0,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x01,0x02,0x03,0x04]

print("Get Status: (FPGA Communication)")
# print("Position:   -6   -5   -4   -3   -2   -1   00   01   02   03   04   05   06   07   08   09   10   11   12   13   14   15   16   17   18   19   20   21   22   23   24   25   26   27   28   29   30   31   32   33   34   35   36   37   38   39")
# print("Position:   [   UDP COUNTER   ]  IP  PORT   00   01   02   03   04   05   06   07   08   09   10   11   12   13   14   15   16   17   18   19   20   21   22   23   24   25   26   27   28   29   30   31   32   33   34   35   36   37   38   39")
print("Position:   [   UDP COUNTER   ]  IP  PORT  " + MAGENTA + "HDR FPGA COMM" + RESET + "   03   04   05   06   07   08   09   10   11   12   13   14   15   16   17   18   19   20   21   22   23   24   25   26   27   28   29   30   31   32   33   34   35   36   37   38   39")

MesGetStatus[7] = BOARD_ADDRESS

s.sendto(bytes(MesGetStatus), (UDP_IP, PORT))
data, add = s.recvfrom(1024)

hex_string = binascii.hexlify(data).decode('utf-8')
hex_string2 = r" 0x" + r" 0x".join(hex_string[n : n+2] for n in range(0, len(hex_string), 2))

tr_pre  = hex_string2[0:30]
tr_hdr  = MAGENTA + hex_string2[30:45] + RESET
tr_post = hex_string2[45:]
    
print("Status:    %s%s%s" % (tr_pre, tr_hdr, tr_post))
# print("Status:    %s" % (hex_string2))
print("")

time.sleep(0.5)




# -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# Read I2C Top Register
#
# Read All (NumberOfASIC) ASIC Top Registers...
# Sub-block address -> Top: 0d45
# -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# Position:       -6   -5   -4   -3   -2   -1   00   01   02   03   04   05   06   07   08   09   10   11   12   13   14   15   16   17   18   19   20   21   22   23   24   25   26   27   28   29   30   31   32   33   34   35   36   37   38   39")
# Position:      [   UDP COUNTER   ]  IP  PORT  00   01   02   03   04   05   06   07   08   09   10   11   12   13   14   15   16   17   18   19   20   21   22   23   24   25   26   27   28   29   30   31   32   33   34   35   36   37   38   39")
MesReadI2CTop  =[0x00,0x00,0x00,0x00,0x00,0x00,0xa0,0x00,0x10,0x00,0x00,0x95,0x05,0xa0,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x0f,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00]

print("Read I2C Top Register:")
# print("Position:   -6   -5   -4   -3   -2   -1   00   01   02   03   04   05   06   07   08   09   10   11   12   13   14   15   16   17   18   19   20   21   22   23   24   25   26   27   28   29   30   31   32   33   34   35   36   37   38   39")
# print("Position:   [   UDP COUNTER   ]  IP  PORT  HDR   01   02   03   04   05   06   07  RUN   09   10   11   12   13   14   15   16   17   18   19   20   21   22   23   24   25   26   27   28   29   30   31   32   33   34   35   36   37   38   39")
print("Position:   [   UDP COUNTER   ]  IP  PORT  " + MAGENTA + "HDR FPGA COMM" + RESET + "   03   04   05   06   07  " + CYAN + "RUN" + RESET + "   09   10   11   12   13   14   15   16   17   18   19   20   21   22   23   24   25   26   27   28   29   30   31   32   33   34   35   36   37   38   39")



for i in range (NumberOfASIC):
    MesReadI2CTop[6] = 160+i
    MesReadI2CTop[7] = BOARD_ADDRESS

    s.sendto(bytes(MesReadI2CTop), (UDP_IP, PORT))
    data, add = s.recvfrom(1024)
    
    hex_string = binascii.hexlify(data).decode('utf-8')
    hex_string2 = r" 0x" + r" 0x".join(hex_string[n : n+2] for n in range(0, len(hex_string), 2))

    tr_pre  = hex_string2[0:30]
    tr_hdr  = MAGENTA + hex_string2[30:45] + RESET
    tr_mid  = hex_string2[45:70]
    tr_run  = CYAN + hex_string2[70:75] + RESET
    tr_post = hex_string2[75:]
    
    print("Status (%s):%s%s%s%s%s" % (i, tr_pre, tr_hdr, tr_mid, tr_run, tr_post))
    # print("Status (%s):%s" % (i, hex_string2))

print("")
    
time.sleep(0.5)




# -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# Write the base config to all ASIC
# -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# Position:                -6   -5   -4   -3   -2   -1   00   01   02   03   04   05   06   07   08   09   10   11   12   13   14   15   16   17   18   19   20   21   22   23   24   25   26   27   28   29   30   31   32   33   34   35   36   37   38   39")
# Position:               [   UDP COUNTER   ]  IP  PORT  00   01   02   03   04   05   06   07   08   09   10   11   12   13   14   15   16   17   18   19   20   21   22   23   24   25   26   27   28   29   30   31   32   33   34   35   36   37   38   39")
CFG_Top                 =[0x00,0x00,0x00,0x00,0x00,0x00,0xa0,0x00,0x11,0x00,0x00,0x08,0x05,0xa0,0x08,0x0f,0x40,0x7f,0x00,0x07,0x85,0x00,0xff,0x00,0xff,0x00,0xff,0x00,0x7f,0x00,0x11,0x01,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00]
CFG_Digital_half_0      =[0x00,0x00,0x00,0x00,0x00,0x00,0xa0,0x00,0x11,0x00,0x00,0x1b,0x0b,0x20,0x00,0x00,0x00,0x00,0x80,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x19,0x00,0x0a,0xcc,0xcc,0xcc,0x0c,0xcc,0xcc,0xcc,0xcc,0x0f,0x02,0x00,0x00,0x00,0x00,0x00,0x00]
CFG_Digital_half_1      =[0x00,0x00,0x00,0x00,0x00,0x00,0xa0,0x00,0x11,0x00,0x00,0x1b,0x05,0x60,0x00,0x00,0x00,0x00,0x80,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x19,0x00,0x0a,0xcc,0xcc,0xcc,0x0c,0xcc,0xcc,0xcc,0xcc,0x0f,0x02,0x00,0x00,0x00,0x00,0x00,0x00]
CFG_Global_Analog_0     =[0x00,0x00,0x00,0x00,0x00,0x00,0xa0,0x00,0x11,0x00,0x00,0x0f,0x0a,0xe0,0x6f,0xdb,0x83,0x28,0x28,0x28,0x9a,0x9a,0xa8,0x8a,0x40,0x4a,0x4b,0x68,0x6f,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00]
CFG_Global_Analog_1     =[0x00,0x00,0x00,0x00,0x00,0x00,0xa0,0x00,0x11,0x00,0x00,0x0f,0x05,0x20,0x6f,0xdb,0x83,0x28,0x28,0x28,0x9a,0x9a,0xa8,0x8a,0x40,0x4a,0x4b,0x68,0x6f,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00]
CFG_Master_TDC_0        =[0x00,0x00,0x00,0x00,0x00,0x00,0xa0,0x00,0x11,0x00,0x00,0x10,0x0b,0x00,0x37,0xd4,0x54,0x80,0x0a,0xd4,0x03,0x00,0x80,0x80,0x0a,0x95,0x03,0x00,0x40,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00]
CFG_Master_TDC_1        =[0x00,0x00,0x00,0x00,0x00,0x00,0xa0,0x00,0x11,0x00,0x00,0x10,0x05,0x40,0x37,0xd4,0x54,0x80,0x0a,0xd4,0x03,0x00,0x80,0x80,0x0a,0x95,0x03,0x00,0x40,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00]
CFG_Reference_Voltage_0 =[0x00,0x00,0x00,0x00,0x00,0x00,0xa0,0x00,0x11,0x00,0x00,0x0b,0x0a,0xc0,0xb4,0x0a,0xfa,0xfa,0xb8,0xd4,0xda,0x42,0x00,0x00,0x40,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00]
CFG_Reference_Voltage_1 =[0x00,0x00,0x00,0x00,0x00,0x00,0xa0,0x00,0x11,0x00,0x00,0x0b,0x05,0x00,0xb4,0x0e,0xfa,0xfa,0xad,0xd4,0xda,0x42,0x00,0x00,0x40,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00]
CFG_Half_Wise_0         =[0x00,0x00,0x00,0x00,0x00,0x00,0xa0,0x00,0x11,0x00,0x00,0x0f,0x0b,0x40,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00]
CFG_Half_Wise_1         =[0x00,0x00,0x00,0x00,0x00,0x00,0xa0,0x00,0x11,0x00,0x00,0x0f,0x05,0x80,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00]

for i in range (NumberOfASIC):
    CFG_Digital_half_0[6] = 160+i
    CFG_Digital_half_0[7] = BOARD_ADDRESS
    s.sendto(bytes(CFG_Digital_half_0), (UDP_IP, PORT))

    CFG_Digital_half_1[6] = 160+i
    CFG_Digital_half_1[7] = BOARD_ADDRESS
    s.sendto(bytes(CFG_Digital_half_1), (UDP_IP, PORT))

    CFG_Global_Analog_0[6] = 160+i
    CFG_Global_Analog_0[7] = BOARD_ADDRESS
    s.sendto(bytes(CFG_Global_Analog_0), (UDP_IP, PORT))

    CFG_Global_Analog_1[6] = 160+i
    CFG_Global_Analog_1[7] = BOARD_ADDRESS
    s.sendto(bytes(CFG_Global_Analog_1), (UDP_IP, PORT))

    CFG_Master_TDC_0[6] = 160+i
    CFG_Master_TDC_0[7] = BOARD_ADDRESS
    s.sendto(bytes(CFG_Master_TDC_0), (UDP_IP, PORT))

    CFG_Master_TDC_1[6] = 160+i
    CFG_Master_TDC_1[7] = BOARD_ADDRESS
    s.sendto(bytes(CFG_Master_TDC_1), (UDP_IP, PORT))

    CFG_Reference_Voltage_0[6] = 160+i
    CFG_Reference_Voltage_0[7] = BOARD_ADDRESS
    s.sendto(bytes(CFG_Reference_Voltage_0), (UDP_IP, PORT))

    CFG_Reference_Voltage_1[6] = 160+i
    CFG_Reference_Voltage_1[7] = BOARD_ADDRESS
    s.sendto(bytes(CFG_Reference_Voltage_1), (UDP_IP, PORT))

    CFG_Half_Wise_0[6] = 160+i
    CFG_Half_Wise_0[7] = BOARD_ADDRESS
    s.sendto(bytes(CFG_Half_Wise_0), (UDP_IP, PORT))

    CFG_Half_Wise_1[6] = 160+i
    CFG_Half_Wise_1[7] = BOARD_ADDRESS
    s.sendto(bytes(CFG_Half_Wise_1), (UDP_IP, PORT))

    CFG_Top[6] = 160+i
    CFG_Top[7] = BOARD_ADDRESS
    s.sendto(bytes(CFG_Top), (UDP_IP, PORT))    
    # ... Some channel info place here

print("Base Config downloaded...")

time.sleep(1)


# -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# Start Adjustment
# -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# Position:      -6   -5   -4   -3   -2   -1   00   01   02   03   04   05   06   07   08   09   10   11   12   13   14   15   16   17   18   19   20   21   22   23   24   25   26   27   28   29   30   31   32   33   34   35   36   37   38   39")
# Position:     [   UDP COUNTER   ]  IP  PORT  00   01   02   03   04   05   06   07   08   09   10   11   12   13   14   15   16   17   18   19   20   21   22   23   24   25   26   27   28   29   30   31   32   33   34   35   36   37   38   39")
SetDlyA01     =[0x00,0x00,0x00,0x00,0x00,0x00,0xa0,0x00,0x05,0x00,0x00,0x00,0x00,0x00,0x03,0x02,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x02,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00]
SetDlyA23     =[0x00,0x00,0x00,0x00,0x00,0x00,0xa2,0x00,0x05,0x00,0x00,0x00,0x00,0x00,0x03,0x02,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x02,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00]
SetDlyA45     =[0x00,0x00,0x00,0x00,0x00,0x00,0xa4,0x00,0x05,0x00,0x00,0x00,0x00,0x00,0x03,0x02,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x02,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00]
SetDlyA67     =[0x00,0x00,0x00,0x00,0x00,0x00,0xa6,0x00,0x05,0x00,0x00,0x00,0x00,0x00,0x03,0x02,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x02,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00]

# Position:      -6   -5   -4   -3   -2   -1   00   01   02   03   04   05   06   07   08   09   10   11   12   13   14   15   16   17   18   19   20   21   22   23   24   25   26   27   28   29   30   31   32   33   34   35   36   37   38   39")
MesAdjustAll  =[0x00,0x00,0x00,0x00,0x00,0x00,0xa0,0x00,0x01,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0xFF,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00]

# Position:      -6   -5   -4   -3   -2   -1   00   01   02   03   04   05   06   07   08   09   10   11   12   13   14   15   16   17   18   19   20   21   22   23   24   25   26   27   28   29   30   31   32   33   34   35   36   37   38   39")
MesRstAll     =[0x00,0x00,0x00,0x00,0x00,0x00,0xa0,0x00,0x01,0x00,0x00,0x00,0x00,0x00,0xFF,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00]

# Position:      -6   -5   -4   -3   -2   -1   00   01   02   03   04   05   06   07   08   09   10   11   12   13   14   15   16   17   18   19   20   21   22   23   24   25   26   27   28   29   30   31   32   33   34   35   36   37   38   39")
GetDebugData  =[0x00,0x00,0x00,0x00,0x00,0x00,0xa0,0x00,0x0C,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00]

# s.sendto(bytes(MesRstAll), (UDP_IP, PORT))
# time.sleep(1)

for j in range (NumberOfASIC):

    print("")
    print("Test ASIC %s IO Delay..." % (j))
    print("")
    print("                 ASIC CMD  DLY10 AR   Data1    Data0    Trig3    Trig2    Trig1    Trig0")

    i= 0
    daq0dly_prev = "ff"
    wrong_packet = 0

    daq0_prev    = ""
    daq1_prev    = ""
    daq_dly_cnt  = 0
    daq_dly_pos  = 0
    daq_dly_cnt2 = 0
    daq_dly_pos2 = 0

    SetDlyA01[7]  = BOARD_ADDRESS
    SetDlyA23[7]  = BOARD_ADDRESS
    SetDlyA45[7]  = BOARD_ADDRESS
    SetDlyA67[7]  = BOARD_ADDRESS

    MesAdjustAll[7]  = BOARD_ADDRESS
    MesRstAll[7]     = BOARD_ADDRESS
    GetDebugData[7]  = BOARD_ADDRESS

    SetDlyA01[14] = ASIC_SELECT
    SetDlyA23[14] = ASIC_SELECT
    SetDlyA45[14] = ASIC_SELECT
    SetDlyA67[14] = ASIC_SELECT
    MesAdjustAll[21] = ASIC_SELECT

    while i < 256:    
    # for i in range (256):
        SetDlyA01[18] = i
        SetDlyA01[19] = i
        SetDlyA01[20] = i
        SetDlyA01[21] = i
        SetDlyA01[22] = i
        SetDlyA01[23] = i
    
        SetDlyA01[34] = i
        SetDlyA01[35] = i
        SetDlyA01[36] = i
        SetDlyA01[37] = i
        SetDlyA01[38] = i
        SetDlyA01[39] = i

        SetDlyA23[18] = i
        SetDlyA23[19] = i
        SetDlyA23[20] = i
        SetDlyA23[21] = i
        SetDlyA23[22] = i
        SetDlyA23[23] = i
    
        SetDlyA23[34] = i
        SetDlyA23[35] = i
        SetDlyA23[36] = i
        SetDlyA23[37] = i
        SetDlyA23[38] = i
        SetDlyA23[39] = i

        SetDlyA45[18] = i
        SetDlyA45[19] = i
        SetDlyA45[20] = i
        SetDlyA45[21] = i
        SetDlyA45[22] = i
        SetDlyA45[23] = i
    
        SetDlyA45[34] = i
        SetDlyA45[35] = i
        SetDlyA45[36] = i
        SetDlyA45[37] = i
        SetDlyA45[38] = i
        SetDlyA45[39] = i

        SetDlyA67[18] = i
        SetDlyA67[19] = i
        SetDlyA67[20] = i
        SetDlyA67[21] = i
        SetDlyA67[22] = i
        SetDlyA67[23] = i
    
        SetDlyA67[34] = i
        SetDlyA67[35] = i
        SetDlyA67[36] = i
        SetDlyA67[37] = i
        SetDlyA67[38] = i
        SetDlyA67[39] = i

        s.sendto(bytes(SetDlyA01), (UDP_IP, PORT))
        s.sendto(bytes(SetDlyA23), (UDP_IP, PORT))
        s.sendto(bytes(SetDlyA45), (UDP_IP, PORT))
        s.sendto(bytes(SetDlyA67), (UDP_IP, PORT))
        
        s.sendto(bytes(MesAdjustAll), (UDP_IP, PORT))    
        time.sleep(0.01)   
    
        cache = [''] 

        GetDebugData[6] = 160+j
        s.sendto(bytes(GetDebugData), (UDP_IP, PORT))

        pack_ok = 0
        
        while pack_ok < 1 :

            data, add = s.recvfrom(1024)
            hex_string = binascii.hexlify(data).decode('utf-8')
            hex_string2 = r" 0x" + r" 0x".join(hex_string[n : n+2] for n in range(0, len(hex_string), 2))
    
            addr = hex_string2[30:35]
    
            cmd = hex_string2[41:45]

            id_cnt = hex_string2[46:49]
            mes_start = hex_string2[30:110]
    
            daq1dly = hex_string2[76:80]
            daq1dly = daq1dly.replace(" ", "")
            daq1dly = daq1dly.replace("0x", "")
    
            daq0dly = hex_string2[81:85]
            daq0dly = daq0dly.replace(" ", "")
            daq0dly = daq0dly.replace("0x", "")
    
            adjr = hex_string2[86:90]
    
            tr0 = hex_string2[111:130]
            tr0 = tr0.replace(" ", "")
            tr0 = tr0.replace("0x", "")
        
            tr1 = hex_string2[131:150]
            tr1 = tr1.replace(" ", "")
            tr1 = tr1.replace("0x", "")
    
            tr2 = hex_string2[151:170]
            tr2 = tr2.replace(" ", "")
            tr2 = tr2.replace("0x", "")
    
            tr3 = hex_string2[171:190]
            tr3 = tr3.replace(" ", "")
            tr3 = tr3.replace("0x", "")
            
            daq0 = hex_string2[191:210]
            daq0 = daq0.replace(" ", "")
            daq0 = daq0.replace("0x", "")
    
            daq1 = hex_string2[211:230]
            daq1 = daq1.replace(" ", "")
            daq1 = daq1.replace("0x", "")
    

            # Filter all of the non-correct package...
            if (cmd == "0x0c" and daq0dly_prev != daq0dly) :
                daq0dly_prev = daq0dly

    
                # --------------------------------------------------------------------------------------------------------------------------------
                # Find the good Delay...
                # --------------------------------------------------------------------------------------------------------------------------------
                if (daq0 == "accccccc" and daq0_prev == "accccccc" and daq1 == "accccccc" and daq1_prev == "accccccc") :
                    daq_dly_cnt = daq_dly_cnt + 1
                    daq_dly_pos = i
                else :
                    if (daq_dly_cnt > daq_dly_cnt2) :
                        daq_dly_cnt2 = daq_dly_cnt
                        daq_dly_pos2 = daq_dly_pos 
                    daq_dly_cnt  = 0
                    daq_dly_pos  = 0

                daq0_prev = daq0
                daq1_prev = daq1
                    


                # --------------------------------------------------------------------------------------------------------------------------------
                # Colorize
                # --------------------------------------------------------------------------------------------------------------------------------
                if (adjr != "0x3f"): adjr =  RED + adjr + RESET  
                if (tr0 != "accccccc"): tr0 =  RED + tr0 + RESET
                if (tr1 != "accccccc"): tr1 =  RED + tr1 + RESET
                if (tr2 != "accccccc"): tr2 =  RED + tr2 + RESET
                if (tr3 != "accccccc"): tr3 =  RED + tr3 + RESET
                if (daq0 != "accccccc"): daq0 =  RED + daq0 + RESET
                if (daq1 != "accccccc"): daq1 =  RED + daq1 + RESET

                cache = (addr + " " + cmd + " " + daq1dly + "/" + daq0dly + " " + adjr + " " + daq1 + " " + daq0 + " " + tr3 + " " + tr2 + " " + tr1 + " " + tr0)
                print("Iteration #%s: %s " % (f'{i:03d}',cache))
                # print("Iteration #%s: %s -- %s" % (f'{i:03d}',cache,f'{daq_dly_cnt:03d}'))

                i = i + 1
                pack_ok = 1
            
            else :
                wrong_packet = wrong_packet + 1
                print("Wrong packet Command ID :" + addr + " " + cmd + " " + id_cnt + " >> " + mes_start )

    print("Unexpected Packet Counter: %s: " % (wrong_packet))
    print("Loongest Good Range/Pos: %s / %s >>> Proposed: %s" % (daq_dly_cnt2, daq_dly_pos2, (daq_dly_pos2-daq_dly_cnt2/2)))
    time.sleep(0.01)   




# -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# Write the Final Adjust Value (It is coming from my excel or the previous results)
# -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

SetDlyA01[7]  = BOARD_ADDRESS
SetDlyA23[7]  = BOARD_ADDRESS
SetDlyA45[7]  = BOARD_ADDRESS
SetDlyA67[7]  = BOARD_ADDRESS

MesAdjustAll[7]  = BOARD_ADDRESS
MesRstAll[7]     = BOARD_ADDRESS
GetDebugData[7]  = BOARD_ADDRESS


SetDlyA01[18] = ASIC0_IODly
SetDlyA01[19] = ASIC0_IODly
SetDlyA01[20] = ASIC0_IODly
SetDlyA01[21] = ASIC0_IODly
SetDlyA01[22] = ASIC0_IODly
SetDlyA01[23] = ASIC0_IODly

SetDlyA01[34] = ASIC1_IODly
SetDlyA01[35] = ASIC1_IODly
SetDlyA01[36] = ASIC1_IODly
SetDlyA01[37] = ASIC1_IODly
SetDlyA01[38] = ASIC1_IODly
SetDlyA01[39] = ASIC1_IODly

SetDlyA23[18] = ASIC2_IODly
SetDlyA23[19] = ASIC2_IODly
SetDlyA23[20] = ASIC2_IODly
SetDlyA23[21] = ASIC2_IODly
SetDlyA23[22] = ASIC2_IODly
SetDlyA23[23] = ASIC2_IODly

SetDlyA23[34] = ASIC3_IODly
SetDlyA23[35] = ASIC3_IODly
SetDlyA23[36] = ASIC3_IODly
SetDlyA23[37] = ASIC3_IODly
SetDlyA23[38] = ASIC3_IODly
SetDlyA23[39] = ASIC3_IODly

SetDlyA45[18] = ASIC4_IODly
SetDlyA45[19] = ASIC4_IODly
SetDlyA45[20] = ASIC4_IODly
SetDlyA45[21] = ASIC4_IODly
SetDlyA45[22] = ASIC4_IODly
SetDlyA45[23] = ASIC4_IODly

SetDlyA45[34] = ASIC5_IODly
SetDlyA45[35] = ASIC5_IODly
SetDlyA45[36] = ASIC5_IODly
SetDlyA45[37] = ASIC5_IODly
SetDlyA45[38] = ASIC5_IODly
SetDlyA45[39] = ASIC5_IODly

SetDlyA67[18] = ASIC6_IODly
SetDlyA67[19] = ASIC6_IODly
SetDlyA67[20] = ASIC6_IODly
SetDlyA67[21] = ASIC6_IODly
SetDlyA67[22] = ASIC6_IODly
SetDlyA67[23] = ASIC6_IODly

SetDlyA67[34] = ASIC7_IODly
SetDlyA67[35] = ASIC7_IODly
SetDlyA67[36] = ASIC7_IODly
SetDlyA67[37] = ASIC7_IODly
SetDlyA67[38] = ASIC7_IODly
SetDlyA67[39] = ASIC7_IODly

s.sendto(bytes(SetDlyA01), (UDP_IP, PORT))
s.sendto(bytes(SetDlyA23), (UDP_IP, PORT))
s.sendto(bytes(SetDlyA45), (UDP_IP, PORT))
s.sendto(bytes(SetDlyA67), (UDP_IP, PORT))


print("")
print("Final Delay Values are set...")
print("Test it...")

s.sendto(bytes(MesAdjustAll), (UDP_IP, PORT))    
time.sleep(0.01)   

cache = ['']


for j in range (NumberOfASIC):

    print("")
    print("")
    print("Test ASIC %s..." % (j))
    if (j == 0): print("Delay: %s" % (ASIC0_IODly))
    if (j == 1): print("Delay: %s" % (ASIC1_IODly))
    if (j == 2): print("Delay: %s" % (ASIC2_IODly))
    if (j == 3): print("Delay: %s" % (ASIC3_IODly))
    if (j == 4): print("Delay: %s" % (ASIC4_IODly))
    if (j == 5): print("Delay: %s" % (ASIC5_IODly))
    if (j == 6): print("Delay: %s" % (ASIC6_IODly))
    if (j == 7): print("Delay: %s" % (ASIC7_IODly))
    print("                 ASIC CMD  DLY10 AR   Data1    Data0    Trig3    Trig2    Trig1    Trig0")

    for i in range (20):     
        GetDebugData[6] = 160+j
        GetDebugData[7] = BOARD_ADDRESS
        s.sendto(bytes(GetDebugData), (UDP_IP, PORT))
        data, add = s.recvfrom(1024)
        hex_string = binascii.hexlify(data).decode('utf-8')
        hex_string2 = r" 0x" + r" 0x".join(hex_string[n : n+2] for n in range(0, len(hex_string), 2))

        addr = hex_string2[30:35]

        cmd = hex_string2[41:45]

        daq1dly = hex_string2[76:80]
        daq1dly = daq1dly.replace(" ", "")
        daq1dly = daq1dly.replace("0x", "")

        daq0dly = hex_string2[81:85]
        daq0dly = daq0dly.replace(" ", "")
        daq0dly = daq0dly.replace("0x", "")

        adjr = hex_string2[86:90]
        if (adjr != "0x3f"): adjr =  RED + adjr + RESET  
    
        tr0 = hex_string2[111:130]
        tr0 = tr0.replace(" ", "")
        tr0 = tr0.replace("0x", "")
        if (tr0 != "accccccc"): tr0 =  RED + tr0 + RESET
    
        tr1 = hex_string2[131:150]
        tr1 = tr1.replace(" ", "")
        tr1 = tr1.replace("0x", "")
        if (tr1 != "accccccc"): tr1 =  RED + tr1 + RESET
    
        tr2 = hex_string2[151:170]
        tr2 = tr2.replace(" ", "")
        tr2 = tr2.replace("0x", "")
        if (tr2 != "accccccc"): tr2 =  RED + tr2 + RESET
    
        tr3 = hex_string2[171:190]
        tr3 = tr3.replace(" ", "")
        tr3 = tr3.replace("0x", "")
        if (tr3 != "accccccc"): tr3 =  RED + tr3 + RESET
        
        daq0 = hex_string2[191:210]
        daq0 = daq0.replace(" ", "")
        daq0 = daq0.replace("0x", "")
        if (daq0 != "accccccc"): daq0 =  RED + daq0 + RESET
    
        daq1 = hex_string2[211:230]
        daq1 = daq1.replace(" ", "")
        daq1 = daq1.replace("0x", "")
        if (daq1 != "accccccc"): daq1 =  RED + daq1 + RESET
         
        cache = (addr + " " + cmd + " " + daq1dly + "/" + daq0dly + " " + adjr + " " + daq1 + " " + daq0 + " " + tr3 + " " + tr2 + " " + tr1 + " " + tr0)
        print("Iteration #%s: %s " % (f'{i:03d}',cache))        


        time.sleep(0.01)  
        

# -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# Close
# -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
s.close()

print("")
print(" >>> END <<<")
print("")

