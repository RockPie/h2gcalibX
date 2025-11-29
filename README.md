# CalibX for H2GCROC - KCU System
[![ALICE @ CERN](https://img.shields.io/badge/ALICE%20%40%20CERN-heavy%20ion%20collisions-cc0000?style=for-the-badge)](https://home.cern/science/experiments/alice)  [![Niels Bohr Institute](https://img.shields.io/badge/Niels%20Bohr%20Institute-University%20of%20Copenhagen-660000?style=for-the-badge)](https://nbi.ku.dk/english/)

## Quick Start

1. Start with the TUI interface:

   ```bash
   python3 ./200_UI.py
   ```

2. If it is your first time running the calibration, you have to create a new FPGA tab with shortcut `Ctrl+N` or click it from the bottom bar.
![New FPGA Tab](doc/tui_startup.png)

3. Choose the FPGA UDP setting json file, and make sure the `ASIC Number` is set correctly.
![FPGA UDP Config](doc/tui_fpga_setting.png)
