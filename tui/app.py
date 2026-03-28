"""MyClashShell Textual application (main screen)."""

from __future__ import annotations

import os
import signal
import sys
import threading
import time
from collections import deque
from typing import Any, Callable

import requests
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.events import Key
from textual.containers import Horizontal, ItemGrid, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    ContentSwitcher,
    Footer,
    Input,
    Label,
    ListItem,
    ListView,
    RichLog,
    Select,
    Static,
    Switch,
)

from tui.client import ClashClient
from tui.config_api import _cfg_int
from tui.constants import VIEW_IDS
from tui.formatting import _fmt_bytes, _fmt_rate, _sparkline, _truncate
from tui.state import TuiState
from tui.widgets import ProxyNodeButton


class ClashTuiApp(App[None]):
    theme = "nord"

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
        background: $foreground 8%;
    }
    #sidebar-nav ListItem.-highlight {
        background: $primary 28%;
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
    }
    #proxy-grid {
        height: auto;
        grid-gutter: 0 1;
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
    #overview-chart {
        height: auto;
        margin-top: 0;
        color: $text-muted;
    }
    #overview-chart:focus {
        background-tint: $foreground 8%;
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
    #log-panel {
        height: 1fr;
        min-height: 5;
        border: tall $primary;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=False),
        Binding("up", "move_up", "Up", show=False),
        Binding("down", "move_down", "Down", show=False),
        Binding("left", "move_left", "Left", show=False),
        Binding("right", "move_right", "Right", show=False),
        Binding("k", "move_up", "Up", show=False),
        Binding("j", "move_down", "Down", show=False),
        Binding("h", "move_left", "Left", show=False),
        Binding("l", "move_right", "Right", show=False),
        Binding("enter", "select_node", "Select", show=False),
        Binding("r", "retest", "Retest", show=False),
        Binding("[", "prev_group", "Prev group", show=False),
        Binding("]", "next_group", "Next group", show=False),
        Binding("u", "sync", "Sync", show=False),
        Binding("escape", "focus_proxy_grid", "Main", show=False),
        Binding("ctrl+i", "focus_search", "Search", show=False, key_display="ctrl+i"),
        Binding("ctrl+b", "focus_sidebar", "Sidebar", show=False, key_display="ctrl+b"),
    ]

    def __init__(self, preferred_group: str | None = None):
        super().__init__()
        _theme = os.getenv("MYCLASH_TUI_THEME", "").strip() or "nord"
        self.theme = _theme
        self._preferred_group = preferred_group
        self._client = ClashClient()
        self._state = TuiState(self._client, preferred_group=preferred_group)
        self._auto_refresh_s = int(os.getenv("MYCLASH_TUI_AUTO_REFRESH", "20"))
        self._prev_t: float | None = None
        self._prev_down = 0
        self._prev_up = 0
        self._down_hist: deque[float] = deque(maxlen=120)
        self._up_hist: deque[float] = deque(maxlen=120)
        self._log_filter = ""
        self._log_stop = threading.Event()
        self._log_started = False
        self._overview_err = ""
        self._last_runtime_config: dict[str, Any] | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="root"):
            with Vertical(id="sidebar"):
                yield ListView(
                    ListItem(Label("概览")),
                    ListItem(Label("代理")),
                    ListItem(Label("配置")),
                    ListItem(Label("日志")),
                    id="sidebar-nav",
                    classes="sidebar-list",
                    initial_index=0,
                )
            with Vertical(id="main"):
                with ContentSwitcher(id="main-views", initial="view-overview"):
                    with Vertical(id="view-overview", classes="view-pane"):
                        yield Static("概览", classes="page-title")
                        with Horizontal(classes="stat-row"):
                            with Vertical(classes="stat-card"):
                                yield Static("上传", classes="stat-label")
                                yield Static("—", id="ov-ul", classes="stat-value")
                            with Vertical(classes="stat-card"):
                                yield Static("下载", classes="stat-label")
                                yield Static("—", id="ov-dl", classes="stat-value")
                            with Vertical(classes="stat-card"):
                                yield Static("上传总量", classes="stat-label")
                                yield Static("—", id="ov-ut", classes="stat-value")
                            with Vertical(classes="stat-card"):
                                yield Static("下载总量", classes="stat-label")
                                yield Static("—", id="ov-dt", classes="stat-value")
                            with Vertical(classes="stat-card"):
                                yield Static("活动连接", classes="stat-label")
                                yield Static("—", id="ov-nb", classes="stat-value")
                        yield Static("", id="overview-chart", markup=False)
                    with Vertical(id="view-proxies", classes="view-pane"):
                        yield Static("代理", classes="page-title")
                        yield Static(id="group-line", markup=False)
                        with VerticalScroll(id="proxy-scroll", can_focus=False):
                            yield ItemGrid(
                                id="proxy-grid",
                                min_column_width=12,
                                regular=True,
                            )
                    with Vertical(id="view-config", classes="view-pane"):
                        with Horizontal(classes="page-header"):
                            yield Static("配置", classes="page-title")
                        with Vertical(classes="config-sheet"):
                            yield Static("", id="cfg-api-status", markup=False)
                            with VerticalScroll():
                                yield Static("端口", classes="config-section-title")
                                with Vertical(classes="config-section"):
                                    with Horizontal(classes="cfg-row"):
                                        yield Label("HTTP 端口", classes="cfg-label")
                                        yield Input("0", id="cfg-port", placeholder="port")
                                    with Horizontal(classes="cfg-row"):
                                        yield Label("SOCKS5", classes="cfg-label")
                                        yield Input("0", id="cfg-socks", placeholder="socks-port")
                                    with Horizontal(classes="cfg-row"):
                                        yield Label("Mixed", classes="cfg-label")
                                        yield Input("7890", id="cfg-mixed", placeholder="mixed-port")
                                    with Horizontal(classes="cfg-row"):
                                        yield Label("Redir", classes="cfg-label")
                                        yield Input("0", id="cfg-redir", placeholder="redir-port")
                                    with Horizontal(classes="cfg-row"):
                                        yield Label("TProxy", classes="cfg-label")
                                        yield Input("0", id="cfg-tproxy", placeholder="tproxy-port")
                                yield Static("运行", classes="config-section-title")
                                with Vertical(classes="config-section"):
                                    with Horizontal(classes="cfg-row"):
                                        yield Label("模式", classes="cfg-label")
                                        yield Select(
                                            [("Rule", "rule"), ("Global", "global"), ("Direct", "direct")],
                                            id="cfg-mode",
                                            allow_blank=False,
                                        )
                                    with Horizontal(classes="cfg-row"):
                                        yield Label("日志级别", classes="cfg-label")
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
                                        yield Label("允许局域网", classes="cfg-label")
                                        yield Switch(value=False, id="cfg-lan")
                                    with Horizontal(classes="cfg-row"):
                                        yield Label("IPv6", classes="cfg-label")
                                        yield Switch(value=False, id="cfg-ipv6")
                                    with Horizontal(classes="cfg-row"):
                                        yield Label("绑定地址", classes="cfg-label")
                                        yield Static("—", id="cfg-bind", markup=False)
                                yield Button("应用到内核 (PATCH /configs)", id="cfg-apply", variant="primary")
                    with Vertical(id="view-logs", classes="view-pane"):
                        with Horizontal(classes="page-header"):
                            yield Static("日志", classes="page-title")
                            yield Input(placeholder="过滤日志…", id="logs-filter")
                        yield RichLog(id="log-panel", max_lines=5000, auto_scroll=True, markup=False)
                yield Static(id="status-line", markup=False)
        yield Footer()

    def _current_view(self) -> str | None:
        try:
            return self.query_one("#main-views", ContentSwitcher).current
        except Exception:
            return None

    def _safe_call_from_thread(self, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """测速/日志等后台线程可能在 App 退出后才结束，避免 call_from_thread 抛错。"""
        try:
            self.call_from_thread(callback, *args, **kwargs)
        except RuntimeError as exc:
            if "App is not running" not in str(exc):
                raise

    async def on_mount(self) -> None:
        try:
            self._state.refresh_groups_and_nodes()
        except Exception as exc:
            self._state.last_error = str(exc)
        await self._rebuild_cards_async()
        grid = self.query_one("#proxy-grid", ItemGrid)
        grid.can_focus = True
        self.query_one("#overview-chart", Static).can_focus = True
        self.query_one("#sidebar-nav", ListView).focus()
        self.set_interval(1.0, self._tick_overview)
        self._start_delay_test_with_ui()
        if self._auto_refresh_s > 0:
            self.set_interval(float(self._auto_refresh_s), self._on_auto_timer)
        nav = self.query_one("#sidebar-nav", ListView)
        self._apply_sidebar_index(nav.index if nav.index is not None else 0)

    def on_unmount(self) -> None:
        self._log_stop.set()
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
                self.query_one("#overview-chart", Static).focus()
            elif vid == "view-proxies":
                self.query_one("#proxy-grid", ItemGrid).focus()
            elif vid == "view-config":
                self.query_one("#cfg-port", Input).focus()
            elif vid == "view-logs":
                self.query_one("#logs-filter", Input).focus()
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

    def _on_view_switched(self, vid: str) -> None:
        if vid == "view-config":
            self.run_worker(self._load_config_async(), group="config", exit_on_error=False)
        elif vid == "view-logs":
            self._ensure_log_tail()

    def _ensure_log_tail(self) -> None:
        if self._log_started:
            return
        self._log_started = True

        def worker():
            while not self._log_stop.is_set():
                try:
                    url = f"{self._client.base_url}/logs"
                    params = {"level": "info"}
                    with requests.get(
                        url,
                        params=params,
                        headers=self._client._headers(),
                        stream=True,
                        timeout=(5, 3),
                    ) as r:
                        r.raise_for_status()
                        for line in r.iter_lines(decode_unicode=True):
                            if self._log_stop.is_set():
                                return
                            if not line:
                                continue
                            self._safe_call_from_thread(self._append_log_line, line)
                except Exception as exc:
                    self._safe_call_from_thread(
                        self._append_log_line, f"[log stream error] {exc} (retrying…)"
                    )
                    time.sleep(2)

        threading.Thread(target=worker, daemon=True).start()

    def _append_log_line(self, line: str) -> None:
        if self._log_filter and self._log_filter.lower() not in line.lower():
            return
        try:
            self.query_one("#log-panel", RichLog).write(line)
        except Exception:
            pass

    def _tick_overview(self) -> None:
        try:
            data = self._client.get_connections()
            self._overview_err = ""
        except Exception as exc:
            self._overview_err = str(exc)
            self.query_one("#ov-ul", Static).update("—")
            self.query_one("#ov-dl", Static).update("—")
            self.query_one("#overview-chart", Static).update(f"error: {exc}")
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

        chart = (
            f"下载 {_sparkline(list(self._down_hist))}\n"
            f"上传 {_sparkline(list(self._up_hist))}"
        )
        self.query_one("#overview-chart", Static).update(chart)

    def _apply_config_form_from_dict(self, cfg: dict[str, Any], *, status_msg: str | None = None) -> None:
        """把 GET /configs 的扁平字段填回表单，并可选更新顶栏说明。"""
        self._last_runtime_config = dict(cfg)
        self.query_one("#cfg-port", Input).value = str(_cfg_int(cfg.get("port")))
        self.query_one("#cfg-socks", Input).value = str(_cfg_int(cfg.get("socks-port")))
        self.query_one("#cfg-mixed", Input).value = str(_cfg_int(cfg.get("mixed-port")))
        self.query_one("#cfg-redir", Input).value = str(_cfg_int(cfg.get("redir-port")))
        self.query_one("#cfg-tproxy", Input).value = str(_cfg_int(cfg.get("tproxy-port")))
        bind = cfg.get("bind-address") or cfg.get("bind_address")
        bind_s = str(bind) if bind not in (None, "") else "—"
        self.query_one("#cfg-bind", Static).update(bind_s)
        mode = str(cfg.get("mode", "rule")).lower()
        mode_w = self.query_one("#cfg-mode", Select)
        try:
            mode_w.value = mode
        except Exception as exc:
            self.notify(f"模式值 {mode!r} 与选项不匹配: {exc}", severity="warning", timeout=4)
        logl = str(cfg.get("log-level", cfg.get("log_level", "info"))).lower()
        log_w = self.query_one("#cfg-loglevel", Select)
        try:
            log_w.value = logl
        except Exception as exc:
            self.notify(f"日志级别 {logl!r} 与选项不匹配: {exc}", severity="warning", timeout=4)
        self.query_one("#cfg-lan", Switch).value = bool(cfg.get("allow-lan", cfg.get("allow_lan", False)))
        self.query_one("#cfg-ipv6", Switch).value = bool(cfg.get("ipv6", False))
        if status_msg is not None:
            self.query_one("#cfg-api-status", Static).update(status_msg)

    async def _load_config_async(self) -> None:
        try:
            cfg = self._client.get_configs()
        except Exception as exc:
            self._safe_call_from_thread(
                lambda: self.notify(f"读取配置失败: {exc}", severity="error", timeout=4)
            )
            return

        api = self._client.base_url
        msg = (
            f"已从 GET {api}/configs 加载  ·  mode={cfg.get('mode')}  "
            f"mixed-port={cfg.get('mixed-port')}"
        )

        def apply() -> None:
            self._apply_config_form_from_dict(cfg, status_msg=msg)

        self._safe_call_from_thread(apply)

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
            port = int(self.query_one("#cfg-port", Input).value or 0)
            socks = int(self.query_one("#cfg-socks", Input).value or 0)
            mixed = int(self.query_one("#cfg-mixed", Input).value or 0)
            redir = int(self.query_one("#cfg-redir", Input).value or 0)
            tproxy = int(self.query_one("#cfg-tproxy", Input).value or 0)
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
            payload: dict[str, Any] = {
                "port": port,
                "socks-port": socks,
                "mixed-port": mixed,
                "redir-port": redir,
                "tproxy-port": tproxy,
                "mode": mode,
                "log-level": logl,
                "allow-lan": bool(lan),
                "ipv6": bool(ipv6),
            }
            self._client.patch_configs(payload)
            cfg2 = self._client.get_configs()
        except Exception as exc:
            self.notify(f"应用失败: {exc}", severity="error", timeout=5)
            return
        api = self._client.base_url
        self._apply_config_form_from_dict(
            cfg2,
            status_msg=f"已 PATCH {api}/configs 并重新读取",
        )
        self.notify("已写入内核并刷新表单", severity="information", timeout=3)

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

    def _main_grid_commands_active(self) -> bool:
        if self._current_view() != "view-proxies":
            return False
        w = self.focused
        while w is not None:
            if w.id == "proxy-grid":
                return True
            if isinstance(w, Input):
                return False
            if w.id == "sidebar-nav":
                return False
            w = w.parent
        return False

    def _grid_columns(self) -> int:
        try:
            grid = self.query_one("#proxy-grid", ItemGrid)
            gl = grid.layout
            from textual.layouts.grid import GridLayout

            if isinstance(gl, GridLayout) and gl.grid_size:
                return max(1, int(gl.grid_size[0]))
        except Exception:
            pass
        return 6

    def _sync_proxy_chrome(self) -> None:
        group_name = self._state.groups[self._state.group_idx] if self._state.groups else "-"
        visible = self._state.display_nodes()
        status = "测速中…" if self._state.testing else "就绪"
        cur = self._state.current_node
        cur_part = f"  ·  当前 {cur}" if cur else ""
        line = f"🚀 {group_name}{cur_part}  ·  {len(visible)} 节点  ·  {status}"
        self.query_one("#group-line", Static).update(line)

    def _sync_main_footer(self) -> None:
        vid = self._current_view()
        err = self._state.last_error
        base = (
            "侧栏[↑↓]换页 [Enter]/[Tab]进主区  [ctrl+b]回侧栏  "
            "[Esc]代理节点区  [ctrl+c]退出"
        )
        if vid == "view-proxies":
            extra = (
                "  [↑↓←→/hjkl] 节点  [Enter]/点击 切换  [r] 测速  [[]/]] 分组  [u] 同步"
                + (f"  ·  {err}" if err else "")
            )
        elif vid == "view-overview":
            extra = f"  ·  {_truncate(self._overview_err, 80)}" if self._overview_err else ""
        elif vid == "view-config":
            extra = "  修改后点「应用」PATCH /configs"
        elif vid == "view-logs":
            extra = "  [ctrl+i]过滤  日志流来自 GET /logs?level=info"
        else:
            extra = ""
        self.query_one("#status-line", Static).update(base + extra)

    def _schedule_rebuild_cards(self) -> None:
        self.run_worker(
            self._rebuild_cards_async(),
            name="rebuild_proxy_grid",
            group="rebuild-grid",
            exclusive=True,
            exit_on_error=False,
        )

    async def _rebuild_cards_async(self) -> None:
        grid = self.query_one("#proxy-grid", ItemGrid)
        await grid.remove_children()
        visible = self._state.display_nodes()
        for i, node in enumerate(visible):
            btn = ProxyNodeButton(node, id=f"pb-{i}")
            await grid.mount(btn)
        self._refresh_card_contents()
        self.call_after_refresh(self._scroll_to_selection)

    def _refresh_card_contents(self) -> None:
        visible = self._state.display_nodes()
        buttons = list(self.query("#proxy-grid ProxyNodeButton"))
        for i, btn in enumerate(buttons):
            if i >= len(visible):
                break
            name = visible[i]
            delay = self._state.delays.get(name)
            btn.set_node_state(
                selected=(i == self._state.selected_idx),
                current=(name == self._state.current_node),
                delay=delay,
            )

    def _scroll_to_selection(self) -> None:
        visible = self._state.display_nodes()
        if not visible:
            return
        i = min(self._state.selected_idx, len(visible) - 1)
        buttons = list(self.query("#proxy-grid ProxyNodeButton"))
        if i < len(buttons):
            self.query_one("#proxy-scroll", VerticalScroll).scroll_to_widget(
                buttons[i], animate=False
            )

    def _move(self, drow: int, dcol: int) -> None:
        if not self._main_grid_commands_active():
            return
        visible = self._state.display_nodes()
        n = len(visible)
        if n == 0:
            return
        cols = self._grid_columns()
        row = self._state.selected_idx // cols
        col = self._state.selected_idx % cols
        nrow = row + drow
        ncol = col + dcol
        if ncol < 0 or ncol >= cols:
            return
        new_idx = nrow * cols + ncol
        if new_idx < 0 or new_idx >= n:
            return
        self._state.selected_idx = new_idx
        self._refresh_card_contents()
        self.call_after_refresh(self._scroll_to_selection)

    def action_move_up(self) -> None:
        self._move(-1, 0)

    def action_move_down(self) -> None:
        self._move(1, 0)

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
        if not self._main_grid_commands_active():
            return
        self._state.cycle_group(-1)
        self._start_delay_test_with_ui()
        await self._rebuild_cards_async()
        self._sync_proxy_chrome()
        self._sync_main_footer()

    async def action_next_group(self) -> None:
        if not self._main_grid_commands_active():
            return
        self._state.cycle_group(1)
        self._start_delay_test_with_ui()
        await self._rebuild_cards_async()
        self._sync_proxy_chrome()
        self._sync_main_footer()

    async def action_sync(self) -> None:
        if not self._main_grid_commands_active():
            return
        try:
            self._state.refresh_groups_and_nodes()
            self._state.last_error = ""
        except Exception as exc:
            self._state.last_error = str(exc)
        self._start_delay_test_with_ui()
        await self._rebuild_cards_async()
        self._sync_proxy_chrome()
        self._sync_main_footer()

    def action_focus_search(self) -> None:
        if self._current_view() == "view-logs":
            self.query_one("#logs-filter", Input).focus()

    def action_focus_sidebar(self) -> None:
        self.query_one("#sidebar-nav", ListView).focus()

    def action_focus_proxy_grid(self) -> None:
        if self._current_view() == "view-proxies":
            self.query_one("#proxy-grid", ItemGrid).focus()

    @on(Button.Pressed, ".proxy-node-btn")
    def on_proxy_node_pressed(self, event: Button.Pressed) -> None:
        if self._current_view() != "view-proxies":
            return
        wid = event.button.id or ""
        if not wid.startswith("pb-"):
            return
        try:
            idx = int(wid[3:])
        except ValueError:
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

    @on(Input.Changed, "#logs-filter")
    def filter_logs(self, event: Input.Changed) -> None:
        self._log_filter = event.value.strip()


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
