#!/usr/bin/env python3
"""
APEX LIQUIDITY AI — PERSONAL QUANT TRADING SYSTEM PRO
Script de inicialização rápida
"""
import subprocess, sys, os

print("""
╔══════════════════════════════════════════════════════════════╗
║         APEX LIQUIDITY AI — PERSONAL QUANT PRO              ║
║         Sistema de Trading Quantitativo Institucional        ║
╚══════════════════════════════════════════════════════════════╝
""")

# Verificar Python
if sys.version_info < (3, 10):
    print("❌ Python 3.10+ necessário")
    sys.exit(1)

# Instalar dependências se necessário
print("📦 Verificando dependências...")
subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "-q"], check=True)

# Criar diretório de dados
os.makedirs("data", exist_ok=True)

# Verificar config
from config.api_keys import POLYGON_API_KEY, TELEGRAM_BOT_TOKEN
unconfigured = [k for k,v in {"POLYGON_API_KEY": POLYGON_API_KEY, "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN}.items() if v == "COLE_AQUI"]
if unconfigured:
    print(f"⚠️  APIs não configuradas: {', '.join(unconfigured)}")
    print("   Configure em: config/api_keys.py")
    print("   Sistema vai rodar em modo simulação.")
else:
    print("✅ APIs configuradas")

print("\n🚀 Iniciando servidor...")
print("   Dashboard: http://localhost:8000")
print("   API Docs:  http://localhost:8000/docs")
print("   WebSocket: ws://localhost:8000/ws")
print("\n   Para iniciar o MT5 Bridge (separo):")
print("   python mt5_bridge.py\n")

subprocess.run([sys.executable, "-m", "uvicorn", "backend.main:app",
                "--host", "0.0.0.0", "--port", "8000", "--reload"])
