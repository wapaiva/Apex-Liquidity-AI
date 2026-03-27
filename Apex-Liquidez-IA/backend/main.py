"""
APEX LIQUIDITY AI — Personal Quant Trading System PRO
FastAPI Server + Loop Principal de Trading
"""
import asyncio
import json
import os
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger

from backend.ai.decision_engine import decision_engine
from backend.ai.adaptive_ai import adaptive_ai
from backend.execution.mt5_bridge import mt5_bridge
from backend.risk.risk_manager import risk_manager
from backend.services.telegram_bot import telegram
from backend.services.news_analyzer import news_analyzer
from backend.market.market_data import market_data
from backend.market.indicators import indicators_engine
from config.api_keys import ASSETS, LOOP_INTERVAL

app = FastAPI(title="Apex Liquidity AI", version="2.0.0")

app.add_middleware(CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ─── Estado global do sistema ──────────────────────────────────────

system_state = {
    "robot_active": False,
    "loop_running": False,
    "signals": {},          # Últimos sinais por ativo
    "account": {},          # Info da conta MT5
    "positions": [],        # Posições abertas
    "news": {},             # Notícias por ativo
    "last_loop": None,
    "errors": [],
    "active_assets": {k: v["active"] for k, v in ASSETS.items()},
    "settings": {
        "risk_pct": 1.0,
        "aggression": 5,    # 1-10
        "timeframe": "H1",
        "loop_interval": LOOP_INTERVAL,
        "auto_execute": False,
    }
}

# WebSocket connections
ws_clients: list[WebSocket] = []


# ─── WebSocket broadcast ──────────────────────────────────────────

async def broadcast(data: dict):
    """Envia atualização para todos os clientes WebSocket."""
    disconnected = []
    for ws in ws_clients:
        try:
            await ws.send_json(data)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        ws_clients.remove(ws)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    ws_clients.append(ws)
    logger.info(f"WebSocket conectado. Total: {len(ws_clients)}")
    try:
        # Enviar estado atual imediatamente
        await ws.send_json({"type": "state", "data": system_state})
        while True:
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        ws_clients.remove(ws)
        logger.info("WebSocket desconectado")


# ─── Loop principal de trading ────────────────────────────────────

async def trading_loop():
    """
    Loop principal: coleta → analisa → decide → executa → aprende
    Roda a cada LOOP_INTERVAL segundos.
    """
    logger.info("🚀 Loop de trading iniciado")
    await telegram.send("⚡ <b>APEX LIQUIDITY AI</b>\nSistema iniciado e operando! 🚀")

    while system_state["loop_running"]:
        try:
            loop_start = datetime.utcnow()
            system_state["last_loop"] = loop_start.isoformat()

            # 1. Atualizar info da conta MT5
            account = await mt5_bridge.get_account_info()
            if account:
                system_state["account"] = account
                risk_manager.update_equity(account.get("equity", 0))

            # 2. Atualizar posições abertas
            positions = await mt5_bridge.get_positions()
            system_state["positions"] = positions

            # 3. Analisar todos os ativos ativos
            active = [s for s, cfg in ASSETS.items()
                      if system_state["active_assets"].get(s, cfg["active"])]

            timeframe = system_state["settings"]["timeframe"]
            signals = await decision_engine.analyze_all(timeframe)

            for signal in signals:
                symbol = signal["symbol"]
                system_state["signals"][symbol] = signal

                # 4. Executar trade se robot ativo e sinal válido
                if (system_state["robot_active"] and
                    system_state["settings"]["auto_execute"] and
                    signal["direction"] != "WAIT" and
                    not signal.get("blocked", False)):

                    can_trade, reason = risk_manager.check_can_trade()
                    if can_trade:
                        await _execute_signal(signal, account)

                # 5. Enviar sinal via Telegram (apenas BUY/SELL)
                if signal["direction"] != "WAIT" and not signal.get("blocked"):
                    await telegram.send_signal(signal)

            # 6. Broadcast WebSocket
            await broadcast({
                "type": "update",
                "signals": system_state["signals"],
                "account": system_state["account"],
                "positions": system_state["positions"],
                "risk": risk_manager.get_status(),
                "ai": adaptive_ai.get_summary(),
                "timestamp": loop_start.isoformat(),
            })

            # 7. Aguardar próximo ciclo
            elapsed = (datetime.utcnow() - loop_start).seconds
            wait = max(1, system_state["settings"]["loop_interval"] - elapsed)
            await asyncio.sleep(wait)

        except Exception as e:
            error_msg = f"Loop error: {str(e)}"
            logger.error(error_msg)
            system_state["errors"].append({"time": datetime.utcnow().isoformat(), "msg": error_msg})
            system_state["errors"] = system_state["errors"][-50:]
            await asyncio.sleep(10)

    logger.info("⏹️ Loop de trading encerrado")


async def _execute_signal(signal: dict, account: Optional[dict]):
    """Executa um sinal no MT5 com gestão de risco completa."""
    symbol = signal["symbol"]
    direction = signal["direction"]
    entry = signal["entry"]
    sl = signal["sl"]
    tp = signal["tp"]

    balance = account.get("balance", 1000) if account else 1000
    lots = risk_manager.calculate_position_size(symbol, entry, sl, balance)

    result = await mt5_bridge.execute_trade(symbol, direction, lots, entry, sl, tp)

    if result.get("success"):
        trade_data = {
            "symbol": symbol, "direction": direction, "lots": lots,
            "entry": entry, "sl": sl, "tp": tp,
            "ticket": result.get("ticket"), "result": "OPEN",
        }
        adaptive_ai.record_trade(trade_data)
        risk_manager.daily_trades += 1
        await telegram.send_trade_executed({**trade_data, **result})
    else:
        logger.error(f"Falha ao executar {symbol}: {result.get('error')}")


# ─── REST Endpoints ───────────────────────────────────────────────

@app.get("/api/health")
async def health():
    mt5 = await mt5_bridge.health_check()
    return {
        "status": "ok",
        "robot_active": system_state["robot_active"],
        "loop_running": system_state["loop_running"],
        "mt5_online": mt5.get("online", False),
        "signals_count": len(system_state["signals"]),
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/api/signals")
async def get_signals():
    return {"signals": system_state["signals"]}


@app.get("/api/account")
async def get_account():
    account = await mt5_bridge.get_account_info()
    if account:
        system_state["account"] = account
    return {"account": system_state["account"]}


@app.get("/api/positions")
async def get_positions():
    positions = await mt5_bridge.get_positions()
    system_state["positions"] = positions
    return {"positions": positions}


@app.get("/api/history")
async def get_history(days: int = 30):
    history = await mt5_bridge.get_history(days)
    return {"history": history, "ai_history": adaptive_ai.history[-50:]}


@app.get("/api/risk")
async def get_risk():
    return {"risk": risk_manager.get_status()}


@app.get("/api/ai")
async def get_ai():
    return adaptive_ai.get_summary()


@app.get("/api/news/{symbol}")
async def get_news(symbol: str):
    news = await news_analyzer.get_sentiment(symbol)
    return {"symbol": symbol, "news": news}


@app.post("/api/robot/start")
async def start_robot(background_tasks: BackgroundTasks):
    if not system_state["loop_running"]:
        system_state["loop_running"] = True
        system_state["robot_active"] = True
        background_tasks.add_task(trading_loop)
        logger.info("▶️ Robot iniciado")
        return {"status": "started"}
    system_state["robot_active"] = True
    return {"status": "already_running"}


@app.post("/api/robot/stop")
async def stop_robot():
    system_state["loop_running"] = False
    system_state["robot_active"] = False
    logger.info("⏹️ Robot parado")
    return {"status": "stopped"}


@app.post("/api/robot/pause")
async def pause_robot():
    system_state["robot_active"] = False
    return {"status": "paused"}


@app.patch("/api/settings")
async def update_settings(settings: dict):
    system_state["settings"].update(settings)
    return {"settings": system_state["settings"]}


@app.patch("/api/assets")
async def update_assets(assets: dict):
    system_state["active_assets"].update(assets)
    return {"active_assets": system_state["active_assets"]}


@app.post("/api/close/{ticket}")
async def close_position(ticket: int):
    result = await mt5_bridge.close_position(ticket)
    return result


@app.get("/api/backtest/{symbol}")
async def backtest(symbol: str, days: int = 30, timeframe: str = "H1"):
    """Backtest simplificado usando dados históricos."""
    df = await market_data.get_candles(symbol, timeframe, limit=days * 24)
    if df is None or len(df) < 50:
        return {"error": "Dados insuficientes"}

    results = []
    for i in range(50, len(df)):
        chunk = df.iloc[:i]
        indicators = indicators_engine.calculate_all(chunk)
        score = indicators.get("score", {})
        direction = score.get("direction", "WAIT")

        if direction != "WAIT":
            entry = float(chunk["close"].iloc[-1])
            future = df.iloc[i:i+10] if i + 10 < len(df) else df.iloc[i:]
            if len(future) == 0:
                continue

            atr = indicators.get("atr", {}).get("atr", entry * 0.001)
            sl = entry - atr * 1.5 if direction == "BUY" else entry + atr * 1.5
            tp = entry + atr * 3.0 if direction == "BUY" else entry - atr * 3.0

            result = "UNKNOWN"
            pnl = 0.0
            for _, row in future.iterrows():
                if direction == "BUY":
                    if row["low"] <= sl:
                        result, pnl = "LOSS", round((sl - entry) * 10000, 2)
                        break
                    if row["high"] >= tp:
                        result, pnl = "WIN", round((tp - entry) * 10000, 2)
                        break
                else:
                    if row["high"] >= sl:
                        result, pnl = "LOSS", round((entry - sl) * 10000, 2)
                        break
                    if row["low"] <= tp:
                        result, pnl = "WIN", round((entry - tp) * 10000, 2)
                        break

            if result != "UNKNOWN":
                results.append({
                    "timestamp": chunk["timestamp"].iloc[-1].isoformat() if hasattr(chunk["timestamp"].iloc[-1], 'isoformat') else str(chunk["timestamp"].iloc[-1]),
                    "direction": direction,
                    "entry": round(entry, 5),
                    "result": result,
                    "pnl": pnl,
                    "confidence": score.get("confidence", 0),
                })

    if not results:
        return {"symbol": symbol, "trades": 0, "win_rate": 0, "profit_factor": 0, "results": []}

    wins = sum(1 for r in results if r["result"] == "WIN")
    losses = sum(1 for r in results if r["result"] == "LOSS")
    total = wins + losses
    win_rate = wins / total if total > 0 else 0

    gross_profit = sum(r["pnl"] for r in results if r["pnl"] > 0)
    gross_loss = abs(sum(r["pnl"] for r in results if r["pnl"] < 0))
    profit_factor = gross_profit / (gross_loss + 1e-10)
    total_pnl = sum(r["pnl"] for r in results)

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "days": days,
        "trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 3),
        "profit_factor": round(profit_factor, 2),
        "total_pnl": round(total_pnl, 2),
        "results": results[-100:],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
