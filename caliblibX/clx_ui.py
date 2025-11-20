import os, json
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
)
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.messages import Message
from textual import on
import asyncio
from pathlib import Path

# ! === Messages ==============================================================
class ASIC_Number_Changed(Message):
    """Message indicating the ASIC number has changed."""

    def __init__(self, sender, fpga_id: str, asic_num: int) -> None:
        super().__init__()
        self.sender = sender
        self.fpga_id = fpga_id
        self.asic_num = asic_num

class ASIC_Number_Request(Message):
    """Message requesting the current ASIC number."""

    def __init__(self, sender, fpga_id: str) -> None:
        super().__init__()
        self.sender = sender
        self.fpga_id = fpga_id

class UdpJsonSelected(Message):
    """Message indicating a UDP JSON file has been selected."""

    def __init__(self, sender, fpga_id: str, json_path: str) -> None:
        super().__init__()
        self.sender = sender
        self.fpga_id = fpga_id
        self.json_path = json_path

def expand_path_manually(tree: DirectoryTree, target: Path):
    """手动展开指定路径的父目录链。"""
    path = target.resolve()

    # 逐层展开父目录
    parts = path.parts
    current_path = Path(parts[0])

    for part in parts[1:]:
        current_path = current_path / part

        # 找到这个路径对应的 node
        node = tree.root.find(str(current_path))
        if node:
            tree.expand(node)

# ! === File and Folder Picker Screens ========================================
class FilePicker(ModalScreen[Path]):
    """A modal screen that lets the user pick a file using DirectoryTree."""

    def __init__(self, start_path: Path | None = None) -> None:
        super().__init__()
        self.start_path = start_path or Path.home()

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static("Select a json file", id="picker-header"),
            DirectoryTree(self.start_path, id="tree"),
            id="picker-root",
        )

    def on_directory_tree_file_selected(
        self, event: DirectoryTree.FileSelected
    ) -> None:
        """When the user selects a file, dismiss the screen with the path."""
        event.stop()
        self.dismiss(event.path)

    def on_directory_tree_directory_selected(
        self, event: DirectoryTree.DirectorySelected
    ) -> None:
        """Optional: If you want to allow selecting directories as well, you can enable this."""
        # self.dismiss(event.path)
        pass

    def on_mount(self) -> None:
        tree = self.query_one("#tree", DirectoryTree)
        tree.focus()
        # expand_path_manually(tree, self.start_path)

