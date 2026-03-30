from __future__ import annotations

import gzip
import ipaddress
import json
import os
import random
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

from .lan_constants import (
    LAN_CONFIG_HTTP_PATH,
    LAN_MULTICAST_ADDR,
    LAN_PROTO_VERSION,
    lan_config_http_port,
    lan_udp_port,
)


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


def list_lan_ipv4_with_prefix() -> list[tuple[str, int]]:
    """(address, prefixlen) for global IPv4, non-loopback. Fallback single pick_lan_host/32."""
    raw = os.environ.get("MYCLASH_LAN_ADDRS", "").strip()
    if raw:
        out: list[tuple[str, int]] = []
        for part in raw.split(","):
            p = part.strip()
            if not p:
                continue
            if "/" in p:
                try:
                    iface = ipaddress.IPv4Interface(p)
                    out.append((str(iface.ip), int(iface.network.prefixlen)))
                except ValueError:
                    continue
            else:
                out.append((p, 32))
        if out:
            return out
    try:
        proc = subprocess.run(
            ["ip", "-j", "addr", "show"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            out = []
            for iface in json.loads(proc.stdout):
                for ainfo in iface.get("addr_info", []):
                    if ainfo.get("family") != "inet":
                        continue
                    sc = ainfo.get("scope")
                    if sc is not None and not str(sc).startswith("global"):
                        continue
                    ip = ainfo.get("local")
                    plen = ainfo.get("prefixlen")
                    if not ip or plen is None or ip.startswith("127."):
                        continue
                    out.append((ip, int(plen)))
            if out:
                seen: set[str] = set()
                dedup: list[tuple[str, int]] = []
                for t in out:
                    if t[0] not in seen:
                        seen.add(t[0])
                        dedup.append(t)
                return dedup
    except Exception:
        pass
    h = pick_lan_host()
    return [(h, 32)] if h and h != "127.0.0.1" else [("127.0.0.1", 32)]


def slave_http_serve_port() -> int:
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
    config_port: int
    name: str
    last_seen: float = field(default_factory=time.monotonic)


def _ip_add_membership(sock: socket.socket, mcast: str, if_addr: str) -> None:
    mreq = socket.inet_aton(mcast) + socket.inet_aton(if_addr)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)


def _ip_drop_membership(sock: socket.socket, mcast: str, if_addr: str) -> None:
    mreq = socket.inet_aton(mcast) + socket.inet_aton(if_addr)
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_DROP_MEMBERSHIP, mreq)
    except OSError:
        pass


def _multicast_send(sock: socket.socket, mcast: str, port: int, payload: bytes, if_addr: str) -> None:
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(if_addr))
    sock.sendto(payload, (mcast, port))


def _broadcast_send(sock: socket.socket, port: int, payload: bytes, bcast: str, if_addr: str) -> None:
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(if_addr))
    except OSError:
        pass
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        sock.sendto(payload, (bcast, port))
    except OSError:
        pass


def fetch_remote_config(
    host: str,
    config_port: int,
    pin: str,
    *,
    timeout: float = 15.0,
) -> bytes:
    q = urllib.parse.urlencode({"pin": pin, "proto": str(LAN_PROTO_VERSION)})
    url = f"http://{host}:{config_port}{LAN_CONFIG_HTTP_PATH}?{q}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        raise RuntimeError(body.strip() or e.reason or str(e.code)) from e
    except urllib.error.URLError as e:
        raise RuntimeError(str(e.reason)) from e
    try:
        return gzip.decompress(data)
    except OSError as exc:
        raise RuntimeError(f"invalid gzip response: {exc}") from exc


