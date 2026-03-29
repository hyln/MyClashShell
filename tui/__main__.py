"""Backward-compatible entry: ``PYTHONPATH=<repo> python -m tui`` → ``scripts.tui``."""

from __future__ import annotations


def main() -> None:
    from scripts.tui.__main__ import main as _run

    _run()


if __name__ == "__main__":
    main()