class FolderPicker(ModalScreen[Path]):
    """A modal screen that lets the user pick a folder using DirectoryTree."""

    def __init__(self, start_path: Path | None = None) -> None:
        super().__init__()
        self.start_path = start_path or Path.home()

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static("Select a folder", id="picker-header"),
            DirectoryTree(str(self.start_path), id="tree"),
            id="picker-root",
        )

    def on_directory_tree_directory_selected(
        self, event: DirectoryTree.DirectorySelected
    ) -> None:
        """When the user selects a directory, dismiss the screen with the path."""
        event.stop()
        self.dismiss(event.path)

    def on_mount(self) -> None:
        self.query_one("#tree", DirectoryTree).focus()

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
        margin: 1;
        width: 1fr;
        content-align: center middle;
        height: 3;
    }

    Page_201 #iodelay-log {
        height: 1fr;
        border: solid #778873 50%;
        margin-top: 5;
    }
    """

    def __init__(self, parent, fpga_id: str, json_dict=None, **kwargs):
        super().__init__(**kwargs)
        self.parent_panel = parent
        self.fpga_id = fpga_id
        self.id = f"fpga-{self.fpga_id}-iodelayx"

        self.enable_trigger_lines = True  # default
        self.enable_reset = True  # default
        self.phase_setting = 0  # default

        if json_dict:
            self.import_settings_from_json(json_dict)

    def export_settings_to_json(self) -> dict:
        """Export current settings to a JSON-serializable dictionary."""
        return {
            "enable_trigger_lines": self.enable_trigger_lines,
            "enable_reset": self.enable_reset,
            "phase_setting": self.phase_setting,
        }
    
    def import_settings_from_json(self, json_dict: dict) -> None:
        """Import settings from a JSON dictionary."""
        self.enable_trigger_lines = json_dict.get("enable_trigger_lines", self.enable_trigger_lines)
        self.enable_reset = json_dict.get("enable_reset", self.enable_reset)
        self.phase_setting = json_dict.get("phase_setting", self.phase_setting)

        # Update UI elements
        trigger_radio = self.query_one("#enable-trigger-lines", RadioButton)
        trigger_radio.value = self.enable_trigger_lines

        reset_radio = self.query_one("#enable-reset", RadioButton)
        reset_radio.value = self.enable_reset

        phase_label = self.query_one("#phase-setting", Label)
        phase_label.update(str(self.phase_setting))

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
        yield Button.success("Start IO Delay Scan", id="start-iodelay-scan")
        yield Log(
            id="iodelay-log",
            auto_scroll=True,
            highlight=True,
        )

    # python3 /home/nbi-focal/Code/h2gcalibX/201_IODelayX.py  -t -r -p 12 -a 2
    async def run_scipt(self) -> None:
        # clear log
        log = self.query_one("#iodelay-log", Log)
        log.clear()
        log.write_line("▶ Starting IO Delay Scan ...")

        self.run_cmd = 'python3 -u ./201_IODelayX.py'

        if self.enable_trigger_lines:
            self.run_cmd += ' -t'
        if self.enable_reset:
            self.run_cmd += ' -r'
        self.run_cmd += f' -p {self.phase_setting}'
        self.run_cmd += f' -a {self.parent_panel.asic_num}'
        self.run_cmd += f' -c {self.parent_panel.udp_config_file}'

        log.write_line(f"▶ Running command: {self.run_cmd}")

        process = await asyncio.create_subprocess_exec(
            *self.run_cmd.split(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        async def read_stream(stream, prefix: str):
            while True:
                line = await stream.readline()
                text = line.decode(errors="ignore").rstrip("\n")
                if line:
                    log.write_line(f"{prefix}{text}")
                else:
                    break
        
        await asyncio.gather(
            read_stream(process.stdout, ""),
            read_stream(process.stderr, "ERR: ")
        )

        rc = await process.wait()
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
            asyncio.create_task(self.run_scipt())


# ! === 202 PedestalX Page =====================================================
class Page_202(Static):
    """Page for 202_PedestalX script."""
    DEFAULT_CSS = """
    Page_202 .sub-header {
        color: $text;
        text-style: bold;
        height: 3;
        padding: 0 1;
        content-align: center middle;
        border: solid $accent 50%;
    }
    Page_202 #target-pedestal-grid {
        grid-size: 3;
        grid-columns: auto 1fr auto;
        grid-rows: auto;
        height: auto;
        align-vertical: middle;
        padding: 0 1;
    }
    Page_202 #target-pedestal-label {
        width: 20;
        padding-top: 1;
    }
    Page_202 #target-pedestal-input {
        width: 25;
    }
    Page_202 #target-pedestal-value {
        width: 1fr;
        overflow: hidden;
        text-overflow: ellipsis;
        padding-top: 1;
        padding-left: 3;
        text-style: italic;
    }
    Page_202 #start-pedestal-scan {
        margin: 1;
        width: 1fr;
        content-align: center middle;
        height: 3;
    }
    Page_202 #pedestal-log {
        height: 1fr;
        border: solid #778873 50%;
        margin-top: 5;
    }
    Page_202 #template-json-grid {
        grid-size: 3;
        grid-columns: auto 1fr auto;
        grid-rows: auto;
        height: auto;
        align-vertical: middle;
        padding: 0 1;
    }
    Page_202 #template-json-label {
        width: 20;
        padding-top: 1;
    }
    Page_202 #template-json-path {
        width: 1fr;
        overflow: hidden;
        text-overflow: ellipsis;
        padding-top: 1;
        padding-left: 3;
        text-style: italic;
    }
    Page_202 #browse-template-json {
        width: 24;
        padding: 0 1;
        margin: 0;
    }
    """

    def __init__(self, parent, fpga_id: str, **kwargs):
        super().__init__(**kwargs)
        self.parent_panel = parent
        self.fpga_id = fpga_id
        self.id = f"fpga-{self.fpga_id}-pedestalx"
        self.target_pedestal = 100  # default
        self.template_json_path = ""

    def compose(self) -> ComposeResult:
        yield Static("202 PedestalX", classes="sub-header")
        yield Horizontal(
            Label("[b]Target pedestal:[/b]", markup=True, id="target-pedestal-label"),
            Label(str(self.target_pedestal), id="target-pedestal-value", expand=True),
            Input(placeholder="Target pedestal", id="target-pedestal-input"),
            id="target-pedestal-grid",
        )
        yield Horizontal(
            Label("[b]Template JSON File:[/b]", markup=True, id="template-json-label"),
            Label("Not selected", id="template-json-path", expand=True),
            Button("Browse Template JSON", id="browse-template-json"),
            id="template-json-grid",
        )
        yield Button.success("Start Pedestal Scan", id="start-pedestal-scan")
        yield Log(
            id="pedestal-log",
            auto_scroll=True,
            highlight=True,
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "browse-template-json":
            self.app.push_screen(
                FilePicker(start_path=Path("./")),
                self.on_file_picked
            )
        elif event.button.id == "start-pedestal-scan":
            asyncio.create_task(self.run_script())

    def on_file_picked(self, result: Path | None) -> None:
        """Callback when FilePicker is dismissed."""
        if result is None:
            self.notify("No file selected", severity="warning")
            self.query_one("#template-json-path", Static).update("Not selected")
        elif not os.path.isfile(result):
            self.notify(f"File does not exist: {result}", severity="error")
            self.query_one("#template-json-path", Static).update("Not selected")
        else:
            self.template_json_path = str(result)
            self.query_one("#template-json-path", Static).update(str(result))
            self.notify(f"Template JSON file set to: {result}", severity="info")

    async def run_script(self) -> None:
        # clear log
        log = self.query_one("#pedestal-log", Log)
        log.clear()
        log.write_line("▶ Starting Pedestal Scan ...")

        self.run_cmd = 'python3 -u ./202_PedestalCalibX.py'
        self.run_cmd += f' -t {self.target_pedestal}'
        if self.template_json_path:
            self.run_cmd += f' -i {self.template_json_path}'
        self.run_cmd += f' -a {self.parent_panel.asic_num}'
        self.run_cmd += f' -c {self.parent_panel.udp_config_file}'

        log.write_line(f"▶ Running command: {self.run_cmd}")

        process = await asyncio.create_subprocess_exec(
            *self.run_cmd.split(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        async def read_stream(stream, prefix: str):
            while True:
                line = await stream.readline()
                text = line.decode(errors="ignore").rstrip("\n")
                if line:
                    log.write_line(f"{prefix}{text}")
                else:
                    break
        
        await asyncio.gather(
            read_stream(process.stdout, ""),
            read_stream(process.stderr, "ERR: ")
        )

        rc = await process.wait()
        log.write_line(f"✅ Pedestal Scan finished with exit code {rc}.")
        self.notify("Pedestal Scan completed.", severity="info")

class Page_203(Static):
    """Page for 203_ToAX script."""

    def __init__(self, parent, fpga_id: str, **kwargs):
        super().__init__(**kwargs)
        self.fpga_id = fpga_id
        self.parent_panel = parent
        self.id = f"fpga-{self.fpga_id}-toax"

class Page_204(Static):
    """Page for 204_ToTX script."""

    def __init__(self, parent, fpga_id: str, **kwargs):
        super().__init__(**kwargs)
        self.fpga_id = fpga_id
        self.parent_panel = parent
        self.id = f"fpga-{self.fpga_id}-totx"

    def compose(self) -> ComposeResult:
        yield Static("[b]204_ToTX[/b]\n\nThis is the FPGA ToT Calibration page.", markup=True)

# ! === FPGA Settings Page ====================================================
class FPGA_Settings(Static):
    """FPGA Settings page."""
    DEFAULT_CSS = """
    FPGA_Settings .sub-header {
        color: $text;
        text-style: bold;
        height: 3;
        padding: 0 1;
        content-align: center middle;
        border: solid $accent 50%;
    }

    FPGA_Settings #udp-grid {
        grid-size: 3;
        grid-columns: auto 1fr auto;
        grid-rows: auto;
        height: auto;
        align-vertical: middle;
        padding: 0 1;
    }

    FPGA_Settings #asic-grid {
        grid-size: 3;
        grid-columns: auto 1fr auto;
        grid-rows: auto;
        height: auto;
        align-vertical: middle;
        padding: 0 1;
    }

    FPGA_Settings #udp-label {
        padding-top: 1;
        width: 20;
    }

    FPGA_Settings #asic-label {
        padding-top: 1;
        width: 20;
    }

    FPGA_Settings #udp-json-path {
        width: 1fr;
        overflow: hidden;
        text-overflow: ellipsis;
        padding-top: 1;
        padding-left: 3;
        text-style: italic;
    }

    FPGA_Settings #browse-udp-json {
        width: 24;
        padding: 0 1;
        margin: 0;
    }

    FPGA_Settings #asic-number {
        width: 1fr;
        overflow: hidden;
        text-overflow: ellipsis;
        padding-top: 1;
        padding-left: 3;
        text-style: italic;
    }

    FPGA_Settings #asic-input {
        width: 25;
        padding: 0 1;
        margin: 0;
    }
    """

    def __init__(self, parent, fpga_id: str, **kwargs):
        super().__init__(**kwargs)
        self.fpga_id = fpga_id
        self.id = f"fpga-{self.fpga_id}-settings"
        self.asic_num = 2  # default
        self.config_folder = Path.home()

    def compose(self) -> ComposeResult:
        yield Static("FPGA Settings", classes="sub-header")
        yield Horizontal(
            Label("[b]UDP JSON File:[/b]", markup=True, id="udp-label"),
            Label("No file selected", id="udp-json-path", expand=True),
            Button("Browse UDP JSON", id="browse-udp-json"),
            id="udp-grid",
        )
        yield Horizontal(
            Label("[b]ASIC Number:[/b]", markup=True, id="asic-label"),
            Label(str(self.asic_num), id="asic-number", expand=True),
            Input(placeholder="ASIC number", id="asic-input"),
            id="asic-grid",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "browse-udp-json":

            self.app.push_screen(
                FilePicker(start_path=Path("./")),
                self.on_file_picked
            )

    def on_file_picked(self, result: Path | None) -> None:
        """Callback when FilePicker is dismissed."""
        if result is None:
            self.notify("No file selected", severity="warning")
            self.query_one("#udp-json-path", Static).update("No file selected")
        else:
            # check if file exists
            if not os.path.isfile(result):
                self.notify(f"File does not exist: {result}", severity="error")
                self.query_one("#udp-json-path", Static).update("No file selected")
                return
            # check if file is a valid JSON
            try:
                with open(result, 'r') as f:
                    json.load(f)
            except json.JSONDecodeError:
                self.notify(f"Invalid JSON file: {result}", severity="error")
                self.query_one("#udp-json-path", Static).update("No file selected")
                return
            self.config_folder = result.parent
            self.query_one("#udp-json-path", Static).update(str(result))
            self.post_message(UdpJsonSelected(self, self.fpga_id, str(result)))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle ASIC number input submission."""
        if event.input.id == "asic-input":
            try:
                asic_num = int(event.value)
                if asic_num < 1 or asic_num > 8:
                    self.notify("ASIC number must be >= 1 and <= 8", severity="warning")
                else:
                    self.asic_num = asic_num
                    asic_label = self.query_one("#asic-number", Label)
                    asic_label.update(str(self.asic_num))
                    self.post_message(ASIC_Number_Changed(self, self.fpga_id, self.asic_num))
                event.input.value = ""
            except ValueError:
                self.notify("Invalid ASIC number", severity="error")
                event.input.value = ""

