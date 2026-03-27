"""
APEX LIQUIDITY AI — Motor de Decisão Principal
Pipeline completo: dados → indicadores → IA → sinal → filtros → execução
"""
import asyncio
import numpy as np
from datetime import datetime
from typing import Optional
from loguru import logger

from backend.market.market_data import market_data
from backend.market.indicators import indicators_engine
from backend.ai.adaptive_ai import adaptive_ai
from backend.services.news_analyzer import news_analyzer
from backend.market.liquidity import liquidity_engine
from config.api_keys import ASSETS, MIN_SCORE_BUY, MIN_SCORE_SELL


class DecisionEngine:
    """
    Motor central de decisão. Orquestra todo o pipeline de análise.
    """

    async def analyze(self, symbol: str, timeframe: str = "H1") -> dict:
        """
        Pipeline completo de análise para um ativo.
        Retorna sinal com todos os componentes de decisão.
        """
        result = {
            "symbol": symbol,
            "timeframe": timeframe,
            "timestamp": datetime.utcnow().isoformat(),
            "direction": "WAIT",
            "confidence": 0.0,
            "score": 0,
            "entry": None,
            "sl": None,
            "tp": None,
            "blocked": False,
            "block_reason": "",
        }

        # 1. Obter candles
        df = await market_data.get_candles(symbol, timeframe, limit=200)
        if df is None or len(df) < 50:
            result["block_reason"] = "Dados insuficientes"
            result["blocked"] = True
            return result

        price = float(df["close"].iloc[-1])
        result["entry"] = round(price, 5)

        # 2. Calcular indicadores técnicos
        indicators = indicators_engine.calculate_all(df)
        result["indicators"] = indicators

        # 3. Filtro Anti-Loss — não operar em condições ruins
        blocked, reason = self._anti_loss_filter(indicators, symbol)
        if blocked:
            result["blocked"] = True
            result["block_reason"] = reason
            result["direction"] = "WAIT"
            return result

        # 4. Score base dos indicadores
        base_score = indicators.get("score", {}).get("total", 0)
        confidence = indicators.get("score", {}).get("confidence", 0)

        # 5. Análise de liquidez institucional
        liquidity = await liquidity_engine.analyze(df, symbol)
        result["liquidity"] = liquidity
        liq_score = liquidity.get("score_contribution", 0)

        # 6. Análise de sentimento de notícias
        news = await news_analyzer.get_sentiment(symbol)
        result["news"] = news
        news_score = news.get("score_contribution", 0)

        # 7. Correlação intermarket
        corr_score = await self._intermarket_correlation(symbol)
        result["correlation_score"] = corr_score

        # 8. Sessão de mercado
        session = await market_data.get_session()
        session_mult = self._session_multiplier(symbol, session)
        result["session"] = session

        # 9. Score final ponderado
        total_score = int(
            base_score * 1.0 +
            liq_score * 0.5 +
            news_score * 0.3 +
            corr_score * 0.2
        )
        total_score = max(-10, min(10, total_score))
        result["score"] = total_score

        # Ajustar confiança com múltiplos fatores
        confidence = min(abs(total_score) / 10 * 100, 100) * session_mult
        result["confidence"] = round(confidence, 1)

        # 10. Verificar IA adaptativa
        ai_ok, ai_reason = adaptive_ai.should_trade(symbol, total_score, confidence)
        if not ai_ok:
            result["blocked"] = True
            result["block_reason"] = f"IA Adaptativa: {ai_reason}"
            return result

        # 11. Gerar direção
        if total_score >= MIN_SCORE_BUY:
            direction = "BUY"
        elif total_score <= MIN_SCORE_SELL:
            direction = "SELL"
        else:
            direction = "WAIT"

        result["direction"] = direction

        # 12. Calcular SL e TP baseados em ATR
        if direction != "WAIT":
            atr = indicators.get("atr", {}).get("atr", price * 0.001)
            asset_type = ASSETS.get(symbol, {}).get("type", "forex")
            sl_mult, tp_mult = self._get_sl_tp_multipliers(asset_type)

            if direction == "BUY":
                result["sl"] = round(price - atr * sl_mult, 5)
                result["tp"] = round(price + atr * tp_mult, 5)
            else:
                result["sl"] = round(price + atr * sl_mult, 5)
                result["tp"] = round(price - atr * tp_mult, 5)

            result["rr_ratio"] = round(tp_mult / sl_mult, 2)

        # 13. Bias da IA por ativo
        result["ai_bias"] = adaptive_ai.compute_symbol_bias(symbol)
        result["ai_params"] = adaptive_ai.params

        logger.info(f"📊 {symbol} | {direction} | Score:{total_score} | Conf:{confidence:.1f}%")
        return result

    def _anti_loss_filter(self, indicators: dict, symbol: str) -> tuple[bool, str]:
        """
        Filtros obrigatórios que bloqueiam operações em condições ruins.
        """
        adx = indicators.get("adx", {})
        atr = indicators.get("atr", {})
        bb = indicators.get("bb", {})
        score = indicators.get("score", {})

        # ADX muito baixo = mercado sem tendência
        if adx.get("adx", 25) < 15:
            return True, f"ADX muito baixo ({adx.get('adx', 0):.1f}) — mercado lateral"

        # Volatilidade muito baixa = spread alto, armadilha
        if atr.get("volatility") == "LOW" and atr.get("atr_pct", 1) < 0.05:
            return True, "Volatilidade extremamente baixa — evitar"

        # Bollinger squeeze = mercado comprimido, aguardar breakout
        if bb.get("squeeze", False) and abs(score.get("total", 0)) < 3:
            return True, "Bollinger Bands em squeeze — aguardar rompimento"

        # Conflito de indicadores — sinais opostos
        signals_up = score.get("signals_up", 0)
        signals_dn = score.get("signals_dn", 0)
        if signals_up >= 3 and signals_dn >= 3:
            return True, "Conflito de indicadores — sinais opostos detectados"

        return False, ""

    async def _intermarket_correlation(self, symbol: str) -> int:
        """
        Triangulação intermarket para confirmar direção.
        DXY vs EURUSD | Ouro vs Dólar | BTC vs Nasdaq
        """
        score = 0
        try:
            if symbol == "EURUSD":
                dxy = await market_data.get_price("DXY")
                if dxy:
                    score += -1  # DXY sobe = EURUSD cai (inverso)

            elif symbol == "XAUUSD":
                dxy = await market_data.get_price("DXY")
                if dxy:
                    score += -1  # DXY sobe = Ouro cai

            elif symbol in ("BTCUSDT", "ETHUSDT"):
                nas = await market_data.get_price("NAS100")
                if nas:
                    score += 1  # correlação positiva com Nasdaq

            elif symbol in ("SP500", "NAS100"):
                score += 1  # índices americanos correlacionados

        except Exception as e:
            logger.debug(f"Intermarket correlation error: {e}")

        return score

    def _session_multiplier(self, symbol: str, session: str) -> float:
        """
        Ajusta confiança baseado na sessão de mercado.
        Cada ativo tem melhor performance em certas sessões.
        """
        best_sessions = {
            "EURUSD":  ["LONDON", "NEW_YORK"],
            "XAUUSD":  ["LONDON", "NEW_YORK"],
            "SP500":   ["NEW_YORK"],
            "NAS100":  ["NEW_YORK"],
            "US30":    ["NEW_YORK"],
            "BTCUSDT": ["ASIA", "LONDON", "NEW_YORK"],  # 24h
            "ETHUSDT": ["ASIA", "LONDON", "NEW_YORK"],
        }
        if session == "OFF":
            return 0.7
        best = best_sessions.get(symbol, ["LONDON", "NEW_YORK"])
        return 1.0 if session in best else 0.85

    def _get_sl_tp_multipliers(self, asset_type: str) -> tuple[float, float]:
        """
        SL e TP em múltiplos de ATR por tipo de ativo.
        """
        return {
            "forex":  (1.5, 3.0),   # RR 1:2
            "index":  (2.0, 4.0),   # RR 1:2
            "crypto": (2.0, 5.0),   # RR 1:2.5
        }.get(asset_type, (1.5, 3.0))

    async def analyze_all(self, timeframe: str = "H1") -> list:
        """Analisa todos os ativos configurados em paralelo."""
        tasks = [
            self.analyze(symbol, timeframe)
            for symbol, cfg in ASSETS.items()
            if cfg.get("active", True)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [r for r in results if isinstance(r, dict)]


decision_engine = DecisionEngine()
