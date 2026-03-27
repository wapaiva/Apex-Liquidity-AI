"""
APEX LIQUIDITY AI — Smart Money Detector
Detecta: Liquidity Sweeps, Stop Hunts, Order Blocks, Break of Structure (BOS).
"""
import numpy as np
import pandas as pd
from loguru import logger


class SmartMoneyDetector:

    def analyze(self, df: pd.DataFrame, cfg: dict = None) -> dict:
        """Pipeline completo de análise Smart Money."""
        if df is None or len(df) < 20:
            return self._empty()

        cfg = cfg or {}
        h = df["high"].values.astype(float)
        l = df["low"].values.astype(float)
        c = df["close"].values.astype(float)
        o = df["open"].values.astype(float)
        v = df["volume"].values.astype(float)

        results = {
            "liquidity_sweep": self._detect_liquidity_sweep(h, l, c, cfg),
            "stop_hunt":       self._detect_stop_hunt(h, l, c),
            "order_blocks":    self._detect_order_blocks(o, h, l, c, v),
            "bos":             self._detect_bos(h, l, c),
            "structure":       self._market_structure(h, l, c),
        }

        # Score composto Smart Money (-2 a +2)
        score = 0
        sweep = results["liquidity_sweep"]
        if sweep.get("detected"):
            score += 1 if sweep.get("direction") == "BULLISH" else -1

        hunt = results["stop_hunt"]
        if hunt.get("detected"):
            score += 1 if hunt.get("direction") == "BULLISH" else -1

        bos = results["bos"]
        if bos.get("detected"):
            score += 1 if bos.get("direction") == "BULLISH" else -1

        results["smart_money_score"] = score
        results["bias"] = "BULLISH" if score > 0 else ("BEARISH" if score < 0 else "NEUTRAL")
        return results

    # ─── Liquidity Sweep ─────────────────────────────────────────

    def _detect_liquidity_sweep(self, h, l, c, cfg: dict) -> dict:
        """
        Detecta rompimento de nível de liquidez com reversão rápida.
        Ex: preço rompe high anterior, mas fecha abaixo → Sweep bearish.
        """
        if len(h) < 5:
            return {"detected": False}

        lookback = 20
        min_sweep_pct = cfg.get("MIN_SWEEP_PCT", 0.0015)

        prev_high = np.max(h[-lookback-1:-1])
        prev_low  = np.min(l[-lookback-1:-1])
        curr_high = h[-1]
        curr_low  = l[-1]
        curr_close = c[-1]

        # Sweep de alta: rompeu high e voltou
        bull_sweep = (curr_high > prev_high * (1 + min_sweep_pct)
                      and curr_close < prev_high)

        # Sweep de baixa: rompeu low e voltou
        bear_sweep = (curr_low < prev_low * (1 - min_sweep_pct)
                      and curr_close > prev_low)

        if bull_sweep:
            return {"detected": True, "direction": "BEARISH",
                    "level": round(float(prev_high), 5),
                    "description": "Liquidity Sweep acima dos highs — possível reversão bearish"}
        if bear_sweep:
            return {"detected": True, "direction": "BULLISH",
                    "level": round(float(prev_low), 5),
                    "description": "Liquidity Sweep abaixo dos lows — possível reversão bullish"}

        return {"detected": False}

    # ─── Stop Hunt ───────────────────────────────────────────────

    def _detect_stop_hunt(self, h, l, c) -> dict:
        """
        Detecta stop hunt: wick extremo além de nível relevante com retorno rápido.
        Wick > 60% do range total da vela.
        """
        if len(c) < 3:
            return {"detected": False}

        curr_h = h[-1]
        curr_l = l[-1]
        curr_c = c[-1]
        curr_o = c[-2]  # open aprox

        candle_range = curr_h - curr_l
        if candle_range == 0:
            return {"detected": False}

        upper_wick = curr_h - max(curr_c, curr_o)
        lower_wick = min(curr_c, curr_o) - curr_l

        # Upper wick > 60% do range = stop hunt de shorts
        if upper_wick / candle_range > 0.60:
            return {"detected": True, "direction": "BEARISH",
                    "wick_pct": round(upper_wick/candle_range*100, 1),
                    "description": "Stop Hunt: wick superior longo — stops comprados ativados"}

        # Lower wick > 60% do range = stop hunt de longs
        if lower_wick / candle_range > 0.60:
            return {"detected": True, "direction": "BULLISH",
                    "wick_pct": round(lower_wick/candle_range*100, 1),
                    "description": "Stop Hunt: wick inferior longo — stops vendidos ativados"}

        return {"detected": False}

    # ─── Order Blocks ────────────────────────────────────────────

    def _detect_order_blocks(self, o, h, l, c, v) -> dict:
        """
        Order Block: última vela antes de movimento impulsivo forte.
        Identifica zonas de interesse institucional.
        """
        if len(c) < 10:
            return {"detected": False, "blocks": []}

        blocks = []
        avg_vol = np.mean(v[-20:]) if len(v) >= 20 else np.mean(v)

        for i in range(2, min(20, len(c)-2)):
            idx = -(i+1)
            # Verificar se houve impulso após esta vela
            body_curr = abs(c[idx] - o[idx])
            body_next = abs(c[idx+1] - o[idx+1])

            if body_next > body_curr * 2 and v[idx+1] > avg_vol * 1.5:
                direction = "BULLISH" if c[idx+1] > o[idx+1] else "BEARISH"
                blocks.append({
                    "direction": direction,
                    "high": round(float(h[idx]), 5),
                    "low": round(float(l[idx]), 5),
                    "strength": round(float(body_next / (body_curr + 1e-10)), 2),
                })

        if blocks:
            # Pegar o mais recente e forte
            best = sorted(blocks, key=lambda b: b["strength"], reverse=True)[0]
            return {"detected": True, "blocks": blocks[:3], "nearest": best}

        return {"detected": False, "blocks": []}

    # ─── Break of Structure ──────────────────────────────────────

    def _detect_bos(self, h, l, c) -> dict:
        """
        Break of Structure: preço rompe o último pivot high/low significativo.
        Indica mudança de direção institucional.
        """
        if len(c) < 10:
            return {"detected": False}

        n = min(30, len(c))
        h_slice = h[-n:]
        l_slice = l[-n:]
        c_slice = c[-n:]

        # Pivot highs e lows (simplificado: máximos/mínimos locais)
        recent_high = np.max(h_slice[:-3])
        recent_low  = np.min(l_slice[:-3])
        curr_close  = c_slice[-1]
        curr_high   = h_slice[-1]
        curr_low    = l_slice[-1]

        # BOS bullish: fechou acima do último pivot high
        if curr_close > recent_high:
            return {"detected": True, "direction": "BULLISH",
                    "level": round(float(recent_high), 5),
                    "description": f"BOS Bullish: fechou acima do pivot high {recent_high:.5f}"}

        # BOS bearish: fechou abaixo do último pivot low
        if curr_close < recent_low:
            return {"detected": True, "direction": "BEARISH",
                    "level": round(float(recent_low), 5),
                    "description": f"BOS Bearish: fechou abaixo do pivot low {recent_low:.5f}"}

        return {"detected": False}

    # ─── Estrutura de Mercado ─────────────────────────────────────

    def _market_structure(self, h, l, c) -> dict:
        """HH/HL = Bullish structure | LH/LL = Bearish structure"""
        if len(c) < 6:
            return {"type": "UNKNOWN", "pivots": []}

        pivots = []
        for i in range(1, min(10, len(c)-1)):
            idx = -(i)
            if h[idx] > h[idx-1] and h[idx] > h[idx+1] if idx+1 < 0 else True:
                pivots.append({"type": "HIGH", "value": float(h[idx])})
            elif l[idx] < l[idx-1] and l[idx] < l[idx+1] if idx+1 < 0 else True:
                pivots.append({"type": "LOW", "value": float(l[idx])})

        if len(pivots) < 2:
            return {"type": "UNCLEAR", "pivots": pivots}

        highs = [p["value"] for p in pivots if p["type"] == "HIGH"][:3]
        lows  = [p["value"] for p in pivots if p["type"] == "LOW"][:3]

        if len(highs) >= 2 and len(lows) >= 2:
            hh = highs[0] > highs[1]  # Higher High
            hl = lows[0] > lows[1]    # Higher Low
            lh = highs[0] < highs[1]  # Lower High
            ll = lows[0] < lows[1]    # Lower Low

            if hh and hl:
                return {"type": "BULLISH", "description": "HH + HL — Estrutura bullish", "pivots": pivots[:4]}
            if lh and ll:
                return {"type": "BEARISH", "description": "LH + LL — Estrutura bearish", "pivots": pivots[:4]}

        return {"type": "RANGING", "pivots": pivots[:4]}

    def _empty(self):
        return {
            "liquidity_sweep": {"detected": False},
            "stop_hunt":       {"detected": False},
            "order_blocks":    {"detected": False, "blocks": []},
            "bos":             {"detected": False},
            "structure":       {"type": "UNKNOWN"},
            "smart_money_score": 0,
            "bias": "NEUTRAL",
        }


smart_money = SmartMoneyDetector()
