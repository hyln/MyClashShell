"""Master–Slave install hints (paths only; no Textual)."""

from __future__ import annotations

from pathlib import Path

from scripts.lib.paths import GITHUB_RAW_SLAVE_BOOTSTRAP_MAIN, slave_bootstrap_script


def slave_install_hint_lines(
    *,
    host: str,
    clash_http_port: int,
    serve_port: int,
    repo_root: str,
) -> list[str]:
    script = slave_bootstrap_script(Path(repo_root))
    return [
        f"Local proxy: http://{host}:{clash_http_port}\n",
        "Temporary export (current shell):\n",
        f"  export http_proxy=http://{host}:{clash_http_port}\n",
        f"  export https_proxy=http://{host}:{clash_http_port}\n\n",
        "HTTP install from this host (run myclash share serve [port] here first; default 8765):\n",
        f"  curl -fsSL http://{host}:{serve_port}/slave_bootstrap.sh "
        f"| sudo bash -s -- {host} {clash_http_port}\n\n",
        "Local script install (copy slave_bootstrap.sh to the slave via scp or USB):\n",
        f"  sudo bash {script} {host} {clash_http_port}\n\n",
        "If published to Git, on the slave run:\n",
        f"  curl -fsSL {GITHUB_RAW_SLAVE_BOOTSTRAP_MAIN} "
        f"| sudo bash -s -- {host} {clash_http_port}\n",
    ]
