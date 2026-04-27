"""HTTP client for Clash / mihomo REST API."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
import yaml

from .config_api import normalize_runtime_config


def _normalize_api_base(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return "http://127.0.0.1:9090"
    if s.startswith("http://") or s.startswith("https://"):
        return s.rstrip("/")
    if s.startswith(":"):
        return f"http://127.0.0.1{s}".rstrip("/")
    return f"http://{s}".rstrip("/")


def _api_base_from_user_config() -> str | None:
    root = os.environ.get("MYCLASH_ROOT_PWD", "").strip()
    if not root:
        return None
    uc = Path(root) / "user_config.yaml"
    if not uc.is_file():
        return None
    try:
        doc = yaml.safe_load(uc.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(doc, dict):
        return None
    ec = doc.get("external-controller")
    if isinstance(ec, str) and ec.strip():
        return _normalize_api_base(ec)
    return None


class ClashClient:
    def __init__(self):
        # 优先级：MYCLASH_API > user_config external-controller > 默认 127.0.0.1:9090
        env_api = os.getenv("MYCLASH_API", "").strip()
        if env_api:
            self.base_url = _normalize_api_base(env_api)
        else:
            self.base_url = _api_base_from_user_config() or "http://127.0.0.1:9090"
        self.secret = os.getenv("MYCLASH_SECRET", "").strip()

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.secret:
            headers["Authorization"] = f"Bearer {self.secret}"
        return headers

    def _get_json(
        self,
        path: str,
        params: dict | None = None,
        timeout: float | tuple[float, float] | None = None,
    ) -> Any:
        # 分开 connect/read，避免错误地址或内核未起时 TCP 握手拖很久（体感「启动卡死」）。
        if timeout is None:
            connect = float(os.environ.get("MYCLASH_TUI_API_CONNECT_TIMEOUT", "1.25"))
            read = float(os.environ.get("MYCLASH_TUI_API_READ_TIMEOUT", "4"))
            timeout = (connect, read)
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
        connect = float(os.environ.get("MYCLASH_TUI_API_CONNECT_TIMEOUT", "1.25"))
        read = float(os.environ.get("MYCLASH_TUI_API_PATCH_READ_TIMEOUT", "10"))
        r = requests.patch(
            f"{self.base_url}/configs",
            headers=self._headers(),
            json=payload,
            timeout=(connect, read),
        )
        if r.status_code >= 400:
            detail = (r.text or "").strip() or r.reason or str(r.status_code)
            raise RuntimeError(detail)
        r.raise_for_status()

    def test_delay(self, proxy_name: str, test_url: str, timeout_ms: int):
        encoded_name = quote(proxy_name, safe="")
        connect = float(os.environ.get("MYCLASH_TUI_API_CONNECT_TIMEOUT", "1.25"))
        read = max(4.0, timeout_ms / 1000.0 + 1.0)
        response = requests.get(
            f"{self.base_url}/proxies/{encoded_name}/delay",
            params={"url": test_url, "timeout": timeout_ms},
            headers=self._headers(),
            timeout=(connect, read),
        )
        response.raise_for_status()
        return response.json().get("delay")

    def select_proxy(self, group_name: str, proxy_name: str) -> None:
        encoded_group = quote(group_name, safe="")
        connect = float(os.environ.get("MYCLASH_TUI_API_CONNECT_TIMEOUT", "1.25"))
        read = float(os.environ.get("MYCLASH_TUI_API_READ_TIMEOUT", "4"))
        response = requests.put(
            f"{self.base_url}/proxies/{encoded_group}",
            json={"name": proxy_name},
            headers=self._headers(),
            timeout=(connect, read),
        )
        response.raise_for_status()
