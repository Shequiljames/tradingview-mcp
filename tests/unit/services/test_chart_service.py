"""Chart rendering service tests.

Mocks the OHLCV fetcher so tests run offline and deterministically —
only the rendering/parameter logic in chart_service is under test here.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from tradingview_mcp.core.services.chart_service import (
    _parse_indicators,
    render_price_chart,
)


def _make_candles(n: int = 80) -> list[dict]:
    candles = []
    price = 100.0
    for i in range(n):
        o = price
        c = price + (1 if i % 3 else -1) * 0.5
        h = max(o, c) + 0.3
        l = min(o, c) - 0.3
        candles.append({
            "date": f"2026-01-{(i % 28) + 1:02d}",
            "open": round(o, 4), "high": round(h, 4),
            "low": round(l, 4), "close": round(c, 4),
            "volume": 1000 + i * 10,
        })
        price = c
    return candles


class TestParseIndicators:
    def test_defaults_when_none(self):
        assert _parse_indicators(None) == ["sma20", "sma50"]

    def test_defaults_when_empty(self):
        assert _parse_indicators([]) == ["sma20", "sma50"]

    def test_filters_unknown_and_dedupes(self):
        assert _parse_indicators(["sma20", "bogus", "SMA20", "rsi"]) == ["sma20", "rsi"]


class TestRenderPriceChart:
    @patch("tradingview_mcp.core.services.chart_service._fetch_ohlcv")
    def test_candlestick_with_overlays_returns_png(self, mock_fetch):
        mock_fetch.return_value = _make_candles(80)
        img = render_price_chart(
            "AAPL", period="6mo", interval="1d",
            chart_type="candlestick", theme="dark",
            indicators=["sma20", "sma50", "bollinger", "rsi"],
            show_volume=True,
        )
        assert isinstance(img.data, (bytes, bytearray))
        assert img.data[:8] == b"\x89PNG\r\n\x1a\n"
        assert len(img.data) > 1000

    @patch("tradingview_mcp.core.services.chart_service._fetch_ohlcv")
    def test_line_chart_light_theme_no_volume(self, mock_fetch):
        mock_fetch.return_value = _make_candles(40)
        img = render_price_chart(
            "SPY", chart_type="line", theme="light",
            indicators=None, show_volume=False,
        )
        assert img.data[:8] == b"\x89PNG\r\n\x1a\n"

    @patch("tradingview_mcp.core.services.chart_service._fetch_ohlcv")
    def test_unknown_theme_and_chart_type_fall_back_to_defaults(self, mock_fetch):
        mock_fetch.return_value = _make_candles(40)
        img = render_price_chart("AAPL", chart_type="bogus", theme="bogus")
        assert img.data[:8] == b"\x89PNG\r\n\x1a\n"

    @patch("tradingview_mcp.core.services.chart_service._fetch_ohlcv")
    def test_insufficient_data_raises(self, mock_fetch):
        mock_fetch.return_value = _make_candles(1)
        with pytest.raises(ValueError):
            render_price_chart("AAPL")
