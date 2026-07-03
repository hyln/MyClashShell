"""v2ray/Xray 无官方延迟 API：本模块用「临时子进程 + 本机 SOCKS + curl 计时」测延迟（与 v2rayN 思路一致）。"""

from __future__ import annotations

import copy
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from scripts.lib.paths import repo_root_from_env, xray_executable
from scripts.lib.v2ray_subscribe import _proxy_outbounds_from_saved_v2ray


def _pick_free_port(host: str = "127.0.0.1") -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((host, 0))
    port = int(s.getsockname()[1])
    s.close()
    return port


def _wait_tcp(host: str, port: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.35):
                return True
        except OSError:
            time.sleep(0.04)
    return False


def _build_probe_config(proxy_ob: dict[str, Any], socks_port: int) -> dict[str, Any]:
    pob = copy.deepcopy(proxy_ob)
    tag = str(pob.get("tag") or "probe-proxy")
    pob["tag"] = tag
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "listen": "127.0.0.1",
                "port": socks_port,
                "protocol": "socks",
                "settings": {"udp": True},
                "tag": "socks-in",
            }
        ],
        "outbounds": [
            pob,
            {"protocol": "freedom", "tag": "direct"},
        ],
        "routing": {
            "domainStrategy": "AsIs",
            "rules": [{"type": "field", "network": "tcp,udp", "outboundTag": tag}],
        },
    }


def _curl_through_socks(socks_port: int, url: str, max_time: float) -> bool:
    r = subprocess.run(
        [
            "curl",
            "-fsSL",
            "--max-time",
            str(max_time),
            "--socks5-hostname",
            f"127.0.0.1:{socks_port}",
            url,
        ],
        capture_output=True,
        text=True,
    )
    return r.returncode == 0


def measure_proxy_delay_ms(
    *,
    xray_exe: Path,
    proxy_ob: dict[str, Any],
    test_url: str,
    curl_timeout: float = 4.0,
    listen_ready_timeout: float = 8.0,
    process_grace: float = 2.0,
) -> int | None:
    """为单条 outbound 起临时 Xray，经 SOCKS 访问 ``test_url``，返回耗时毫秒；失败为 ``None``。"""
    if not xray_exe.is_file():
        return None
    if shutil.which("curl") is None:
        return None
    port = _pick_free_port()
    cfg = _build_probe_config(proxy_ob, port)
    fd, path = tempfile.mkstemp(prefix="mcs-v2probe-", suffix=".json", text=True)
    os.close(fd)
    proc: subprocess.Popen[Any] | None = None
    try:
        Path(path).write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        proc = subprocess.Popen(
            [str(xray_exe), "run", "-config", path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not _wait_tcp("127.0.0.1", port, listen_ready_timeout):
            return None
        if proc.poll() is not None:
            return None
        t0 = time.monotonic()
        ok = _curl_through_socks(port, test_url, curl_timeout)
        elapsed = int((time.monotonic() - t0) * 1000)
        return elapsed if ok else None
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=process_grace)
            except subprocess.TimeoutExpired:
                proc.kill()
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass


def load_v2ray_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def list_proxy_outbounds_from_file(path: Path) -> list[dict[str, Any]]:
    data = load_v2ray_json(path)
    if not data:
        return []
    return _proxy_outbounds_from_saved_v2ray(data)


def default_v2ray_config_path(root: Path | None = None) -> Path:
    base = root if root is not None else repo_root_from_env()
    if base is None:
        raise RuntimeError("MYCLASH_ROOT_PWD 未设置，无法定位 mcs/configs/v2ray.json")
    return base / "mcs" / "configs" / "v2ray.json"
