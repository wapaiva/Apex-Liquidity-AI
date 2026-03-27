"""
APEX LIQUIDITY AI — IA Adaptativa Auto-Evolutiva
Aprende com cada trade e ajusta parâmetros automaticamente.
"""
import json
import os
import numpy as np
from datetime import datetime
from typing import Optional
from loguru import logger

HISTORY_FILE = "data/trade_history.json"


class AdaptiveAI:
    """
    Motor de IA que evolui baseado no histórico de trades.
    - Reduz risco após perdas consecutivas
    - Aumenta filtros após streaks negativos
    - Otimiza entradas após wins
    """

    def __init__(self):
        self.history = self._load_history()
        self.params = self._compute_adaptive_params()

    def _load_history(self) -> list:
        os.makedirs("data", exist_ok=True)
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def save_history(self):
        with open(HISTORY_FILE, "w") as f:
            json.dump(self.history[-500:], f, indent=2, default=str)

    def record_trade(self, trade: dict):
        """Registra resultado de um trade e recalcula parâmetros."""
        trade["recorded_at"] = datetime.utcnow().isoformat()
        self.history.append(trade)
        self.save_history()
        self.params = self._compute_adaptive_params()
        logger.info(f"📚 Trade registrado: {trade.get('symbol')} {trade.get('direction')} → {trade.get('result', 'OPEN')}")

    def _compute_adaptive_params(self) -> dict:
        """
        Analisa histórico e gera parâmetros adaptativos.
        Regras:
        - LOSS → reduzir risco, aumentar filtros
        - WIN  → otimizar entradas
        """
        if len(self.history) < 5:
            return self._default_params()

        recent = [t for t in self.history[-20:] if t.get("result") in ("WIN", "LOSS")]
        if not recent:
            return self._default_params()

        wins = sum(1 for t in recent if t.get("result") == "WIN")
        losses = sum(1 for t in recent if t.get("result") == "LOSS")
        win_rate = wins / len(recent) if recent else 0.5

        # Streak atual
        streak = 0
        streak_type = None
        for t in reversed(recent):
            if streak_type is None:
                streak_type = t.get("result")
                streak = 1
            elif t.get("result") == streak_type:
                streak += 1
            else:
                break

        # Ajuste de risco baseado em win rate
        if win_rate >= 0.65:
            risk_multiplier = 1.2    # Aumentar risco se performance boa
            min_score = 4            # Filtros normais
            confidence_threshold = 60
        elif win_rate >= 0.50:
            risk_multiplier = 1.0    # Risco padrão
            min_score = 4
            confidence_threshold = 65
        elif win_rate >= 0.35:
            risk_multiplier = 0.75   # Reduzir risco
            min_score = 5            # Filtros mais rígidos
            confidence_threshold = 70
        else:
            risk_multiplier = 0.5    # Risco mínimo
            min_score = 6            # Filtros muito rígidos
            confidence_threshold = 75

        # Penalidade por streak de losses
        if streak_type == "LOSS" and streak >= 3:
            risk_multiplier *= max(0.3, 1 - streak * 0.1)
            min_score = min(min_score + streak - 2, 8)
            logger.warning(f"🔴 Streak de {streak} losses — risco reduzido para {risk_multiplier:.0%}")

        # Boost por streak de wins
        if streak_type == "WIN" and streak >= 3:
            risk_multiplier = min(risk_multiplier * 1.1, 1.5)
            logger.info(f"🟢 Streak de {streak} wins — risco otimizado {risk_multiplier:.0%}")

        # Profit factor
        pnls = [t.get("pnl", 0) for t in recent]
        gross_profit = sum(p for p in pnls if p > 0)
        gross_loss = abs(sum(p for p in pnls if p < 0))
        profit_factor = gross_profit / (gross_loss + 1e-10)

        return {
            "risk_multiplier": round(risk_multiplier, 2),
            "min_score": min_score,
            "confidence_threshold": confidence_threshold,
            "win_rate": round(win_rate, 3),
            "streak": streak,
            "streak_type": streak_type,
            "profit_factor": round(profit_factor, 2),
            "total_trades": len(self.history),
            "recent_trades": len(recent),
        }

    def _default_params(self) -> dict:
        return {
            "risk_multiplier": 1.0,
            "min_score": 4,
            "confidence_threshold": 65,
            "win_rate": 0.5,
            "streak": 0,
            "streak_type": None,
            "profit_factor": 1.0,
            "total_trades": 0,
            "recent_trades": 0,
        }

    def should_trade(self, symbol: str, score: int, confidence: float) -> tuple[bool, str]:
        """
        Decide se deve operar baseado nos parâmetros adaptativos.
        Retorna (can_trade, reason).
        """
        min_score = self.params["min_score"]
        min_confidence = self.params["confidence_threshold"]

        if abs(score) < min_score:
            return False, f"Score {score} abaixo do mínimo adaptativo {min_score}"
        if confidence < min_confidence:
            return False, f"Confiança {confidence:.1f}% abaixo do mínimo {min_confidence}%"

        return True, "OK"

    def adjust_risk(self, base_risk_pct: float) -> float:
        """Aplica multiplicador adaptativo ao risco base."""
        return base_risk_pct * self.params["risk_multiplier"]

    def get_summary(self) -> dict:
        """Retorna resumo do estado atual da IA."""
        return {
            "params": self.params,
            "total_trades": len(self.history),
            "history_preview": self.history[-5:]
        }

    def compute_symbol_bias(self, symbol: str) -> dict:
        """
        Analisa histórico por ativo e retorna bias de performance.
        """
        sym_trades = [t for t in self.history if t.get("symbol") == symbol and t.get("result") in ("WIN","LOSS")]
        if not sym_trades:
            return {"bias": "NEUTRAL", "win_rate": 0.5, "total": 0}

        wins = sum(1 for t in sym_trades if t.get("result") == "WIN")
        wr = wins / len(sym_trades)
        bias = "BULLISH" if wr > 0.6 else ("BEARISH" if wr < 0.4 else "NEUTRAL")

        return {"bias": bias, "win_rate": round(wr, 3), "total": len(sym_trades)}


adaptive_ai = AdaptiveAI()
