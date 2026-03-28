#!/usr/bin/env python3
"""Supervise Clash core as a child process (run as systemd's main process)."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def _root() -> Path:
    raw = os.environ.get("MYCLASH_ROOT_PWD")
    if raw:
        return Path(raw).resolve()
    return Path(__file__).resolve().parents[2]


def _terminate(proc: subprocess.Popen, grace: float = 25.0) -> None:
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


def main() -> None:
    root = _root()
    clash = root / "clash" / "clash"
    if not clash.is_file():
        print(f"clash binary not found: {clash}", file=sys.stderr)
        sys.exit(1)

    cmd = [str(clash), "-d", "clash/configs"]
    proc = subprocess.Popen(cmd, cwd=str(root))

    def on_signal(signum: int, frame: object | None) -> None:  # noqa: ARG001
        _terminate(proc)

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    rc = proc.wait()
    sys.exit(rc if rc is not None else 1)


if __name__ == "__main__":
    main()
