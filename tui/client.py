"""HTTP client for Clash / mihomo REST API."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

import requests

from tui.config_api import normalize_runtime_config


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
