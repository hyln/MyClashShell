#!/usr/bin/env python3
"""HTTP 只读提供 shell/slave 下脚本，供局域网 Slave 用 curl 下载安装。

仅暴露固定路径，无目录列表。默认绑定 0.0.0.0，端口由 --port 或环境变量 MYCLASH_SLAVE_SERVE_PORT 指定。
"""

from __future__ import annotations

import argparse
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Keep in sync with scripts.lib.paths.SLAVE_SCRIPT_RELPATHS (no package import: this file is run as a script).
_SLAVE_RELS = (
    "shell/slave/slave_bootstrap.sh",
    "shell/slave/connect_other_proxy.sh",
)

_FILES: dict[str, Path] = {}


def _root() -> Path:
    r = os.environ.get("MYCLASH_ROOT_PWD", "").strip()
    if not r:
        print("MYCLASH_ROOT_PWD is not set", file=sys.stderr)
        sys.exit(1)
    return Path(r).resolve()


def _build_files(root: Path) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for rel in _SLAVE_RELS:
        p = (root / rel).resolve()
        if not str(p).startswith(str(root)) or not p.is_file():
            print(f"Missing or invalid: {rel}", file=sys.stderr)
            sys.exit(1)
        name = Path(rel).name
        out["/" + name] = p
    return out


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        if path not in _FILES:
            self.send_error(404, "Not found")
            return
        fpath = _FILES[path]
        try:
            data = fpath.read_bytes()
        except OSError as exc:
            self.send_error(500, str(exc))
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), fmt % args))


def main() -> None:
    global _FILES
    root = _root()
    _FILES = _build_files(root)

    ap = argparse.ArgumentParser(description="Serve slave install scripts over HTTP")
    ap.add_argument(
        "--bind",
        default=os.environ.get("MYCLASH_SLAVE_SERVE_BIND", "0.0.0.0"),
        help="Listen address (default 0.0.0.0)",
    )
    ap.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("MYCLASH_SLAVE_SERVE_PORT", "8765")),
        help="Listen port (default 8765)",
    )
    args = ap.parse_args()

    httpd = ThreadingHTTPServer((args.bind, args.port), Handler)
    print(
        f"slave_http_server: http://{args.bind}:{args.port}/  "
        f"slave_bootstrap.sh connect_other_proxy.sh (MYCLASH_ROOT_PWD={root})",
        flush=True,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
