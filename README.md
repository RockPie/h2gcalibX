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

4. Click the `Start Socket Pool` button to set up the UDP communication.

5. Now you can run the IODelay settings for the FPGA to correctly receive data from the H2GCROC.
![IODelay Setting](doc/tui_iodelay.png)

6. For the pedestal calibration, go to the `PedestalX` tab, set the target pedestal value in ADC, and choose the template register json file. This will take around 5 minutes for a 2-ASIC setup. And the results will be saved in the `dump/` folder.
![Pedestal Calibration](doc/tui_pedestalx.png)

7. Next step is usually the ToA scan in the `ToAX` tab. Again, set the target ToA value in injection DAC, and choose the tamplate register json file. Is is recommended to use the `Read from 202 output` button to load the pedestal calibration results. This will take around 15 minutes if you inject 8 channels in parallel for a 2-ASIC setup. The results will also be saved in the `dump/` folder.
![ToA Calibration](doc/tui_toax.png)