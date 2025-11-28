from textual.app import ComposeResult
from textual.widgets import (
    Static,
    DirectoryTree,
)
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual import on
from pathlib import Path
from caliblibX.clx_ui_messager import *

def expand_path_manually(tree: DirectoryTree, target: Path):
    path = target.resolve()

    parts = path.parts
    current_path = Path(parts[0])

    for part in parts[1:]:
        current_path = current_path / part

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