"""MyClashShell Textual application (main screen)."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import time
from collections import deque
from typing import Any, Callable

from textual import on
from textual.actions import SkipAction
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.dom import DOMNode
from textual.events import Key
from textual.widget import Widget
from textual.theme import BUILTIN_THEMES, Theme
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    ContentSwitcher,
    Footer,
    Input,
    Label,
    ListItem,
    ListView,
    Select,
    Static,
    Switch,
)

from scripts.lib.config_runtime import runtime_config_patch_payload
from .client import ClashClient
from .constants import VIEW_IDS
from .formatting import (
    _fmt_bytes,
    _fmt_rate,
    _overview_sparkline_columns,
    _sparkline,
    _truncate,
)
from .state import TuiState
from .widgets import ProxyNodeButton, ProxyNodeRows, ProxyNodeScroll, ProxyRightPanel

def _atom_one_dark_theme_no_purple() -> Theme:
    """Textual 内置 atom-one-dark 的 accent/secondary 为紫色；与常见编辑器配色不一致，改为金/青。"""
    b = BUILTIN_THEMES["atom-one-dark"]
    return Theme(
        name="atom-one-dark",
        primary=b.primary,
        secondary="#56B6C2",
        warning=b.warning,
        error=b.error,
        success=b.success,
        accent="#E5C07B",
        foreground=b.foreground,
        background=b.background,
        surface=b.surface,
        panel=b.panel,
        boost=b.boost,
        dark=b.dark,
        luminosity_spread=b.luminosity_spread,
        text_alpha=b.text_alpha,
        variables=dict(b.variables),
    )


class ClashTuiApp(App[None]):
    theme = "atom-one-dark"

    CSS = """
    Screen {
        background: $surface;
    }
    #root {
        layout: horizontal;
        height: 100%;
    }
    #sidebar {
        width: 18;
        min-width: 18;
        height: 100%;
        layout: vertical;
        background: $panel;
        border-right: tall $primary;
        padding: 1 0;
    }
    #sidebar-nav {
        height: 1fr;
        width: 100%;
        background: $panel;
        border: none;
        padding: 0;
    }
    #sidebar-nav ListItem {
        padding: 1 1;
        margin: 0 1;
        height: auto;
        min-height: 3;
    }
    #sidebar-nav Label {
        text-style: bold;
    }
    #sidebar-nav ListItem:hover {
        background: $foreground 12%;
    }
    #sidebar-nav ListItem.-highlight {
        background: $primary 48%;
        text-style: bold;
        border-left: tall $accent;
        margin-left: 0;
    }
    #sidebar-nav:focus ListItem.-highlight {
        background: $accent 42%;
        border-left: heavy $accent;
        text-style: bold;
    }
    #main {
        width: 1fr;
        height: 100%;
        layout: vertical;
        padding: 0 0 0 1;
    }
    #main-views {
        height: 1fr;
        min-height: 5;
    }
    .view-pane {
        height: 1fr;
        layout: vertical;
        overflow: hidden;
    }
    .page-header {
        height: auto;
        layout: horizontal;
        padding: 0 0 1 0;
        align-vertical: middle;
    }
    .page-title {
        width: 1fr;
        text-style: bold;
        color: $accent;
        margin-bottom: 0;
        padding-bottom: 1;
        border-bottom: wide $boost;
    }
    #group-line {
        height: auto;
        color: $text-muted;
        margin-bottom: 0;
    }
    #proxy-scroll {
        height: 1fr;
        min-height: 5;
        border: round $boost;
        background: $panel;
    }
    ProxyRightPanel:focus-within #proxy-scroll {
        border: tall $accent;
        background-tint: $primary 18%;
    }
    #proxy-rows {
        width: 100%;
        height: auto;
    }
    #proxy-split {
        height: 1fr;
        layout: horizontal;
        min-height: 5;
    }
    #proxy-group-list {
        width: 22;
        min-width: 18;
        height: 1fr;
        margin-right: 1;
        border: round $boost;
        background: $panel;
    }
    #proxy-group-list:focus {
        border: tall $accent;
        background-tint: $primary 18%;
    }
    #proxy-group-list ListItem {
        padding: 0 1;
        height: auto;
        min-height: 2;
    }
    #proxy-group-list ListItem.-highlight {
        background: $primary 35%;
        text-style: bold;
    }
    #proxy-group-list:focus ListItem.-highlight {
        background: $accent 40%;
        text-style: bold;
    }
    ProxyRightPanel {
        width: 1fr;
        height: 1fr;
        layout: vertical;
        min-width: 10;
    }
    #status-line {
        height: auto;
        color: $text-muted;
        padding-top: 0;
    }
    .stat-row {
        layout: horizontal;
        height: auto;
        margin: 0 0 1 0;
        grid-gutter: 0;
    }
    .stat-card {
        width: 1fr;
        height: auto;
        min-height: 3;
        padding: 0;
        border: round $primary;
        background: $panel;
    }
    .stat-label {
        color: $text-muted;
    }
    .stat-value {
        text-style: bold;
    }
    #ov-ul, #ov-dl {
        color: $accent;
        text-style: bold;
    }
    #overview-charts {
        height: auto;
        margin-top: 1;
        padding: 1 1;
        border: round $primary;
        background: $panel;
    }
    .overview-chart-title {
        color: $accent;
        text-style: bold;
        margin-top: 1;
        height: auto;
    }
    .overview-chart-title:first-of-type {
        margin-top: 0;
    }
    .overview-spark {
        width: 100%;
        height: auto;
        min-height: 2;
        color: $foreground;
        text-style: bold;
        margin-top: 0;
        margin-bottom: 0;
    }
    #overview-charts:focus {
        background-tint: $foreground 6%;
    }
    .config-sheet {
        height: 1fr;
        layout: vertical;
        border: round $boost;
        padding: 0 1 1 1;
        margin-top: 0;
        background: $panel;
    }
    .config-section-title {
        height: auto;
        color: $text-muted;
        text-style: bold;
        margin-top: 1;
        margin-bottom: 0;
    }
    .config-section-title:first-of-type {
        margin-top: 0;
    }
    .config-section {
        height: auto;
        layout: vertical;
    }
    .cfg-row {
        height: auto;
        margin-bottom: 0;
        layout: horizontal;
        align-vertical: middle;
    }
    .cfg-label {
        width: 14;
        color: $text-muted;
    }
    #cfg-api-status {
        height: auto;
        color: $text-muted;
        text-style: italic;
        margin-bottom: 0;
    }
    #cfg-bind {
        color: $text-muted;
        text-style: italic;
    }
    Input:focus {
        border: tall $accent;
    }
    Select:focus {
        border: tall $accent;
    }
    Switch:focus {
        border: tall $accent;
    }
    #cfg-apply {
        margin-top: 0;
        width: auto;
    }
    """

    def _get_dom_base(self) -> DOMNode:
        """栈顶为 ModalScreen 时，仍从主界面屏查询 #status-line 等控件（见 Textual App.default_screen）。"""
        stack = self._screen_stack
        if len(stack) > 1:
            return stack[0]
        return super()._get_dom_base()

    BINDINGS = [
        Binding("q", "quit", "Quit", show=False),
        Binding(
            "up,k",
            "proxy_list_up",
            "Proxy nodes up",
            show=False,
            priority=True,
        ),
        Binding(
            "down,j",
            "proxy_list_down",
            "Proxy nodes down",
            show=False,
            priority=True,
        ),
        Binding("left", "move_left", "Left", show=False),
        Binding("right", "move_right", "Right", show=False),
        Binding("h", "move_left", "Left", show=False),
        Binding("l", "move_right", "Right", show=False),
        Binding("enter", "select_node", "Select", show=False),
        Binding("r", "retest", "Retest", show=False),
        Binding("[", "prev_group", "Prev group", show=False),
        Binding("]", "next_group", "Next group", show=False),
        Binding("u", "sync", "Sync", show=False),
        Binding("escape", "focus_proxy_grid", "Main", show=False),
        Binding("ctrl+b", "focus_sidebar", "Sidebar", show=False, key_display="ctrl+b"),
    ]

    def __init__(self, preferred_group: str | None = None):
        super().__init__()
        _theme = os.getenv("MYCLASH_TUI_THEME", "").strip() or "atom-one-dark"
        self.theme = _theme
        self._preferred_group = preferred_group
        self._client = ClashClient()
        self._state = TuiState(self._client, preferred_group=preferred_group)
        # >0 时每 N 秒自动测速；默认 0，仅按 r 或换组/同步等单次触发
        self._auto_refresh_s = int(os.getenv("MYCLASH_TUI_AUTO_REFRESH", "0"))
        self._prev_t: float | None = None
        self._prev_down = 0
        self._prev_up = 0
        self._down_hist: deque[float] = deque(maxlen=400)
        self._up_hist: deque[float] = deque(maxlen=400)
        self._overview_err = ""
        self._last_runtime_config: dict[str, Any] | None = None
        self._proxy_group_sync = False
        self._proxy_lazy_init_done = False

    def compose(self) -> ComposeResult:
        with Horizontal(id="root"):
            with Vertical(id="sidebar"):
                yield ListView(
                    ListItem(Label("Overview")),
                    ListItem(Label("Proxies")),
                    ListItem(Label("Config")),
                    id="sidebar-nav",
                    classes="sidebar-list",
                    initial_index=0,
                )
            with Vertical(id="main"):
                with ContentSwitcher(id="main-views", initial="view-overview"):
                    with Vertical(id="view-overview", classes="view-pane"):
                        yield Static("Overview", classes="page-title")
                        with Horizontal(classes="stat-row"):
                            with Vertical(classes="stat-card"):
                                yield Static("Upload", classes="stat-label")
                                yield Static("—", id="ov-ul", classes="stat-value")
                            with Vertical(classes="stat-card"):
                                yield Static("Download", classes="stat-label")
                                yield Static("—", id="ov-dl", classes="stat-value")
                            with Vertical(classes="stat-card"):
                                yield Static("Upload total", classes="stat-label")
                                yield Static("—", id="ov-ut", classes="stat-value")
                            with Vertical(classes="stat-card"):
                                yield Static("Download total", classes="stat-label")
                                yield Static("—", id="ov-dt", classes="stat-value")
                            with Vertical(classes="stat-card"):
                                yield Static("Active conns", classes="stat-label")
                                yield Static("—", id="ov-nb", classes="stat-value")
                        with Vertical(id="overview-charts"):
                            yield Static("Download rate", classes="overview-chart-title")
                            yield Static("", id="overview-chart-dl", classes="overview-spark", markup=False)
                            yield Static("Upload rate", classes="overview-chart-title")
                            yield Static("", id="overview-chart-ul", classes="overview-spark", markup=False)
                    with Vertical(id="view-proxies", classes="view-pane"):
                        yield Static("Proxies", classes="page-title")
                        yield Static(id="group-line", markup=False)
                        with Horizontal(id="proxy-split"):
                            yield ListView(id="proxy-group-list")
                            with ProxyRightPanel(
                                id="proxy-right",
                                get_current_view=self._current_view,
                                on_refresh_card_contents=self._refresh_card_contents,
                            ):
                                with ProxyNodeScroll(
                                    id="proxy-scroll",
                                    can_focus=False,
                                    get_current_view=self._current_view,
                                    on_proxy_move_selection_delta=self._proxy_move_selection_delta,
                                    on_proxy_pick_by_name=self._activate_proxy_by_name,
                                ):
                                    yield ProxyNodeRows(
                                        id="proxy-rows",
                                        get_current_view=self._current_view,
                                        on_proxy_move_selection_delta=self._proxy_move_selection_delta,
                                    )
                    with Vertical(id="view-config", classes="view-pane"):
                        with Horizontal(classes="page-header"):
                            yield Static("Config", classes="page-title")
                        with Vertical(classes="config-sheet"):
                            yield Static("", id="cfg-api-status", markup=False)
                            with VerticalScroll():
                                yield Static("Runtime", classes="config-section-title")
                                with Vertical(classes="config-section"):
                                    with Horizontal(classes="cfg-row"):
                                        yield Label("Mode", classes="cfg-label")
                                        yield Select(
                                            [("Rule", "rule"), ("Global", "global"), ("Direct", "direct")],
                                            id="cfg-mode",
                                            allow_blank=False,
                                        )
                                    with Horizontal(classes="cfg-row"):
                                        yield Label("Log level", classes="cfg-label")
                                        yield Select(
                                            [
                                                ("Debug", "debug"),
                                                ("Info", "info"),
                                                ("Warning", "warning"),
                                                ("Error", "error"),
                                                ("Silent", "silent"),
                                            ],
                                            id="cfg-loglevel",
                                            allow_blank=False,
                                        )
                                    with Horizontal(classes="cfg-row"):
                                        yield Label("Allow LAN", classes="cfg-label")
                                        yield Switch(value=False, id="cfg-lan")
                                    with Horizontal(classes="cfg-row"):
                                        yield Label("IPv6", classes="cfg-label")
                                        yield Switch(value=False, id="cfg-ipv6")
                                    with Horizontal(classes="cfg-row"):
                                        yield Label("Bind address", classes="cfg-label")
                                        yield Static("—", id="cfg-bind", markup=False)
                                yield Button("Apply to runtime (PATCH /configs)", id="cfg-apply", variant="primary")
                yield Static(id="status-line", markup=False)
        yield Footer()

    def _current_view(self) -> str | None:
        try:
            return self.query_one("#main-views", ContentSwitcher).current
        except Exception:
            return None

    def _safe_call_from_thread(self, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """测速等后台线程可能在 App 退出后才结束，避免 call_from_thread 抛错。"""
        try:
            self.call_from_thread(callback, *args, **kwargs)
        except RuntimeError as exc:
            if "App is not running" not in str(exc):
                raise

    async def on_mount(self) -> None:
        self.register_theme(_atom_one_dark_theme_no_purple())
        self.refresh_css(animate=False)
        # 代理节点多时，逐 mount 按钮很慢；默认在「概览」不必先建整表，等进入代理页再建。
        rows = self.query_one("#proxy-rows", Vertical)
        rows.can_focus = True
        self.query_one("#overview-charts", Vertical).can_focus = True
        self.query_one("#sidebar-nav", ListView).focus()
        self.set_interval(1.0, self._tick_overview)
        if self._auto_refresh_s > 0:
            self.set_interval(float(self._auto_refresh_s), self._on_auto_timer)
        nav = self.query_one("#sidebar-nav", ListView)
        self._apply_sidebar_index(nav.index if nav.index is not None else 0)
        # 首次拉 /proxies 放在 worker，避免阻塞首帧（内核未起或 API 慢时尤其明显）。
        self.run_worker(
            self._bootstrap_after_mount_async(),
            group="tui-bootstrap",
            exclusive=True,
            exit_on_error=False,
        )

    async def _bootstrap_after_mount_async(self) -> None:
        try:
            await asyncio.to_thread(self._state.refresh_groups_and_nodes)
        except Exception as exc:
            self._state.last_error = str(exc)
        await self._rebuild_group_list_async()

    def on_unmount(self) -> None:
        self._state._abort_delay_test.set()

    def action_help_quit(self) -> None:
        """Ctrl+C 字符路径（与 SIGINT 二选一或同时）：直接退出。"""
        self.exit()

    def _apply_sidebar_index(self, idx: int | None) -> None:
        if idx is None or not (0 <= idx < len(VIEW_IDS)):
            return
        self.query_one("#main-views", ContentSwitcher).current = VIEW_IDS[idx]
        self._on_view_switched(VIEW_IDS[idx])
        self._sync_main_footer()

    def _sidebar_has_focus(self) -> bool:
        w = self.focused
        while w is not None:
            if w.id == "sidebar":
                return True
            w = w.parent
        return False

    def _focus_first_in_main(self) -> None:
        """进入当前页主区的第一个可交互控件（侧栏 ↑↓ 只换页，需 Enter/Tab 再进来）。"""
        vid = self._current_view()
        try:
            if vid == "view-overview":
                self.query_one("#overview-charts", Vertical).focus()
            elif vid == "view-proxies":
                self.query_one("#proxy-group-list", ListView).focus()
            elif vid == "view-config":
                self.query_one("#cfg-mode", Select).focus()
        except Exception:
            pass

    def on_key(self, event: Key) -> None:
        if event.key == "tab" and self._sidebar_has_focus():
            event.prevent_default()
            event.stop()
            self._focus_first_in_main()

    @on(ListView.Highlighted, "#sidebar-nav")
    def sidebar_highlighted(self, event: ListView.Highlighted) -> None:
        self._apply_sidebar_index(event.list_view.index)

    @on(ListView.Selected, "#sidebar-nav")
    def sidebar_selected(self, event: ListView.Selected) -> None:
        self._apply_sidebar_index(event.index)
        self._focus_first_in_main()

    @on(ListView.Highlighted, "#proxy-group-list")
    async def proxy_group_highlighted(self, event: ListView.Highlighted) -> None:
        if self._proxy_group_sync or self._current_view() != "view-proxies":
            return
        idx = event.list_view.index
        if idx is None or not (0 <= idx < len(self._state.groups)):
            return
        if idx == self._state.group_idx:
            return
        self._state.group_idx = idx
        self._state.delays = {}
        try:
            self._state.refresh_groups_and_nodes()
            self._state.last_error = ""
        except Exception as exc:
            self._state.last_error = str(exc)
        self._start_delay_test_with_ui()
        await self._rebuild_cards_async()
        self._sync_proxy_chrome()
        self._sync_main_footer()

    def _on_view_switched(self, vid: str) -> None:
        if vid == "view-config":
            self.run_worker(
                self._load_config_async(),
                group="config",
                exclusive=True,
                exit_on_error=False,
            )
        elif vid == "view-proxies":
            self.run_worker(
                self._ensure_proxy_grid_async(),
                group="proxy-grid-init",
                exclusive=True,
                exit_on_error=False,
            )

    def _tick_overview(self) -> None:
        try:
            data = self._client.get_connections()
            self._overview_err = ""
        except Exception as exc:
            self._overview_err = str(exc)
            self.query_one("#ov-ul", Static).update("—")
            self.query_one("#ov-dl", Static).update("—")
            self.query_one("#overview-chart-dl", Static).update(f"error: {exc}")
            self.query_one("#overview-chart-ul", Static).update("—")
            return

        now = time.monotonic()
        down_total = float(data.get("downloadTotal", 0))
        up_total = float(data.get("uploadTotal", 0))
        conns = data.get("connections") or []

        if self._prev_t is not None:
            dt = now - self._prev_t
            if dt > 0:
                d_rate = max(0.0, (down_total - self._prev_down) / dt)
                u_rate = max(0.0, (up_total - self._prev_up) / dt)
                self._down_hist.append(d_rate)
                self._up_hist.append(u_rate)

        self._prev_t = now
        self._prev_down = down_total
        self._prev_up = up_total

        ul = _fmt_rate(self._up_hist[-1]) if self._up_hist else "0 B/s"
        dl = _fmt_rate(self._down_hist[-1]) if self._down_hist else "0 B/s"
        self.query_one("#ov-ul", Static).update(ul)
        self.query_one("#ov-dl", Static).update(dl)
        self.query_one("#ov-ut", Static).update(_fmt_bytes(up_total))
        self.query_one("#ov-dt", Static).update(_fmt_bytes(down_total))
        self.query_one("#ov-nb", Static).update(str(len(conns)))

        tw = int(self.size.width) if self.size.width else 80
        cols, st = _overview_sparkline_columns(tw)
        dl_spark = _sparkline(list(self._down_hist), width=cols, stretch=st)
        ul_spark = _sparkline(list(self._up_hist), width=cols, stretch=st)
        self.query_one("#overview-chart-dl", Static).update(dl_spark)
        self.query_one("#overview-chart-ul", Static).update(ul_spark)

    def _apply_config_form_from_dict(self, cfg: dict[str, Any], *, status_msg: str | None = None) -> None:
        """把 GET /configs 的扁平字段填回表单，并可选更新顶栏说明。"""
        self._last_runtime_config = dict(cfg)
        bind = cfg.get("bind-address") or cfg.get("bind_address")
        bind_s = str(bind) if bind not in (None, "") else "—"
        self.query_one("#cfg-bind", Static).update(bind_s)
        mode = str(cfg.get("mode", "rule")).lower()
        mode_w = self.query_one("#cfg-mode", Select)
        try:
            mode_w.value = mode
        except Exception as exc:
            self.notify(f"Mode {mode!r} does not match options: {exc}", severity="warning", timeout=4)
        logl = str(cfg.get("log-level", cfg.get("log_level", "info"))).lower()
        log_w = self.query_one("#cfg-loglevel", Select)
        try:
            log_w.value = logl
        except Exception as exc:
            self.notify(f"Log level {logl!r} does not match options: {exc}", severity="warning", timeout=4)
        self.query_one("#cfg-lan", Switch).value = bool(cfg.get("allow-lan", cfg.get("allow_lan", False)))
        self.query_one("#cfg-ipv6", Switch).value = bool(cfg.get("ipv6", False))
        if status_msg is not None:
            self.query_one("#cfg-api-status", Static).update(status_msg)

    async def _load_config_async(self) -> None:
        """run_worker 默认在主线程跑协程，禁止此处使用 call_from_thread（会抛 RuntimeError）。"""
        try:
            cfg = await asyncio.to_thread(self._client.get_configs)
        except Exception as exc:
            self.notify(f"Failed to load config: {exc}", severity="error", timeout=4)
            return

        api = self._client.base_url
        msg = f"Loaded GET {api}/configs  ·  mode={cfg.get('mode')}"
        self._apply_config_form_from_dict(cfg, status_msg=msg)

    @staticmethod
    def _select_runtime_value(sel: Select, last: dict[str, Any], *keys: str, default: str) -> str:
        v = sel.value
        if v is Select.NULL or v is None:
            for k in keys:
                if k in last and last[k] is not None:
                    return str(last[k]).lower()
            return default
        return str(v).lower()

    @on(Button.Pressed, "#cfg-apply")
    async def apply_config(self) -> None:
        try:
            last = self._last_runtime_config or {}
            mode = self._select_runtime_value(
                self.query_one("#cfg-mode", Select), last, "mode", default="rule"
            )
            logl = self._select_runtime_value(
                self.query_one("#cfg-loglevel", Select),
                last,
                "log-level",
                "log_level",
                default="info",
            )
            lan = self.query_one("#cfg-lan", Switch).value
            ipv6 = self.query_one("#cfg-ipv6", Switch).value
            payload = runtime_config_patch_payload(
                mode=mode,
                log_level=logl,
                allow_lan=bool(lan),
                ipv6=bool(ipv6),
            )
            self._client.patch_configs(payload)
            cfg2 = self._client.get_configs()
        except Exception as exc:
            self.notify(f"Apply failed: {exc}", severity="error", timeout=5)
            return
        api = self._client.base_url
        self._apply_config_form_from_dict(
            cfg2,
            status_msg=f"Patched {api}/configs and reloaded",
        )
        self.notify("Applied to runtime; form refreshed", severity="information", timeout=3)

    def _on_auto_timer(self) -> None:
        if self._state.testing:
            return
        self._start_delay_test_with_ui()

    def _start_delay_test_with_ui(self) -> None:
        self._state.start_delay_test(
            on_done=lambda: self._safe_call_from_thread(self._after_delay_test),
            on_progress=lambda: self._safe_call_from_thread(self._delay_test_progress),
        )

    def _delay_test_progress(self) -> None:
        if self._current_view() == "view-proxies":
            self._refresh_card_contents()
            self._sync_proxy_chrome()

    def _after_delay_test(self) -> None:
        if self._current_view() == "view-proxies":
            self._refresh_card_contents()
            self._sync_proxy_chrome()
        self._sync_main_footer()

    def _proxy_group_or_grid_focused(self) -> bool:
        if self._current_view() != "view-proxies":
            return False
        w = self.focused
        while w is not None:
            if w.id == "proxy-rows":
                return True
            if w.id == "proxy-group-list":
                return True
            if isinstance(w, Input):
                return False
            if w.id == "sidebar-nav":
                return False
            w = w.parent
        return False

    def _main_grid_commands_active(self) -> bool:
        if self._current_view() != "view-proxies":
            return False
        w = self.focused
        while w is not None:
            if w.id in ("proxy-rows", "proxy-scroll"):
                return True
            if isinstance(w, Input):
                return False
            if w.id == "sidebar-nav":
                return False
            if w.id == "proxy-group-list":
                return False
            w = w.parent
        return False

    def _focus_in_proxy_right_panel(self) -> bool:
        w = self.focused
        while w is not None:
            if w.id in ("proxy-right", "proxy-scroll", "proxy-rows"):
                return True
            w = w.parent
        return False

    def action_proxy_list_up(self) -> None:
        if self._current_view() != "view-proxies":
            raise SkipAction()
        if not self._focus_in_proxy_right_panel():
            raise SkipAction()
        if self._proxy_move_selection_delta(-1):
            return
        sc = self.query_one("#proxy-scroll", ProxyNodeScroll)
        try:
            Widget.action_scroll_up(sc)
        except SkipAction:
            pass

    def action_proxy_list_down(self) -> None:
        if self._current_view() != "view-proxies":
            raise SkipAction()
        if not self._focus_in_proxy_right_panel():
            raise SkipAction()
        if self._proxy_move_selection_delta(1):
            return
        sc = self.query_one("#proxy-scroll", ProxyNodeScroll)
        try:
            Widget.action_scroll_down(sc)
        except SkipAction:
            pass

    def _sync_proxy_chrome(self) -> None:
        visible = self._state.display_nodes()
        status = "testing…" if self._state.testing else "ready"
        cur = (self._state.current_node or "").strip()
        idx = self._state.selected_idx
        parts: list[str] = []
        if visible and 0 <= idx < len(visible):
            focus_name = visible[idx]
            if focus_name == cur:
                parts.append(f"光标/生效: {focus_name}")
            else:
                parts.append(f"光标: {focus_name}")
                if cur:
                    parts.append(f"生效: {cur}")
        elif cur:
            parts.append(f"生效: {cur}")
        parts.append(f"{len(visible)} nodes")
        parts.append(status)
        line = "  |  ".join(parts)
        self.query_one("#group-line", Static).update(line)

    def _sync_main_footer(self) -> None:
        vid = self._current_view()
        err = self._state.last_error
        base = "Sidebar ↑↓ pages · Enter/Tab enter page · Ctrl+B sidebar · q quit"
        if vid == "view-proxies":
            extra = (
                "  |  Proxies: Tab = Group list ↔ Node list · "
                "[ ] prev/next strategy group · ↑↓ or j/k move · Enter apply · "
                "r latency test · u reload from API · Esc focus node list"
                + (f"  |  {err}" if err else "")
            )
        elif vid == "view-overview":
            extra = (
                f"  |  {_truncate(self._overview_err, 72)}"
                if self._overview_err
                else "  |  Overview: live traffic + connection counts"
            )
        elif vid == "view-config":
            extra = "  |  Config: Apply patches runtime (PATCH /configs)"
        else:
            extra = ""
        self.query_one("#status-line", Static).update(base + extra)

    async def _rebuild_group_list_async(self) -> None:
        lv = self.query_one("#proxy-group-list", ListView)
        await lv.remove_children()
        for g in self._state.groups:
            await lv.mount(ListItem(Label(g)))
        self._proxy_group_sync = True
        try:
            if self._state.groups:
                i = min(max(0, self._state.group_idx), len(self._state.groups) - 1)
                lv.index = i
        finally:
            self._proxy_group_sync = False

    async def _sync_proxy_group_list_index_async(self) -> None:
        if not self._state.groups:
            return
        lv = self.query_one("#proxy-group-list", ListView)
        self._proxy_group_sync = True
        try:
            i = min(max(0, self._state.group_idx), len(self._state.groups) - 1)
            lv.index = i
        finally:
            self._proxy_group_sync = False

    async def _rebuild_proxy_panes_async(self) -> None:
        await self._rebuild_group_list_async()
        await self._rebuild_cards_async()

    async def _ensure_proxy_grid_async(self) -> None:
        """首次进入代理页时再挂载节点按钮并触发测速，避免启动时在概览页卡很久。"""
        if self._proxy_lazy_init_done:
            return
        await self._rebuild_cards_async()
        self._start_delay_test_with_ui()
        self._proxy_lazy_init_done = True

    async def _rebuild_cards_async(self) -> None:
        rows = self.query_one("#proxy-rows", Vertical)
        await rows.remove_children()
        visible = self._state.display_nodes()
        for i, node in enumerate(visible):
            btn = ProxyNodeButton(node, id=f"pb-{i}")
            await rows.mount(btn)
        self._refresh_card_contents()
        self.call_after_refresh(self._scroll_to_selection)

    def _proxy_list_content_width(self) -> int:
        try:
            return int(self.query_one("#proxy-right", ProxyRightPanel).size.width)
        except Exception:
            return 0

    def _refresh_card_contents(self) -> None:
        visible = self._state.display_nodes()
        buttons = list(self.query("#proxy-rows ProxyNodeButton"))
        cw = self._proxy_list_content_width()
        for i, btn in enumerate(buttons):
            if i >= len(visible):
                break
            name = visible[i]
            delay = self._state.delays.get(name)
            btn.set_node_state(
                selected=(i == self._state.selected_idx),
                current=(name == self._state.current_node),
                delay=delay,
                node_type=self._state.node_types.get(name, ""),
                content_width=cw,
            )

    def _scroll_to_selection(self) -> None:
        visible = self._state.display_nodes()
        if not visible:
            return
        i = min(self._state.selected_idx, len(visible) - 1)
        buttons = list(self.query("#proxy-rows ProxyNodeButton"))
        if i < len(buttons):
            self.query_one("#proxy-scroll", ProxyNodeScroll).scroll_to_widget(
                buttons[i], animate=False
            )

    def _proxy_move_selection_delta(self, drow: int) -> bool:
        """在代理页移动节点选中；供 ProxyNodeRows / ProxyNodeScroll 与 App 绑定共用。返回是否改变了选中下标。"""
        if self._current_view() != "view-proxies" or drow == 0:
            return False
        visible = self._state.display_nodes()
        n = len(visible)
        if n == 0:
            return False
        new_idx = self._state.selected_idx + drow
        if new_idx < 0 or new_idx >= n:
            return False
        self._state.selected_idx = new_idx
        self._refresh_card_contents()
        self._sync_proxy_chrome()
        self._sync_main_footer()
        self.call_after_refresh(self._scroll_to_selection)
        return True

    def _move(self, drow: int, dcol: int) -> None:
        if not self._main_grid_commands_active():
            return
        if dcol != 0:
            return
        self._proxy_move_selection_delta(drow)

    def action_move_left(self) -> None:
        self._move(0, -1)

    def action_move_right(self) -> None:
        self._move(0, 1)

    def action_select_node(self) -> None:
        if not self._main_grid_commands_active():
            return
        try:
            self._state.select_current()
        except Exception as exc:
            self._state.last_error = str(exc)
        self._refresh_card_contents()
        self._sync_proxy_chrome()
        self._sync_main_footer()

    def action_retest(self) -> None:
        if not self._main_grid_commands_active():
            return
        self._start_delay_test_with_ui()
        self._sync_proxy_chrome()
        self._sync_main_footer()

    async def action_prev_group(self) -> None:
        if not self._proxy_group_or_grid_focused():
            return
        self._state.cycle_group(-1)
        self._start_delay_test_with_ui()
        await self._rebuild_cards_async()
        await self._sync_proxy_group_list_index_async()
        self._sync_proxy_chrome()
        self._sync_main_footer()

    async def action_next_group(self) -> None:
        if not self._proxy_group_or_grid_focused():
            return
        self._state.cycle_group(1)
        self._start_delay_test_with_ui()
        await self._rebuild_cards_async()
        await self._sync_proxy_group_list_index_async()
        self._sync_proxy_chrome()
        self._sync_main_footer()

    async def action_sync(self) -> None:
        if not self._proxy_group_or_grid_focused():
            return
        try:
            self._state.refresh_groups_and_nodes()
            self._state.last_error = ""
        except Exception as exc:
            self._state.last_error = str(exc)
        self._start_delay_test_with_ui()
        await self._rebuild_group_list_async()
        await self._rebuild_cards_async()
        self._sync_proxy_chrome()
        self._sync_main_footer()

    def action_focus_sidebar(self) -> None:
        self.query_one("#sidebar-nav", ListView).focus()

    def action_focus_proxy_grid(self) -> None:
        if self._current_view() == "view-proxies":
            self.query_one("#proxy-rows", Vertical).focus()

    def _activate_proxy_by_name(self, name: str) -> None:
        if self._current_view() != "view-proxies":
            return
        visible = self._state.display_nodes()
        if name not in visible:
            return
        self._activate_proxy_index(visible.index(name))

    def _activate_proxy_index(self, idx: int) -> None:
        if self._current_view() != "view-proxies":
            return
        visible = self._state.display_nodes()
        if not (0 <= idx < len(visible)):
            return
        self._state.selected_idx = idx
        try:
            self._state.select_current()
        except Exception as exc:
            self._state.last_error = str(exc)
        self._refresh_card_contents()
        self._sync_proxy_chrome()
        self._sync_main_footer()


def main() -> None:
    preferred_group = sys.argv[1] if len(sys.argv) > 1 else None
    app = ClashTuiApp(preferred_group=preferred_group)

    def _sigint(_signum: int, _frame: object | None) -> None:
        try:
            app.exit()
        except Exception:
            sys.exit(0)

    signal.signal(signal.SIGINT, _sigint)
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f"failed to start tui: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        try:
            signal.signal(signal.SIGINT, signal.SIG_DFL)
        except (OSError, ValueError):
            pass