class LanShareHub:
    def __init__(
        self,
        *,
        node_id: str,
        get_http_port: Callable[[], int],
        get_config_port: Callable[[], int],
        get_display_name: Callable[[], str],
        get_pin: Callable[[], str],
        config_yaml_path: str,
        on_peers: Callable[[dict[str, LanPeer]], None],
        offer_config: bool,
    ) -> None:
        self.node_id = node_id
        self._get_http_port = get_http_port
        self._get_config_port = get_config_port
        self._get_display_name = get_display_name
        self._get_pin = get_pin
        self._config_path = config_yaml_path
        self._on_peers = on_peers
        self._offer_config = offer_config
        self._stop = threading.Event()
        self._udp_thread: threading.Thread | None = None
        self._udp_sock: socket.socket | None = None
        self._memberships: list[tuple[str, str]] = []
        self._httpd: ThreadingHTTPServer | None = None
        self._http_thread: threading.Thread | None = None
        self._peers: dict[str, LanPeer] = {}
        self._peers_lock = threading.Lock()

    def start(self) -> None:
        if self._udp_thread and self._udp_thread.is_alive():
            return
        self._stop.clear()
        self._udp_thread = threading.Thread(target=self._run_udp, name="myclash-lan-udp", daemon=True)
        self._udp_thread.start()
        if self._offer_config:
            self._http_thread = threading.Thread(target=self._run_http, name="myclash-lan-http", daemon=True)
            self._http_thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._httpd:
            try:
                self._httpd.shutdown()
            except Exception:
                pass
        if self._http_thread:
            self._http_thread.join(timeout=4.0)
            self._http_thread = None
        if self._httpd:
            try:
                self._httpd.server_close()
            except Exception:
                pass
            self._httpd = None
        if self._udp_thread:
            self._udp_thread.join(timeout=4.0)
            self._udp_thread = None
        self._memberships.clear()
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

    def _apply_announce(self, data: dict, _sender_ip: str) -> None:
        try:
            if int(data.get("proto", 0)) != LAN_PROTO_VERSION:
                return
        except (TypeError, ValueError):
            return
        nid = str(data.get("node_id") or "")
        if not nid:
            return
        host = str(data.get("host") or "") or _sender_ip
        role = str(data.get("role") or "master")
        try:
            port = int(data.get("http_port") or 7890)
        except (TypeError, ValueError):
            port = 7890
        try:
            cport = int(data.get("config_port") or lan_config_http_port())
        except (TypeError, ValueError):
            cport = lan_config_http_port()
        name = str(data.get("name") or nid)
        with self._peers_lock:
            self._peers[nid] = LanPeer(
                node_id=nid,
                role=role,
                host=host,
                http_port=port,
                config_port=cport,
                name=name,
                last_seen=time.monotonic(),
            )
        self._emit_peers()

    def _run_udp(self) -> None:
        port = lan_udp_port()
        mcast = LAN_MULTICAST_ADDR
        pairs = list_lan_ipv4_with_prefix()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("", port))
        except OSError:
            sock.close()
            return
        self._udp_sock = sock
        for ip, _plen in pairs:
            if ip.startswith("127."):
                continue
            try:
                _ip_add_membership(sock, mcast, ip)
                self._memberships.append((mcast, ip))
            except OSError:
                pass

        def announce_once() -> None:
            for ip, plen in pairs:
                if ip.startswith("127."):
                    continue
                try:
                    body = {
                        "proto": LAN_PROTO_VERSION,
                        "role": "master",
                        "node_id": self.node_id,
                        "host": ip,
                        "http_port": self._get_http_port(),
                        "config_port": self._get_config_port(),
                        "name": self._get_display_name(),
                    }
                    payload = json.dumps(body).encode("utf-8")
                    _multicast_send(sock, mcast, port, payload, ip)
                    try:
                        net = ipaddress.IPv4Network(f"{ip}/{plen}", strict=False)
                        bcast = str(net.broadcast_address)
                        if bcast != ip:
                            _broadcast_send(sock, port, payload, bcast, ip)
                    except ValueError:
                        pass
                except OSError:
                    pass

        next_announce = time.monotonic()
        sock.settimeout(1.0)
        while not self._stop.is_set():
            now = time.monotonic()
            if now >= next_announce:
                announce_once()
                next_announce = now + 2.0
            try:
                data, addr = sock.recvfrom(65535)
            except TimeoutError:
                continue
            except OSError:
                break
            try:
                obj = json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if not isinstance(obj, dict):
                continue
            self._apply_announce(obj, addr[0] if addr else "")

        for mcast_a, if_ip in self._memberships:
            _ip_drop_membership(sock, mcast_a, if_ip)
        self._memberships.clear()
        try:
            sock.close()
        except Exception:
            pass
        if self._udp_sock is sock:
            self._udp_sock = None

    def _run_http(self) -> None:
        pin_fn = self._get_pin
        path = self._config_path

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, _format: str, *_args: object) -> None:
                return

            def do_GET(self) -> None:
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path != LAN_CONFIG_HTTP_PATH:
                    self.send_error(404, "Not found")
                    return
                qs = urllib.parse.parse_qs(parsed.query)
                pin = (qs.get("pin") or [""])[0]
                if pin != pin_fn():
                    self.send_error(403, "PIN mismatch")
                    return
                try:
                    raw = open(path, "rb").read()
                except OSError as exc:
                    self.send_error(500, str(exc))
                    return
                blob = gzip.compress(raw, compresslevel=6)
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(blob)))
                self.end_headers()
                self.wfile.write(blob)

        port = self._get_config_port()
        try:
            httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
            httpd.allow_reuse_address = True
        except OSError:
            return
        self._httpd = httpd
        try:
            httpd.serve_forever(poll_interval=0.5)
        except Exception:
            pass
        try:
            httpd.server_close()
        except Exception:
            pass
