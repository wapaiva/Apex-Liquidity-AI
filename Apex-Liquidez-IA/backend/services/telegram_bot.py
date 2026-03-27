"""
APEX LIQUIDITY AI — Telegram Bot
Envia sinais profissionais formatados em tempo real.
"""
import httpx
from datetime import datetime
from loguru import logger
from config.api_keys import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


class TelegramBot:

    async def send(self, message: str) -> bool:
        if TELEGRAM_BOT_TOKEN == "COLE_AQUI" or TELEGRAM_CHAT_ID == "COLE_AQUI":
            logger.debug(f"Telegram não configurado. Mensagem: {message[:50]}...")
            return False
        try:
            async with httpx.AsyncClient(timeout=8) as c:
                r = await c.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                    json={"chat_id": TELEGRAM_CHAT_ID, "text": message,
                          "parse_mode": "HTML", "disable_web_page_preview": True}
                )
                return r.status_code == 200
        except Exception as e:
            logger.warning(f"Telegram error: {e}")
            return False

    async def send_signal(self, signal: dict) -> bool:
        """Formata e envia sinal de trading profissional."""
        direction = signal.get("direction", "WAIT")
        if direction == "WAIT":
            return False  # Só envia BUY e SELL

        symbol = signal.get("symbol", "")
        score = signal.get("score", 0)
        conf = signal.get("confidence", 0)
        entry = signal.get("entry", 0)
        sl = signal.get("sl", 0)
        tp = signal.get("tp", 0)
        rr = signal.get("rr_ratio", 0)
        session = signal.get("session", "")
        news = signal.get("news", {})
        liquidity = signal.get("liquidity", {})
        indicators = signal.get("indicators", {})
        ai_params = signal.get("ai_params", {})

        dir_emoji = "🟢" if direction == "BUY" else "🔴"
        dir_arrow = "📈" if direction == "BUY" else "📉"

        ind = indicators
        rsi_val = ind.get("rsi", {}).get("value", "N/A")
        macd_hist = ind.get("macd", {}).get("histogram", "N/A")
        adx_val = ind.get("adx", {}).get("adx", "N/A")
        atr_pct = ind.get("atr", {}).get("atr_pct", "N/A")
        regime = ind.get("regime", {}).get("regime", "N/A")

        msg = f"""⚡ <b>APEX LIQUIDITY AI</b> {dir_emoji}

{dir_arrow} <b>{direction}</b> | <b>{symbol}</b> | {session}
━━━━━━━━━━━━━━━━━━

📊 <b>Score IA:</b> {score:+d}/10 | <b>Confiança:</b> {conf:.1f}%
🎯 <b>Regime:</b> {regime}
🔢 <b>Win Rate IA:</b> {ai_params.get('win_rate', 0)*100:.0f}%

💰 <b>EXECUÇÃO</b>
• Entrada: <code>{entry}</code>
• Stop Loss: <code>{sl}</code>
• Take Profit: <code>{tp}</code>
• R:R Ratio: <b>1:{rr}</b>

📈 <b>INDICADORES</b>
• RSI: {rsi_val} | ADX: {adx_val}
• MACD Hist: {macd_hist:.6f if isinstance(macd_hist, float) else macd_hist}
• ATR: {atr_pct}%

📰 <b>SENTIMENTO NEWS</b>
• Score: {news.get('score', 0):+.2f} | {news.get('label', 'N/A')}
• Impacto: {news.get('impact', 'N/A')}

💧 <b>LIQUIDEZ</b>
• Score: {liquidity.get('score', 0)}/10
• {liquidity.get('zone', 'N/A')}

⏰ {datetime.utcnow().strftime('%d/%m %H:%M')} UTC
━━━━━━━━━━━━━━━━━━
⚠️ <i>Trading envolve riscos. Opere com responsabilidade.</i>"""

        return await self.send(msg)

    async def send_trade_executed(self, trade: dict) -> bool:
        symbol = trade.get("symbol", "")
        direction = trade.get("direction", "")
        lots = trade.get("lots", 0)
        entry = trade.get("entry", 0)
        sl = trade.get("sl", 0)
        tp = trade.get("tp", 0)
        ticket = trade.get("ticket", "")

        emoji = "🟢" if direction == "BUY" else "🔴"
        msg = f"""✅ <b>ORDEM EXECUTADA</b> {emoji}

<b>{direction}</b> {lots} lotes <b>{symbol}</b>
• Ticket: #{ticket}
• Entrada: <code>{entry}</code>
• Stop Loss: <code>{sl}</code>
• Take Profit: <code>{tp}</code>
⏰ {datetime.utcnow().strftime('%H:%M:%S')} UTC"""

        return await self.send(msg)

    async def send_trade_closed(self, trade: dict) -> bool:
        pnl = trade.get("pnl", 0)
        emoji = "🏆" if pnl > 0 else "💸"
        result = "WIN" if pnl > 0 else "LOSS"
        msg = f"""{emoji} <b>TRADE FECHADO — {result}</b>

<b>{trade.get('symbol')}</b> {trade.get('direction')}
• P&L: <b>{pnl:+.2f}</b>
• Motivo: {trade.get('close_reason', 'N/A')}
⏰ {datetime.utcnow().strftime('%H:%M:%S')} UTC"""
        return await self.send(msg)

    async def send_risk_alert(self, message: str) -> bool:
        msg = f"🚨 <b>ALERTA DE RISCO</b>\n\n{message}\n\n⏰ {datetime.utcnow().strftime('%H:%M')} UTC"
        return await self.send(msg)

    async def send_daily_report(self, stats: dict) -> bool:
        pnl = stats.get("daily_pnl", 0)
        emoji = "📈" if pnl > 0 else "📉"
        msg = f"""{emoji} <b>RELATÓRIO DIÁRIO — APEX AI</b>

📊 <b>Resumo do Dia</b>
• P&L: <b>{pnl:+.2f}</b>
• Trades: {stats.get('daily_trades', 0)}
• Win Rate: {stats.get('win_rate', 0)*100:.0f}%
• Drawdown: {stats.get('drawdown_pct', 0):.1f}%

🤖 <b>IA Adaptativa</b>
• Profit Factor: {stats.get('profit_factor', 1):.2f}
• Multiplicador Risco: {stats.get('risk_multiplier', 1):.1%}
• Streak: {stats.get('streak', 0)} {stats.get('streak_type', '')}

━━━━━━━━━━━━━━━━━━
⏰ Encerramento {datetime.utcnow().strftime('%d/%m/%Y')}"""
        return await self.send(msg)


telegram = TelegramBot()
