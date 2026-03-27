"""
APEX LIQUIDITY AI — Liquidity Engine
Mapeamento de liquidez institucional, zonas de S/D, equal highs/lows.
"""
import numpy as np
import pandas as pd
from loguru import logger


class LiquidityEngine:

    async def analyze(self, df: pd.DataFrame, symbol: str) -> dict:
        """Analisa liquidez institucional nos dados OHLCV."""
        if df is None or len(df) < 20:
            return {"score": 5, "zone": "N/A", "score_contribution": 0}

        h = df["high"].values.astype(float)
        l = df["low"].values.astype(float)
        c = df["close"].values.astype(float)
        v = df["volume"].values.astype(float)

        # Zonas de liquidez: equal highs/lows
        eq_highs = self._find_equal_levels(h, tolerance=0.0003)
        eq_lows = self._find_equal_levels(l, tolerance=0.0003)

        # Volume institucional (volume acima da média 2x)
        avg_vol = np.mean(v[-50:]) if len(v) >= 50 else np.mean(v)
        high_vol_candles = sum(1 for vi in v[-20:] if vi > avg_vol * 1.8)

        # Zonas de Supply e Demand
        sd_zones = self._find_sd_zones(df)

        # Score de liquidez (0-10)
        score = 5
        score += min(len(eq_highs) + len(eq_lows), 2)  # Equal levels
        score += min(high_vol_candles // 2, 2)           # Volume institucional
        score += 1 if len(sd_zones) > 0 else 0           # S/D zones
        score = min(score, 10)

        # Zona mais próxima do preço
        price = float(c[-1])
        zone = "NEUTRO"
        contribution = 0

        if eq_highs and any(abs(lvl - price) / price < 0.002 for lvl in eq_highs):
            zone = "SELL SIDE LIQUIDITY (SSH)"
            contribution = -1  # Preço perto de equal highs = possível reversão
        elif eq_lows and any(abs(lvl - price) / price < 0.002 for lvl in eq_lows):
            zone = "BUY SIDE LIQUIDITY (SSL)"
            contribution = 1   # Preço perto de equal lows = possível bounce

        if sd_zones:
            nearest = min(sd_zones, key=lambda z: abs(z["price"] - price))
            if abs(nearest["price"] - price) / price < 0.003:
                zone = f"{nearest['type']} ZONE"
                contribution = 1 if nearest["type"] == "DEMAND" else -1

        return {
            "score": score,
            "zone": zone,
            "score_contribution": contribution,
            "equal_highs": len(eq_highs),
            "equal_lows": len(eq_lows),
            "high_vol_candles": high_vol_candles,
            "sd_zones": len(sd_zones),
            "details": {
                "eq_high_levels": [round(l, 5) for l in eq_highs[:3]],
                "eq_low_levels": [round(l, 5) for l in eq_lows[:3]],
            }
        }

    def _find_equal_levels(self, arr: np.ndarray, tolerance: float = 0.0003, lookback: int = 50) -> list:
        """Encontra níveis de preço com múltiplos toques (equal highs/lows)."""
        recent = arr[-lookback:] if len(arr) > lookback else arr
        levels = []
        for i, level in enumerate(recent):
            touches = sum(1 for other in recent if abs(other - level) / (level + 1e-10) < tolerance)
            if touches >= 2 and level not in levels:
                levels.append(float(level))
        return list(set(round(l, 5) for l in levels))

    def _find_sd_zones(self, df: pd.DataFrame, lookback: int = 30) -> list:
        """Identifica zonas de Supply e Demand baseadas em movimentos bruscos."""
        zones = []
        if len(df) < 10:
            return zones

        h = df["high"].values.astype(float)
        l = df["low"].values.astype(float)
        c = df["close"].values.astype(float)
        o = df["open"].values.astype(float)

        for i in range(2, min(lookback, len(c) - 1)):
            body = abs(c[i] - o[i])
            avg_body = np.mean([abs(c[j] - o[j]) for j in range(max(0, i-10), i)])
            # Candle com corpo 2x maior que média = zona S/D
            if body > avg_body * 2 and avg_body > 0:
                if c[i] > o[i]:  # Candle bullish = DEMAND zone
                    zones.append({"type": "DEMAND", "price": float(l[i]), "strength": body/avg_body})
                else:  # Candle bearish = SUPPLY zone
                    zones.append({"type": "SUPPLY", "price": float(h[i]), "strength": body/avg_body})

        # Ordenar por força e retornar top 3
        return sorted(zones, key=lambda z: z["strength"], reverse=True)[:3]


liquidity_engine = LiquidityEngine()
