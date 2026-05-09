"""Modern Textual YAML editor for MyClashShell."""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

import yaml
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Footer, Static, TextArea

from scripts.lib.paths import repo_root_from_env

try:
    from tree_sitter import Language
    import tree_sitter_yaml
except Exception:  # pragma: no cover
    Language = None  # type: ignore[assignment]
    tree_sitter_yaml = None  # type: ignore[assignment]


class YamlEditorApp(App[None]):
    CSS = """
    Screen {
        background: $surface;
    }
    #root {
        height: 100%;
        layout: vertical;
        padding: 1;
    }
    .header {
        height: auto;
        layout: vertical;
        margin-bottom: 1;
    }
    #title {
        text-style: bold;
        color: $accent;
    }
    #file-state {
        color: $text-muted;
        text-style: italic;
    }
    #path {
        color: $text-muted;
    }
    #status {
        height: auto;
        color: $text-muted;
        margin-bottom: 1;
    }
    #editor {
        height: 1fr;
        border: round $boost;
    }
    #editor:focus {
        border: tall $accent;
    }
    .toolbar {
        height: auto;
        layout: horizontal;
        margin-top: 1;
        align-vertical: middle;
    }
    .toolbar Button {
        margin-right: 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+s", "save_file", "Save", show=False, key_display="ctrl+s"),
        Binding("ctrl+r", "reset_file", "Reset", show=False, key_display="ctrl+r"),
        Binding("escape", "quit", "Exit", show=False, key_display="esc"),
        Binding("ctrl+q", "quit", "Quit", show=False, key_display="ctrl+q"),
    ]

    def __init__(self, yaml_path: Path | None = None):
        super().__init__()
        root = repo_root_from_env() or Path(__file__).resolve().parents[2]
        self._yaml_path = yaml_path or (root / "user_config.yaml")
        self._last_valid: dict | list | str | int | float | bool | None = None
        self._loaded_text = ""
        self._dirty = False

    def compose(self) -> ComposeResult:
        with Vertical(id="root"):
            with Vertical(classes="header"):
                yield Static("YAML Editor", id="title")
                yield Static("clean", id="file-state", markup=False)
                yield Static(str(self._yaml_path), id="path", markup=False)
                yield Static("ready", id="status", markup=False)
            yield TextArea(
                text="",
                language="yaml",
                id="editor",
                show_line_numbers=True,
                tab_behavior="indent",
                soft_wrap=False,
                compact=False,
            )
            with Horizontal(classes="toolbar"):
                yield Button("Reset", id="reset", variant="default")
                yield Button("Validate", id="validate", variant="default")
                yield Button("Save", id="save", variant="primary")
                yield Button("Exit", id="exit", variant="error")
        yield Footer()

    async def on_mount(self) -> None:
        self._install_yaml_highlight()
        await self._load_file()
        editor = self.query_one("#editor", TextArea)
        editor.focus()
        try:
            editor.language = "yaml"
        except Exception:
            pass
        try:
            editor.theme = "monokai"
        except Exception:
            pass
        try:
            editor.update_highlight_query()
        except Exception:
            pass

    def _set_title_state(self) -> None:
        status = "dirty" if self._dirty else "clean"
        self.query_one("#file-state", Static).update(status)

    def _install_yaml_highlight(self) -> None:
        editor = self.query_one("#editor", TextArea)
        if Language is None or tree_sitter_yaml is None:
            return
        try:
            editor.register_language("yaml", Language(tree_sitter_yaml.language()), tree_sitter_yaml.HIGHLIGHTS_QUERY)
            editor.language = "yaml"
            editor.update_highlight_query("yaml", tree_sitter_yaml.HIGHLIGHTS_QUERY)
        except Exception:
            pass

    async def _load_file(self) -> None:
        try:
            text = await asyncio.to_thread(self._yaml_path.read_text, encoding="utf-8")
        except Exception as exc:
            self.query_one("#status", Static).update(f"load failed: {exc}")
            return
        self._loaded_text = text
        self._dirty = False
        self.query_one("#editor", TextArea).text = text
        self.query_one("#status", Static).update("loaded")
        self._set_title_state()

    def _editor_text(self) -> str:
        return self.query_one("#editor", TextArea).text

    def _set_status(self, msg: str) -> None:
        self.query_one("#status", Static).update(msg)

    @staticmethod
    def _yaml_hint() -> str:
        return "保存后如改了运行时配置，可能需要 myclash service reload_kernel"

    @staticmethod
    def _yaml_error(exc: Exception) -> str:
        mark = getattr(exc, "problem_mark", None)
        if mark is not None:
            line = getattr(mark, "line", None)
            column = getattr(mark, "column", None)
            if line is not None and column is not None:
                return f"{exc} (line {line + 1}, col {column + 1})"
        return str(exc)

    @on(TextArea.Changed, "#editor")
    def editor_changed(self) -> None:
        text = self._editor_text()
        self._dirty = text != self._loaded_text
        self._set_title_state()
        if self._dirty:
            self._set_status("modified")

    @on(Button.Pressed, "#reset")
    async def reset_file(self) -> None:
        await self._load_file()
        self._set_status("reset and local changes discarded")

    @on(Button.Pressed, "#validate")
    async def validate_file(self) -> None:
        try:
            self._last_valid = yaml.safe_load(self._editor_text())
        except Exception as exc:
            self._set_status(f"invalid yaml: {self._yaml_error(exc)}")
            return
        if isinstance(self._last_valid, dict):
            self._set_status(f"valid yaml: {len(self._last_valid)} top-level keys")
        else:
            self._set_status("valid yaml")

    @on(Button.Pressed, "#save")
    async def save_file(self) -> None:
        text = self._editor_text()
        if not self._dirty:
            self._set_status("nothing to save")
            return
        try:
            self._last_valid = yaml.safe_load(text)
        except Exception as exc:
            self._set_status(f"save blocked: {exc}")
            return
        try:
            await asyncio.to_thread(self._atomic_write_text, text)
        except Exception as exc:
            self._set_status(f"save failed: {exc}")
            return
        self._loaded_text = text
        self._dirty = False
        self._set_title_state()
        self._set_status(f"saved · {self._yaml_hint()}")

    @on(Button.Pressed, "#exit")
    async def exit_editor(self) -> None:
        self.exit()

    def action_reset_file(self) -> None:
        self.run_worker(self._load_file(), group="yaml-load", exclusive=True, exit_on_error=False)

    def action_save_file(self) -> None:
        self.run_worker(self.save_file(), group="yaml-save", exclusive=True, exit_on_error=False)

    def _atomic_write_text(self, text: str) -> None:
        self._yaml_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(self._yaml_path.parent)) as tmp:
            tmp.write(text)
            tmp.flush()
            tmp_path = Path(tmp.name)
        tmp_path.replace(self._yaml_path)


def main() -> None:
    YamlEditorApp().run()


if __name__ == "__main__":
    main()
