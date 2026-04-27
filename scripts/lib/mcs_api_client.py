"""调用 ``mcs_manager`` 内置 Flask 控制面。

监听地址与端口池（**不可**再指定单一 ``mcs_api_port``）：

- **YAML**：优先读取 ``mcs_api_port_range: [start, end]``（含端点）；
  兼容旧键 ``mcs_api_start_port`` / ``mcs_api_end_port``。缺省 ``29190``–``29290``。
- **服务端**：若设置 ``MYCLASH_MCS_API_PORT`` 则强制使用该端口；否则在池内选首个可绑定端口，并写入
  ``cache/current_mcs_port.txt``（与 ``current_sub.txt`` 类似，供客户端发现）。
- **客户端**：``MYCLASH_MCS_API_PORT`` > ``cache/current_mcs_port.txt`` > 池的起始端口（无缓存时的回退）。
"""

from __future__ import annotations

import json
import logging
import os
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml

from scripts.lib.paths import download_cache_dir, repo_root

# user_config 未写 mcs_api_port_range 时的默认池（含端点）
DEFAULT_MCS_API_START_PORT = 29190
DEFAULT_MCS_API_END_PORT = 29290


def _current_mcs_port_path(base: Path) -> Path:
    return download_cache_dir(base) / "current_mcs_port.txt"


def read_mcs_port_from_file(root: Path | None = None) -> int | None:
    """读取 ``cache/current_mcs_port.txt`` 中的端口号；无效或不存在则 ``None``。"""
    base = repo_root() if root is None else root
    path = _current_mcs_port_path(base)
    if not path.is_file():
        return None
    try:
        raw = path.read_text(encoding="utf-8").strip()
        if raw.isdigit():
            p = int(raw)
            if 1 <= p <= 65535:
                return p
    except OSError:
        return None
    return None


def write_current_mcs_port_file(root: Path, port: int) -> None:
    """将当前 mcs_manager 监听端口写入 ``cache/current_mcs_port.txt``。"""
    d = download_cache_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    _current_mcs_port_path(root).write_text(f"{int(port)}\n", encoding="utf-8")


def _parse_yaml_port_int(doc: dict, key: str) -> int | None:
    v = doc.get(key)
    if isinstance(v, int) and 1 <= v <= 65535:
        return v
    if isinstance(v, str) and v.strip().isdigit():
        p = int(v.strip())
        if 1 <= p <= 65535:
            return p
    return None


def _parse_yaml_mcs_host(doc: dict, default: str) -> str:
    vh = doc.get("mcs_api_host")
    if isinstance(vh, str) and vh.strip():
        return vh.strip()
    return default


def _parse_yaml_port_range(doc: dict, key: str) -> tuple[int, int] | None:
    v = doc.get(key)
    if not isinstance(v, (list, tuple)) or len(v) != 2:
        return None
    a = _parse_yaml_port_int({"x": v[0]}, "x")
    b = _parse_yaml_port_int({"x": v[1]}, "x")
    if a is None or b is None:
        return None
    return (a, b) if a <= b else (b, a)


def _mcs_bind_from_user_config(base: Path) -> tuple[str, int, int]:
    """单次解析 ``user_config.yaml``：``(mcs_api_host, pool_start, pool_end)``，含端点；``start>end`` 时交换。"""
    host = "127.0.0.1"
    lo, hi = DEFAULT_MCS_API_START_PORT, DEFAULT_MCS_API_END_PORT
    uc = base / "user_config.yaml"
    if uc.is_file():
        try:
            doc = yaml.safe_load(uc.read_text(encoding="utf-8"))
            if isinstance(doc, dict):
                host = _parse_yaml_mcs_host(doc, host)
                rng = _parse_yaml_port_range(doc, "mcs_api_port_range")
                if rng is not None:
                    lo, hi = rng
                else:
                    a = _parse_yaml_port_int(doc, "mcs_api_start_port")
                    b = _parse_yaml_port_int(doc, "mcs_api_end_port")
                    if a is not None:
                        lo = a
                    if b is not None:
                        hi = b
        except Exception:  # noqa: BLE001
            pass
    if lo > hi:
        lo, hi = hi, lo
    return host, lo, hi


def read_mcs_api_port_range(root: Path | None = None) -> tuple[int, int]:
    """MCS API 端口池 ``(start, end)``，与 :func:`allocate_mcs_listen_port` 使用的范围一致。"""
    base = repo_root() if root is None else root
    _h, lo, hi = _mcs_bind_from_user_config(base)
    return lo, hi


def _load_user_config_mcs_host_and_range(base: Path) -> tuple[str, int, int]:
    """``(host, pool_start, pool_end)``。"""
    return _mcs_bind_from_user_config(base)


def _tcp_bind_possible(host: str, port: int) -> bool:
    """检测 ``host:port`` 是否可被当前进程绑定（与 Werkzeug 监听族一致）。"""
    try:
        for res in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM):
            af, socktype, proto, _, sockaddr = res
            try:
                with socket.socket(af, socktype, proto) as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.bind(sockaddr)
                    return True
            except OSError:
                continue
    except OSError:
        return False
    return False


def allocate_mcs_listen_port(root: Path) -> tuple[str, int]:
    """供 ``mcs_manager`` 选择监听端口：``MYCLASH_MCS_API_PORT`` > 配置端口池内首个空闲。"""
    host, pool_lo, pool_hi = _load_user_config_mcs_host_and_range(root)
    eh = os.environ.get("MYCLASH_MCS_API_HOST", "").strip()
    if eh:
        host = eh
    ep = os.environ.get("MYCLASH_MCS_API_PORT", "").strip()
    if ep:
        try:
            p = int(ep)
            if 1 <= p <= 65535:
                return host, p
        except ValueError:
            pass
    for p in range(pool_lo, pool_hi + 1):
        if _tcp_bind_possible(host, p):
            return host, p
    raise SystemExit(
        f"mcs_manager: 端口池 {pool_lo}-{pool_hi} 均被占用；可扩大 mcs_api_port_range"
        " 或设置环境变量 MYCLASH_MCS_API_PORT"
    )


def read_mcs_api_bind(root: Path | None = None) -> tuple[str, int]:
    """返回 ``(host, port)``：客户端连接 mcs_manager 时使用。"""
    base = repo_root() if root is None else root
    host, pool_lo, _pool_hi = _load_user_config_mcs_host_and_range(base)
    eh = os.environ.get("MYCLASH_MCS_API_HOST", "").strip()
    if eh:
        host = eh
    ep = os.environ.get("MYCLASH_MCS_API_PORT", "").strip()
    if ep:
        try:
            p = int(ep)
            if 1 <= p <= 65535:
                return host, p
        except ValueError:
            pass
    fp = read_mcs_port_from_file(base)
    if fp is not None:
        return host, fp
    return host, pool_lo


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


def request_sync_meta(
    *, logger: logging.Logger | None = None, timeout: float = 6.0, root: Path | None = None
) -> bool:
    """``POST /kernel/sync_meta``：刷新 ``cache/current_sub.txt``。"""
    url = f"{_mcs_base_url(root)}/kernel/sync_meta"
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
