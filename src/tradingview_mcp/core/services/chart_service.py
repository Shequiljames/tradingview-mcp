"""
Chart Rendering Service — matplotlib-based candlestick/line/area charts
styled after TradingView's dark and light themes.

Reuses the existing OHLCV fetcher and pure-Python indicator math so no
pandas/numpy dependency is introduced for data handling — matplotlib is
the only new dependency, used purely for drawing.
"""
from __future__ import annotations

import io
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from mcp.server.fastmcp import Image

from tradingview_mcp.core.services.backtest_service import _fetch_ohlcv
from tradingview_mcp.core.services.indicators_calc import (
    calc_sma, calc_ema, calc_bollinger, calc_rsi,
)

_THEMES = {
    "dark": {
        "bg": "#131722",
        "grid": "#2a2e39",
        "text": "#d1d4dc",
        "up": "#26a69a",
        "down": "#ef5350",
        "volume_up": "#26a69a80",
        "volume_down": "#ef535080",
        "band": "#787b86",
    },
    "light": {
        "bg": "#ffffff",
        "grid": "#e0e3eb",
        "text": "#131722",
        "up": "#089981",
        "down": "#f23645",
        "volume_up": "#08998180",
        "volume_down": "#f2364580",
        "band": "#9598a1",
    },
}

_VALID_CHART_TYPES = {"candlestick", "line", "area"}
_VALID_INDICATORS = {"sma20", "sma50", "sma200", "ema20", "ema50", "bollinger", "rsi"}
_OVERLAY_COLORS = {
    "sma20": "#2962ff",
    "sma50": "#ff6d00",
    "sma200": "#9c27b0",
    "ema20": "#00bcd4",
    "ema50": "#ffca28",
}