class Registers_Page(Static):
    """FPGA Registers page."""

    def __init__(self, fpga_id: str, **kwargs):
        super().__init__(**kwargs)
        self.fpga_id = fpga_id
        self.id = f"fpga-{self.fpga_id}-registers"

class FpgaPanel(Static):
    """FPGA panel with a left list menu and right content pages."""

    PAGES = [
        "FPGA Settings",
        "Registers",
        "IODelayX",
        "PedestalX",
        "ToAX",
        "ToTX"
    ]

    def __init__(self, parent, name: str, fpga_id: str, **kwargs):
        super().__init__(**kwargs)
        self.app_parent = parent
        self.fpga_name = name
        self.fpga_id = fpga_id
        self.asic_num = 2  # default
        self.udp_config_file = ""

    def compose(self) -> ComposeResult:
        with Horizontal(classes="fpga-row"):

            with ListView(id=f"{self.fpga_id}-menu", classes="menu"):
                for page in self.PAGES:
                    if page == "FPGA Settings":
                        yield ListItem(Static(page), id=f"fpga-{self.fpga_id}-settings")
                    elif page == "Registers":
                        yield ListItem(Static(page), id=f"fpga-{self.fpga_id}-registers")
                    else:
                        yield ListItem(Static(page), id=f"fpga-{self.fpga_id}-{page.lower()}")

            with ContentSwitcher(
                id=f"{self.fpga_id}-content",
                classes="content",
                initial=f"{self.fpga_id}-status",
            ):

                yield FPGA_Settings(self, self.fpga_id)
                yield Registers_Page(self.fpga_id)

                yield Page_201(self, self.fpga_id)
                yield Page_202(self, self.fpga_id)
                yield Page_203(self, self.fpga_id)
                yield Page_204(self, self.fpga_id)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """When user selects from the left list, switch the right content."""
        menu_id = f"{self.fpga_id}-menu"
        if event.list_view.id != menu_id:
            return

        selected_item = event.item

        if selected_item is None:
            return

        page_id = f"{selected_item.id}"  # already fpga-1-status / fpga-1-config...
        switcher = self.query_one(f"#{self.fpga_id}-content", ContentSwitcher)
        switcher.current = page_id

    @on(ASIC_Number_Changed)
    def handle_asic_number_changed(self, msg: ASIC_Number_Changed) -> None:
        """Handle ASIC number changed message."""
        if msg.fpga_id != self.fpga_id:
            return 
        self.asic_num = msg.asic_num
        self.notify(f"ASIC number for {self.fpga_name} set to {self.asic_num}", severity="info")

    # @on(ASIC_Number_Request)
    # def handle_asic_number_request(self, msg: ASIC_Number_Request) -> None:
    #     """Handle ASIC number request message."""
    #     if msg.fpga_id != self.fpga_id:
    #         return 
    #     msg.sender.asic_num = self.asic_num

    @on(UdpJsonSelected)
    def handle_udp_json_selected(self, msg: UdpJsonSelected) -> None:
        """Handle UDP JSON file selected message."""
        if msg.fpga_id != self.fpga_id:
            return
        self.udp_config_file = msg.json_path
        self.notify(f"UDP JSON file for {self.fpga_name} set to {self.udp_config_file}", severity="info")   