"""MyClashShell Textual application (main screen)."""

from __future__ import annotations

import asyncio
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any, Callable

import requests
from textual import on
from textual.actions import SkipAction
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.dom import DOMNode
from textual.screen import ModalScreen
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
    RichLog,
    Select,
    Static,
    Switch,
)

from scripts.lib.config_runtime import runtime_config_patch_payload
from scripts.lib.paths import clash_config_yaml, update_proxy_config_script
from scripts.lib.share import slave_install_hint_lines
from scripts.lib.subscribe import (
    is_valid_subscribe_url,
    load_user_config_dict,
    normalize_subscribes,
    save_user_config_dict,
    set_document_subscribes,
    user_config_path,
)

from .client import ClashClient
from .config_api import _cfg_int
from .constants import VIEW_IDS
from .formatting import (
    _fmt_bytes,
    _fmt_rate,
    _overview_sparkline_columns,
    _sparkline,
    _truncate,
    clash_log_searchable,
    clash_log_to_rich,
)
from .lan_constants import lan_config_http_port, lan_udp_port
from .lan_share import (
    LanPeer,
    LanShareHub,
    fetch_remote_config,
    pick_lan_host,
    random_pin3,
    slave_http_serve_port,
)
from .state import TuiState
from .widgets import ProxyNodeButton, ProxyNodeRows, ProxyNodeScroll, ProxyRightPanel

_ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
_SUB_REFRESH_LOG_MAX_CHARS = 48_000


def _strip_ansi(s: str) -> str:
    return _ANSI_ESCAPE_RE.sub("", s)


def _subscribe_refresh_log_text(proc: subprocess.CompletedProcess[str]) -> str:
    out = (proc.stdout or "").rstrip()
    err = (proc.stderr or "").rstrip()
    chunks: list[str] = []
    if out:
        chunks.append("stdout:\n" + _strip_ansi(out))
    if err:
        chunks.append("stderr:\n" + _strip_ansi(err))
    if not chunks:
        return (
            "（本进程未捕获到 stdout/stderr；若脚本只写文件，请查看仓库根目录 app.log）\n"
            f"退出码: {proc.returncode}"
        )
    text = "\n\n".join(chunks)
    if len(text) > _SUB_REFRESH_LOG_MAX_CHARS:
        text = (
            f"… 输出过长，仅显示末尾 {_SUB_REFRESH_LOG_MAX_CHARS} 字符 …\n\n"
            + text[-_SUB_REFRESH_LOG_MAX_CHARS:]
        )
    return text


