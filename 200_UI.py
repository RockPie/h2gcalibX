import asyncio
from textual.app import App, ComposeResult
from textual.widgets import (
    Header,
    Footer,
    TabbedContent,
    TabPane,
    Button,
    Log,
)
from textual.containers import Horizontal, Vertical
import caliblibX
import contextlib
import configparser, os

class CalibX(App):
    """H2GCalibX"""

    ENABLE_WEB = True

    CSS = """
    Screen {
        layout: vertical;
    }

    TabbedContent#fpga-tabs {
        height: 1fr;
    }

    Horizontal.fpga-row {
        height: 1fr;
    }

    ListView.menu {
        width: 20;
        height: 1fr;
        border: solid $accent 10%;
    }

    ContentSwitcher.content {
        height: 1fr;
        border: solid $accent 10%;
    }

    #control-panel {
        height: 10;
    }

    #button-panel {
        height: 3;
    }

    Log#pool-log-panel {
        height: 1fr;
    }

    #start-pool-btn, #close-pool-btn {
        margin: 0 1;
        width: 50%;
    }
    """

    BINDINGS = [
        ("ctrl+n", "add_tab", "New FPGA tab"),
        ("ctrl+w", "close_tab", "Close FPGA tab"),
        ("q", "quit", "Quit application"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._tab_counter = 0
        self.pool_process = None
        self.pool_task = None

        # Check if any ini file exists for the App settings
        self.config = configparser.ConfigParser()
        script_dir = os.path.dirname(os.path.abspath(__file__))
        ini_path = os.path.join(script_dir, 'caliblibX.ini')
        if os.path.exists(ini_path):
            self.config.read(ini_path)
        else:
            # create a default config if none exists, so no tab
            self.config['APP_SETTINGS'] = {}

    async def save_config(self):
        """Save current application configuration to ini file."""
        # clean existing FPGA sections
        for section in self.config.sections():
            if section.startswith('FPGA_'):
                self.config.remove_section(section)
        # Gather current settings
        tabs = self.query_one("#fpga-tabs", TabbedContent)
        for idx, pane in enumerate(tabs.query(TabPane), start=1):
            try:
                fpga_panel: caliblibX.FpgaPanel = pane.query_one(caliblibX.FpgaPanel)
                # print info for debugging
                print(f"Saving config for tab {pane.id}: {fpga_panel.fpga_name}, {fpga_panel.asic_num}, {fpga_panel.udp_config_file}")
                self.config[f'FPGA_{idx}'] = fpga_panel.save_to_dict()
            except Exception as e:
                print(f"Error saving config for tab {pane.id}: {e}")

        # Write to ini file
        script_dir = os.path.dirname(os.path.abspath(__file__))
        ini_path = os.path.join(script_dir, 'caliblibX.ini')
        with open(ini_path, 'w') as configfile:
            self.config.write(configfile)


    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield TabbedContent(id="fpga-tabs")
        yield Vertical(
            Horizontal(
                Button.success("Start Socket Pool", id="start-pool-btn", flat=True),
                Button.warning("Close Socket Pool", id="close-pool-btn", flat=True),
                id="button-panel",
            ),
            Log(id="pool-log-panel", auto_scroll=True, highlight=True),
            id="control-panel",
        )
        yield Footer()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        log = self.query_one("#pool-log-panel", Log)

        if event.button.id == "start-pool-btn":
            log.clear()
            log.write_line("▶ Starting UDP Socket Pool...")

            cmd = ["python3", "-u", "./101_SocketPool.py"]
            log.write_line(f"▶ Running command: {' '.join(cmd)}")

            # start subprocess
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self.pool_process = process

            async def stream_reader(stream, prefix):
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    log.write_line(f"{prefix}{line.decode().rstrip()}")

            async def process_monitor():
                await asyncio.gather(
                    stream_reader(process.stdout, ""),
                    stream_reader(process.stderr, "ERROR: "),
                )
                rc = await process.wait()
                log.write_line(f"▶ Socket Pool exited with code {rc}")

                self.query_one("#start-pool-btn", Button).disabled = False
                self.query_one("#close-pool-btn", Button).disabled = True
                self.pool_process = None

            self.pool_task = asyncio.create_task(process_monitor())

            self.query_one("#start-pool-btn", Button).disabled = True
            self.query_one("#close-pool-btn", Button).disabled = False

        elif event.button.id == "close-pool-btn":
            log.write_line("▶ Closing UDP Socket Pool...")

            if self.pool_process:
                self.pool_process.terminate()  # or kill()
                log.write_line("▶ Sent terminate signal to Socket Pool")

            self.query_one("#start-pool-btn", Button).disabled = False
            self.query_one("#close-pool-btn", Button).disabled = True
            # caliblibX.close_socket_pool(log)
        
    async def on_mount(self):
        # await self.add_fpga_tab()
        # await self.add_fpga_tab()
        if self.config.sections():
            # Load FPGA tabs from config
            for section in self.config.sections():
                if section.startswith('FPGA_'):
                    fpga_settings = self.config[section]
                    fpga_name = fpga_settings.get('fpga_name', '')
                    fpga_id   = fpga_settings.get('fpga_id', '')
                    await self.add_fpga_tab(fpga_name, fpga_id, initial_dict=fpga_settings)
        self.pool_process: asyncio.subprocess.Process | None = None
        self.pool_task: asyncio.Task | None = None

    async def action_add_tab(self):
        await self.add_fpga_tab()

    async def add_fpga_tab(self, fpga_name: str = "", fpga_id: str = "", initial_dict: dict = None):
        self._tab_counter += 1
        if not fpga_name or not fpga_id:
            fpga_name = f"FPGA {self._tab_counter}"
            fpga_id   = f"fpga-{self._tab_counter}"

        top_tabs = self.query_one("#fpga-tabs", TabbedContent)

        panel = caliblibX.FpgaPanel(self, fpga_name, fpga_id, initial_dict=initial_dict)

        pane = TabPane(fpga_name, panel, id=fpga_id)
        await top_tabs.add_pane(pane)
        top_tabs.active = fpga_id

    async def action_close_tab(self) -> None:
        top_tabs = self.query_one("#fpga-tabs", TabbedContent)

        if top_tabs.tab_count <= 1:
            return

        active_id = top_tabs.active
        if not active_id:
            return
        await top_tabs.remove_pane(active_id)
    
    async def _stop_socket_pool(self) -> None:
        proc = self.pool_process
        task = self.pool_task

        if proc and proc.returncode is None:
            try:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
            except ProcessLookupError:
                pass

        self.pool_process = None

        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            self.pool_task = None

    async def action_quit(self) -> None:
        """Q to quit the app."""
        # Save config before quitting
        await self.save_config()
        await self._stop_socket_pool()
        self.exit()

if __name__ == "__main__":
    CalibX().run()