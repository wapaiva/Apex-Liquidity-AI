"""
APEX LIQUIDITY AI — MT5 Bridge Server
Roda na sua máquina com MetaTrader 5 instalado.
Expose endpoints HTTP para o backend Python consumir.

COMO RODAR:
  pip install fastapi uvicorn MetaTrader5
  python mt5_bridge.py

Ficará disponível em: http://localhost:5001
"""
import MetaTrader5 as mt5
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn
from datetime import datetime
import sys

# ─── Configuração ──────────────────────────────────────────────────
BRIDGE_TOKEN = "apex_local_token_2024"  # Mesmo token em config/api_keys.py
PORT = 5001

app = FastAPI(title="Apex MT5 Bridge", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def verify_token(authorization: Optional[str] = Header(None)):
    if not authorization or authorization != f"Bearer {BRIDGE_TOKEN}":
        raise HTTPException(status_code=401, detail="Token inválido")


# ─── Inicializar MT5 ───────────────────────────────────────────────

def init_mt5():
    if not mt5.initialize():
        print(f"❌ Falha ao inicializar MT5: {mt5.last_error()}")
        sys.exit(1)
    info = mt5.account_info()
    if info is None:
        print("❌ Não foi possível obter informações da conta. Certifique-se de estar logado no MT5.")
        sys.exit(1)
    print(f"✅ MT5 conectado: Conta #{info.login} | {info.name} | Saldo: {info.balance}")


# ─── Schemas ──────────────────────────────────────────────────────

class TradeRequest(BaseModel):
    symbol: str
    direction: str  # BUY | SELL
    lots: float
    sl: float
    tp: float
    magic: int = 100000
    comment: str = "ApexAI"


class CloseRequest(BaseModel):
    ticket: int


class ModifyRequest(BaseModel):
    ticket: int
    sl: float
    tp: float


# ─── Endpoints ────────────────────────────────────────────────────

@app.get("/health")
def health():
    init_ok = mt5.initialize()
    return {"online": init_ok, "version": mt5.version() if init_ok else None}


@app.get("/account-info", dependencies=[Depends(verify_token)])
def account_info():
    info = mt5.account_info()
    if not info:
        raise HTTPException(500, f"MT5 erro: {mt5.last_error()}")
    return {
        "login": info.login, "name": info.name, "server": info.server,
        "balance": info.balance, "equity": info.equity,
        "margin": info.margin, "free_margin": info.margin_free,
        "profit": info.profit, "leverage": info.leverage,
        "currency": info.currency, "company": info.company,
    }


@app.get("/positions", dependencies=[Depends(verify_token)])
def get_positions():
    positions = mt5.positions_get()
    if positions is None:
        return {"positions": []}
    return {"positions": [
        {
            "ticket": p.ticket, "symbol": p.symbol,
            "direction": "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL",
            "lots": p.volume, "entry": p.price_open,
            "current": p.price_current, "sl": p.sl, "tp": p.tp,
            "pnl": p.profit, "swap": p.swap,
            "magic": p.magic, "comment": p.comment,
            "open_time": datetime.fromtimestamp(p.time).isoformat(),
        }
        for p in positions
    ]}


@app.post("/execute-order", dependencies=[Depends(verify_token)])
def execute_order(req: TradeRequest):
    """Executa ordem no MT5."""
    symbol_info = mt5.symbol_info(req.symbol)
    if symbol_info is None:
        raise HTTPException(400, f"Símbolo {req.symbol} não encontrado no MT5")
    if not symbol_info.visible:
        mt5.symbol_select(req.symbol, True)

    order_type = mt5.ORDER_TYPE_BUY if req.direction == "BUY" else mt5.ORDER_TYPE_SELL
    price = mt5.symbol_info_tick(req.symbol).ask if req.direction == "BUY" else mt5.symbol_info_tick(req.symbol).bid

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": req.symbol,
        "volume": req.lots,
        "type": order_type,
        "price": price,
        "sl": req.sl,
        "tp": req.tp,
        "magic": req.magic,
        "comment": req.comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result is None:
        return {"success": False, "error": str(mt5.last_error())}
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return {"success": False, "error": f"MT5 retcode: {result.retcode} — {result.comment}"}

    return {"success": True, "ticket": result.order, "price": result.price,
            "volume": result.volume, "comment": result.comment}


@app.post("/close-order", dependencies=[Depends(verify_token)])
def close_order(req: CloseRequest):
    """Fecha posição pelo ticket."""
    position = mt5.positions_get(ticket=req.ticket)
    if not position:
        raise HTTPException(404, f"Posição #{req.ticket} não encontrada")

    pos = position[0]
    order_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
    price = mt5.symbol_info_tick(pos.symbol).bid if pos.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(pos.symbol).ask

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": pos.symbol,
        "volume": pos.volume,
        "type": order_type,
        "position": req.ticket,
        "price": price,
        "magic": pos.magic,
        "comment": "ApexAI_Close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        return {"success": True, "ticket": req.ticket, "price": result.price}
    return {"success": False, "error": str(result.comment if result else mt5.last_error())}


@app.post("/modify-order", dependencies=[Depends(verify_token)])
def modify_order(req: ModifyRequest):
    """Modifica SL/TP de uma posição."""
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": req.ticket,
        "sl": req.sl,
        "tp": req.tp,
    }
    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        return {"success": True}
    return {"success": False, "error": str(result.comment if result else mt5.last_error())}


@app.get("/history", dependencies=[Depends(verify_token)])
def get_history(days: int = 30):
    """Histórico de ordens fechadas."""
    from datetime import timedelta
    date_from = datetime.utcnow() - timedelta(days=days)
    deals = mt5.history_deals_get(date_from, datetime.utcnow())
    if deals is None:
        return {"history": []}
    return {"history": [
        {
            "ticket": d.ticket, "order": d.order,
            "symbol": d.symbol, "lots": d.volume,
            "direction": "BUY" if d.type == mt5.DEAL_TYPE_BUY else "SELL",
            "price": d.price, "profit": d.profit, "swap": d.swap,
            "commission": d.commission, "magic": d.magic,
            "time": datetime.fromtimestamp(d.time).isoformat(),
            "comment": d.comment,
        }
        for d in deals if d.symbol  # Filtra entradas de depósito
    ]}


if __name__ == "__main__":
    print("=" * 50)
    print("  APEX LIQUIDITY AI — MT5 Bridge Server")
    print(f"  Iniciando na porta {PORT}...")
    print("=" * 50)
    init_mt5()
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")
