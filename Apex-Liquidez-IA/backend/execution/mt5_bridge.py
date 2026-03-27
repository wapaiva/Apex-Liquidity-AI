"""
APEX LIQUIDITY AI — MT5 Execution Bridge
Executa ordens reais no MetaTrader 5 via bridge HTTP local.
Bridge URL: http://localhost:5001
"""
import httpx
from datetime import datetime
from typing import Optional
from loguru import logger

from config.api_keys import MT5_BRIDGE_URL, MT5_BRIDGE_TOKEN, ASSETS
from backend.risk.risk_manager import risk_manager


class MT5Bridge:
    """Comunicação com o servidor HTTP do MetaTrader 5."""

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {MT5_BRIDGE_TOKEN}", "Content-Type": "application/json"}

    async def health_check(self) -> dict:
        """Verifica se o bridge MT5 está online."""
        try:
            async with httpx.AsyncClient(timeout=3) as c:
                r = await c.get(f"{MT5_BRIDGE_URL}/health", headers=self._headers())
                if r.status_code == 200:
                    return {"online": True, "data": r.json()}
        except Exception as e:
            logger.warning(f"MT5 Bridge offline: {e}")
        return {"online": False, "error": "Bridge não acessível em localhost:5001"}

    async def get_account_info(self) -> Optional[dict]:
        """Retorna informações da conta MT5."""
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get(f"{MT5_BRIDGE_URL}/account-info", headers=self._headers())
                if r.status_code == 200:
                    data = r.json()
                    risk_manager.update_equity(data.get("equity", 0))
                    return data
        except Exception as e:
            logger.warning(f"MT5 account-info error: {e}")
        return None

    async def get_positions(self) -> list:
        """Retorna posições abertas do MT5."""
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get(f"{MT5_BRIDGE_URL}/positions", headers=self._headers())
                if r.status_code == 200:
                    return r.json().get("positions", [])
        except Exception as e:
            logger.warning(f"MT5 positions error: {e}")
        return []

    async def execute_trade(
        self,
        symbol: str,
        direction: str,
        lots: float,
        entry: float,
        sl: float,
        tp: float,
        comment: str = "ApexAI"
    ) -> dict:
        """
        Executa ordem no MT5.
        Validações duplas antes de enviar.
        """
        # Verificações de segurança
        if direction not in ("BUY", "SELL"):
            return {"success": False, "error": "Direção inválida"}
        if lots <= 0 or lots > 10:
            return {"success": False, "error": f"Lote inválido: {lots}"}
        if sl == 0 or tp == 0:
            return {"success": False, "error": "SL/TP obrigatórios"}

        can_trade, reason = risk_manager.check_can_trade()
        if not can_trade:
            logger.warning(f"🚫 Trade bloqueado pelo Risk Manager: {reason}")
            return {"success": False, "error": reason}

        magic = ASSETS.get(symbol, {}).get("magic", 100000)

        payload = {
            "symbol": symbol,
            "direction": direction,
            "lots": lots,
            "sl": round(sl, 5),
            "tp": round(tp, 5),
            "magic": magic,
            "comment": comment,
        }

        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.post(f"{MT5_BRIDGE_URL}/execute-order",
                                  json=payload, headers=self._headers())
                r.raise_for_status()
                result = r.json()

                if result.get("success"):
                    risk_manager.daily_trades += 1
                    logger.info(f"✅ Trade executado: {direction} {lots} {symbol} @ {entry} | SL:{sl} TP:{tp} | Ticket:{result.get('ticket')}")
                else:
                    logger.error(f"❌ MT5 recusou ordem: {result.get('error')}")

                return result

        except httpx.ConnectError:
            msg = "Bridge MT5 offline. Certifique-se que localhost:5001 está rodando."
            logger.error(msg)
            return {"success": False, "error": msg}
        except Exception as e:
            logger.error(f"MT5 execute error: {e}")
            return {"success": False, "error": str(e)}

    async def close_position(self, ticket: int) -> dict:
        """Fecha posição pelo ticket."""
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.post(f"{MT5_BRIDGE_URL}/close-order",
                                  json={"ticket": ticket}, headers=self._headers())
                r.raise_for_status()
                return r.json()
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_history(self, days: int = 30) -> list:
        """Histórico de trades fechados."""
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(f"{MT5_BRIDGE_URL}/history",
                                  params={"days": days}, headers=self._headers())
                if r.status_code == 200:
                    return r.json().get("history", [])
        except Exception as e:
            logger.warning(f"MT5 history error: {e}")
        return []


mt5_bridge = MT5Bridge()
