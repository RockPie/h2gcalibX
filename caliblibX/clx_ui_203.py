import asyncio, os, json, ast

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
    ProgressBar,
)
from textual.containers import Horizontal, Vertical, Center, Middle

from caliblibX.clx_ui_messager import *
from caliblibX.clx_ui_file_picker import FilePicker, FolderPicker

class Page_203(Static):
    """Page for 203_ToAX script."""
    DEFAULT_CSS = """
    Page_203 .sub-header {
        color: $text;
        text-style: bold;
        height: 3;
        padding: 0 1;
        content-align: center middle;
        border: solid $accent 50%;
    }
    Page_203 .value_grid {
        grid-size: 3;
        grid-columns: auto 1fr auto;
        grid-rows: auto;
        height: auto;
        align-vertical: middle;
        padding: 1 1;
    }
    Page_203 .value_label {
        width: 25;
    }
    Page_203 .value_display {
        width: 1fr;
        text-style: italic;
        padding-left: 3;
        padding-right: 2;
    }
    Page_203 .value_input {
        width: 25;
    }
    Page_203 .value_button {
        width: 25;
    }
    Page_203 .asic_json_grid {
        grid-size: 2;
        grid-columns: auto 1fr;
        grid-rows: auto;
        height: auto;
        align-vertical: middle;
        padding: 0 1;
    }
    Page_203 #toa_log {
        height: 1fr;
        border: solid #778873 50%;
        margin-top: 2;
    }
    Page_203 #start-toa-scan {
        width: 1fr;
        content-align: center middle;
        height: 3;
    }
    Page_203 ProgressBar Bar {
        width: 1fr;
    }
    Page_203 #toa_template_label_grid {
        grid-size: 2;
        grid-columns: 1fr auto;
        grid-rows: auto;
        height: auto;
        align-vertical: middle;
        padding: 1 1;
    }
    Page_203 #toa_template_label {
        width: 1fr;
    }
    """
    def __init__(self, parent, fpga_id: str, initial_dict=None, **kwargs):
        super().__init__(**kwargs)
        self.fpga_id = fpga_id
        self.parent_panel = parent
        self.id = f"fpga-{self.fpga_id}-toax"

        self.target_toa = 50 # default target ToA
        self.template_json_path_list: list[str] = []
        self.output_file_list: list[str] = []  # output files

        self.settings_compact = True

        if initial_dict is not None:
            self.load_from_dict(initial_dict)

        self.process_running: bool = False
        self.process: asyncio.subprocess.Process | None = None

    def save_to_dict(self) -> dict:
        """Save current settings to a dictionary."""
        return {
            "target_toa": self.target_toa,
            "template_json_path_list": self.template_json_path_list,
            "output_file_list": self.output_file_list,
        }

    def load_from_dict(self, settings: dict) -> None:
        """Load settings from a dictionary."""
        self.target_toa = settings.get("target_toa", self.target_toa)
        self.template_json_path_list = settings.get("template_json_path_list", self.template_json_path_list)
        self.output_file_list = settings.get("output_file_list", self.output_file_list)

    def compose(self) -> ComposeResult:
        yield Static("203 ToAX", classes="sub-header")
        # --- Setting target ToA ---
        yield Horizontal(
            Label("Target ToA:", classes="value_label"),
            Label(str(self.target_toa), classes="value_display"),
            Input(placeholder="Enter target ToA in DAC", id="toa_input", classes="value_input", compact=self.settings_compact),
            id="toa_target_grid", classes="value_grid",
        )
        with Vertical():
            # adding asic setting json file lines the same number as asic_num
            yield Horizontal(
                Label("Template JSONs:", classes="value_label", id="toa_template_label"),
                Button("Read from 202 Output", id="read-202-toa-templates", variant="primary", compact=self.settings_compact, classes="value_button"),
                id="toa_template_label_grid",
            )
            for i in range(int(self.parent_panel.asic_num)):
                yield Horizontal(
                    Label(f"asic {i} input json file", classes="value_display", id=f"toa_template_label_asic{i}"),
                    Button("Browse", id=f"browse-toa-template-{i}", compact=self.settings_compact, classes="value_button"),
                    id=f"toa_template_grid_asic{i}", classes="asic_json_grid"
                )
        yield Log(
            id="toa_log",
            auto_scroll=True,
            highlight=True
        )

        yield ProgressBar(total=100, id="toa-progress-bar", classes="run_progress_bar")
        yield Button.success("Start ToA Scan", id="start-toa-scan")

    def _on_mount(self, event):
        # load the input json names to ui
        if len(self.template_json_path_list) == int(self.parent_panel.asic_num):
            for i, file in enumerate(self.template_json_path_list):
                label = self.query_one(f"#toa_template_label_asic{i}", Label)
                label.update(file)
        return super()._on_mount(event)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submitted events."""
        if event.input.id == "toa_input":
            try:
                value = int(event.value)
                if value < 0 or value > 4095:
                    raise ValueError("Target ToA must be between 0 and 4095.")
                self.target_toa = value
                display_label = self.query_one("#toa_target_grid > .value_display", Label)
                display_label.update(str(self.target_toa))
                self.notify(f"Set Target ToA to {self.target_toa}.", severity="info")
            except ValueError as e:
                self.notify(f"Invalid Target ToA: {e}", severity="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button pressed events."""
        if event.button.id == "read-202-toa-templates":
            # read the output files from page 202
            template_files = self.parent_panel.get_202_output_files()
            if len(template_files) != int(self.parent_panel.asic_num):
                self.notify(f"Error: Expected {self.parent_panel.asic_num} template files, but got {len(template_files)}.", severity="error")
                return
            else:
                # check if all files exist
                for file in template_files:
                    if not os.path.exists(file):
                        self.notify(f"Error: Template file {file} does not exist.", severity="error")
                        return
                self.template_json_path_list = template_files
                # set the labels
                for i, file in enumerate(template_files):
                    label = self.query_one(f"#toa_template_label_asic{i}", Label)
                    label.update(file)
                self.notify("Successfully read template files from 202 output.", severity="info")
        elif event.button.id == "start-toa-scan":
            if not self.process_running:
                self.process_running = True
                event.button.variant = "error"
                event.button.label = "Stop ToA Scan"
                asyncio.create_task(self.run_script())
            else:
                if self.process is not None and self.process.returncode is None:
                    self.process.kill()
                    self.notify("ToA Scan process killed by user.", severity="warning")
                    progress_bar = self.query_one("#toa-progress-bar", ProgressBar)
                    progress_bar.update(progress=0)

    async def run_script(self) -> None:
        log = self.query_one("#toa_log", Log)
        log.clear()
        log.write_line("▶ Starting ToA Scan ...")

        self.run_cmd = 'python3 -u ./203_ToACalibX.py --ui'
        self.run_cmd += f' -t {self.target_toa}'
        self.run_cmd += f' -a {self.parent_panel.asic_num}'
        self.run_cmd += f' -c {self.parent_panel.udp_config_file}'

        if len(self.template_json_path_list) == int(self.parent_panel.asic_num):
            asic_json_str = ','.join(self.template_json_path_list)
            self.run_cmd += f' -i {asic_json_str}'

        log.write_line(f"▶ Running command: {self.run_cmd}")

        self.process = await asyncio.create_subprocess_exec(
            *self.run_cmd.split(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        self.running_output_unordered_list = []
        self.running_output_unordered_asic = []

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
                        progress_bar = self.query_one("#toa-progress-bar", ProgressBar)
                        bounded_value = max(0, min(progress_bar.total, progress_value))
                        progress_bar.update(progress=bounded_value)
                    except (IndexError, ValueError):
                        pass
                elif text.startswith("- Saved final I2C settings for ASIC"):
                    try:
                        parts = text.split(" ")
                        _asic = parts[7]
                        output_i2c_path = parts[9]
                        self.running_output_unordered_asic.append(int(_asic))
                        self.running_output_unordered_list.append(output_i2c_path)
                        self.notify(f"Pedestal output for ASIC {_asic} saved to {output_i2c_path}", severity="info")
                    except (IndexError, ValueError):
                        pass
                else:
                    log.write_line(text)

        await read_stream(self.process.stdout)

        rc = await self.process.wait()

        self.process_running = False
        self.process = None

        self.output_file_list = []
        for asic_index in range(len(self.running_output_unordered_asic)):
            if asic_index in self.running_output_unordered_asic:
                idx = self.running_output_unordered_asic.index(asic_index)
                self.output_file_list.append(self.running_output_unordered_list[idx])

        btn = self.query_one("#start-toa-scan", Button)
        btn.variant = "success"
        btn.label = "Start ToA Scan"

        progress_bar = self.query_one("#toa-progress-bar", ProgressBar)
        progress_bar.update(progress=0)

        if rc == -9:
            log.write_line("⛔ ToA Scan was killed.")
        else:
            log.write_line(f"✅ ToA Scan completed with exit code {rc}.")

        self.notify("ToA Scan process has completed.", severity="info")
        
