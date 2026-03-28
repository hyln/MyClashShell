#!/usr/bin/env python3
"""MyClashShell terminal UI (Textual + Clash / mihomo REST API)."""

from __future__ import annotations

import concurrent.futures
import os
import signal
import sys
import threading
import time
from collections import deque
from typing import Any, Callable
from urllib.parse import quote

import requests

try:
    from textual import on
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.events import Key
    from textual.containers import Horizontal, ItemGrid, Vertical, VerticalScroll
    from textual.widgets import (
        Button,
        ContentSwitcher,
        DataTable,
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
except ImportError:
    print(
        "Textual is required. Install with:\n"
        "  ${MYCLASH_ROOT_PWD}/venv/bin/pip install textual",
        file=sys.stderr,
    )
    sys.exit(1)


VIEW_IDS = [
    "view-overview",
    "view-proxies",
    "view-rules",
    "view-connections",
    "view-config",
    "view-logs",
]


def _fmt_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024.0:
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"


def _fmt_rate(bps: float) -> str:
    return _fmt_bytes(bps) + "/s"


def _truncate(text: str, max_len: int) -> str:
    if max_len <= 0:
        return ""
    if len(text) <= max_len:
        return text
    if max_len <= 3:
        return text[:max_len]
    return text[: max_len - 3] + "..."


def _sparkline(values: list[float], width: int = 48) -> str:
    if not values:
        return "—"
    blocks = "▁▂▃▄▅▆▇█"
    chunk = max(1, len(values) // width)
    samples = [sum(values[i : i + chunk]) / chunk for i in range(0, len(values), chunk)][-width:]
    if not samples:
        return "—"
    lo, hi = min(samples), max(samples)
    if hi <= lo:
        return blocks[4] * len(samples)
    return "".join(blocks[int((v - lo) / (hi - lo) * 7.999)] for v in samples)


def _cfg_int(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def normalize_runtime_config(raw: Any) -> dict[str, Any]:
    """统一不同内核/版本的 GET /configs 结构（扁平或包在 config 里）。"""
    if not isinstance(raw, dict):
        return {}
    data = raw
    for wrap in ("config", "Config", "data", "Data"):
        inner = data.get(wrap)
        if isinstance(inner, dict) and any(
            k in inner for k in ("port", "mixed-port", "mode", "log-level", "allow-lan")
        ):
            data = dict(inner)
            break
    return data


class ClashClient:
    def __init__(self):
        self.base_url = os.getenv("MYCLASH_API", "http://127.0.0.1:9090").rstrip("/")
        self.secret = os.getenv("MYCLASH_SECRET", "").strip()

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.secret:
            headers["Authorization"] = f"Bearer {self.secret}"
        return headers

    def _get_json(self, path: str, params: dict | None = None, timeout: float = 4) -> Any:
        r = requests.get(
            f"{self.base_url}{path}",
            headers=self._headers(),
            params=params or {},
            timeout=timeout,
        )
        r.raise_for_status()
        if not r.content:
            return {}
        return r.json()

    def get_proxies(self) -> dict:
        return self._get_json("/proxies").get("proxies", {})

    def get_connections(self) -> dict[str, Any]:
        return self._get_json("/connections")

    def get_rules(self) -> dict[str, Any]:
        return self._get_json("/rules")

    def get_configs(self) -> dict[str, Any]:
        raw = self._get_json("/configs")
        return normalize_runtime_config(raw)

    def patch_configs(self, payload: dict[str, Any]) -> None:
        r = requests.patch(
            f"{self.base_url}/configs",
            headers=self._headers(),
            json=payload,
            timeout=10,
        )
        if r.status_code >= 400:
            detail = (r.text or "").strip() or r.reason or str(r.status_code)
            raise RuntimeError(detail)
        r.raise_for_status()

    def test_delay(self, proxy_name: str, test_url: str, timeout_ms: int):
        encoded_name = quote(proxy_name, safe="")
        response = requests.get(
            f"{self.base_url}/proxies/{encoded_name}/delay",
            params={"url": test_url, "timeout": timeout_ms},
            headers=self._headers(),
            timeout=max(4, timeout_ms / 1000 + 1),
        )
        response.raise_for_status()
        return response.json().get("delay")

    def select_proxy(self, group_name: str, proxy_name: str) -> None:
        encoded_group = quote(group_name, safe="")
        response = requests.put(
            f"{self.base_url}/proxies/{encoded_group}",
            json={"name": proxy_name},
            headers=self._headers(),
            timeout=4,
        )
        response.raise_for_status()


class TuiState:
    def __init__(self, client: ClashClient, preferred_group: str | None = None):
        self.client = client
        self.groups: list[str] = []
        self.group_idx = 0
        self.nodes: list[str] = []
        self.current_node = ""
        self.selected_idx = 0
        self.delays: dict[str, int | None] = {}
        self.testing = False
        self.last_error = ""
        self.filter_text = ""
        self.test_url = os.getenv(
            "MYCLASH_TUI_TEST_URL", "https://www.gstatic.com/generate_204"
        )
        self.test_timeout_ms = int(os.getenv("MYCLASH_TUI_TIMEOUT_MS", "2500"))
        self._lock = threading.Lock()
        self._abort_delay_test = threading.Event()
        self._preferred_group = preferred_group or os.getenv("MYCLASH_TUI_GROUP", "").strip()

    def _pick_initial_group(self) -> int:
        if not self.groups:
            return 0
        if self._preferred_group and self._preferred_group in self.groups:
            return self.groups.index(self._preferred_group)
        if "GLOBAL" in self.groups:
            return self.groups.index("GLOBAL")
        return 0

    def display_nodes(self) -> list[str]:
        if not self.filter_text.strip():
            return list(self.nodes)
        needle = self.filter_text.strip().lower()
        return [n for n in self.nodes if needle in n.lower()]

    @staticmethod
    def _index_in_proxy_list(name: str, names: list[str]) -> int | None:
        """在 all 列表里定位节点下标（与 API 的 now 对齐，忽略大小写差异）。"""
        n = (name or "").strip()
        if not n:
            return None
        if n in names:
            return names.index(n)
        low = n.lower()
        for i, item in enumerate(names):
            if item.lower() == low:
                return i
        return None

    def sync_selection_to_api_current(self) -> None:
        """键盘选中下标与 GET /proxies 里当前组的 now 一致（过滤后若在列表中也会对准）。"""
        visible = self.display_nodes()
        if not visible:
            self.selected_idx = 0
            return
        idx = self._index_in_proxy_list(self.current_node, visible)
        if idx is not None:
            self.selected_idx = idx
            return
        if self.selected_idx >= len(visible):
            self.selected_idx = max(0, len(visible) - 1)
        elif self.selected_idx < 0:
            self.selected_idx = 0

    def refresh_groups_and_nodes(self) -> None:
        proxies = self.client.get_proxies()
        selector_types = {"Selector", "URLTest", "Fallback", "LoadBalance"}
        groups: list[str] = []
        for name, data in proxies.items():
            if data.get("type") in selector_types and isinstance(data.get("all"), list) and data["all"]:
                groups.append(name)
        groups.sort()
        if not groups:
            raise RuntimeError("No proxy selector groups found from Clash REST API.")

        previous_group = self.groups[self.group_idx] if self.groups else None
        self.groups = groups
        if previous_group in self.groups:
            self.group_idx = self.groups.index(previous_group)
        else:
            self.group_idx = self._pick_initial_group()

        group_name = self.groups[self.group_idx]
        group_data = proxies.get(group_name, {})
        self.nodes = list(group_data.get("all", []))
        raw_now = group_data.get("now")
        if raw_now is None:
            raw_now = group_data.get("Now")
        self.current_node = str(raw_now).strip() if raw_now is not None else ""
        self.sync_selection_to_api_current()

    def cycle_group(self, step: int) -> None:
        if not self.groups:
            return
        self.group_idx = (self.group_idx + step) % len(self.groups)
        self.delays = {}
        self.refresh_groups_and_nodes()

    def start_delay_test(self, on_done: Callable[[], None] | None = None) -> None:
        if self.testing or not self.nodes:
            return
        self._abort_delay_test.clear()
        self.testing = True
        self.last_error = ""
        nodes = list(self.nodes)

        def worker():
            result: dict[str, int | None] = {}
            try:
                executor = concurrent.futures.ThreadPoolExecutor(max_workers=8)
                try:
                    future_map = {
                        executor.submit(
                            self.client.test_delay, node, self.test_url, self.test_timeout_ms
                        ): node
                        for node in nodes
                    }
                    pending = set(future_map.keys())
                    while pending:
                        if self._abort_delay_test.is_set():
                            break
                        done, pending = concurrent.futures.wait(
                            pending,
                            timeout=0.4,
                            return_when=concurrent.futures.FIRST_COMPLETED,
                        )
                        for fut in done:
                            node = future_map[fut]
                            try:
                                result[node] = fut.result()
                            except Exception:
                                result[node] = None
                finally:
                    executor.shutdown(wait=False, cancel_futures=True)
            except Exception as exc:
                self.last_error = str(exc)
            with self._lock:
                self.delays = result
                self.testing = False
            if on_done:
                on_done()

        threading.Thread(target=worker, daemon=True).start()

    def select_current(self) -> None:
        visible = self.display_nodes()
        if not visible:
            return
        group_name = self.groups[self.group_idx]
        node = visible[self.selected_idx]
        self.client.select_proxy(group_name, node)
        self.current_node = node


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


class ProxyCard(Static):
    def __init__(self, node_name: str, **kwargs):
        kwargs.setdefault("markup", True)
        super().__init__(**kwargs)
        self.node_name = node_name

    DEFAULT_CSS = """
    ProxyCard {
        height: auto;
        min-height: 5;
        padding: 0 1;
        border: round $primary;
        background: $surface;
    }
    ProxyCard.selected {
        border: heavy $accent;
        background: $primary 18%;
    }
    """

    def set_content(self, selected: bool, current: bool, delay: int | None) -> None:
        prefix = "* " if current else "  "
        name_line = _truncate(prefix + self.node_name, 28)
        delay_line = _delay_text(delay)
        dstyle = _delay_style(delay)
        self.border_title = name_line
        if selected:
            self.add_class("selected")
        else:
            self.remove_class("selected")
        self.update(f"[{dstyle}]{delay_line}[/]")


class ClashTuiApp(App[None]):
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
    .sidebar-brand {
        text-style: bold;
        color: $accent;
        padding: 0 1 1 1;
    }
    #main {
        width: 1fr;
        height: 100%;
        layout: vertical;
        padding: 0 1;
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
        padding: 1 0;
        align-vertical: middle;
    }
    .page-title {
        width: 1fr;
        text-style: bold;
        color: $text;
    }
    #search {
        width: 36;
    }
    #group-line {
        height: auto;
        color: $text-muted;
        margin-bottom: 1;
    }
    #proxy-scroll {
        height: 1fr;
        min-height: 5;
    }
    #proxy-grid {
        height: auto;
        grid-gutter: 1 1;
    }
    #status-line {
        height: auto;
        color: $text-muted;
        padding-top: 1;
    }
    .stat-row {
        layout: horizontal;
        height: auto;
        margin: 1 0;
        grid-gutter: 1;
    }
    .stat-card {
        width: 1fr;
        height: auto;
        min-height: 5;
        padding: 0 1;
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
        margin-top: 1;
        color: $text-muted;
    }
    #overview-chart:focus {
        background-tint: $foreground 8%;
    }
    #rules-table, #conn-table {
        height: 1fr;
        border: tall $primary;
    }
    .cfg-row {
        height: auto;
        margin-bottom: 1;
        layout: horizontal;
        align-vertical: middle;
    }
    .cfg-label {
        width: 18;
        color: $text-muted;
    }
    #cfg-api-status {
        height: auto;
        color: $text-muted;
        margin-bottom: 1;
    }
    #cfg-apply {
        margin-top: 1;
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
        self._preferred_group = preferred_group
        self._client = ClashClient()
        self._state = TuiState(self._client, preferred_group=preferred_group)
        self._auto_refresh_s = int(os.getenv("MYCLASH_TUI_AUTO_REFRESH", "20"))
        self._prev_t: float | None = None
        self._prev_down = 0
        self._prev_up = 0
        self._down_hist: deque[float] = deque(maxlen=120)
        self._up_hist: deque[float] = deque(maxlen=120)
        self._conn_filter = ""
        self._log_filter = ""
        self._log_stop = threading.Event()
        self._log_started = False
        self._overview_err = ""
        self._conn_err = ""
        self._rules_err = ""
        self._last_runtime_config: dict[str, Any] | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="root"):
            with Vertical(id="sidebar"):
                yield Static("MCS", classes="sidebar-brand")
                yield ListView(
                    ListItem(Label("概览")),
                    ListItem(Label("代理")),
                    ListItem(Label("规则")),
                    ListItem(Label("连接")),
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
                        with Horizontal(classes="page-header"):
                            yield Static("代理", classes="page-title")
                            yield Input(placeholder="搜索节点…", id="search")
                        yield Static(id="group-line", markup=False)
                        with VerticalScroll(id="proxy-scroll", can_focus=False):
                            yield ItemGrid(
                                id="proxy-grid",
                                min_column_width=26,
                                regular=True,
                            )
                    with Vertical(id="view-rules", classes="view-pane"):
                        with Horizontal(classes="page-header"):
                            yield Static("规则", classes="page-title")
                        yield DataTable(id="rules-table", zebra_stripes=True)
                    with Vertical(id="view-connections", classes="view-pane"):
                        with Horizontal(classes="page-header"):
                            yield Static("连接", classes="page-title")
                            yield Input(placeholder="过滤…", id="conn-filter")
                        yield DataTable(id="conn-table", zebra_stripes=True)
                    with Vertical(id="view-config", classes="view-pane"):
                        with Horizontal(classes="page-header"):
                            yield Static("配置", classes="page-title")
                        yield Static("", id="cfg-api-status", markup=False)
                        with VerticalScroll():
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
        self.set_interval(1.0, self._tick_connections)
        self._state.start_delay_test(on_done=lambda: self._safe_call_from_thread(self._after_delay_test))
        if self._auto_refresh_s > 0:
            self.set_interval(float(self._auto_refresh_s), self._on_auto_timer)
        self._prepare_rules_table()
        self._prepare_conn_table()
        nav = self.query_one("#sidebar-nav", ListView)
        self._apply_sidebar_index(nav.index if nav.index is not None else 0)

    def on_unmount(self) -> None:
        self._log_stop.set()
        self._state._abort_delay_test.set()

    def action_help_quit(self) -> None:
        """Ctrl+C 字符路径（与 SIGINT 二选一或同时）：直接退出。"""
        self.exit()

    def _prepare_rules_table(self) -> None:
        table = self.query_one("#rules-table", DataTable)
        if table.columns:
            return
        table.add_columns("#", "类型", "匹配", "策略")

    def _prepare_conn_table(self) -> None:
        table = self.query_one("#conn-table", DataTable)
        if table.columns:
            return
        table.add_columns("主机", "进程", "下载", "上传", "↓/s", "↑/s", "链路", "规则")

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
                self.query_one("#search", Input).focus()
            elif vid == "view-rules":
                self.query_one("#rules-table", DataTable).focus()
            elif vid == "view-connections":
                self.query_one("#conn-filter", Input).focus()
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
        if vid == "view-rules":
            self.run_worker(self._load_rules_async(), group="rules", exit_on_error=False)
        elif vid == "view-config":
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

    def _tick_connections(self) -> None:
        if self._current_view() != "view-connections":
            return
        self.run_worker(self._refresh_connections_async(), group="conn", exclusive=True, exit_on_error=False)

    async def _refresh_connections_async(self) -> None:
        try:
            data = self._client.get_connections()
            self._conn_err = ""
        except Exception as exc:
            self._conn_err = str(exc)
            self._safe_call_from_thread(self._sync_main_footer)
            return

        conns = data.get("connections") or []
        needle = self._conn_filter.strip().lower()
        rows: list[tuple[str, ...]] = []
        now_ms = time.time() * 1000
        for c in conns:
            meta = c.get("metadata") or {}
            host = meta.get("host") or meta.get("destinationIP") or "—"
            if meta.get("destinationPort"):
                host = f"{host}:{meta.get('destinationPort')}"
            proc = meta.get("processPath") or meta.get("process") or ""
            if proc and "/" in proc:
                proc = proc.rsplit("/", 1)[-1]
            chains = " / ".join(c.get("chains") or []) or "—"
            rule = str(c.get("rule") or c.get("rulePayload") or "—")
            dl = int(c.get("download", 0))
            ul = int(c.get("upload", 0))
            start = c.get("start")
            elapsed_s = 1.0
            if isinstance(start, str):
                try:
                    elapsed_s = max(0.001, (now_ms - float(start)) / 1000.0)
                except ValueError:
                    pass
            d_speed = dl / elapsed_s
            u_speed = ul / elapsed_s
            line = " ".join([host, proc, chains, rule]).lower()
            if needle and needle not in line:
                continue
            rows.append(
                (
                    _truncate(str(host), 28),
                    _truncate(str(proc), 12),
                    _fmt_bytes(float(dl)),
                    _fmt_bytes(float(ul)),
                    _fmt_rate(d_speed),
                    _fmt_rate(u_speed),
                    _truncate(chains, 36),
                    _truncate(rule, 24),
                )
            )

        def apply():
            table = self.query_one("#conn-table", DataTable)
            table.clear()
            for row in rows:
                table.add_row(*row)

        self._safe_call_from_thread(apply)
        self._safe_call_from_thread(self._sync_main_footer)

    async def _load_rules_async(self) -> None:
        try:
            payload = self._client.get_rules()
            self._rules_err = ""
        except Exception as exc:
            self._rules_err = str(exc)
            self._safe_call_from_thread(self._sync_main_footer)
            return

        rules = payload.get("rules")
        if rules is None:
            rules = payload if isinstance(payload, list) else []

        def apply():
            table = self.query_one("#rules-table", DataTable)
            table.clear()
            for i, r in enumerate(rules):
                if isinstance(r, dict):
                    table.add_row(
                        str(i),
                        _truncate(str(r.get("type", "")), 16),
                        _truncate(str(r.get("payload", "")), 40),
                        _truncate(str(r.get("proxy", "")), 20),
                    )
                else:
                    table.add_row(str(i), "", str(r), "")

        self._safe_call_from_thread(apply)
        self._safe_call_from_thread(self._sync_main_footer)

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
        self._state.start_delay_test(on_done=lambda: self._safe_call_from_thread(self._after_delay_test))

    def _after_delay_test(self) -> None:
        if self._current_view() == "view-proxies":
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
            "[ctrl+i]搜索/过滤  [Esc]代理节点区  [ctrl+c]退出"
        )
        if vid == "view-proxies":
            extra = (
                "  [↑↓←→/hjkl] 节点  [Enter] 切换  [r] 测速  [[]/]] 分组  [u] 同步"
                + (f"  ·  {err}" if err else "")
            )
        elif vid == "view-overview":
            extra = f"  ·  {_truncate(self._overview_err, 80)}" if self._overview_err else ""
        elif vid == "view-connections":
            extra = f"  ·  {_truncate(self._conn_err, 80)}" if self._conn_err else ""
        elif vid == "view-rules":
            extra = f"  ·  {_truncate(self._rules_err, 80)}" if self._rules_err else ""
        elif vid == "view-config":
            extra = "  修改后点「应用」PATCH /configs"
        elif vid == "view-logs":
            extra = "  日志流来自 GET /logs?level=info"
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
            card = ProxyCard(node, id=f"pc-{i}")
            await grid.mount(card)
        self._refresh_card_contents()
        self.call_after_refresh(self._scroll_to_selection)

    def _refresh_card_contents(self) -> None:
        visible = self._state.display_nodes()
        cards = list(self.query("#proxy-grid ProxyCard"))
        for i, card in enumerate(cards):
            if i >= len(visible):
                break
            name = visible[i]
            delay = self._state.delays.get(name)
            card.set_content(
                selected=(i == self._state.selected_idx),
                current=(name == self._state.current_node),
                delay=delay,
            )

    def _scroll_to_selection(self) -> None:
        visible = self._state.display_nodes()
        if not visible:
            return
        i = min(self._state.selected_idx, len(visible) - 1)
        cards = list(self.query("#proxy-grid ProxyCard"))
        if i < len(cards):
            self.query_one("#proxy-scroll", VerticalScroll).scroll_to_widget(
                cards[i], animate=False
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
        self._state.start_delay_test(on_done=lambda: self._safe_call_from_thread(self._after_delay_test))
        self._sync_proxy_chrome()
        self._sync_main_footer()

    async def action_prev_group(self) -> None:
        if not self._main_grid_commands_active():
            return
        self._state.cycle_group(-1)
        self._state.start_delay_test(on_done=lambda: self._safe_call_from_thread(self._after_delay_test))
        await self._rebuild_cards_async()
        self._sync_proxy_chrome()
        self._sync_main_footer()

    async def action_next_group(self) -> None:
        if not self._main_grid_commands_active():
            return
        self._state.cycle_group(1)
        self._state.start_delay_test(on_done=lambda: self._safe_call_from_thread(self._after_delay_test))
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
        self._state.start_delay_test(on_done=lambda: self._safe_call_from_thread(self._after_delay_test))
        await self._rebuild_cards_async()
        self._sync_proxy_chrome()
        self._sync_main_footer()

    def action_focus_search(self) -> None:
        vid = self._current_view()
        if vid == "view-proxies":
            self.query_one("#search", Input).focus()
        elif vid == "view-connections":
            self.query_one("#conn-filter", Input).focus()
        elif vid == "view-logs":
            self.query_one("#logs-filter", Input).focus()

    def action_focus_sidebar(self) -> None:
        self.query_one("#sidebar-nav", ListView).focus()

    def action_focus_proxy_grid(self) -> None:
        if self._current_view() == "view-proxies":
            self.query_one("#proxy-grid", ItemGrid).focus()

    @on(Input.Changed, "#search")
    def filter_nodes(self, event: Input.Changed) -> None:
        self._state.filter_text = event.value
        self._state.sync_selection_to_api_current()
        self._sync_proxy_chrome()
        self._schedule_rebuild_cards()

    @on(Input.Changed, "#conn-filter")
    def filter_connections(self, event: Input.Changed) -> None:
        self._conn_filter = event.value
        self._tick_connections()

    @on(Input.Changed, "#logs-filter")
    def filter_logs(self, event: Input.Changed) -> None:
        self._log_filter = event.value.strip()


def main():
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


if __name__ == "__main__":
    main()
