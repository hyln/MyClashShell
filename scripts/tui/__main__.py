"""Run: PYTHONPATH=<repo_root> python -m scripts.tui [optional_proxy_group]"""

from __future__ import annotations

import sys


def main() -> None:
    try:
        from textual.app import App  # noqa: F401
    except ImportError:
        print(
            "Textual is required. Install with:\n"
            "  ${MYCLASH_ROOT_PWD}/venv/bin/pip install textual",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        from ruamel.yaml import YAML  # noqa: F401
    except ImportError:
        print(
            "ruamel.yaml is required. Install with:\n"
            "  ${MYCLASH_ROOT_PWD}/venv/bin/pip install ruamel.yaml",
            file=sys.stderr,
        )
        sys.exit(1)

    from .app import main as run_app

    run_app()


if __name__ == "__main__":
    main()