def _parse_indicators(indicators: Optional[list[str]]) -> list[str]:
    if not indicators:
        return ["sma20", "sma50"]
    seen, out = set(), []
    for raw in indicators:
        key = str(raw).strip().lower()
        if key in _VALID_INDICATORS and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def render_price_chart(
    symbol: str,
    period: str = "6mo",
    interval: str = "1d",
    chart_type: str = "candlestick",
    theme: str = "dark",
    indicators: Optional[list[str]] = None,
    show_volume: bool = True,
) -> Image:
    palette = _THEMES.get(theme.strip().lower(), _THEMES["dark"])
    chart_type = chart_type.strip().lower()
    if chart_type not in _VALID_CHART_TYPES:
        chart_type = "candlestick"

    candles = _fetch_ohlcv(symbol, period, interval)
    if len(candles) < 2:
        raise ValueError(f"Not enough data for '{symbol}' to render a chart.")

    closes = [c["close"] for c in candles]
    n = len(candles)
    x = list(range(n))

    active = _parse_indicators(indicators)
    show_rsi = "rsi" in active
    overlays = [i for i in active if i != "rsi"]

    rows = 1 + (1 if show_volume else 0) + (1 if show_rsi else 0)
    height_ratios = [3] + ([1] if show_volume else []) + ([1] if show_rsi else [])

    fig, axes = plt.subplots(
        rows, 1,
        figsize=(11, 6.5 + 1.4 * (rows - 1)),
        sharex=True,
        gridspec_kw={"height_ratios": height_ratios, "hspace": 0.08},
        facecolor=palette["bg"],
        layout="constrained",
    )
    axes = [axes] if rows == 1 else list(axes)

    price_ax = axes[0]
    idx = 1
    volume_ax = axes[idx] if show_volume else None
    if show_volume:
        idx += 1
    rsi_ax = axes[idx] if show_rsi else None

    for ax in axes:
        ax.set_facecolor(palette["bg"])
        ax.grid(True, color=palette["grid"], linewidth=0.6, alpha=0.5)
        ax.tick_params(colors=palette["text"], labelsize=8)
        for spine in ax.spines.values():
            spine.set_color(palette["grid"])

    # ── Price panel ─────────────────────────────────────────────────────
    if chart_type == "candlestick":
        width = 0.6
        for i, c in enumerate(candles):
            color = palette["up"] if c["close"] >= c["open"] else palette["down"]
            price_ax.plot([i, i], [c["low"], c["high"]], color=color, linewidth=0.8, zorder=2)
            lower = min(c["open"], c["close"])
            height = abs(c["close"] - c["open"]) or 1e-9
            price_ax.add_patch(Rectangle(
                (i - width / 2, lower), width, height,
                facecolor=color, edgecolor=color, zorder=3,
            ))
    elif chart_type == "area":
        price_ax.plot(x, closes, color=palette["up"], linewidth=1.4, zorder=3)
        price_ax.fill_between(x, closes, min(closes), color=palette["up"], alpha=0.15, zorder=2)
    else:  # line
        price_ax.plot(x, closes, color=palette["up"], linewidth=1.4, zorder=3)

    for ind in overlays:
        if ind == "bollinger":
            bb = calc_bollinger(closes, 20, 2.0)
            price_ax.plot(x, bb["upper"], color=palette["band"], linewidth=0.9, linestyle="--", zorder=4)
            price_ax.plot(x, bb["lower"], color=palette["band"], linewidth=0.9, linestyle="--", zorder=4)
            price_ax.plot(x, bb["middle"], color=palette["band"], linewidth=0.9, zorder=4, label="BB(20,2)")
            continue
        series = {
            "sma20": lambda: calc_sma(closes, 20),
            "sma50": lambda: calc_sma(closes, 50),
            "sma200": lambda: calc_sma(closes, 200),
            "ema20": lambda: calc_ema(closes, 20),
            "ema50": lambda: calc_ema(closes, 50),
        }[ind]()
        price_ax.plot(x, series, color=_OVERLAY_COLORS[ind], linewidth=1.2, label=ind.upper(), zorder=4)

    if overlays:
        price_ax.legend(loc="upper left", fontsize=7, facecolor=palette["bg"],
                         edgecolor=palette["grid"], labelcolor=palette["text"])

    last = candles[-1]
    change_pct = round((last["close"] - candles[0]["close"]) / candles[0]["close"] * 100, 2)
    price_ax.set_title(
        f"{symbol.upper()}  ·  {interval}  ·  {last['close']:.4f}  ({change_pct:+.2f}%)",
        color=palette["text"], fontsize=11, loc="left", pad=8,
    )
    price_ax.set_ylabel("Price", color=palette["text"], fontsize=8)

    # ── Volume panel ────────────────────────────────────────────────────
    if show_volume:
        for i, c in enumerate(candles):
            color = palette["volume_up"] if c["close"] >= c["open"] else palette["volume_down"]
            volume_ax.bar(i, c["volume"], color=color, width=0.6)
        volume_ax.set_ylabel("Volume", color=palette["text"], fontsize=8)

    # ── RSI panel ───────────────────────────────────────────────────────
    if show_rsi:
        rsi = calc_rsi(closes, 14)
        rsi_ax.plot(x, rsi, color="#7e57c2", linewidth=1.1)
        rsi_ax.axhline(70, color=palette["down"], linewidth=0.7, linestyle="--", alpha=0.6)
        rsi_ax.axhline(30, color=palette["up"], linewidth=0.7, linestyle="--", alpha=0.6)
        rsi_ax.set_ylim(0, 100)
        rsi_ax.set_ylabel("RSI", color=palette["text"], fontsize=8)

    # ── X-axis date labels ──────────────────────────────────────────────
    tick_count = min(8, n)
    tick_idx = [int(i * (n - 1) / max(1, tick_count - 1)) for i in range(tick_count)]
    axes[-1].set_xticks(tick_idx)
    axes[-1].set_xticklabels([candles[i]["date"][:10] for i in tick_idx], rotation=30, ha="right", fontsize=7)
    price_ax.set_xlim(-1, n)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, facecolor=palette["bg"])
    plt.close(fig)
    buf.seek(0)
    return Image(data=buf.getvalue(), format="png")
