"""
APEX LIQUIDITY AI — Market Data Service
Coleta de dados multi-fonte com fallback automático.
Fonte primária: Polygon.io | Fallback: Alpha Vantage, Binance, Yahoo
"""
import asyncio
import httpx
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional
from loguru import logger

from config.api_keys import (
    POLYGON_API_KEY, ALPHA_VANTAGE_API_KEY,
    BINANCE_API_KEY, BINANCE_SECRET_KEY, FINNHUB_API_KEY
)


class MarketDataService:
    """Serviço unificado de coleta de dados com fallback em cascata."""

    def __init__(self):
        self._cache: dict = {}
        self._cache_ttl: dict = {}
        self.CACHE_SECONDS = 10  # ticks: 10s

    def _is_cached(self, key: str) -> bool:
        if key not in self._cache_ttl:
            return False
        return (datetime.utcnow() - self._cache_ttl[key]).seconds < self.CACHE_SECONDS

    async def get_price(self, symbol: str) -> Optional[float]:
        """Retorna preço atual do ativo com fallback."""
        cache_key = f"price_{symbol}"
        if self._is_cached(cache_key):
            return self._cache[cache_key]

        # Cripto via Binance
        if "BTC" in symbol or "ETH" in symbol:
            price = await self._binance_price(symbol)
            if price:
                self._cache[cache_key] = price
                self._cache_ttl[cache_key] = datetime.utcnow()
                return price

        # Forex/Índices via Polygon
        price = await self._polygon_price(symbol)
        if not price:
            price = await self._finnhub_price(symbol)
        if not price:
            price = await self._alpha_vantage_price(symbol)

        if price:
            self._cache[cache_key] = price
            self._cache_ttl[cache_key] = datetime.utcnow()
        return price

    async def get_candles(self, symbol: str, timeframe: str = "H1", limit: int = 200) -> Optional[pd.DataFrame]:
        """
        Retorna DataFrame com colunas: open, high, low, close, volume, timestamp
        """
        cache_key = f"candles_{symbol}_{timeframe}"
        if self._is_cached(cache_key):
            return self._cache[cache_key]

        df = None

        if "BTC" in symbol or "ETH" in symbol:
            df = await self._binance_candles(symbol, timeframe, limit)

        if df is None:
            df = await self._polygon_candles(symbol, timeframe, limit)
        if df is None:
            df = await self._alpha_vantage_candles(symbol, timeframe, limit)

        if df is not None and not df.empty:
            self._cache[cache_key] = df
            self._cache_ttl[cache_key] = datetime.utcnow()
            logger.debug(f"✅ Candles {symbol}/{timeframe}: {len(df)} barras")

        return df

    # ─── Polygon.io ──────────────────────────────────────────────

    async def _polygon_price(self, symbol: str) -> Optional[float]:
        if POLYGON_API_KEY == "COLE_AQUI":
            return self._mock_price(symbol)
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get(
                    f"https://api.polygon.io/v2/last/trade/{symbol}",
                    params={"apiKey": POLYGON_API_KEY}
                )
                if r.status_code == 200:
                    return r.json().get("results", {}).get("p")
        except Exception as e:
            logger.warning(f"Polygon price error {symbol}: {e}")
        return None

    async def _polygon_candles(self, symbol: str, timeframe: str, limit: int) -> Optional[pd.DataFrame]:
        if POLYGON_API_KEY == "COLE_AQUI":
            return self._mock_candles(symbol, limit)
        tf_map = {"M1": "minute", "M5": "5/minute", "M15": "15/minute", "H1": "hour", "H4": "4/hour", "D1": "day"}
        tf = tf_map.get(timeframe, "hour")
        to_date = datetime.utcnow().strftime("%Y-%m-%d")
        from_date = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(
                    f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/{tf}/{from_date}/{to_date}",
                    params={"adjusted": True, "sort": "asc", "limit": limit, "apiKey": POLYGON_API_KEY}
                )
                if r.status_code == 200 and r.json().get("results"):
                    data = r.json()["results"]
                    df = pd.DataFrame(data)
                    df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume", "t": "timestamp"})
                    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
                    return df[["timestamp", "open", "high", "low", "close", "volume"]].tail(limit)
        except Exception as e:
            logger.warning(f"Polygon candles error {symbol}: {e}")
        return None

    # ─── Binance ─────────────────────────────────────────────────

    async def _binance_price(self, symbol: str) -> Optional[float]:
        sym = symbol.replace("USDT", "") + "USDT"
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get("https://api.binance.com/api/v3/ticker/price", params={"symbol": sym})
                if r.status_code == 200:
                    return float(r.json()["price"])
        except Exception as e:
            logger.warning(f"Binance price error {symbol}: {e}")
        return None

    async def _binance_candles(self, symbol: str, timeframe: str, limit: int) -> Optional[pd.DataFrame]:
        sym = symbol.replace("USDT", "") + "USDT"
        tf_map = {"M1": "1m", "M5": "5m", "M15": "15m", "H1": "1h", "H4": "4h", "D1": "1d"}
        interval = tf_map.get(timeframe, "1h")
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(
                    "https://api.binance.com/api/v3/klines",
                    params={"symbol": sym, "interval": interval, "limit": limit}
                )
                if r.status_code == 200:
                    raw = r.json()
                    df = pd.DataFrame(raw, columns=["timestamp","open","high","low","close","volume","ct","qav","nt","tb","tqav","ig"])
                    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
                    for col in ["open","high","low","close","volume"]:
                        df[col] = df[col].astype(float)
                    return df[["timestamp","open","high","low","close","volume"]]
        except Exception as e:
            logger.warning(f"Binance candles error {symbol}: {e}")
        return None

    # ─── Finnhub ─────────────────────────────────────────────────

    async def _finnhub_price(self, symbol: str) -> Optional[float]:
        if FINNHUB_API_KEY == "COLE_AQUI":
            return None
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get(
                    "https://finnhub.io/api/v1/quote",
                    params={"symbol": symbol, "token": FINNHUB_API_KEY}
                )
                if r.status_code == 200:
                    return r.json().get("c")
        except Exception as e:
            logger.warning(f"Finnhub price error: {e}")
        return None

    # ─── Alpha Vantage ───────────────────────────────────────────

    async def _alpha_vantage_price(self, symbol: str) -> Optional[float]:
        if ALPHA_VANTAGE_API_KEY == "COLE_AQUI":
            return self._mock_price(symbol)
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(
                    "https://www.alphavantage.co/query",
                    params={"function": "FX_INTRADAY", "from_symbol": symbol[:3],
                            "to_symbol": symbol[3:], "interval": "1min",
                            "apikey": ALPHA_VANTAGE_API_KEY}
                )
                if r.status_code == 200:
                    data = r.json()
                    series = data.get("Time Series FX (1min)", {})
                    if series:
                        latest = list(series.values())[0]
                        return float(latest["4. close"])
        except Exception as e:
            logger.warning(f"AV price error: {e}")
        return None

    async def _alpha_vantage_candles(self, symbol: str, timeframe: str, limit: int) -> Optional[pd.DataFrame]:
        if ALPHA_VANTAGE_API_KEY == "COLE_AQUI":
            return self._mock_candles(symbol, limit)
        return None

    # ─── Mock data (quando APIs não configuradas) ─────────────────

    def _mock_price(self, symbol: str) -> float:
        base = {"EURUSD": 1.0850, "XAUUSD": 2050.0, "SP500": 5200.0,
                "NAS100": 18200.0, "US30": 39000.0, "BTCUSDT": 68000.0, "ETHUSDT": 3500.0}
        price = base.get(symbol, 1.0)
        return price * (1 + np.random.normal(0, 0.0001))

    def _mock_candles(self, symbol: str, limit: int) -> pd.DataFrame:
        """Gera candles sintéticos para testes quando API não configurada."""
        base = {"EURUSD": 1.085, "XAUUSD": 2050, "SP500": 5200,
                "NAS100": 18200, "US30": 39000, "BTCUSDT": 68000, "ETHUSDT": 3500}
        price = base.get(symbol, 1.0)
        dates = pd.date_range(end=datetime.utcnow(), periods=limit, freq="1h")
        prices = [price]
        for _ in range(limit - 1):
            prices.append(prices[-1] * (1 + np.random.normal(0, 0.002)))
        opens = prices
        closes = [p * (1 + np.random.normal(0, 0.001)) for p in prices]
        highs = [max(o, c) * (1 + abs(np.random.normal(0, 0.001))) for o, c in zip(opens, closes)]
        lows = [min(o, c) * (1 - abs(np.random.normal(0, 0.001))) for o, c in zip(opens, closes)]
        volumes = [abs(np.random.normal(50000, 20000)) for _ in range(limit)]
        return pd.DataFrame({"timestamp": dates, "open": opens, "high": highs,
                              "low": lows, "close": closes, "volume": volumes})

    async def get_session(self) -> str:
        """Detecta a sessão de mercado atual: ASIA, LONDON, NEW_YORK, OFF."""
        hour = datetime.utcnow().hour
        if 0 <= hour < 7:
            return "ASIA"
        elif 7 <= hour < 12:
            return "LONDON"
        elif 12 <= hour < 21:
            return "NEW_YORK"
        else:
            return "OFF"

    async def get_dxy(self) -> Optional[float]:
        """DXY (Dollar Index) para correlação intermarket."""
        return await self.get_price("DXY")


market_data = MarketDataService()
