"""运行: PYTHONPATH=<repo> python3 -m scripts.tui_v2ray"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_repo = Path(__file__).resolve().parents[2]
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))


def main() -> None:
    raw = os.environ.get("MYCLASH_ROOT_PWD", "").strip()
    if not raw:
        print("tui_v2ray: 请设置 MYCLASH_ROOT_PWD", file=sys.stderr)
        sys.exit(2)
    root = Path(raw).resolve()
    try:
        from textual.app import App  # noqa: F401
    except ImportError:
        print(
            "Textual 未安装。请执行: ${MYCLASH_ROOT_PWD}/venv/bin/pip install textual",
            file=sys.stderr,
        )
        sys.exit(1)
    from scripts.tui_v2ray.app import V2rayPickerApp

    V2rayPickerApp(root=root).run()


if __name__ == "__main__":
    main()
