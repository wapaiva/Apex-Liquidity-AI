"""
APEX LIQUIDITY AI — Risk Manager Institucional
Stop Loss automático, Take Profit dinâmico, limites diários, drawdown control.
"""
import asyncio
import httpx
from datetime import datetime, date
from typing import Optional
from loguru import logger

from config.api_keys import RISK_PER_TRADE, MAX_DAILY_LOSS, MAX_DRAWDOWN, MT5_BRIDGE_URL, MT5_BRIDGE_TOKEN
from backend.ai.adaptive_ai import adaptive_ai


class RiskManager:

    def __init__(self):
        self.daily_pnl = 0.0
        self.peak_equity = 0.0
        self.current_equity = 0.0
        self.daily_trades = 0
        self.paused = False
        self.pause_reason = ""
        self._last_reset = date.today()

    def reset_daily(self):
        """Reseta contadores diários à meia-noite."""
        if date.today() > self._last_reset:
            self.daily_pnl = 0.0
            self.daily_trades = 0
            self._last_reset = date.today()
            if self.paused and "diária" in self.pause_reason.lower():
                self.paused = False
                self.pause_reason = ""
            logger.info("🔄 Contadores diários resetados")

    def check_can_trade(self) -> tuple[bool, str]:
        """Verifica se é seguro operar agora."""
        self.reset_daily()

        if self.paused:
            return False, f"Sistema pausado: {self.pause_reason}"

        if self.current_equity > 0:
            # Verificar perda diária
            daily_loss_pct = abs(self.daily_pnl) / self.current_equity * 100
            if self.daily_pnl < 0 and daily_loss_pct >= MAX_DAILY_LOSS:
                self.paused = True
                self.pause_reason = f"Perda diária atingida: {daily_loss_pct:.1f}% (limite: {MAX_DAILY_LOSS}%)"
                logger.error(f"🛑 {self.pause_reason}")
                return False, self.pause_reason

            # Verificar drawdown
            if self.peak_equity > 0:
                drawdown = (self.peak_equity - self.current_equity) / self.peak_equity * 100
                if drawdown >= MAX_DRAWDOWN:
                    self.paused = True
                    self.pause_reason = f"Drawdown máximo atingido: {drawdown:.1f}% (limite: {MAX_DRAWDOWN}%)"
                    logger.error(f"🛑 {self.pause_reason}")
                    return False, self.pause_reason

        return True, "OK"

    def update_equity(self, equity: float):
        """Atualiza equity e peak equity."""
        self.current_equity = equity
        if equity > self.peak_equity:
            self.peak_equity = equity

    def update_pnl(self, pnl: float):
        """Atualiza P&L diário após fechar trade."""
        self.daily_pnl += pnl
        adaptive_ai.record_trade({
            "pnl": pnl,
            "result": "WIN" if pnl > 0 else "LOSS",
            "timestamp": datetime.utcnow().isoformat()
        })

    def calculate_position_size(self, symbol: str, entry: float, sl: float, balance: float) -> float:
        """
        Calcula tamanho da posição baseado em % de risco.
        Aplica multiplicador adaptativo da IA.
        """
        risk_pct = RISK_PER_TRADE
        risk_pct = adaptive_ai.adjust_risk(risk_pct)  # Ajuste adaptativo
        risk_pct = max(0.1, min(risk_pct, 5.0))  # Limite de segurança

        risk_amount = balance * risk_pct / 100
        sl_distance = abs(entry - sl)

        if sl_distance == 0:
            return 0.01

        # Pip value aproximado por ativo
        pip_values = {
            "EURUSD": 10, "GBPUSD": 10, "XAUUSD": 100,
            "SP500": 50, "NAS100": 20, "US30": 10,
            "BTCUSDT": 1, "ETHUSDT": 1
        }
        pip_val = pip_values.get(symbol, 10)

        lots = risk_amount / (sl_distance * pip_val)
        lots = round(max(0.01, min(lots, 10.0)), 2)
        logger.debug(f"📐 Position size {symbol}: {lots} lotes (risco {risk_pct:.1f}%)")
        return lots

    def get_status(self) -> dict:
        """Retorna estado atual do risk manager."""
        self.reset_daily()
        drawdown = 0.0
        if self.peak_equity > 0:
            drawdown = (self.peak_equity - self.current_equity) / self.peak_equity * 100

        daily_loss_pct = 0.0
        if self.current_equity > 0 and self.daily_pnl < 0:
            daily_loss_pct = abs(self.daily_pnl) / self.current_equity * 100

        return {
            "paused": self.paused,
            "pause_reason": self.pause_reason,
            "daily_pnl": round(self.daily_pnl, 2),
            "daily_loss_pct": round(daily_loss_pct, 2),
            "drawdown_pct": round(drawdown, 2),
            "peak_equity": round(self.peak_equity, 2),
            "current_equity": round(self.current_equity, 2),
            "daily_trades": self.daily_trades,
            "risk_pct": round(adaptive_ai.adjust_risk(RISK_PER_TRADE), 2),
        }

    def resume(self):
        """Retoma operações manualmente."""
        self.paused = False
        self.pause_reason = ""
        logger.info("▶️ Sistema retomado manualmente")


risk_manager = RiskManager()
