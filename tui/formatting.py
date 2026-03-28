"""Display helpers for overview, tables, and sparklines."""

from __future__ import annotations


def _fmt_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024.0:
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"


def _fmt_rate(bps: float) -> str:
    return _fmt_bytes(bps) + "/s"


def _truncate(text: str, max_len: int) -> str:
    if max_len <= 0:
        return ""
    if len(text) <= max_len:
        return text
    if max_len <= 3:
        return text[:max_len]
    return text[: max_len - 3] + "..."


def _sparkline(values: list[float], width: int = 48) -> str:
    if not values:
        return "—"
    blocks = "▁▂▃▄▅▆▇█"
    chunk = max(1, len(values) // width)
    samples = [sum(values[i : i + chunk]) / chunk for i in range(0, len(values), chunk)][-width:]
    if not samples:
        return "—"
    lo, hi = min(samples), max(samples)
    if hi <= lo:
        return blocks[4] * len(samples)
    return "".join(blocks[int((v - lo) / (hi - lo) * 7.999)] for v in samples)
