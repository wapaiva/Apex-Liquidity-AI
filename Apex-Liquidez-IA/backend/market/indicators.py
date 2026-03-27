"""
APEX LIQUIDITY AI — Indicators Engine
Cálculo completo de todos os indicadores técnicos obrigatórios.
"""
import numpy as np
import pandas as pd
from typing import Optional
from loguru import logger


class IndicatorsEngine:

    def calculate_all(self, df: pd.DataFrame) -> dict:
        """
        Calcula todos os indicadores para um DataFrame OHLCV.
        Retorna dict com valores e scores direcionais.
        """
        if df is None or len(df) < 30:
            return {}

        c = df["close"].values.astype(float)
        h = df["high"].values.astype(float)
        l = df["low"].values.astype(float)
        v = df["volume"].values.astype(float)
        o = df["open"].values.astype(float)

        result = {}

        try:
            result["rsi"]      = self._rsi(c)
            result["macd"]     = self._macd(c)
            result["adx"]      = self._adx(h, l, c)
            result["atr"]      = self._atr(h, l, c)
            result["bb"]       = self._bollinger(c)
            result["vwap"]     = self._vwap(h, l, c, v)
            result["ema"]      = self._ema_stack(c)
            result["volume"]   = self._volume_analysis(v, c)
            result["stoch"]    = self._stochastic(h, l, c)
            result["cci"]      = self._cci(h, l, c)
            result["obv"]      = self._obv(c, v)
            result["mfi"]      = self._mfi(h, l, c, v)
            result["regime"]   = self._detect_regime(c, h, l, v, result)
            result["score"]    = self._compute_score(result, c)
        except Exception as e:
            logger.error(f"Indicators error: {e}")

        return result

    # ─── RSI ─────────────────────────────────────────────────────

    def _rsi(self, c: np.ndarray, period: int = 14) -> dict:
        delta = np.diff(c)
        gain = np.where(delta > 0, delta, 0)
        loss = np.where(delta < 0, -delta, 0)
        avg_gain = np.convolve(gain, np.ones(period)/period, mode='valid')
        avg_loss = np.convolve(loss, np.ones(period)/period, mode='valid')
        rs = np.where(avg_loss == 0, 100, avg_gain / avg_loss)
        rsi = 100 - (100 / (1 + rs))
        val = float(rsi[-1]) if len(rsi) > 0 else 50.0
        signal = "SELL" if val > 70 else ("BUY" if val < 30 else "NEUTRAL")
        score = 1 if val < 40 else (-1 if val > 60 else 0)
        return {"value": round(val, 2), "signal": signal, "score": score,
                "overbought": val > 70, "oversold": val < 30}

    # ─── MACD ────────────────────────────────────────────────────

    def _macd(self, c: np.ndarray, fast=12, slow=26, signal=9) -> dict:
        def ema(arr, n):
            alpha = 2 / (n + 1)
            result = [arr[0]]
            for v in arr[1:]:
                result.append(alpha * v + (1 - alpha) * result[-1])
            return np.array(result)

        ema_fast = ema(c, fast)
        ema_slow = ema(c, slow)
        macd_line = ema_fast - ema_slow
        signal_line = ema(macd_line, signal)
        histogram = macd_line - signal_line

        val = float(macd_line[-1])
        sig = float(signal_line[-1])
        hist = float(histogram[-1])
        prev_hist = float(histogram[-2]) if len(histogram) > 1 else 0

        cross_up = hist > 0 and prev_hist <= 0
        cross_dn = hist < 0 and prev_hist >= 0
        trend = "BUY" if hist > 0 else "SELL"
        score = 1 if cross_up or hist > 0 else (-1 if cross_dn or hist < 0 else 0)

        return {"macd": round(val, 6), "signal": round(sig, 6),
                "histogram": round(hist, 6), "trend": trend,
                "cross_up": cross_up, "cross_dn": cross_dn, "score": score}

    # ─── ADX ─────────────────────────────────────────────────────

    def _adx(self, h, l, c, period=14) -> dict:
        tr = np.maximum(h[1:] - l[1:],
             np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))
        dm_plus = np.where((h[1:] - h[:-1]) > (l[:-1] - l[1:]),
                           np.maximum(h[1:] - h[:-1], 0), 0)
        dm_minus = np.where((l[:-1] - l[1:]) > (h[1:] - h[:-1]),
                            np.maximum(l[:-1] - l[1:], 0), 0)

        def smooth(arr, n):
            result = [np.sum(arr[:n])]
            for v in arr[n:]:
                result.append(result[-1] - result[-1]/n + v)
            return np.array(result)

        if len(tr) < period * 2:
            return {"adx": 20.0, "plus_di": 20.0, "minus_di": 20.0,
                    "trending": False, "direction": "NEUTRAL", "score": 0}

        atr_s = smooth(tr, period)
        dmp_s = smooth(dm_plus, period)
        dmm_s = smooth(dm_minus, period)

        eps = 1e-10
        di_plus = 100 * dmp_s / (atr_s + eps)
        di_minus = 100 * dmm_s / (atr_s + eps)
        dx = 100 * abs(di_plus - di_minus) / (di_plus + di_minus + eps)

        adx_arr = smooth(dx, period)
        adx = float(adx_arr[-1]) if len(adx_arr) > 0 else 20.0
        dip = float(di_plus[-1]) if len(di_plus) > 0 else 20.0
        dim = float(di_minus[-1]) if len(di_minus) > 0 else 20.0

        trending = adx > 25
        direction = "BUY" if dip > dim else "SELL"
        score = (1 if trending and dip > dim else -1 if trending and dim > dip else 0)

        return {"adx": round(adx, 2), "plus_di": round(dip, 2), "minus_di": round(dim, 2),
                "trending": trending, "direction": direction, "score": score}

    # ─── ATR ─────────────────────────────────────────────────────

    def _atr(self, h, l, c, period=14) -> dict:
        tr = np.maximum(h[1:] - l[1:],
             np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))
        if len(tr) < period:
            return {"atr": 0.0, "atr_pct": 0.0, "volatility": "LOW"}
        atr = float(np.mean(tr[-period:]))
        atr_pct = atr / float(c[-1]) * 100
        volatility = "HIGH" if atr_pct > 0.5 else ("NORMAL" if atr_pct > 0.2 else "LOW")
        return {"atr": round(atr, 5), "atr_pct": round(atr_pct, 3), "volatility": volatility}

    # ─── Bollinger Bands ─────────────────────────────────────────

    def _bollinger(self, c, period=20, std_dev=2) -> dict:
        if len(c) < period:
            return {"upper": 0, "middle": 0, "lower": 0, "width": 0, "signal": "NEUTRAL", "score": 0}
        sma = float(np.mean(c[-period:]))
        std = float(np.std(c[-period:]))
        upper = sma + std_dev * std
        lower = sma - std_dev * std
        price = float(c[-1])
        width = (upper - lower) / sma * 100
        pos = (price - lower) / (upper - lower) * 100 if (upper - lower) > 0 else 50

        signal = "SELL" if price > upper else ("BUY" if price < lower else "NEUTRAL")
        score = -1 if price > upper else (1 if price < lower else 0)

        return {"upper": round(upper, 5), "middle": round(sma, 5), "lower": round(lower, 5),
                "width": round(width, 2), "position_pct": round(pos, 1),
                "signal": signal, "score": score,
                "squeeze": width < 1.5}

    # ─── VWAP ────────────────────────────────────────────────────

    def _vwap(self, h, l, c, v, period=50) -> dict:
        typical = (h + l + c) / 3
        n = min(period, len(typical))
        vwap = float(np.sum(typical[-n:] * v[-n:]) / (np.sum(v[-n:]) + 1e-10))
        price = float(c[-1])
        signal = "BUY" if price > vwap else "SELL"
        score = 1 if price > vwap else -1
        return {"vwap": round(vwap, 5), "price_vs_vwap": round(price - vwap, 5),
                "signal": signal, "score": score}

    # ─── EMA Stack ───────────────────────────────────────────────

    def _ema_stack(self, c) -> dict:
        def ema(arr, n):
            if len(arr) < n:
                return float(arr[-1])
            alpha = 2 / (n + 1)
            val = arr[0]
            for v in arr[1:]:
                val = alpha * v + (1 - alpha) * val
            return float(val)

        price = float(c[-1])
        e9 = ema(c, 9)
        e21 = ema(c, 21)
        e50 = ema(c, 50)
        e200 = ema(c, 200) if len(c) >= 200 else None

        # Score baseado em quantas EMAs o preço está acima
        above = sum([price > e9, price > e21, price > e50])
        if e200:
            above += int(price > e200)
            total = 4
        else:
            total = 3

        score = 1 if above >= total * 0.7 else (-1 if above <= total * 0.3 else 0)
        alignment = "BULLISH" if e9 > e21 > e50 else ("BEARISH" if e9 < e21 < e50 else "MIXED")

        return {"ema9": round(e9, 5), "ema21": round(e21, 5), "ema50": round(e50, 5),
                "ema200": round(e200, 5) if e200 else None,
                "alignment": alignment, "score": score, "above_count": above}

    # ─── Volume Analysis ─────────────────────────────────────────

    def _volume_analysis(self, v, c, period=20) -> dict:
        if len(v) < period:
            return {"avg": 0, "current": 0, "ratio": 1.0, "signal": "NEUTRAL", "score": 0}
        avg = float(np.mean(v[-period:]))
        current = float(v[-1])
        ratio = current / (avg + 1e-10)
        delta = float(c[-1]) - float(c[-2]) if len(c) > 1 else 0
        signal = "BUY" if ratio > 1.5 and delta > 0 else ("SELL" if ratio > 1.5 and delta < 0 else "NEUTRAL")
        score = 1 if ratio > 1.5 and delta > 0 else (-1 if ratio > 1.5 and delta < 0 else 0)
        return {"avg": round(avg, 0), "current": round(current, 0),
                "ratio": round(ratio, 2), "signal": signal, "score": score,
                "high_volume": ratio > 1.5}

    # ─── Stochastic ──────────────────────────────────────────────

    def _stochastic(self, h, l, c, k=14, d=3) -> dict:
        if len(c) < k:
            return {"k": 50, "d": 50, "signal": "NEUTRAL", "score": 0}
        low_min = np.min(l[-k:])
        high_max = np.max(h[-k:])
        k_val = float((c[-1] - low_min) / (high_max - low_min + 1e-10) * 100)
        d_val = k_val  # simplified
        signal = "BUY" if k_val < 20 else ("SELL" if k_val > 80 else "NEUTRAL")
        score = 1 if k_val < 25 else (-1 if k_val > 75 else 0)
        return {"k": round(k_val, 2), "d": round(d_val, 2), "signal": signal, "score": score}

    # ─── CCI ─────────────────────────────────────────────────────

    def _cci(self, h, l, c, period=20) -> dict:
        if len(c) < period:
            return {"value": 0, "signal": "NEUTRAL", "score": 0}
        tp = (h + l + c) / 3
        sma = np.mean(tp[-period:])
        mad = np.mean(np.abs(tp[-period:] - sma))
        cci = float((tp[-1] - sma) / (0.015 * mad + 1e-10))
        signal = "BUY" if cci < -100 else ("SELL" if cci > 100 else "NEUTRAL")
        score = 1 if cci < -100 else (-1 if cci > 100 else 0)
        return {"value": round(cci, 2), "signal": signal, "score": score}

    # ─── OBV ─────────────────────────────────────────────────────

    def _obv(self, c, v) -> dict:
        obv = [0.0]
        for i in range(1, len(c)):
            if c[i] > c[i-1]:
                obv.append(obv[-1] + v[i])
            elif c[i] < c[i-1]:
                obv.append(obv[-1] - v[i])
            else:
                obv.append(obv[-1])
        trend = "UP" if obv[-1] > obv[-10] else "DOWN"
        score = 1 if trend == "UP" else -1
        return {"value": round(obv[-1], 0), "trend": trend, "score": score}

    # ─── MFI ─────────────────────────────────────────────────────

    def _mfi(self, h, l, c, v, period=14) -> dict:
        if len(c) < period + 1:
            return {"value": 50, "signal": "NEUTRAL", "score": 0}
        tp = (h + l + c) / 3
        mf = tp * v
        pos_mf = sum(mf[i] for i in range(1, period+1) if tp[i] > tp[i-1])
        neg_mf = sum(mf[i] for i in range(1, period+1) if tp[i] < tp[i-1])
        mfi = 100 - 100 / (1 + pos_mf / (neg_mf + 1e-10))
        signal = "BUY" if mfi < 20 else ("SELL" if mfi > 80 else "NEUTRAL")
        score = 1 if mfi < 30 else (-1 if mfi > 70 else 0)
        return {"value": round(float(mfi), 2), "signal": signal, "score": score}

    # ─── Regime Detection ────────────────────────────────────────

    def _detect_regime(self, c, h, l, v, indicators) -> dict:
        adx = indicators.get("adx", {}).get("adx", 20)
        bb = indicators.get("bb", {})
        atr = indicators.get("atr", {})

        if adx > 30:
            regime = "TRENDING"
            direction = indicators.get("adx", {}).get("direction", "NEUTRAL")
        elif bb.get("squeeze", False):
            regime = "CONSOLIDATION"
            direction = "NEUTRAL"
        elif atr.get("volatility") == "HIGH":
            regime = "VOLATILE"
            direction = "NEUTRAL"
        else:
            regime = "RANGING"
            direction = "NEUTRAL"

        return {"regime": regime, "direction": direction, "adx": adx}

    # ─── Score Final ─────────────────────────────────────────────

    def _compute_score(self, indicators, c) -> dict:
        """Calcula score direcional de -10 a +10."""
        scores = {
            "rsi":    indicators.get("rsi", {}).get("score", 0),
            "macd":   indicators.get("macd", {}).get("score", 0),
            "adx":    indicators.get("adx", {}).get("score", 0),
            "bb":     indicators.get("bb", {}).get("score", 0),
            "vwap":   indicators.get("vwap", {}).get("score", 0),
            "ema":    indicators.get("ema", {}).get("score", 0),
            "volume": indicators.get("volume", {}).get("score", 0),
            "stoch":  indicators.get("stoch", {}).get("score", 0),
            "cci":    indicators.get("cci", {}).get("score", 0),
            "obv":    indicators.get("obv", {}).get("score", 0),
        }
        total = sum(scores.values())
        direction = "BUY" if total >= 4 else ("SELL" if total <= -4 else "WAIT")
        confidence = min(abs(total) / 10 * 100, 100)

        return {
            "total": total,
            "direction": direction,
            "confidence": round(confidence, 1),
            "breakdown": scores,
            "signals_up": sum(1 for s in scores.values() if s > 0),
            "signals_dn": sum(1 for s in scores.values() if s < 0),
        }


indicators_engine = IndicatorsEngine()
