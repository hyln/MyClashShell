"""调用 ``mcs_manager`` 内置 Flask 控制面。

监听地址与端口优先读 ``user_config.yaml`` 的 ``mcs_api_host`` / ``mcs_api_port``；
若设置环境变量 ``MYCLASH_MCS_API_HOST`` / ``MYCLASH_MCS_API_PORT`` 则覆盖 YAML。
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml

from scripts.lib.paths import repo_root


def read_mcs_api_bind(root: Path | None = None) -> tuple[str, int]:
    """返回 ``(host, port)`` 供 ``make_server`` 与 HTTP 客户端共用。"""
    base = repo_root() if root is None else root
    host = "127.0.0.1"
    port = 9091
    uc = base / "user_config.yaml"
    if uc.is_file():
        try:
            doc = yaml.safe_load(uc.read_text(encoding="utf-8"))
            if isinstance(doc, dict):
                vh = doc.get("mcs_api_host")
                if isinstance(vh, str) and vh.strip():
                    host = vh.strip()
                vp = doc.get("mcs_api_port")
                if isinstance(vp, int) and 1 <= vp <= 65535:
                    port = vp
                elif isinstance(vp, str) and vp.strip().isdigit():
                    p = int(vp.strip())
                    if 1 <= p <= 65535:
                        port = p
        except Exception:  # noqa: BLE001
            pass
    eh = os.environ.get("MYCLASH_MCS_API_HOST", "").strip()
    if eh:
        host = eh
    ep = os.environ.get("MYCLASH_MCS_API_PORT", "").strip()
    if ep:
        try:
            p = int(ep)
            if 1 <= p <= 65535:
                port = p
        except ValueError:
            pass
    return host, port


def _auth_headers() -> dict[str, str]:
    tok = os.environ.get("MYCLASH_MCS_API_TOKEN", "").strip()
    return {"Authorization": f"Bearer {tok}"} if tok else {}


def _post_json_headers() -> dict[str, str]:
    h: dict[str, str] = {"Content-Type": "application/json"}
    h.update(_auth_headers())
    return h


def _mcs_base_url(root: Path | None = None) -> str:
    host, port = read_mcs_api_bind(root)
    if ":" in host and not host.startswith("["):
        netloc = f"[{host}]:{port}"
    else:
        netloc = f"{host}:{port}"
    return f"http://{netloc}"


def mcs_control_base_url(root: Path | None = None) -> str:
    """与 API 请求一致的 base URL（用于日志 / 提示）。"""
    return _mcs_base_url(root)


_direct_opener: urllib.request.OpenerDirector | None = None


def _opener_no_env_proxy() -> urllib.request.OpenerDirector:
    """不使用环境变量里的 HTTP(S)_PROXY，避免本机 mcs API 被误走 Clash 代理。"""
    global _direct_opener
    if _direct_opener is None:
        _direct_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return _direct_opener


def get_kernel_status(
    *, timeout: float = 5.0, root: Path | None = None
) -> tuple[dict[str, object] | None, str | None]:
    """``GET /kernel/status``。成功 ``(dict, None)``，失败 ``(None, 简短原因)``。"""
    url = f"{_mcs_base_url(root)}/kernel/status"
    req = urllib.request.Request(url, method="GET", headers=_auth_headers())
    try:
        with _opener_no_env_proxy().open(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
        if isinstance(data, dict):
            return data, None
        return None, "响应不是 JSON 对象"
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return None, "HTTP 401（请检查 MYCLASH_MCS_API_TOKEN 与 Authorization: Bearer 是否一致）"
        return None, f"HTTP {e.code} {e.reason or ''}".strip()
    except urllib.error.URLError as e:
        return None, str(e.reason) if getattr(e, "reason", None) else repr(e)
    except OSError as e:
        return None, f"{type(e).__name__}: {e}"
    except json.JSONDecodeError as e:
        return None, f"JSON 解析失败: {e}"


def request_kernel_reload(
    *, logger: logging.Logger | None = None, timeout: float = 8.0, root: Path | None = None
) -> bool:
    """``POST /kernel/reload``。成功返回 True；连接失败返回 False。"""
    url = f"{_mcs_base_url(root)}/kernel/reload"
    req = urllib.request.Request(url, method="POST", data=b"{}", headers=_post_json_headers())
    try:
        with _opener_no_env_proxy().open(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        if logger:
            logger.info("mcs_manager 热重载: HTTP %s %s", resp.status, raw[:300])
        return True
    except urllib.error.HTTPError as e:
        if logger:
            logger.warning("mcs_manager 热重载 HTTP 错误: %s %s", e.code, e.reason)
        return False
    except urllib.error.URLError as e:
        if logger:
            logger.warning("无法连接 mcs_manager API（%s）；可手动执行 myclash service restart", e)
        return False
    except OSError as e:
        if logger:
            logger.warning(
                "mcs_manager API 连接异常（%s: %s）；若服务已重启仍失败，可执行 myclash service restart",
                type(e).__name__,
                e,
            )
        return False


def wait_kernel_ready(
    *,
    want_backend: str | None = "v2ray",
    timeout: float = 18.0,
    poll: float = 0.28,
    root: Path | None = None,
) -> tuple[bool, str | None]:
    """在 ``timeout`` 秒内轮询 ``GET /kernel/status``，直到 ``alive`` 且（若给定）``backend_running`` 匹配。"""
    deadline = time.monotonic() + timeout
    want = (want_backend or "").strip().lower()
    last_err: str | None = None
    while time.monotonic() < deadline:
        st, err = get_kernel_status(timeout=min(4.0, max(1.0, deadline - time.monotonic())), root=root)
        if err:
            last_err = err
        if isinstance(st, dict) and st.get("alive"):
            be = str(st.get("backend_running") or "").strip().lower()
            if not want or be == want:
                return True, None
        time.sleep(poll)
    return False, last_err or "timeout"


def request_sync_meta(*, logger: logging.Logger | None = None, timeout: float = 6.0) -> bool:
    """``POST /kernel/sync_meta``：刷新 ``cache/current_sub.txt``。"""
    url = f"{_mcs_base_url(None)}/kernel/sync_meta"
    req = urllib.request.Request(url, method="POST", data=b"{}", headers=_post_json_headers())
    try:
        with _opener_no_env_proxy().open(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        if logger:
            logger.info("mcs_manager sync_meta: HTTP %s %s", resp.status, raw[:300])
        return True
    except urllib.error.HTTPError as e:
        if logger:
            logger.warning("mcs_manager sync_meta HTTP 错误: %s %s", e.code, e.reason)
        return False
    except urllib.error.URLError as e:
        if logger:
            logger.warning("无法连接 mcs_manager sync_meta（%s）", e)
        return False
    except OSError as e:
        if logger:
            logger.warning("mcs_manager sync_meta 异常: %s: %s", type(e).__name__, e)
        return False


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ok = request_kernel_reload(logger=logging.getLogger("mcs_reload"))
    raise SystemExit(0 if ok else 1)
