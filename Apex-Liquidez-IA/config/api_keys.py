# ============================================================
#  APEX LIQUIDITY AI — CONFIGURAÇÃO DE APIs
#  Cole suas chaves abaixo. NÃO altere o nome das variáveis.
# ============================================================

# Polygon.io — dados de mercado em tempo real (primário)
# https://polygon.io → Dashboard → API Keys
POLYGON_API_KEY = "COLE_AQUI"

# Alpha Vantage — dados históricos e fallback
# https://alphavantage.co → Get free API key
ALPHA_VANTAGE_API_KEY = "COLE_AQUI"

# Binance — dados de criptomoedas (BTC, ETH)
# https://binance.com → Account → API Management
BINANCE_API_KEY = "COLE_AQUI"
BINANCE_SECRET_KEY = "COLE_AQUI"

# NewsAPI — notícias financeiras para sentimento
# https://newsapi.org → Get API Key
NEWS_API_KEY = "COLE_AQUI"

# Finnhub — dados alternativos e notícias
# https://finnhub.io → Dashboard
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "d73f3p9r01qjjol2radgd73f3p9r01qjjol2rae0")

# Telegram — alertas e sinais em tempo real
# @BotFather → /newbot → copie o token
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8347200645:AAEN1Glp-99lPfPAdtaIVxdAfEMSo7BEjcI")
# @userinfobot → envie /start → copie o chat_id
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "-1003745581937")

# ============================================================
#  CONFIGURAÇÕES DO MT5 BRIDGE
#  O bridge roda localmente na sua máquina com MT5 instalado
# ============================================================
MT5_BRIDGE_URL = "http://localhost:5001"
MT5_BRIDGE_TOKEN = "apex_local_token_2024"

# ============================================================
#  CONFIGURAÇÕES GERAIS DO SISTEMA
# ============================================================

# Ativos para operar (pode desativar qualquer um)
ASSETS = {
    "EURUSD":  {"active": True,  "type": "forex",   "magic": 100001},
    "XAUUSD":  {"active": True,  "type": "forex",   "magic": 100002},
    "SP500":   {"active": True,  "type": "index",   "magic": 100003},
    "NAS100":  {"active": True,  "type": "index",   "magic": 100004},
    "US30":    {"active": False, "type": "index",   "magic": 100005},
    "BTCUSDT": {"active": True,  "type": "crypto",  "magic": 100006},
    "ETHUSDT": {"active": False, "type": "crypto",  "magic": 100007},
}

# Risco por operação (% do saldo)
RISK_PER_TRADE = 1.0

# Perda máxima diária antes de pausar (%)
MAX_DAILY_LOSS = 3.0

# Drawdown máximo antes de parar (%)
MAX_DRAWDOWN = 8.0

# Intervalo do loop principal (segundos)
LOOP_INTERVAL = 15

# Score mínimo para gerar sinal (0-10)
MIN_SCORE_BUY  =  4
MIN_SCORE_SELL = -4
