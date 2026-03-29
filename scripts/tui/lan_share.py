from __future__ import annotations

import gzip
import json
import os
import random
import socket
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Callable

from .lan_constants import (
    ANNOUNCE_GLOB,
    LAN_PROTO_VERSION,
    announce_key,
    config_query_key,
)


def zenoh_available() -> bool:
    try:
        import zenoh  as _

        return True
    except ImportError:
        return False


def pick_lan_host() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.3)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def slave_http_serve_port() -> int:
    """Slave 脚本 HTTP 服务端口（与 myclash share serve 默认一致）。"""
    try:
        return int(os.environ.get("MYCLASH_SLAVE_SERVE_PORT", "8765"))
    except ValueError:
        return 8765


def random_pin3() -> str:
    return f"{random.randint(0, 999):03d}"


@dataclass
class LanPeer:
    node_id: str
    role: str
    host: str
    http_port: int
    name: str
    last_seen: float = field(default_factory=time.monotonic)


class LanShareHub:
    def __init__(
        self,
        *,
        node_id: str,
        get_http_port: Callable[[], int],
        get_display_name: Callable[[], str],
        get_pin: Callable[[], str],
        config_yaml_path: str,
        on_peers: Callable[[dict[str, LanPeer]], None],
        offer_config: bool,
    ) -> None:
        self.node_id = node_id
        self._get_http_port = get_http_port
        self._get_display_name = get_display_name
        self._get_pin = get_pin
        self._config_path = config_yaml_path
        self._on_peers = on_peers
        self._offer_config = offer_config
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._session = None
        self._peers: dict[str, LanPeer] = {}
        self._peers_lock = threading.Lock()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="myclash-zenoh", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        sess = self._session
        if sess is not None:
            try:
                sess.close()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None
        self._session = None
        with self._peers_lock:
            self._peers.clear()

    def snapshot_peers(self) -> dict[str, LanPeer]:
        with self._peers_lock:
            return dict(self._peers)

    def _emit_peers(self) -> None:
        with self._peers_lock:
            snap = dict(self._peers)
        try:
            self._on_peers(snap)
        except Exception:
            pass

    def _on_sample(self, sample: Any) -> None:
        try:
            raw = sample.payload.to_string()
            data = json.loads(raw)
        except Exception:
            return
        if int(data.get("proto", 0)) != LAN_PROTO_VERSION:
            return
        nid = str(data.get("node_id") or "")
        if not nid:
            return
        host = str(data.get("host") or "")
        role = str(data.get("role") or "master")
        try:
            port = int(data.get("http_port") or 7890)
        except (TypeError, ValueError):
            port = 7890
        name = str(data.get("name") or nid)
        with self._peers_lock:
            self._peers[nid] = LanPeer(
                node_id=nid,
                role=role,
                host=host,
                http_port=port,
                name=name,
                last_seen=time.monotonic(),
            )
        self._emit_peers()

    def _handle_query(self, query: Any) -> None:
        import zenoh


        key_full = config_query_key(self.node_id)
        try:
            params = getattr(query.selector, "parameters", None) or {}
            pin = str(params.get("pin", "") or "")
        except Exception:
            pin = ""
        if pin != self._get_pin():
            query.reply_err("PIN mismatch or missing")
            return
        try:
            with open(self._config_path, "rb") as f:
                raw = f.read()
        except OSError as exc:
            query.reply_err(f"config read failed: {exc}")
            return
        blob = gzip.compress(raw, compresslevel=6)
        query.reply(key_full, zenoh.ZBytes(blob))

    def _run(self) -> None:
        import zenoh


        cfg = zenoh.Config()
        try:
            self._session = zenoh.open(cfg)
        except Exception:
            self._session = None
            return
        session = self._session
        try:
            session.declare_subscriber(ANNOUNCE_GLOB, self._on_sample)
            pub = session.declare_publisher(announce_key(self.node_id))

            def announce_loop() -> None:
                while not self._stop.is_set():
                    time.sleep(2.0)
                    if self._stop.is_set():
                        break
                    try:
                        body = {
                            "proto": LAN_PROTO_VERSION,
                          "role": "master",
                        "node_id": self.node_id,
                        "host": pick_lan_host(),
                        "http_port": self._get_http_port(),
                        "name": self._get_display_name(),
                        }
                        pub.put(json.dumps(body))
                    except Exception:
                        pass

            threading.Thread(target=announce_loop, daemon=True).start()

            if self._offer_config:
                qy = session.declare_queryable(config_query_key(self.node_id))
                for query in qy:
                    if self._stop.is_set():
                        break
                    try:
                        self._handle_query(query)
                    except Exception:
                        try:
                            query.reply_err("handler error")
                        except Exception:
                            pass
            else:
                while not self._stop.wait(1.0):
                    pass
        finally:
            try:
                session.close()
            except Exception:
                pass
            self._session = None


def fetch_remote_config(remote_node_id: str, pin: str, timeout: float = 15.0) -> bytes:
    import zenoh

    cfg = zenoh.Config()
    sel = f"{config_query_key(remote_node_id)}?pin={urllib.parse.quote(pin, safe='')}&proto={LAN_PROTO_VERSION}"
    with zenoh.open(cfg) as session:
        try:
            replies = session.get(sel, timeout=timeout)
        except TypeError:
            replies = session.get(sel)
        for reply in replies:
            if reply.ok:
                pl = reply.ok.payload
                blob = pl.to_bytes() if hasattr(pl, "to_bytes") else bytes(pl)
                return gzip.decompress(blob)
            err = getattr(reply.err, "payload", None)
            msg = err.to_string() if err is not None else "error"
            raise RuntimeError(msg)
    raise RuntimeError("no reply from peer")
