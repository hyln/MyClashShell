"""v2ray 节点选择 + 本地 SOCKS 测速（Textual）。"""

from __future__ import annotations

import concurrent.futures
import logging
import os
from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.coordinate import Coordinate
from textual.widgets import DataTable, Footer, Static

from scripts.lib.paths import xray_executable
from scripts.lib.v2ray_delay_test import measure_proxy_delay_ms
from scripts.lib.v2ray_persist import (
    apply_v2ray_outbound_selection,
    fixed_routing_outbound_tag_from_mcs,
    load_proxy_outbounds_from_cache,
    load_user_config_dict,
    resolve_v2ray_default_profile,
)


class V2rayPickerApp(App[None]):
    """表格展示节点、延迟；Enter 固定并应用；t 全部测速；r 测当前行；c 取消固定。"""

    TITLE = "v2ray 节点选择"

    CSS = """
    Screen { background: $surface; }
    #title { padding: 0 1; margin: 0 0 0 0; color: $text-muted; }
    #hint { padding: 0 1 1 1; color: $text; text-style: bold; }
    #active-banner {
        padding: 0 1 1 1;
        border: round $success;
        background: $panel;
        margin: 0 1 1 1;
        text-align: center;
    }
    #nodes { height: 1fr; border: tall $primary; }
    #status { padding: 0 1; height: auto; color: $accent; }
    """

    BINDINGS = [
        Binding("q", "quit", "退出", show=True),
        Binding("escape", "quit", "退出", show=False),
        Binding("t", "test_all", "全部测速", show=True),
        Binding("r", "test_row", "测当前行", show=True),
        # DataTable 聚焦时会先吃掉 Enter；priority 让 App 优先处理
        Binding(
            "enter",
            "activate",
            "Enter选用",
            show=True,
            priority=True,
        ),
        Binding("ctrl+o", "activate", "Ctrl+O选用", show=True),
        Binding("c", "clear_fixed", "取消固定", show=True),
    ]

    COL_MARK = 0
    COL_TAG = 1
    COL_DELAY = 2
    COL_PROTO = 3

    def __init__(self, root: Path) -> None:
        super().__init__()
        self._root = root
        self._eff = ""
        self._doc: dict = {}
        self._uc_path: Path | None = None
        self._obs: list[dict] = []
        self._testing = False
        self._log = logging.getLogger("tui_v2ray")

    def compose(self) -> ComposeResult:
        yield Static("", id="title")
        yield Static("", id="hint")
        yield Static("", id="active-banner")
        yield DataTable(show_header=True, cursor_type="row", zebra_stripes=True, id="nodes")
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        try:
            self._eff, self._doc, self._uc_path = resolve_v2ray_default_profile(self._root)
            self._obs = load_proxy_outbounds_from_cache(self._root, self._eff)
        except ValueError as e:
            self.notify(str(e), severity="error", timeout=12)
            self.set_timer(0.2, lambda: self.exit(1))
            return

        title = self.query_one("#title", Static)
        title.update(
            f"默认订阅: [b]{self._eff}[/]  ·  [t]全部测速  [r]测当前行  "
            f"[c]取消固定  [q]退出"
        )
        self.query_one("#hint", Static).update(
            "↑↓ 选中一行后按 [b]Enter[/b] 或 [b]Ctrl+O[/b] → 立即写回并由 mcs 热重载 v2ray。"
            "若 Enter 无反应请试 [b]Ctrl+O[/b]；焦点须在表格上（可 Tab 或鼠标点表格）。"
        )
        self._refresh_active_banner()
        table = self.query_one("#nodes", DataTable)
        table.add_columns("在用标记", "节点 tag", "延迟", "协议")
        active = fixed_routing_outbound_tag_from_mcs(self._root)
        for ob in self._obs:
            tag = str(ob.get("tag") or "?")
            mark = "  ◄◄ 当前出口  ►►  " if active and tag == active else ""
            proto = str(ob.get("protocol") or "?")
            table.add_row(mark, tag, "—", proto)
        self._set_status("就绪。测速后用 ↑↓ 选中节点，Enter 立即生效。")
        table.focus()

    def _table(self) -> DataTable:
        return self.query_one("#nodes", DataTable)

    def _set_status(self, text: str) -> None:
        self.query_one("#status", Static).update(text)

    def _refresh_active_banner(self) -> None:
        ban = self.query_one("#active-banner", Static)
        active = fixed_routing_outbound_tag_from_mcs(self._root)
        if active:
            ban.update(f"[bold green]当前 mcs 固定出口[/bold green]: [bold]{active}[/bold]")
        else:
            ban.update(
                "[bold yellow]当前 mcs 路由[/bold yellow]: [bold]多节点随机 balancer[/bold] "
                "（未固定单一出口；可在下方 Enter 选用一行固定）"
            )

    def _sync_mark_column(self) -> None:
        """按 ``mcs/configs/v2ray.json`` 里实际路由刷新「在用标记」列。"""
        table = self._table()
        active = fixed_routing_outbound_tag_from_mcs(self._root)
        for i, ob in enumerate(self._obs):
            tag = str(ob.get("tag") or "?")
            mark = "  ◄◄ 当前出口  ►►  " if active and tag == active else ""
            table.update_cell_at(Coordinate(i, self.COL_MARK), mark)

    def _reload_doc_and_refresh_marks(self) -> None:
        if not self._uc_path:
            return
        self._doc = load_user_config_dict(self._uc_path)
        self._refresh_active_banner()
        self._sync_mark_column()

    def action_quit(self) -> None:
        self.exit()

    def action_test_all(self) -> None:
        if self._testing:
            self.notify("正在测速，请稍候", severity="warning")
            return
        self._testing = True
        self._set_status("全部测速中（每个节点会临时起 v2ray 子进程）…")
        self._run_test_all()

    @work(thread=True, exclusive=True)
    def _run_test_all(self) -> None:
        exe = xray_executable(self._root)
        url = os.environ.get("MYCLASH_TUI_TEST_URL", "https://www.gstatic.com/generate_204")
        timeout = float(os.environ.get("MYCLASH_V2RAY_PING_CURL_TIMEOUT", "4"))
        listen_wait = float(os.environ.get("MYCLASH_V2RAY_PING_LISTEN_WAIT", "8"))

        def one(i: int, ob: dict) -> tuple[int, int | None]:
            ms = measure_proxy_delay_ms(
                xray_exe=exe,
                proxy_ob=ob,
                test_url=url,
                curl_timeout=timeout,
                listen_ready_timeout=listen_wait,
            )
            return i, ms

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
                futs = [ex.submit(one, i, ob) for i, ob in enumerate(self._obs)]
                for fut in concurrent.futures.as_completed(futs):
                    i, ms = fut.result()
                    self.call_from_thread(self._apply_delay_cell, i, ms)
        finally:
            self.call_from_thread(self._test_done)

    def _apply_delay_cell(self, row: int, ms: int | None) -> None:
        text = f"{ms}ms" if ms is not None else "fail"
        self._table().update_cell_at(Coordinate(row, self.COL_DELAY), text)

    def _test_done(self) -> None:
        self._testing = False
        self._set_status("测速结束：↑↓ 选行后 Enter 立即固定并热重载；[t] 再测。")

    def action_test_row(self) -> None:
        if self._testing:
            return
        table = self._table()
        row = table.cursor_row
        if row is None or row < 0 or row >= len(self._obs):
            self.notify("请先选中一行", severity="warning")
            return
        self._testing = True
        self._set_status(f"测速中: 第 {row + 1} 行 …")
        self._run_test_row(row)

    @work(thread=True, exclusive=True)
    def _run_test_row(self, row: int) -> None:
        exe = xray_executable(self._root)
        url = os.environ.get("MYCLASH_TUI_TEST_URL", "https://www.gstatic.com/generate_204")
        timeout = float(os.environ.get("MYCLASH_V2RAY_PING_CURL_TIMEOUT", "4"))
        listen_wait = float(os.environ.get("MYCLASH_V2RAY_PING_LISTEN_WAIT", "8"))
        ms: int | None = None
        try:
            ms = measure_proxy_delay_ms(
                xray_exe=exe,
                proxy_ob=self._obs[row],
                test_url=url,
                curl_timeout=timeout,
                listen_ready_timeout=listen_wait,
            )
        finally:
            self.call_from_thread(self._apply_delay_cell, row, ms)
            self.call_from_thread(self._row_test_done)

    def _row_test_done(self) -> None:
        self._testing = False
        self._set_status("就绪。")

    def action_activate(self) -> None:
        if self._testing:
            return
        table = self._table()
        row = table.cursor_row
        if row is None or row < 0 or row >= len(self._obs):
            self.notify("请先选中一行", severity="warning")
            return
        tag = str(self._obs[row].get("tag") or "").strip()
        if not tag:
            return
        try:
            ok, msg, reload_ok = apply_v2ray_outbound_selection(
                self._root, tag=tag, clear=False, logger=self._log
            )
        except ValueError as e:
            self.notify(str(e), severity="error")
            return
        sev: str = "error"
        if ok and reload_ok:
            sev = "information"
        elif ok:
            sev = "warning"
        self.notify(msg, severity=sev, timeout=12)
        self._reload_doc_and_refresh_marks()

    def action_clear_fixed(self) -> None:
        if self._testing:
            return
        try:
            ok, msg, reload_ok = apply_v2ray_outbound_selection(
                self._root, tag=None, clear=True, logger=self._log
            )
        except ValueError as e:
            self.notify(str(e), severity="error")
            return
        sev: str = "error"
        if ok and reload_ok:
            sev = "information"
        elif ok:
            sev = "warning"
        self.notify(msg, severity=sev, timeout=12)
        self._reload_doc_and_refresh_marks()
