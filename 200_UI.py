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

class CalibX(App):
    """H2GCalibX"""

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
        await self.add_fpga_tab()
        await self.add_fpga_tab()
        self.pool_process: asyncio.subprocess.Process | None = None
        self.pool_task: asyncio.Task | None = None

    async def action_add_tab(self):
        await self.add_fpga_tab()

    async def add_fpga_tab(self):
        self._tab_counter += 1
        fpga_name = f"FPGA {self._tab_counter}"
        fpga_id   = f"fpga-{self._tab_counter}"

        top_tabs = self.query_one("#fpga-tabs", TabbedContent)

        panel = caliblibX.FpgaPanel(self, fpga_name, fpga_id)

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
            # 先发 terminate，再等一会儿，不行再 kill
            try:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
            except ProcessLookupError:
                # 进程已经没了
                pass

        self.pool_process = None

        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            self.pool_task = None

    async def action_quit(self) -> None:
        """Ctrl+Q 退出前，先把 SocketPool 干净地停掉。"""
        await self._stop_socket_pool()
        self.exit()

if __name__ == "__main__":
    CalibX().run()