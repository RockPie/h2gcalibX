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
    Pretty
)
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.messages import Message
from textual.validation import Function, Number, ValidationResult, Validator
from textual import on
import asyncio
from pathlib import Path

from caliblibX.clx_ui_messager import *
from caliblibX.clx_ui_file_picker import FilePicker, FolderPicker

from caliblibX.clx_ui_201 import Page_201
from caliblibX.clx_ui_202 import Page_202
from caliblibX.clx_ui_203 import Page_203


class Page_204(Static):
    """Page for 204_ToTX script."""

    def __init__(self, parent, fpga_id: str, initial_dict=None, **kwargs):
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

    FPGA_Settings .sub_page{
        height: 1fr;
        width: 1fr;
    }
    """

    def __init__(self, parent, fpga_id: str, **kwargs):
        super().__init__(**kwargs)
        self.fpga_id = fpga_id
        self.parent_panel = parent
        self.id = f"fpga-{self.fpga_id}-settings"
        self.asic_num = self.parent_panel.asic_num
        self.udp_config_file = self.parent_panel.udp_config_file

        self.config_folder = Path.home()

    def compose(self) -> ComposeResult:
        yield Static("FPGA Settings", classes="sub-header")
        yield Horizontal(
            Label("[b]UDP JSON File:[/b]", markup=True, id="udp-label"),
            Label(self.udp_config_file if self.udp_config_file else "No file selected", id="udp-json-path", expand=True),
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

    def __init__(self, parent, name: str, fpga_id: str, initial_dict: dict = None, **kwargs):
        super().__init__(**kwargs)
        self.app_parent = parent
        self.fpga_name = name
        self.fpga_id = fpga_id
        self.asic_num = 2  # default
        self.udp_config_file = ""

        self.page201_init_dict = None
        self.page202_init_dict = None
        self.page203_init_dict = None
        self.page204_init_dict = None

        if initial_dict:
            self.load_from_dict(initial_dict)

    def save_to_dict(self) -> dict:
        """Save current FPGA panel settings to a dictionary."""
        output_dict = {}
        output_dict['fpga_name'] = self.fpga_name
        output_dict['fpga_id']   = self.fpga_id
        output_dict['asic_num']  = self.asic_num
        output_dict['udp_config_file'] = self.udp_config_file

        output_dict['201_settings'] = self.query_one(Page_201).save_to_dict()
        output_dict['202_settings'] = self.query_one(Page_202).save_to_dict()
        output_dict['203_settings'] = self.query_one(Page_203).save_to_dict()
        return output_dict
    
    def load_from_dict(self, input_dict: dict) -> None:
        """Load FPGA panel settings from a dictionary."""
        self.fpga_name = input_dict.get('fpga_name', self.fpga_name)
        self.fpga_id   = input_dict.get('fpga_id', self.fpga_id)
        self.asic_num  = input_dict.get('asic_num', self.asic_num)
        self.udp_config_file = input_dict.get('udp_config_file', self.udp_config_file)

        self.page201_init_dict_raw = input_dict.get('201_settings', '')
        self.page202_init_dict_raw = input_dict.get('202_settings', '')
        self.page203_init_dict_raw = input_dict.get('203_settings', '')
        self.page204_init_dict_raw = input_dict.get('204_settings', '')

        if self.page201_init_dict_raw != '':
            self.page201_init_dict = ast.literal_eval(self.page201_init_dict_raw)
        if self.page202_init_dict_raw != '':
            self.page202_init_dict = ast.literal_eval(self.page202_init_dict_raw)
        if self.page203_init_dict_raw != '':
            self.page203_init_dict = ast.literal_eval(self.page203_init_dict_raw)
        if self.page204_init_dict_raw != '':
            self.page204_init_dict = ast.literal_eval(self.page204_init_dict_raw)

    def compose(self) -> ComposeResult:
        with Horizontal(classes="fpga-row"):

            with ListView(id=f"{self.fpga_id}-menu", classes="menu", initial_index=0):
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

                yield Page_201(self, self.fpga_id, initial_dict=self.page201_init_dict, classes="sub_page")
                yield Page_202(self, self.fpga_id, initial_dict=self.page202_init_dict, classes="sub_page")
                yield Page_203(self, self.fpga_id, initial_dict=self.page203_init_dict, classes="sub_page")
                yield Page_204(self, self.fpga_id, initial_dict=self.page204_init_dict, classes="sub_page")

    def _on_mount(self, event):
        # set the first menu item as selected
        menu_id = f"{self.fpga_id}-menu"
        menu = self.query_one(f"#{menu_id}", ListView)
        if menu.children:
            menu.index = 0
            self.on_list_view_selected(ListView.Selected(menu, menu.children[0], 0))
        return super()._on_mount(event)

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

    def get_202_output_files(self) -> list[str]:
        """Get the list of output files generated by the pedestal scan."""
        page202 = self.query_one(Page_202)
        page202_output = page202.get_output_files()
        if len(page202_output) != int(self.asic_num):
            self.notify(f"Warning: Expected {self.asic_num} output files, but got {len(page202_output)}.", severity="warning")
            return []
        return page202_output
    @on(ASIC_Number_Changed)
    def handle_asic_number_changed(self, msg: ASIC_Number_Changed) -> None:
        """Handle ASIC number changed message."""
        if msg.fpga_id != self.fpga_id:
            return 
        self.asic_num = msg.asic_num
        self.notify(f"ASIC number for {self.fpga_name} set to {self.asic_num}", severity="info")

    @on(UdpJsonSelected)
    def handle_udp_json_selected(self, msg: UdpJsonSelected) -> None:
        """Handle UDP JSON file selected message."""
        if msg.fpga_id != self.fpga_id:
            return
        self.udp_config_file = msg.json_path
        self.notify(f"UDP JSON file for {self.fpga_name} set to {self.udp_config_file}", severity="info")   