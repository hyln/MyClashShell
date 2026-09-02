"""Textual 编辑器：``myclash config edit`` 编辑 ``user_config.yaml``。"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

_repo = Path(__file__).resolve().parents[2]
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

import yaml
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Static, TextArea

from mcs_py.lib.paths import repo_root_from_env

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
        height: 1fr;
        layout: vertical;
        padding: 0 1;
    }
    .header {
        height: 1;
        layout: horizontal;
        align-vertical: middle;
    }
    #title {
        width: auto;
        text-style: bold;
        color: $accent;
        margin-right: 1;
    }
    #file-state {
        width: auto;
        color: $text-muted;
        text-style: italic;
        margin-right: 1;
    }
    #path {
        width: 1fr;
        color: $text-muted;
    }
    #status {
        height: 1;
        color: $text-muted;
        padding-left: 1;
    }
    #editor {
        height: 1fr;
        border: round $boost;
    }
    #editor:focus {
        border: tall $accent;
    }
    """

    BINDINGS = [
        Binding("ctrl+s", "save_file", "Save", key_display="ctrl+s"),
        Binding("ctrl+enter", "validate_file", "Validate", key_display="ctrl+enter"),
        Binding("ctrl+r", "reset_file", "Reset", key_display="ctrl+r"),
        Binding("escape", "quit", "Exit", key_display="esc", priority=True),
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
            with Horizontal(classes="header"):
                yield Static("YAML Editor", id="title")
                yield Static("clean", id="file-state", markup=False)
                yield Static(str(self._yaml_path), id="path", markup=False)
            yield TextArea(
                text="",
                language="yaml",
                id="editor",
                show_line_numbers=True,
                tab_behavior="indent",
                soft_wrap=False,
                compact=False,
            )
            yield Static("ready", id="status", markup=False)
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

    async def reset_file(self) -> None:
        await self._load_file()
        self._set_status("reset and local changes discarded")

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

    def action_reset_file(self) -> None:
        self.run_worker(self._load_file(), group="yaml-load", exclusive=True, exit_on_error=False)

    def action_save_file(self) -> None:
        self.run_worker(self.save_file(), group="yaml-save", exclusive=True, exit_on_error=False)

    def action_validate_file(self) -> None:
        self.run_worker(self.validate_file(), group="yaml-validate", exclusive=True, exit_on_error=False)

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
