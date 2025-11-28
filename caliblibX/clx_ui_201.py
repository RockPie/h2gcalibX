import os, json, ast
from textual.app import ComposeResult
from textual.widgets import (
    Header,
    Footer,
    Static,
    ListView,
    ListItem,
    ContentSwitcher,
    OptionList,
    Button, Label,
    DirectoryTree,
    Input,
    RadioButton,
    Log,
    Checkbox,
    Pretty,
    ProgressBar
)
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.validation import Function, Number, ValidationResult, Validator
from textual import on
import asyncio
from pathlib import Path

from caliblibX.clx_ui_messager import *
from caliblibX.clx_ui_file_picker import FilePicker, FolderPicker

# ! === 201 IODelayX Page =====================================================
class Page_201(Static):
    """Page for 201_IODelayX script."""
    DEFAULT_CSS = """
    Page_201 .sub-header {
        color: $text;
        text-style: bold;
        height: 3;
        padding: 0 1;
        content-align: center middle;
        border: solid $accent 50%;
    }

    Page_201 RadioButton {
        width: 1fr;
        margin: 0 1;
        height: 3;
    }

    Page_201 #radio-buttons {
        grid-size: 3;
        grid-columns: auto auto auto;
        grid-rows: auto;
        height: auto;
        align-vertical: middle;
        padding: 0 1;
        width: 100%;
    }

    Page_201 #phase-grid {
        grid-size: 3;
        grid-columns: auto 1fr auto;
        grid-rows: auto;
        height: auto;
        align-vertical: middle;
        padding: 0 1;
    }

    Page_201 #phase-label {
        width: 30;
        padding-top: 1;
    }

    Page_201 #phase-input {
        width: 25;
    }

    Page_201 #phase-setting {
        width: 1fr;
        overflow: hidden;
        text-overflow: ellipsis;
        padding-top: 1;
        padding-left: 3;
        text-style: italic;
    }

    Page_201 #start-iodelay-scan {
        width: 1fr;
        content-align: center middle;
        height: 3;
    }

    Page_201 #iodelay-log {
        height: 1fr;
        border: solid #778873 50%;
        margin-top: 5;
    }

    Page_201 ProgressBar Bar {
        width: 1fr;
    }
    """

    def __init__(self, parent, fpga_id: str, initial_dict=None, **kwargs):
        super().__init__(**kwargs)
        self.parent_panel = parent
        self.fpga_id = fpga_id
        self.id = f"fpga-{self.fpga_id}-iodelayx"

        self.enable_trigger_lines = True  # default
        self.enable_reset = True  # default
        self.phase_setting = 0  # default

        if initial_dict:
            self.load_from_dict(initial_dict)

        self.process_running: bool = False
        self.process: asyncio.subprocess.Process | None = None

    def save_to_dict(self) -> dict:
        """Export current settings to a JSON-serializable dictionary."""
        return {
            "enable_trigger_lines": self.enable_trigger_lines,
            "enable_reset": self.enable_reset,
            "phase_setting": self.phase_setting,
        }
    
    def load_from_dict(self, settings_dict: dict) -> None:
        """Load settings from a dictionary."""
        self.enable_trigger_lines = settings_dict.get("enable_trigger_lines", self.enable_trigger_lines)
        self.enable_reset = settings_dict.get("enable_reset", self.enable_reset)
        self.phase_setting = settings_dict.get("phase_setting", self.phase_setting)

    def compose(self) -> ComposeResult:
        yield Static("201 IODelay", classes="sub-header")
        yield Horizontal(
            RadioButton("Enable Trigger Lines", id="enable-trigger-lines", value=self.enable_trigger_lines),
            RadioButton("Reset ASICs", id="enable-reset", value=self.enable_reset),
            id="radio-buttons"
        )
        yield Horizontal(
            Label("[b]Phase setting:[/b]", markup=True, id="phase-label"),
            Label(str(self.phase_setting), id="phase-setting", expand=True),
            Input(placeholder="Phase setting (0-15)", id="phase-input"),
            id="phase-grid"
        )
        yield Log(
            id="iodelay-log",
            auto_scroll=True,
            highlight=True,
        )
        yield ProgressBar(total=100, id="iodelay-progress-bar", classes="run_progress_bar")
        yield Button.success("Start IO Delay Scan", id="start-iodelay-scan")

    def _on_mount(self, event):
        # Update UI elements
        trigger_radio = self.query_one("#enable-trigger-lines", RadioButton)
        trigger_radio.value = self.enable_trigger_lines

        reset_radio = self.query_one("#enable-reset", RadioButton)
        reset_radio.value = self.enable_reset

        phase_label = self.query_one("#phase-setting", Label)
        phase_label.update(str(self.phase_setting))

    # python3 /home/nbi-focal/Code/h2gcalibX/201_IODelayX.py  -t -r -p 12 -a 2
    async def run_scipt(self) -> None:
        # clear log
        log = self.query_one("#iodelay-log", Log)
        log.clear()
        log.write_line("▶ Starting IO Delay Scan ...")

        self.run_cmd = 'python3 -u ./201_IODelayX.py --ui'

        if self.enable_trigger_lines:
            self.run_cmd += ' -t'
        if self.enable_reset:
            self.run_cmd += ' -r'
        self.run_cmd += f' -p {self.phase_setting}'
        self.run_cmd += f' -a {self.parent_panel.asic_num}'
        self.run_cmd += f' -c {self.parent_panel.udp_config_file}'

        log.write_line(f"▶ Running command: {self.run_cmd}")

        self.process = await asyncio.create_subprocess_exec(
            *self.run_cmd.split(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        async def read_stream(stream):
            while True:
                line = await stream.readline()
                if not line:
                    break
                text = line.decode(errors="ignore").rstrip("\n")
                # if the line starts with "ui_progress:", update the progress bar
                if text.startswith("ui_progress:"):
                    try:
                        progress_payload = text.split(":", 1)[1].strip().rstrip("%")
                        progress_value = int(progress_payload)
                        progress_bar = self.query_one("#iodelay-progress-bar", ProgressBar)
                        bounded_value = max(0, min(progress_bar.total, progress_value))
                        progress_bar.update(progress=bounded_value)
                    except (IndexError, ValueError):
                        pass
                else:
                    log.write_line(text)

        await read_stream(self.process.stdout)

        rc = await self.process.wait()

        self.process_running = False
        self.process = None

        btn = self.query_one("#start-iodelay-scan", Button)
        btn.variant = "success"
        btn.label = "Start IO Delay Scan"

        log.write_line(f"✅ IO Delay Scan finished with exit code {rc}.")
        self.notify("IO Delay Scan completed.", severity="info")
            
    def on_radio_button_changed(self, event: RadioButton.Changed) -> None:
        """Handle radio button changes."""
        if event.radio_button.id == "enable-trigger-lines":
            self.enable_trigger_lines = event.value
        elif event.radio_button.id == "enable-reset":
            self.enable_reset = event.value

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle phase setting input submission."""
        if event.input.id == "phase-input":
            try:
                phase = int(event.value)
                if phase < 0 or phase > 15:
                    self.notify("Phase setting must be between 0 and 15", severity="warning")
                else:
                    self.phase_setting = phase
                    phase_label = self.query_one("#phase-setting", Label)
                    phase_label.update(str(self.phase_setting))
                    self.notify(f"Phase setting set to {self.phase_setting}", severity="info")
                event.input.value = ""
            except ValueError:
                self.notify("Invalid phase setting", severity="error")
                event.input.value = ""

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "start-iodelay-scan":
            if not self.process_running:
                self.process_running = True
                event.button.variant = "error"
                event.button.label = "Stop IO Delay Scan"
                asyncio.create_task(self.run_scipt())
            else:
                if self.process is not None and self.process.returncode is None:
                    self.process.kill()
                    self.notify("IO Delay Scan process killed.", severity="warning")
                    progress_bar = self.query_one("#iodelay-progress-bar", ProgressBar)
                    progress_bar.update(total=100, progress=0)