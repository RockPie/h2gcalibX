# 000_UI_test.py
from __future__ import annotations

import asyncio
import os
import sys

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Button, Static
from textual.containers import Horizontal

class IODelayApp(App):
    """Run 102_IODelay.py and show its console output."""

    CSS = """
    Screen { layout: vertical; }

    #controls {
        height: 4;
        border: round green;
        content-align: center middle;
    }

    #output {
        border: round cyan;
        overflow: auto;
    }

    #run_button {
        min-width: 18;
        height: 100%;
        margin-right: 2;
        color: white;
        text-style: bold;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Horizontal(id="controls"):
            yield Button("run", id="run_button")
            yield Static("Click the button to run the script.", id="info")
            yield Static("", id="spacer", expand=True)

        yield Static("Output will appear here…", id="output")

        yield Footer()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run_button":
            event.button.disabled = True
            try:
                await self.run_script("102_IODelay.py")
            finally:
                event.button.disabled = False

    async def run_script(self, script_name: str) -> None:
        """Run a Python script asynchronously and stream its output."""
        output_box = self.query_one("#output", Static)
        output_text = [f"▶ Running {script_name} ...\n"]

        script_path = os.path.abspath(script_name)
        if not os.path.exists(script_path):
            output_box.update(f"❌ Script not found: {script_path}")
            return

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        process = await asyncio.create_subprocess_exec(
            sys.executable,
            script_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )

        assert process.stdout is not None
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            text = line.decode(errors="replace")
            output_text.append(text)
            output_box.update("".join(output_text))

        await process.wait()
        code = process.returncode
        output_text.append(f"\n✅ Process finished with exit code {code}.")
        output_box.update("".join(output_text))


if __name__ == "__main__":
    IODelayApp().run()