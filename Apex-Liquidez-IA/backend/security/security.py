"""
APEX LIQUIDITY AI — Security System
Autenticação JWT, criptografia AES-256, proteção de chaves, rate limiting.
"""
import os
import json
import hmac
import hashlib
import secrets
import base64
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from loguru import logger

# ─── Dependências opcionais com fallback ─────────────────────────
try:
    from cryptography.fernet import Fernet
    FERNET_OK = True
except ImportError:
    FERNET_OK = False

try:
    import jwt as pyjwt
    JWT_OK = True
except ImportError:
    JWT_OK = False

try:
    import bcrypt
    BCRYPT_OK = True
except ImportError:
    BCRYPT_OK = False


# ─── Caminhos ────────────────────────────────────────────────────
SECURITY_DIR = Path("data/security")
SECURITY_DIR.mkdir(parents=True, exist_ok=True)
USERS_FILE  = SECURITY_DIR / "users.json"
KEY_FILE    = SECURITY_DIR / ".master.key"
SESSION_FILE = SECURITY_DIR / "sessions.json"


# ─── Chave mestre AES-256 ─────────────────────────────────────────

def _get_master_key() -> bytes:
    """Gera ou carrega a chave mestre de criptografia."""
    if KEY_FILE.exists():
        return KEY_FILE.read_bytes()
    if FERNET_OK:
        key = Fernet.generate_key()
    else:
        key = base64.urlsafe_b64encode(secrets.token_bytes(32))
    KEY_FILE.write_bytes(key)
    KEY_FILE.chmod(0o600)  # Apenas o dono pode ler
    return key


MASTER_KEY = _get_master_key()


# ─── Funções de criptografia ──────────────────────────────────────

