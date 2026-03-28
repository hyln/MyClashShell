"""Textual widgets for the proxy grid."""

from __future__ import annotations

from textual.widgets import Button

from tui.formatting import _truncate


def _delay_text(delay: int | None) -> str:
    if delay is None:
        return "-- ms"
    return f"{delay} ms"


def _delay_style(delay: int | None) -> str:
    if delay is None:
        return "dim"
    if delay <= 250:
        return "green"
    if delay <= 600:
        return "yellow"
    return "red"


class ProxyNodeButton(Button):
    """可点击的代理节点；键盘焦点在父级 ItemGrid 上，避免抢走方向键。"""

    can_focus = False

    DEFAULT_CSS = """
    ProxyNodeButton {
        width: auto;
        min-width: 0;
        min-height: 3;
        height: auto;
    }
    ProxyNodeButton.-cursor {
        border: heavy $accent;
    }
    """

    def __init__(self, node_name: str, **kwargs):
        kwargs.setdefault("classes", "proxy-node-btn")
        kwargs.setdefault("compact", True)
        super().__init__(label=" ", variant="default", **kwargs)
        self.node_name = node_name

    def set_node_state(self, selected: bool, current: bool, delay: int | None) -> None:
        prefix = "* " if current else "  "
        name = _truncate(prefix + self.node_name, 14)
        dt = _delay_text(delay)
        ds = _delay_style(delay)
        self.label = f"{name}\n[{ds}]{dt}[/]"
        self.variant = "success" if current else "default"
        self.set_class(selected, "-cursor")
