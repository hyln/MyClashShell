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


def _sparkline(values: list[float], width: int = 48, *, stretch: int = 1) -> str:
    """块状速率曲线；stretch>1 时每个采样列重复字符，便于在终端里显得更「粗」。"""
    if not values:
        return "—"
    blocks = "▁▂▃▄▅▆▇█"
    chunk = max(1, len(values) // width)
    samples = [sum(values[i : i + chunk]) / chunk for i in range(0, len(values), chunk)][-width:]
    if not samples:
        return "—"
    lo, hi = min(samples), max(samples)
    if hi <= lo:
        core = blocks[4] * len(samples)
    else:
        core = "".join(blocks[int((v - lo) / (hi - lo) * 7.999)] for v in samples)
    if stretch <= 1:
        return core
    return "".join(c * stretch for c in core)


def _overview_sparkline_columns(term_width: int, reserve: int = 10, stretch: int = 2) -> tuple[int, int]:
    """返回 (sparkline 采样列数, stretch)。总显示宽约 sample_cols * stretch。"""
    tw = max(40, term_width)
    visual = max(48, min(tw - reserve, 160))
    sample_cols = max(32, visual // max(1, stretch))
    return sample_cols, stretch