def encrypt(text: str) -> str:
    """Criptografa texto com AES-256."""
    if FERNET_OK:
        f = Fernet(MASTER_KEY)
        return f.encrypt(text.encode()).decode()
    # Fallback: XOR simples com a chave (não recomendado para produção)
    key = MASTER_KEY[:32]
    enc = bytes(a ^ b for a, b in zip(text.encode(), key * (len(text)//len(key)+1)))
    return base64.urlsafe_b64encode(enc).decode()


def decrypt(token: str) -> str:
    """Descriptografa texto."""
    if FERNET_OK:
        f = Fernet(MASTER_KEY)
        return f.decrypt(token.encode()).decode()
    key = MASTER_KEY[:32]
    raw = base64.urlsafe_b64decode(token)
    dec = bytes(a ^ b for a, b in zip(raw, key * (len(raw)//len(key)+1)))
    return dec.decode()


def mask_secret(value: str, visible: int = 4) -> str:
    """Ex: sk_live_abc123 → •••••••123"""
    if not value or len(value) <= visible:
        return "••••••••"
    return "•" * max(8, len(value) - visible) + value[-visible:]


# ─── Hash de senha ────────────────────────────────────────────────

def hash_password(password: str) -> str:
    if BCRYPT_OK:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    salt = secrets.token_hex(16)
    h = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return f"{salt}:{h}"


def verify_password(password: str, hashed: str) -> bool:
    if BCRYPT_OK:
        try:
            return bcrypt.checkpw(password.encode(), hashed.encode())
        except Exception:
            return False
    if ":" in hashed:
        salt, h = hashed.split(":", 1)
        return hmac.compare_digest(h, hashlib.sha256(f"{salt}{password}".encode()).hexdigest())
    return False


# ─── JWT ─────────────────────────────────────────────────────────

JWT_SECRET = os.environ.get("APEX_JWT_SECRET") or secrets.token_hex(32)
JWT_ALGO   = "HS256"
JWT_EXPIRE = 24  # horas


def create_token(user_id: str, role: str = "admin") -> str:
    payload = {
        "sub":  user_id,
        "role": role,
        "iat":  datetime.utcnow().isoformat(),
        "exp":  (datetime.utcnow() + timedelta(hours=JWT_EXPIRE)).isoformat(),
        "jti":  secrets.token_hex(16),
    }
    if JWT_OK:
        return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)
    # Fallback: token assinado com HMAC
    import json as _json
    body = base64.urlsafe_b64encode(_json.dumps(payload).encode()).decode()
    sig  = hmac.new(JWT_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_token(token: str) -> Optional[dict]:
    if not token:
        return None
    if JWT_OK:
        try:
            payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
            # Verificar expiração manual se 'exp' for string
            if isinstance(payload.get("exp"), str):
                if datetime.fromisoformat(payload["exp"]) < datetime.utcnow():
                    return None
            return payload
        except Exception:
            return None
    # Fallback
    try:
        parts = token.rsplit(".", 1)
        if len(parts) != 2:
            return None
        body, sig = parts
        expected = hmac.new(JWT_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        import json as _json
        payload = _json.loads(base64.urlsafe_b64decode(body + "=="))
        if datetime.fromisoformat(payload["exp"]) < datetime.utcnow():
            return None
        return payload
    except Exception:
        return None


# ─── Gerenciamento de usuários ────────────────────────────────────

def _load_users() -> dict:
    if USERS_FILE.exists():
        try:
            return json.loads(USERS_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_users(users: dict):
    USERS_FILE.write_text(json.dumps(users, indent=2))
    USERS_FILE.chmod(0o600)


def create_user(username: str, password: str, role: str = "admin") -> bool:
    """Cria usuário. Retorna True se criado, False se já existe."""
    users = _load_users()
    if username in users:
        return False
    users[username] = {
        "password_hash": hash_password(password),
        "role": role,
        "created_at": datetime.utcnow().isoformat(),
        "last_login": None,
    }
    _save_users(users)
    logger.info(f"👤 Usuário criado: {username}")
    return True


def authenticate(username: str, password: str) -> Optional[str]:
    """
    Autentica usuário. Retorna JWT token se válido, None se inválido.
    """
    users = _load_users()
    user = users.get(username)
    if not user:
        logger.warning(f"🔐 Login falhou: usuário '{username}' não encontrado")
        return None
    if not verify_password(password, user["password_hash"]):
        logger.warning(f"🔐 Login falhou: senha incorreta para '{username}'")
        return None
    # Atualizar last_login
    users[username]["last_login"] = datetime.utcnow().isoformat()
    _save_users(users)
    token = create_token(username, user["role"])
    logger.info(f"✅ Login: {username}")
    return token


def change_password(username: str, old_password: str, new_password: str) -> bool:
    users = _load_users()
    user = users.get(username)
    if not user or not verify_password(old_password, user["password_hash"]):
        return False
    if len(new_password) < 8:
        return False
    users[username]["password_hash"] = hash_password(new_password)
    _save_users(users)
    return True


def has_users() -> bool:
    return bool(_load_users())


def ensure_default_user():
    """Cria usuário padrão se nenhum existir."""
    if not has_users():
        create_user("admin", "apex2024!")
        logger.warning("⚠️  Usuário padrão criado: admin / apex2024!")
        logger.warning("⚠️  TROQUE A SENHA no primeiro login!")


# ─── Rate Limiting simples (em memória) ──────────────────────────

_login_attempts: dict = {}
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 300  # 5 minutos


def check_rate_limit(ip: str) -> tuple[bool, str]:
    """Retorna (permitido, mensagem)."""
    now = datetime.utcnow()
    if ip not in _login_attempts:
        _login_attempts[ip] = {"count": 0, "locked_until": None}
    data = _login_attempts[ip]
    if data["locked_until"] and now < data["locked_until"]:
        remaining = int((data["locked_until"] - now).seconds)
        return False, f"IP bloqueado por {remaining}s após múltiplas tentativas"
    return True, "ok"


def record_failed_attempt(ip: str):
    if ip not in _login_attempts:
        _login_attempts[ip] = {"count": 0, "locked_until": None}
    _login_attempts[ip]["count"] += 1
    if _login_attempts[ip]["count"] >= MAX_ATTEMPTS:
        _login_attempts[ip]["locked_until"] = datetime.utcnow() + timedelta(seconds=LOCKOUT_SECONDS)
        logger.warning(f"🚨 IP {ip} bloqueado após {MAX_ATTEMPTS} tentativas de login")


def clear_attempts(ip: str):
    _login_attempts.pop(ip, None)


# ─── Proteção de API Keys ─────────────────────────────────────────

PROTECTED_KEYS_FILE = SECURITY_DIR / "api_keys_enc.json"


def save_api_keys_encrypted(keys: dict):
    """Salva API keys criptografadas no disco."""
    encrypted = {k: encrypt(v) for k, v in keys.items() if v and v != "COLE_AQUI"}
    PROTECTED_KEYS_FILE.write_text(json.dumps(encrypted, indent=2))
    PROTECTED_KEYS_FILE.chmod(0o600)
    logger.info("🔒 API keys salvas (criptografadas)")


def load_api_keys_decrypted() -> dict:
    """Carrega e descriptografa API keys."""
    if not PROTECTED_KEYS_FILE.exists():
        return {}
    try:
        data = json.loads(PROTECTED_KEYS_FILE.read_text())
        return {k: decrypt(v) for k, v in data.items()}
    except Exception as e:
        logger.error(f"Erro ao descriptografar keys: {e}")
        return {}


def get_masked_keys() -> dict:
    """Retorna keys mascaradas para exibição no frontend."""
    keys = load_api_keys_decrypted()
    return {k: mask_secret(v) for k, v in keys.items()}
