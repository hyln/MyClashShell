#!/usr/bin/env python3
"""MCS manager: systemd 拉起本进程；mihomo（Clash 兼容，mcs/bin/clash）/ v2ray 由子进程运行，并可热切换。

- 子进程由 ``user_config.yaml`` 的 ``default_subscribe`` + ``subscribes[].backend`` 决定。
- 本地 HTTP API（Flask + Werkzeug）在主线程上 ``serve_forever``，
  避免在守护线程里 ``app.run`` 导致对端 ``RemoteDisconnected``。
  监听地址与端口在 ``user_config.yaml`` 的 ``mcs_api_host`` / ``mcs_api_port``（缺省同 ``127.0.0.1:9091``）。

环境变量：

- ``MYCLASH_MCS_API_HOST`` / ``MYCLASH_MCS_API_PORT``：若设置则覆盖 YAML 中的上述两项。
- ``MYCLASH_MCS_API_TOKEN``：若设置，受保护接口须带 ``Authorization: Bearer <token>``。
- ``GET /kernel/status``：含 ``default_subscribe``、``backend_from_config``、``backend_running`` 等。
- ``POST /kernel/sync_meta``：仅根据 ``user_config.yaml`` 重写 ``cache/current_sub.txt``（不重启子进程）。
- ``MYCLASH_MCS_RESTART_SEC``：子进程异常退出后的重试间隔秒数，默认 ``10``。
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

_repo = Path(__file__).resolve().parents[2]
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

import yaml  # noqa: E402

try:
    from flask import Flask, jsonify, request  # noqa: E402
    from werkzeug.serving import make_server  # noqa: E402
except ImportError:
    print(
        "mcs_manager: 需要 Flask，请执行: venv/bin/pip install flask\n"
        "或重新跑 install 流程中的 pip 依赖安装。",
        file=sys.stderr,
    )
    sys.exit(1)

from scripts.lib.mcs_api_client import read_mcs_api_bind  # noqa: E402
from scripts.lib.paths import clash_executable, download_cache_dir, mcs_configs_dir, v2ray_executable  # noqa: E402
from scripts.lib.subscribe import parse_subscribes, resolve_default_subscribe_name  # noqa: E402

_backend: BackendManager | None = None
_httpd: Any = None


def _root() -> Path:
    raw = os.environ.get("MYCLASH_ROOT_PWD")
    if raw:
        return Path(raw).resolve()
    return Path(__file__).resolve().parents[2]


class BackendManager:
    """根据 ``user_config.yaml`` 解析 backend，监督 clash 槽位（mihomo）/ v2ray 子进程生命周期。"""

    def __init__(self, root: Path) -> None:
        self._root = root
        self.shutdown = threading.Event()
        self.fast_respawn = threading.Event()
        self._state_lock = threading.Lock()
        self._child_proc: subprocess.Popen | None = None
        self._current_backend: str | None = None

    @staticmethod
    def terminate_process(proc: subprocess.Popen, grace: float = 25.0) -> None:
        if proc.poll() is not None:
            return
        proc.send_signal(signal.SIGTERM)
        deadline = time.monotonic() + grace
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                return
            time.sleep(0.2)
        proc.kill()
        proc.wait(timeout=5)

    def resolved_backend(self) -> str:
        uc = self._root / "user_config.yaml"
        if not uc.is_file():
            return "clash"
        try:
            doc = yaml.safe_load(uc.read_text(encoding="utf-8"))
            if not isinstance(doc, dict):
                return "clash"
            subs = parse_subscribes(doc.get("subscribes") or {})
            if not subs:
                return "clash"
            name = resolve_default_subscribe_name(subs, doc.get("default_subscribe"))
            be = str(subs.get(name, {}).get("backend") or "clash").strip().lower()
            if be in ("clash", "v2ray"):
                return be
        except Exception as exc:  # noqa: BLE001
            print(f"mcs_manager: 解析 default_subscribe/subscribes 失败，使用 clash: {exc}", file=sys.stderr)
        return "clash"

    def resolved_default_subscribe_name(self) -> str:
        uc = self._root / "user_config.yaml"
        if not uc.is_file():
            return ""
        try:
            doc = yaml.safe_load(uc.read_text(encoding="utf-8"))
            if not isinstance(doc, dict):
                return ""
            subs = parse_subscribes(doc.get("subscribes") or {})
            if not subs:
                return ""
            return resolve_default_subscribe_name(subs, doc.get("default_subscribe"))
        except Exception:  # noqa: BLE001
            return ""

    def sync_current_sub_txt(self) -> str:
        """将 ``cache/current_sub.txt`` 写成与 ``user_config`` 默认订阅名一致。"""
        name = self.resolved_default_subscribe_name()
        cache = download_cache_dir(self._root)
        cache.mkdir(parents=True, exist_ok=True)
        (cache / "current_sub.txt").write_text(name, encoding="utf-8")
        return name

    def spawn_child(self, backend: str) -> subprocess.Popen | None:
        if backend == "v2ray":
            exe = v2ray_executable(self._root)
            cfg = mcs_configs_dir(self._root) / "v2ray.json"
            if not exe.is_file():
                print(f"mcs_manager: v2ray binary not found: {exe}", file=sys.stderr)
                return None
            if not cfg.is_file():
                print(f"mcs_manager: v2ray config not found: {cfg}", file=sys.stderr)
                return None
            cmd = [str(exe), "run", "-config", str(cfg)]
            return subprocess.Popen(cmd, cwd=str(self._root))
        clash = clash_executable(self._root)
        if not clash.is_file():
            print(f"mcs_manager: mihomo 内核未安装（预期路径 mcs/bin/clash）: {clash}", file=sys.stderr)
            return None
        cfg_dir = mcs_configs_dir(self._root)
        cmd = [str(clash), "-d", str(cfg_dir)]
        return subprocess.Popen(cmd, cwd=str(self._root))

    def _set_child(self, proc: subprocess.Popen | None, backend: str | None) -> None:
        with self._state_lock:
            self._child_proc = proc
            self._current_backend = backend

    def get_child(self) -> tuple[subprocess.Popen | None, str | None]:
        with self._state_lock:
            return self._child_proc, self._current_backend

    def supervisor_loop(self) -> None:
        restart_sec = float(os.environ.get("MYCLASH_MCS_RESTART_SEC", "10").strip() or "10")
        while not self.shutdown.is_set():
            try:
                self.sync_current_sub_txt()
            except Exception as exc:  # noqa: BLE001
                print(f"mcs_manager: 写入 cache/current_sub.txt 失败: {exc}", file=sys.stderr)
            backend = self.resolved_backend()
            proc = self.spawn_child(backend)
            if proc is None:
                print("mcs_manager: 无法启动子进程，稍后重试", file=sys.stderr)
                if self.shutdown.wait(timeout=max(restart_sec, 1.0)):
                    break
                continue
            self._set_child(proc, backend)
            print(f"mcs_manager: 已启动 {backend} (pid={proc.pid})", file=sys.stderr)
            rc = proc.wait()
            self._set_child(None, None)
            print(f"mcs_manager: 子进程退出 rc={rc}", file=sys.stderr)
            if self.shutdown.is_set():
                break
            if self.fast_respawn.is_set():
                self.fast_respawn.clear()
                continue
            if self.shutdown.wait(timeout=max(restart_sec, 0.5)):
                break

    def on_shutdown_signal(self) -> None:
        self.shutdown.set()
        proc, _ = self.get_child()
        if proc is not None and proc.poll() is None:
            self.terminate_process(proc)


def _api_auth_ok() -> bool:
    tok = os.environ.get("MYCLASH_MCS_API_TOKEN", "").strip()
    if not tok:
        return True
    auth = request.headers.get("Authorization", "")
    return auth == f"Bearer {tok}"


def _make_flask_app(mgr: BackendManager) -> Flask:
    app = Flask("mcs_manager")

    @app.get("/kernel/status")
    def kernel_status():
        if not _api_auth_ok():
            return jsonify(error="unauthorized"), 401
        proc, be = mgr.get_child()
        pid = proc.pid if proc and proc.poll() is None else None
        alive = pid is not None
        want = mgr.resolved_backend()
        dname = mgr.resolved_default_subscribe_name()
        be_run = be if alive else None
        return jsonify(
            default_subscribe=dname,
            backend_running=be_run,
            pid=pid,
            alive=alive,
            backend_from_config=want,
        )

    @app.post("/kernel/sync_meta")
    def kernel_sync_meta():
        if not _api_auth_ok():
            return jsonify(error="unauthorized"), 401
        name = mgr.sync_current_sub_txt()
        return jsonify(ok=True, default_subscribe=name)

    @app.post("/kernel/reload")
    def kernel_reload():
        if not _api_auth_ok():
            return jsonify(error="unauthorized"), 401
        mgr.fast_respawn.set()
        proc, be = mgr.get_child()
        if proc is not None and proc.poll() is None:
            BackendManager.terminate_process(proc)
        return jsonify(
            ok=True,
            message="子进程已结束或收到 TERM；监督循环将立刻按 user_config 重拉内核",
            previous_backend=be,
            next_backend=mgr.resolved_backend(),
        )

    return app


def _on_sigterm(signum: int, frame: object | None) -> None:  # noqa: ARG001
    # 主线程在 serve_forever；同线程调用 BaseServer.shutdown() 会死锁，须在其它线程触发 shutdown。
    global _httpd
    b = _backend
    if b is not None:
        b.on_shutdown_signal()
    h = _httpd
    if h is not None:

        def _shutdown_httpd() -> None:
            try:
                h.shutdown()
            except Exception:  # noqa: BLE001
                pass

        threading.Thread(target=_shutdown_httpd, daemon=True, name="mcs-http-shutdown").start()


def main() -> int:
    global _backend, _httpd
    root = _root()
    mgr = BackendManager(root)
    _backend = mgr
    signal.signal(signal.SIGTERM, _on_sigterm)
    signal.signal(signal.SIGINT, _on_sigterm)

    sup = threading.Thread(target=mgr.supervisor_loop, daemon=True, name="mcs-supervisor")
    sup.start()

    host, port = read_mcs_api_bind(root)

    app = _make_flask_app(mgr)
    _httpd = make_server(host, port, app, threaded=True)
    print(
        f"mcs_manager: Flask 控制 API http://{host}:{port}/ "
        f"(GET /kernel/status | POST /kernel/reload | POST /kernel/sync_meta)",
        file=sys.stderr,
    )
    try:
        _httpd.serve_forever()
    finally:
        mgr.shutdown.set()
        proc, _ = mgr.get_child()
        if proc is not None and proc.poll() is None:
            BackendManager.terminate_process(proc)
        try:
            _httpd.server_close()
        except Exception:  # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