class SubscribeRefreshLogModal(ModalScreen[None]):
    """展示 update_proxy_config.py 的终端输出。"""

    BINDINGS = [Binding("escape", "dismiss", "关闭")]

    DEFAULT_CSS = """
    SubscribeRefreshLogModal {
        align: center middle;
    }
    SubscribeRefreshLogModal > #refresh-log-shell {
        width: 88%;
        max-width: 120;
        height: 75%;
        border: thick $primary;
        background: $surface;
        padding: 0 1;
    }
    SubscribeRefreshLogModal #refresh-log-scroll {
        height: 1fr;
        border: solid $boost;
        background: $panel;
        margin: 1 0;
    }
    SubscribeRefreshLogModal #refresh-log-body {
        margin: 1;
    }
    """

    def __init__(self, log_text: str, returncode: int) -> None:
        super().__init__()
        self._log_text = log_text
        self._returncode = returncode

    def compose(self) -> ComposeResult:
        with Vertical(id="refresh-log-shell"):
            rc = self._returncode
            status = "成功" if rc == 0 else "失败"
            yield Label(f"update_proxy_config · {status} · 退出码 {rc}")
            with VerticalScroll(id="refresh-log-scroll"):
                yield Static(self._log_text, id="refresh-log-body")
            yield Button("关闭 (Esc)", id="refresh-log-close", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "refresh-log-close":
            self.dismiss()

    def action_dismiss(self) -> None:
        self.dismiss()


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
    #log-panel {
        height: 1fr;
        min-height: 5;
        border: tall $primary;
    }
    #sub-body {
        height: 1fr;
        layout: horizontal;
        min-height: 5;
    }
    #sub-names-list {
        width: 22;
        height: 1fr;
        min-height: 5;
        border: round $boost;
        background: $panel;
    }
    #sub-names-list ListItem {
        padding: 0 1;
        height: auto;
        min-height: 2;
    }
    #sub-form-scroll {
        width: 1fr;
        height: 1fr;
    }
    #sub-actions {
        layout: horizontal;
        height: auto;
        margin-top: 1;
    }
    #sub-actions Button {
        margin-right: 1;
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
        Binding("ctrl+i", "focus_search", "Search", show=False, key_display="ctrl+i"),
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
        self._log_filter = ""
        self._log_stop = threading.Event()
        self._log_started = False
        self._overview_err = ""
        self._last_runtime_config: dict[str, Any] | None = None
        self._share_node_id = uuid.uuid4().hex[:10]
        self._share_pin = random_pin3()
        self._lan_hub: LanShareHub | None = None
        self._share_peers: dict[str, LanPeer] = {}
        self._share_lan_enabled = False
        self._sub_refresh_busy = False
        self._sub_subscribes: dict[str, str] = {}
        self._sub_names_order: list[str] = []
        self._sub_default_silent = False
        self._proxy_group_sync = False

    def compose(self) -> ComposeResult:
        with Horizontal(id="root"):
            with Vertical(id="sidebar"):
                yield ListView(
                    ListItem(Label("概览")),
                    ListItem(Label("代理")),
                    ListItem(Label("配置")),
                    ListItem(Label("订阅")),
                    ListItem(Label("共享")),
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
                        with Vertical(id="overview-charts"):
                            yield Static("下载速率", classes="overview-chart-title")
                            yield Static("", id="overview-chart-dl", classes="overview-spark", markup=False)
                            yield Static("上传速率", classes="overview-chart-title")
                            yield Static("", id="overview-chart-ul", classes="overview-spark", markup=False)
                    with Vertical(id="view-proxies", classes="view-pane"):
                        yield Static("代理", classes="page-title")
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
                                ):
                                    yield ProxyNodeRows(
                                        id="proxy-rows",
                                        get_current_view=self._current_view,
                                        on_proxy_move_selection_delta=self._proxy_move_selection_delta,
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
                    with Vertical(id="view-subscribe", classes="view-pane"):
                        yield Static("订阅", classes="page-title")
                        yield Static("", id="sub-status", markup=False)
                        with Vertical(classes="config-sheet"):
                            with Horizontal(id="sub-body"):
                                yield ListView(id="sub-names-list")
                                with VerticalScroll(id="sub-form-scroll"):
                                    yield Static("订阅链接", classes="config-section-title")
                                    with Horizontal(classes="cfg-row"):
                                        yield Label("URL", classes="cfg-label")
                                        yield Input(placeholder="https://…", id="sub-url")
                                    yield Static("添加订阅", classes="config-section-title")
                                    with Horizontal(classes="cfg-row"):
                                        yield Label("名称", classes="cfg-label")
                                        yield Input(placeholder="新订阅名称", id="sub-new-name")
                                    yield Static("默认订阅", classes="config-section-title")
                                    with Horizontal(classes="cfg-row"):
                                        yield Label("default", classes="cfg-label")
                                        yield Select(
                                            [("DEFAULT", "DEFAULT")],
                                            id="sub-default",
                                            allow_blank=False,
                                        )
                                    with Horizontal(id="sub-actions"):
                                        yield Button("添加", id="sub-add-btn", variant="primary")
                                        yield Button("保存修改", id="sub-save-btn")
                                        yield Button("删除", id="sub-del-btn", variant="error")
                                        yield Button("刷新订阅", id="sub-refresh-btn", variant="warning")
                    with Vertical(id="view-share", classes="view-pane"):
                        yield Static("共享", classes="page-title")
                        yield Static("", id="share-lan-status", markup=False)
                        with Horizontal(classes="cfg-row"):
                            yield Label("局域网发现", classes="cfg-label")
                            yield Switch(value=False, id="share-lan-switch")
                        with Horizontal(classes="cfg-row"):
                            yield Button("配置 Master-Master", id="share-tab-mm", variant="primary")
                            yield Button("代理 Master-Slave", id="share-tab-ms")
                        with ContentSwitcher(id="share-sub", initial="share-mm"):
                            with Vertical(id="share-mm", classes="view-pane"):
                                yield Static("本机 PIN（他机拉取你的 config 时需输入）", classes="config-section-title")
                                yield Static("000", id="share-pin-display", classes="stat-value")
                                yield Button("刷新 PIN", id="share-pin-refresh", variant="default")
                                with Horizontal(classes="cfg-row"):
                                    yield Label("提供配置拉取", classes="cfg-label")
                                    yield Switch(value=True, id="share-offer-config")
                                yield Static("其它主机", classes="config-section-title")
                                yield Select([], id="share-peer-select", allow_blank=True)
                                yield Input(placeholder="对方屏幕上显示的 PIN", id="share-pull-pin", password=True)
                                yield Button("拉取选中主机 config.yaml", id="share-pull-btn", variant="warning")
                                yield Static("手动拉取（自动发现不可用，例如部分热点）", classes="config-section-title")
                                with Horizontal(classes="cfg-row"):
                                    yield Label("对方 IP", classes="cfg-label")
                                    yield Input(placeholder="192.168.x.x", id="share-manual-ip")
                                with Horizontal(classes="cfg-row"):
                                    yield Label("config 端口", classes="cfg-label")
                                    yield Input(str(lan_config_http_port()), id="share-manual-config-port")
                                yield Button("按 IP 拉取 config", id="share-manual-pull-btn", variant="warning")
                            with Vertical(id="share-ms", classes="view-pane"):
                                yield Static("在 Slave 上执行（需 root）", classes="config-section-title")
                                yield RichLog(id="share-slave-cmd", max_lines=30, auto_scroll=True, markup=False)
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
        self.register_theme(_atom_one_dark_theme_no_purple())
        self.refresh_css(animate=False)
        try:
            self._state.refresh_groups_and_nodes()
        except Exception as exc:
            self._state.last_error = str(exc)
        await self._rebuild_group_list_async()
        await self._rebuild_cards_async()
        rows = self.query_one("#proxy-rows", Vertical)
        rows.can_focus = True
        self.query_one("#overview-charts", Vertical).can_focus = True
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
        if self._lan_hub:
            self._lan_hub.stop()
            self._lan_hub = None

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
                self.query_one("#cfg-port", Input).focus()
            elif vid == "view-subscribe":
                lv = self.query_one("#sub-names-list", ListView)
                if lv.children and lv.index is not None:
                    lv.focus()
                else:
                    self.query_one("#sub-url", Input).focus()
            elif vid == "view-share":
                self.query_one("#share-lan-switch", Switch).focus()
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
        elif vid == "view-subscribe":
            self.run_worker(
                self._load_subscribe_async(),
                group="subscribe",
                exclusive=True,
                exit_on_error=False,
            )
        elif vid == "view-share":
            self._update_share_pin_display()
            self._update_slave_cmd_text()
            self._refresh_share_peer_list()
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
                        timeout=(10, None),
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
        searchable = clash_log_searchable(line)
        if self._log_filter and self._log_filter.lower() not in searchable.lower():
            return
        try:
            self.query_one("#log-panel", RichLog).write(clash_log_to_rich(line))
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
        """run_worker 默认在主线程跑协程，禁止此处使用 call_from_thread（会抛 RuntimeError）。"""
        try:
            cfg = await asyncio.to_thread(self._client.get_configs)
        except Exception as exc:
            self.notify(f"读取配置失败: {exc}", severity="error", timeout=4)
            return

        api = self._client.base_url
        msg = (
            f"已从 GET {api}/configs 加载  ·  mode={cfg.get('mode')}  "
            f"mixed-port={cfg.get('mixed-port')}"
        )
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
            payload = runtime_config_patch_payload(
                port=port,
                socks_port=socks,
                mixed_port=mixed,
                redir_port=redir,
                tproxy_port=tproxy,
                mode=mode,
                log_level=logl,
                allow_lan=bool(lan),
                ipv6=bool(ipv6),
            )
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

    def _set_sub_controls_enabled(self, enabled: bool) -> None:
        d = not enabled
        for wid in (
            "sub-url",
            "sub-new-name",
            "sub-default",
            "sub-add-btn",
            "sub-save-btn",
            "sub-del-btn",
            "sub-refresh-btn",
        ):
            try:
                self.query_one(f"#{wid}").disabled = d
            except Exception:
                pass
        try:
            self.query_one("#sub-names-list", ListView).disabled = d
        except Exception:
            pass

    def _sub_key_order_for_persist(self) -> list[str]:
        """与 user_config 中 subscribes 块顺序一致；DEFAULT=文档中第一个订阅（见 update_proxy_config）。"""
        seen: set[str] = set()
        out: list[str] = []
        for k in self._sub_names_order:
            if k in self._sub_subscribes and k not in seen:
                out.append(k)
                seen.add(k)
        for k in self._sub_subscribes:
            if k not in seen:
                out.append(k)
                seen.add(k)
        return out

    def _persist_subscribe_yaml(self) -> None:
        p = user_config_path()
        if not p:
            raise RuntimeError("MYCLASH_ROOT_PWD 未设置")
        data = load_user_config_dict(p)
        order = self._sub_key_order_for_persist()
        set_document_subscribes(data, {k: self._sub_subscribes[k] for k in order}, key_order=order)
        sel_w = self.query_one("#sub-default", Select)
        val = sel_w.value
        if val is Select.NULL or val is None:
            val = data.get("default_subscribe", "DEFAULT")
        data["default_subscribe"] = str(val)
        save_user_config_dict(p, data)

    async def _apply_sub_default_select(self, default_s: str) -> None:
        opts = [("DEFAULT", "DEFAULT")]
        for n in self._sub_names_order:
            opts.append((n, n))
        sel = self.query_one("#sub-default", Select)
        self._sub_default_silent = True
        sel.set_options(opts)
        valid = {v for _, v in opts}
        val = default_s if default_s in valid else "DEFAULT"
        try:
            sel.value = val
        except Exception:
            sel.value = "DEFAULT"
        self._sub_default_silent = False

    async def _rebuild_sub_name_list(self) -> None:
        lv = self.query_one("#sub-names-list", ListView)
        await lv.remove_children()
        for name in self._sub_names_order:
            await lv.mount(ListItem(Label(name)))
        if self._sub_names_order:
            lv.index = 0
            self.query_one("#sub-url", Input).value = self._sub_subscribes[self._sub_names_order[0]]
        else:
            try:
                lv.index = None
            except Exception:
                pass
            self.query_one("#sub-url", Input).value = ""

    async def _load_subscribe_async(self) -> None:
        p = user_config_path()
        if not p:
            self.query_one("#sub-status", Static).update(
                "未设置 MYCLASH_ROOT_PWD，无法编辑 user_config.yaml"
            )
            self._set_sub_controls_enabled(False)
            return
        if not p.exists():
            self.query_one("#sub-status", Static).update(f"文件不存在: {p}")
            self._set_sub_controls_enabled(False)
            return
        try:
            data = await asyncio.to_thread(load_user_config_dict, p)
        except Exception as exc:
            self.notify(f"读取 user_config 失败: {exc}", severity="error", timeout=5)
            self._set_sub_controls_enabled(False)
            return
        self._sub_subscribes = normalize_subscribes(data.get("subscribes"))
        self._sub_names_order = list(self._sub_subscribes.keys())
        dft = data.get("default_subscribe")
        default_s = str(dft).strip() if dft is not None else "DEFAULT"
        self.query_one("#sub-status", Static).update(str(p))
        self._set_sub_controls_enabled(True)
        await self._rebuild_sub_name_list()
        await self._apply_sub_default_select(default_s)

    @on(ListView.Highlighted, "#sub-names-list")
    def sub_names_highlighted(self, event: ListView.Highlighted) -> None:
        if self._current_view() != "view-subscribe":
            return
        idx = event.list_view.index
        if idx is None or not (0 <= idx < len(self._sub_names_order)):
            return
        name = self._sub_names_order[idx]
        self.query_one("#sub-url", Input).value = self._sub_subscribes.get(name, "")

    @on(Select.Changed, "#sub-default")
    def sub_default_changed(self, event: Select.Changed) -> None:
        if self._sub_default_silent or self._current_view() != "view-subscribe":
            return
        try:
            self._persist_subscribe_yaml()
        except Exception as exc:
            self.notify(f"保存默认订阅失败: {exc}", severity="error", timeout=4)
            return
        self.notify("已保存默认订阅", severity="information", timeout=2)

    @on(Button.Pressed, "#sub-save-btn")
    async def sub_save_pressed(self) -> None:
        if self._current_view() != "view-subscribe":
            return
        lv = self.query_one("#sub-names-list", ListView)
        idx = lv.index
        if idx is None or not (0 <= idx < len(self._sub_names_order)):
            self.notify("请先选择一个订阅", severity="warning", timeout=3)
            return
        name = self._sub_names_order[idx]
        url = self.query_one("#sub-url", Input).value.strip()
        if not is_valid_subscribe_url(url):
            self.notify("URL 无效（需 http/https/ftp）", severity="error", timeout=4)
            return
        self._sub_subscribes[name] = url
        try:
            self._persist_subscribe_yaml()
        except Exception as exc:
            self.notify(f"保存失败: {exc}", severity="error", timeout=5)
            return
        self.notify(f"已保存「{name}」", severity="information", timeout=2)

    @on(Button.Pressed, "#sub-add-btn")
    async def sub_add_pressed(self) -> None:
        if self._current_view() != "view-subscribe":
            return
        name = self.query_one("#sub-new-name", Input).value.strip()
        url = self.query_one("#sub-url", Input).value.strip()
        if not name:
            self.notify("请填写新订阅名称", severity="warning", timeout=3)
            return
        if name in self._sub_subscribes:
            self.notify("该名称已存在", severity="warning", timeout=3)
            return
        if not is_valid_subscribe_url(url):
            self.notify("URL 无效（需 http/https/ftp）", severity="error", timeout=4)
            return
        sel = self.query_one("#sub-default", Select)
        prev_def = str(sel.value) if sel.value not in (Select.NULL, None) else "DEFAULT"
        self._sub_subscribes[name] = url
        prev_order = list(self._sub_names_order)
        self._sub_names_order.append(name)
        try:
            self._persist_subscribe_yaml()
        except Exception as exc:
            del self._sub_subscribes[name]
            self._sub_names_order = prev_order
            self.notify(f"保存失败: {exc}", severity="error", timeout=5)
            return
        await self._rebuild_sub_name_list()
        new_idx = self._sub_names_order.index(name)
        lv = self.query_one("#sub-names-list", ListView)
        lv.index = new_idx
        self.query_one("#sub-url", Input).value = self._sub_subscribes[name]
        self.query_one("#sub-new-name", Input).value = ""
        await self._apply_sub_default_select(prev_def)
        self.notify(f"已添加「{name}」", severity="information", timeout=2)

    @on(Button.Pressed, "#sub-del-btn")
    async def sub_del_pressed(self) -> None:
        if self._current_view() != "view-subscribe":
            return
        lv = self.query_one("#sub-names-list", ListView)
        idx = lv.index
        if idx is None or not (0 <= idx < len(self._sub_names_order)):
            self.notify("请先选择一个订阅", severity="warning", timeout=3)
            return
        name = self._sub_names_order[idx]
        sel = self.query_one("#sub-default", Select)
        cur_def = (
            str(sel.value)
            if sel.value not in (Select.NULL, None)
            else "DEFAULT"
        )
        if cur_def == name:
            cur_def = "DEFAULT"
        del self._sub_subscribes[name]
        self._sub_names_order = [k for k in self._sub_names_order if k != name]
        await self._rebuild_sub_name_list()
        await self._apply_sub_default_select(cur_def)
        try:
            self._persist_subscribe_yaml()
        except Exception as exc:
            self.notify(f"保存失败: {exc}", severity="error", timeout=5)
            return
        self.notify(f"已删除「{name}」", severity="information", timeout=2)

    @on(Button.Pressed, "#sub-refresh-btn")
    async def sub_refresh_pressed(self) -> None:
        if self._current_view() != "view-subscribe":
            return
        root = os.environ.get("MYCLASH_ROOT_PWD", "").strip()
        if not root or self._sub_refresh_busy:
            return
        py = Path(root) / "venv" / "bin" / "python3"
        script = update_proxy_config_script(Path(root))
        if not py.is_file() or not script.is_file():
            self.notify(
                "未找到 venv/bin/python3 或 scripts/runtime/update_proxy_config.py",
                severity="error",
                timeout=5,
            )
            return
        self._sub_refresh_busy = True
        try:
            self.query_one("#sub-refresh-btn", Button).disabled = True
        except Exception:
            pass
        self.run_worker(
            self._subscribe_refresh_worker(root, py, script),
            group="subscribe-refresh",
            exclusive=True,
            exit_on_error=False,
        )

    async def _subscribe_refresh_worker(
        self, root: str, py: Path, script: Path
    ) -> None:
        """在 worker 内跑子进程与 push_screen_wait（Textual 要求 wait_for_dismiss 仅能在 worker 中使用）。"""
        proc: subprocess.CompletedProcess[str] | None = None
        try:
            try:
                proc = await asyncio.to_thread(
                    subprocess.run,
                    [str(py), str(script)],
                    cwd=root,
                    env={
                        **os.environ,
                        "PYTHONUNBUFFERED": "1",
                        "http_proxy": "",
                        "https_proxy": "",
                        "HTTP_PROXY": "",
                        "HTTPS_PROXY": "",
                    },
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            except subprocess.TimeoutExpired:
                self.notify("刷新订阅超时", severity="error", timeout=4)
            except Exception as exc:
                self.notify(f"刷新失败: {exc}", severity="error", timeout=5)
            if proc is None:
                return
            log_text = _subscribe_refresh_log_text(proc)
            await self.push_screen_wait(
                SubscribeRefreshLogModal(log_text, proc.returncode)
            )
            if proc.returncode != 0:
                return
            try:
                self._state.refresh_groups_and_nodes()
                self._state.last_error = ""
            except Exception as exc:
                self._state.last_error = str(exc)
            await self._rebuild_group_list_async()
            await self._rebuild_cards_async()
            self._refresh_card_contents()
            self._sync_proxy_chrome()
            self._sync_main_footer()
        finally:
            self._sub_refresh_busy = False
            try:
                self.query_one("#sub-refresh-btn", Button).disabled = False
            except Exception:
                pass

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
        status = "测速中…" if self._state.testing else "就绪"
        cur = self._state.current_node
        cur_part = f"当前 {cur}" if cur else ""
        parts = [f"{len(visible)} 节点", status]
        if cur_part:
            parts.insert(0, cur_part)
        line = "  ·  ".join(parts)
        self.query_one("#group-line", Static).update(line)

    def _sync_main_footer(self) -> None:
        vid = self._current_view()
        err = self._state.last_error
        base = "侧栏↑↓换页  Enter/Tab进主区  ctrl+b回侧栏  q退出"
        if vid == "view-proxies":
            extra = (
                "  ·  代理：左栏选组  右kj/↑↓选节点  Tab换栏  Enter切换  r测速  [/]换组  u同步  Esc→右栏"
                + (f"  ·  {err}" if err else "")
            )
        elif vid == "view-overview":
            extra = (
                f"  ·  {_truncate(self._overview_err, 72)}"
                if self._overview_err
                else "  ·  概览：连接与流量"
            )
        elif vid == "view-config":
            extra = "  ·  配置：改后点「应用」写入内核（PATCH /configs）"
        elif vid == "view-subscribe":
            extra = "  ·  订阅：按钮写入 user_config.yaml  ·  刷新=下载订阅并合并进内核"
        elif vid == "view-logs":
            extra = "  ·  日志：ctrl+i 聚焦过滤框"
        elif vid == "view-share":
            extra = "  ·  共享：仅可信局域网；PIN 防误操作"
        else:
            extra = ""
        self.query_one("#status-line", Static).update(base + extra)

    def _schedule_rebuild_cards(self) -> None:
        self.run_worker(
            self._rebuild_proxy_panes_async(),
            name="rebuild_proxy_grid",
            group="rebuild-grid",
            exclusive=True,
            exit_on_error=False,
        )

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

    def action_focus_search(self) -> None:
        if self._current_view() == "view-logs":
            self.query_one("#logs-filter", Input).focus()

    def action_focus_sidebar(self) -> None:
        self.query_one("#sidebar-nav", ListView).focus()

    def action_focus_proxy_grid(self) -> None:
        if self._current_view() == "view-proxies":
            self.query_one("#proxy-rows", Vertical).focus()

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

    def _get_share_http_port(self) -> int:
        if self._last_runtime_config:
            return _cfg_int(self._last_runtime_config.get("port"))
        return 7890

    def _share_config_path(self) -> Path | None:
        root = os.environ.get("MYCLASH_ROOT_PWD", "").strip()
        if not root:
            return None
        return clash_config_yaml(Path(root))

    def _update_share_pin_display(self) -> None:
        try:
            self.query_one("#share-pin-display", Static).update(self._share_pin)
        except Exception:
            pass

    def _update_slave_cmd_text(self) -> None:
        try:
            log = self.query_one("#share-slave-cmd", RichLog)
            log.clear()
        except Exception:
            return
        host = pick_lan_host()
        port = self._get_share_http_port()
        serve_port = slave_http_serve_port()
        root = os.environ.get("MYCLASH_ROOT_PWD", "").strip()
        if not root:
            log.write("未设置 MYCLASH_ROOT_PWD，无法生成本仓库脚本路径。")
            return
        for line in slave_install_hint_lines(
            host=host,
            clash_http_port=port,
            serve_port=serve_port,
            repo_root=root,
        ):
            log.write(line)

    def _on_lan_peers_from_thread(self, _peers: dict[str, LanPeer]) -> None:
        self._safe_call_from_thread(self._refresh_share_peer_list)

    def _sync_lan_hub(self) -> None:
        st = self.query_one("#share-lan-status", Static)
        cfgp = self._share_config_path()
        if not cfgp or not cfgp.is_file():
            st.update("未找到 clash/configs/config.yaml（检查 MYCLASH_ROOT_PWD）")
            if self._lan_hub:
                self._lan_hub.stop()
                self._lan_hub = None
            return
        if not self._share_lan_enabled:
            st.update("局域网发现已关闭")
            if self._lan_hub:
                self._lan_hub.stop()
                self._lan_hub = None
            return
        try:
            offer = self.query_one("#share-offer-config", Switch).value
        except Exception:
            offer = True
        if self._lan_hub:
            self._lan_hub.stop()
            self._lan_hub = None
        self._lan_hub = LanShareHub(
            node_id=self._share_node_id,
            get_http_port=self._get_share_http_port,
            get_config_port=lan_config_http_port,
            get_display_name=lambda: socket.gethostname(),
            get_pin=lambda: self._share_pin,
            config_yaml_path=str(cfgp),
            on_peers=self._on_lan_peers_from_thread,
            offer_config=bool(offer),
        )
        self._lan_hub.start()
        offer_note = "提供配置 HTTP 已开" if offer else "仅发现、不提供配置拉取"
        st.update(
            f"UDP {lan_udp_port()} 组播 224.0.0.251 · 配置 HTTP {lan_config_http_port()} · {offer_note} · node_id={self._share_node_id}"
        )

    def _refresh_share_peer_list(self) -> None:
        try:
            sel = self.query_one("#share-peer-select", Select)
        except Exception:
            return
        peers = self._lan_hub.snapshot_peers() if self._lan_hub else {}
        order = sorted(peers.values(), key=lambda p: (p.name, p.node_id))
        opts = [
            (f"{p.name}  {p.host}:{p.http_port} cfg:{p.config_port}  [{p.node_id}]", p.node_id)
            for p in order
        ]
        try:
            sel.set_options(opts)
        except Exception:
            pass

    @on(Switch.Changed, "#share-lan-switch")
    def share_lan_changed(self, event: Switch.Changed) -> None:
        self._share_lan_enabled = bool(event.value)
        self._sync_lan_hub()
        self._refresh_share_peer_list()

    @on(Switch.Changed, "#share-offer-config")
    def share_offer_changed(self, event: Switch.Changed) -> None:
        if self._share_lan_enabled:
            self._sync_lan_hub()

    @on(Button.Pressed, "#share-tab-mm")
    def share_tab_mm(self) -> None:
        self.query_one("#share-sub", ContentSwitcher).current = "share-mm"

    @on(Button.Pressed, "#share-tab-ms")
    def share_tab_ms(self) -> None:
        self.query_one("#share-sub", ContentSwitcher).current = "share-ms"
        self._update_slave_cmd_text()

    @on(Button.Pressed, "#share-pin-refresh")
    def share_pin_refresh(self) -> None:
        self._share_pin = random_pin3()
        self._update_share_pin_display()
        if self._share_lan_enabled:
            self._sync_lan_hub()

    @on(Button.Pressed, "#share-pull-btn")
    def share_pull_pressed(self) -> None:
        self.run_worker(self._share_pull_worker(), exclusive=True, exit_on_error=False)

    async def _share_pull_worker(self) -> None:
        try:
            sel = self.query_one("#share-peer-select", Select)
            nid = sel.value
        except Exception:
            self.notify("无法读取列表", severity="error")
            return
        if sel.is_blank():
            self.notify("请先在下拉框选择一台主机", severity="warning")
            return
        if nid == self._share_node_id:
            self.notify("不能拉取本机", severity="warning")
            return
        pin = self.query_one("#share-pull-pin", Input).value.strip()
        if len(pin) != 3 or not pin.isdigit():
            self.notify("请输入对方屏幕上显示的 3 位 PIN", severity="warning")
            return
        cfgp = self._share_config_path()
        if not cfgp:
            self.notify("MYCLASH_ROOT_PWD 未设置", severity="error")
            return
        peers = self._lan_hub.snapshot_peers() if self._lan_hub else {}
        peer = peers.get(nid)
        if not peer:
            self.notify("未找到该主机信息", severity="error")
            return
        loop = asyncio.get_running_loop()
        self.notify("正在拉取配置…", timeout=2)
        try:
            h, cp, pn = peer.host, peer.config_port, pin
            raw = await loop.run_in_executor(
                None,
                lambda h=h, cp=cp, pn=pn: fetch_remote_config(h, cp, pn),
            )
        except Exception as exc:
            self.notify(f"拉取失败: {exc}", severity="error", timeout=6)
            return
        backup = cfgp.parent / f"{cfgp.name}.bak.{int(time.time())}"
        try:
            if cfgp.is_file():
                backup.write_bytes(cfgp.read_bytes())
            cfgp.write_bytes(raw)
        except OSError as exc:
            self.notify(f"写入失败: {exc}", severity="error", timeout=6)
            return
        self.notify(
            f"已写入 {cfgp}，备份 {backup.name}。请执行: sudo systemctl restart myclash",
            severity="information",
            timeout=8,
        )

    @on(Button.Pressed, "#share-manual-pull-btn")
    def share_manual_pull_pressed(self) -> None:
        self.run_worker(self._share_manual_pull_worker(), exclusive=True, exit_on_error=False)

    async def _share_manual_pull_worker(self) -> None:
        host = self.query_one("#share-manual-ip", Input).value.strip()
        port_s = self.query_one("#share-manual-config-port", Input).value.strip()
        pin = self.query_one("#share-pull-pin", Input).value.strip()
        if not host:
            self.notify("请填写对方 IP", severity="warning")
            return
        try:
            cport = int(port_s) if port_s else lan_config_http_port()
        except ValueError:
            self.notify("config 端口无效", severity="warning")
            return
        if len(pin) != 3 or not pin.isdigit():
            self.notify("请输入对方屏幕上显示的 3 位 PIN", severity="warning")
            return
        cfgp = self._share_config_path()
        if not cfgp:
            self.notify("MYCLASH_ROOT_PWD 未设置", severity="error")
            return
        loop = asyncio.get_running_loop()
        self.notify("正在拉取配置…", timeout=2)
        try:
            h, cp, pn = host, cport, pin
            raw = await loop.run_in_executor(
                None,
                lambda h=h, cp=cp, pn=pn: fetch_remote_config(h, cp, pn),
            )
        except Exception as exc:
            self.notify(f"拉取失败: {exc}", severity="error", timeout=6)
            return
        backup = cfgp.parent / f"{cfgp.name}.bak.{int(time.time())}"
        try:
            if cfgp.is_file():
                backup.write_bytes(cfgp.read_bytes())
            cfgp.write_bytes(raw)
        except OSError as exc:
            self.notify(f"写入失败: {exc}", severity="error", timeout=6)
            return
        self.notify(
            f"已写入 {cfgp}，备份 {backup.name}。请执行: sudo systemctl restart myclash",
            severity="information",
            timeout=8,
        )

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
