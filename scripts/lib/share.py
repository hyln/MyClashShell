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
        f"本机代理: http://{host}:{clash_http_port}\n",
        "临时 export（当前 shell）：\n",
        f"  export http_proxy=http://{host}:{clash_http_port}\n",
        f"  export https_proxy=http://{host}:{clash_http_port}\n\n",
        "本机 HTTP 提供脚本（先在本机执行 myclash share serve [端口]，默认 8765）：\n",
        f"  curl -fsSL http://{host}:{serve_port}/slave_bootstrap.sh "
        f"| sudo bash -s -- {host} {clash_http_port}\n\n",
        "本地脚本安装（需 scp 或 U 盘拷贝脚本到 Slave）：\n",
        f"  sudo bash {script} {host} {clash_http_port}\n\n",
        "若已发布到 Git，可在 Slave 上：\n",
        f"  curl -fsSL {GITHUB_RAW_SLAVE_BOOTSTRAP_MAIN} "
        f"| sudo bash -s -- {host} {clash_http_port}\n",
    ]
