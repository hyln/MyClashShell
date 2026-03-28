"""Run: PYTHONPATH=<repo_root> python -m tui [optional_proxy_group]"""

from __future__ import annotations

import sys

try:
    from textual.app import App  # noqa: F401
except ImportError:
    print(
        "Textual is required. Install with:\n"
        "  ${MYCLASH_ROOT_PWD}/venv/bin/pip install textual",
        file=sys.stderr,
    )
    sys.exit(1)

from tui.app import main

main()
