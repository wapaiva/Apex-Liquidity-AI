"""
APEX LIQUIDITY AI — Config Manager
Carrega, valida e salva configurações em tempo real.
"""
import json
import os
from pathlib import Path
from typing import Any
from loguru import logger

CONFIG_PATH = Path(__file__).parent / "runtime_config.json"


class ConfigManager:
    _instance = None

    def __new__(cls):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance._cfg = {}
            cls._instance._load()
        return cls._instance

    def _load(self):
        try:
            with open(CONFIG_PATH) as f:
                self._cfg = json.load(f)
            logger.info("✅ Config carregada")
        except Exception as e:
            logger.error(f"Config error: {e} — usando defaults")
            self._cfg = {}

    def get(self, *keys, default=None) -> Any:
        """cfg.get('risco', 'RISK_PER_TRADE') → 1.0"""
        obj = self._cfg
        for k in keys:
            if not isinstance(obj, dict) or k not in obj:
                return default
            obj = obj[k]
        return obj

    def set(self, section: str, key: str, value: Any):
        """Atualiza valor e persiste no disco."""
        if section not in self._cfg:
            self._cfg[section] = {}
        self._cfg[section][key] = value
        self._save()

    def update_section(self, section: str, data: dict):
        if section not in self._cfg:
            self._cfg[section] = {}
        self._cfg[section].update(data)
        self._save()

    def get_asset(self, symbol: str) -> dict:
        return self._cfg.get("ativos", {}).get(symbol, {"active": True, "risk_mult": 1.0, "sl_mult": 1.5, "tp_mult": 3.0})

    def all(self) -> dict:
        return self._cfg

    def _save(self):
        try:
            with open(CONFIG_PATH, "w") as f:
                json.dump(self._cfg, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Config save error: {e}")

    def reload(self):
        self._load()


cfg = ConfigManager()
