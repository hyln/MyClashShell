"""Textual widgets for the proxy list."""

from __future__ import annotations

from collections.abc import Callable

from textual.containers import Vertical, VerticalScroll
from textual.errors import NoWidget
from textual.events import Click, Key, MouseDown, MouseUp, Resize
from textual.widgets import Button

from .formatting import _truncate


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


# 小于此宽度（终端列）时省略「节点类型」列，把空间留给名称与延时
_MIN_WIDTH_SHOW_TYPE = 48


class ProxyNodeScroll(VerticalScroll):
    """节点列表外层的纵向滚动：在代理页用 ↑↓ 切换选中节点，避免 ScrollableContainer 默认只滚动视图。"""

    def __init__(
        self,
        *args,
        get_current_view: Callable[[], str | None] | None = None,
        on_proxy_move_selection_delta: Callable[[int], bool] | None = None,
        on_proxy_pick_by_name: Callable[[str], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._get_current_view = get_current_view
        self._on_proxy_move_selection_delta = on_proxy_move_selection_delta
        self._on_proxy_pick_by_name = on_proxy_pick_by_name
        # Textual 仅在 down/up 命中同一 widget 时合成 Click；在滚动区内轻微移动会丢 Click，用节点名兜底。
        self._mouse_pick_start: tuple[int, int, str] | None = None

    def action_scroll_up(self) -> None:
        gv = self._get_current_view
        fn = self._on_proxy_move_selection_delta
        if gv is not None and fn is not None and gv() == "view-proxies" and fn(-1):
            return
        super().action_scroll_up()

    def action_scroll_down(self) -> None:
        gv = self._get_current_view
        fn = self._on_proxy_move_selection_delta
        if gv is not None and fn is not None and gv() == "view-proxies" and fn(1):
            return
        super().action_scroll_down()

    def _hit_proxy_button(self, sx: int, sy: int) -> ProxyNodeButton | None:
        try:
            w, _ = self.screen.get_widget_at(sx, sy)
        except NoWidget:
            return None
        while w is not None:
            if isinstance(w, ProxyNodeButton):
                return w
            if w is self:
                break
            w = w.parent
        return None

    def on_mouse_down(self, event: MouseDown) -> None:
        gv = self._get_current_view
        fn = self._on_proxy_pick_by_name
        if gv is None or fn is None or gv() != "view-proxies":
            self._mouse_pick_start = None
            return
        if event.button != 1:
            return
        btn = self._hit_proxy_button(event.screen_x, event.screen_y)
        if btn is not None:
            self._mouse_pick_start = (event.screen_x, event.screen_y, btn.node_name)
        else:
            self._mouse_pick_start = None

    def on_mouse_up(self, event: MouseUp) -> None:
        start = self._mouse_pick_start
        self._mouse_pick_start = None
        gv = self._get_current_view
        pick = self._on_proxy_pick_by_name
        if start is None or gv is None or pick is None or gv() != "view-proxies":
            return
        if event.button != 1:
            return
        sx0, sy0, name = start
        if abs(event.screen_x - sx0) + abs(event.screen_y - sy0) > 2:
            return
        btn_up = self._hit_proxy_button(event.screen_x, event.screen_y)
        if btn_up is not None:
            pick(btn_up.node_name)
            return
        pick(name)


class ProxyNodeRows(Vertical):
    """节点按钮容器；拦截 ↑↓/kj，避免未 consume 时冒泡到父级 VerticalScroll 只滚动不改选中。"""

    can_focus = True

    def __init__(
        self,
        *args,
        get_current_view: Callable[[], str | None] | None = None,
        on_proxy_move_selection_delta: Callable[[int], bool] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._get_current_view = get_current_view
        self._on_proxy_move_selection_delta = on_proxy_move_selection_delta

    def on_key(self, event: Key) -> None:
        if event.key not in ("up", "down", "j", "k"):
            return
        if not self.has_focus:
            return
        gv = self._get_current_view
        fn = self._on_proxy_move_selection_delta
        if gv is None or fn is None or gv() != "view-proxies":
            return
        event.prevent_default()
        event.stop()
        fn(-1 if event.key in ("up", "k") else 1)


class ProxyRightPanel(Vertical):
    """右侧节点区容器；宽度变化时重算每行截断与是否显示类型。"""

    def __init__(
        self,
        *args,
        get_current_view: Callable[[], str | None] | None = None,
        on_refresh_card_contents: Callable[[], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._get_current_view = get_current_view
        self._on_refresh_card_contents = on_refresh_card_contents

    def on_resize(self, _event: Resize) -> None:
        gv = self._get_current_view
        refresh = self._on_refresh_card_contents
        if gv is None or refresh is None or gv() != "view-proxies":
            return
        refresh()


class ProxyNodeButton(Button):
    """单行节点：名称、延时、（可选）类型；焦点在父级 Vertical 上。"""

    can_focus = False

    async def _on_click(self, event: Click) -> None:
        """选用逻辑在 ProxyNodeScroll 的 mouse 兜底中统一处理，避免与 Textual 的 Click 判定重复。"""
        event.stop()

    DEFAULT_CSS = """
    ProxyNodeButton {
        width: 100%;
        min-width: 0;
        min-height: 1;
        height: auto;
        content-align: left middle;
    }
    ProxyNodeButton.-cursor {
        border: heavy $accent;
        background-tint: $accent 25%;
        text-style: bold;
    }
    """

    def __init__(self, node_name: str, **kwargs):
        kwargs.setdefault("classes", "proxy-node-btn")
        kwargs.setdefault("compact", True)
        super().__init__(label=" ", variant="default", **kwargs)
        self.node_name = node_name

    def set_node_state(
        self,
        selected: bool,
        current: bool,
        delay: int | None,
        node_type: str = "",
        *,
        content_width: int = 0,
    ) -> None:
        prefix = "* " if current else "  "
        ds = _delay_style(delay)
        d_plain = _delay_text(delay)
        cw = content_width if content_width > 0 else 80
        show_type = cw >= _MIN_WIDTH_SHOW_TYPE
        typ = (node_type or "").strip()
        if typ:
            typ = _truncate(typ, 18)
        type_suffix = f"  {typ}" if show_type and typ else ""
        delay_segment = f"  [{ds}]{d_plain}[/]"
        delay_cells = len(d_plain) + 2
        name_budget = cw - delay_cells - len(type_suffix)
        name_budget = max(6, name_budget)
        name = _truncate(prefix + self.node_name, name_budget)
        self.label = f"{name}{delay_segment}{type_suffix}"
        self.variant = "success" if current else "default"
        self.set_class(selected, "-cursor")
