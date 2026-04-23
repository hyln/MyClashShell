"""Proxy group / selection / delay-test state."""

from __future__ import annotations

import concurrent.futures
import os
import threading
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .client import ClashClient


class TuiState:
    def __init__(self, client: ClashClient, preferred_group: str | None = None):
        self.client = client
        self.groups: list[str] = []
        self.group_idx = 0
        self.nodes: list[str] = []
        self.node_types: dict[str, str] = {}
        self.current_node = ""
        self.selected_idx = 0
        self.delays: dict[str, int | None] = {}
        self.testing = False
        self.last_error = ""
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
        return list(self.nodes)

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
        """键盘选中下标与 GET /proxies 里当前组的 now 一致。"""
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
        self.node_types = {}
        for n in self.nodes:
            ent = proxies.get(n)
            if isinstance(ent, dict):
                t = ent.get("type")
                self.node_types[n] = str(t) if t is not None else ""
            else:
                self.node_types[n] = ""
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

    def start_delay_test(
        self,
        on_done: Callable[[], None] | None = None,
        on_progress: Callable[[], None] | None = None,
    ) -> None:
        if self.testing or not self.nodes:
            return
        self._abort_delay_test.clear()
        self.testing = True
        self.last_error = ""
        nodes = list(self.nodes)
        with self._lock:
            self.delays = dict.fromkeys(nodes, None)

        def worker():
            # on_progress/on_done 里若使用 call_from_thread，必须从本线程调用，不可在主线程先调一次
            if on_progress:
                on_progress()
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
                                val: int | None = fut.result()
                            except Exception:
                                val = None
                            with self._lock:
                                self.delays[node] = val
                            if on_progress:
                                on_progress()
                finally:
                    executor.shutdown(wait=False, cancel_futures=True)
            except Exception as exc:
                self.last_error = str(exc)
            with self._lock:
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
