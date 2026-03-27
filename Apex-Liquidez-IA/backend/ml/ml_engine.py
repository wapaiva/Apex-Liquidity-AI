"""
APEX LIQUIDITY AI — Machine Learning Engine
Random Forest + Gradient Boosting para previsão de direção de mercado.
Treina com histórico de trades reais e re-treina automaticamente.
"""
import os
import json
import pickle
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Optional
from loguru import logger

# Modelos com fallback gracioso
try:
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score
    SKLEARN_OK = True
except ImportError:
    SKLEARN_OK = False
    logger.warning("scikit-learn não instalado. ML desativado. Execute: pip install scikit-learn")

MODELS_DIR = Path("data/models")
MODELS_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_FILE = Path("data/trade_history.json")


class MLEngine:
    """
    Motor de Machine Learning que treina com dados históricos
    e prevê a probabilidade de WIN para cada sinal.
    """

    def __init__(self):
        self.rf_model = None
        self.gb_model = None
        self.scaler = None
        self.trained = False
        self.last_trained = None
        self.accuracy = 0.0
        self._load_models()

    # ─── Feature Engineering ─────────────────────────────────────

    def extract_features(self, indicators: dict) -> Optional[np.ndarray]:
        """
        Extrai vetor de features dos indicadores calculados.
        14 features: RSI, MACD, ADX, BB, VWAP, EMA, volume, etc.
        """
        try:
            ind = indicators
            features = [
                ind.get("rsi", {}).get("value", 50) / 100,
                ind.get("macd", {}).get("histogram", 0) * 1000,
                ind.get("adx", {}).get("adx", 20) / 100,
                1 if ind.get("adx", {}).get("trending", False) else 0,
                ind.get("bb", {}).get("position_pct", 50) / 100 if ind.get("bb", {}).get("position_pct") else 0.5,
                ind.get("bb", {}).get("width", 2) / 10,
                ind.get("vwap", {}).get("score", 0),
                ind.get("ema", {}).get("score", 0),
                ind.get("volume", {}).get("ratio", 1.0),
                1 if ind.get("volume", {}).get("high_volume", False) else 0,
                ind.get("stoch", {}).get("k", 50) / 100 if ind.get("stoch", {}).get("k") else 0.5,
                ind.get("cci", {}).get("value", 0) / 200,
                ind.get("obv", {}).get("score", 0),
                ind.get("mfi", {}).get("value", 50) / 100 if ind.get("mfi", {}).get("value") else 0.5,
            ]
            return np.array(features, dtype=float).reshape(1, -1)
        except Exception as e:
            logger.debug(f"Feature extraction error: {e}")
            return None

    # ─── Treino ──────────────────────────────────────────────────

    def train(self) -> dict:
        """
        Treina modelos com histórico de trades.
        Mínimo: 30 trades com resultado registrado.
        """
        if not SKLEARN_OK:
            return {"trained": False, "reason": "scikit-learn não instalado"}

        history = self._load_history()
        labeled = [t for t in history if t.get("result") in ("WIN", "LOSS") and t.get("features")]

        if len(labeled) < 30:
            return {
                "trained": False,
                "reason": f"Dados insuficientes: {len(labeled)}/30 trades com features"
            }

        # Montar dataset
        X, y = [], []
        for t in labeled:
            feats = t.get("features")
            if feats and len(feats) == 14:
                X.append(feats)
                y.append(1 if t["result"] == "WIN" else 0)

        X = np.array(X)
        y = np.array(y)

        if len(X) < 20:
            return {"trained": False, "reason": "Features inválidas no histórico"}

        # Split treino/teste
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

        # Normalizar
        self.scaler = StandardScaler()
        X_train_s = self.scaler.fit_transform(X_train)
        X_test_s  = self.scaler.transform(X_test)

        # Random Forest
        self.rf_model = RandomForestClassifier(
            n_estimators=100, max_depth=8, min_samples_split=5,
            random_state=42, class_weight="balanced"
        )
        self.rf_model.fit(X_train_s, y_train)
        rf_acc = accuracy_score(y_test, self.rf_model.predict(X_test_s))

        # Gradient Boosting
        self.gb_model = GradientBoostingClassifier(
            n_estimators=100, learning_rate=0.05, max_depth=4,
            random_state=42, subsample=0.8
        )
        self.gb_model.fit(X_train_s, y_train)
        gb_acc = accuracy_score(y_test, self.gb_model.predict(X_test_s))

        self.accuracy = round((rf_acc + gb_acc) / 2, 4)
        self.trained = True
        self.last_trained = datetime.utcnow().isoformat()

        # Salvar modelos
        self._save_models()

        logger.info(f"🤖 ML treinado: RF={rf_acc:.2%} | GB={gb_acc:.2%} | Média={self.accuracy:.2%} | {len(X)} samples")
        return {
            "trained": True,
            "samples": len(X),
            "rf_accuracy": round(rf_acc, 4),
            "gb_accuracy": round(gb_acc, 4),
            "avg_accuracy": self.accuracy,
            "timestamp": self.last_trained,
        }

    # ─── Predição ────────────────────────────────────────────────

    def predict(self, indicators: dict) -> dict:
        """
        Prevê probabilidade de WIN para o sinal atual.
        Retorna ensemble RF + GB.
        """
        if not self.trained or not SKLEARN_OK:
            return {"probability": 0.5, "confidence": 0, "active": False}

        features = self.extract_features(indicators)
        if features is None:
            return {"probability": 0.5, "confidence": 0, "active": False}

        try:
            X_scaled = self.scaler.transform(features)
            rf_prob  = self.rf_model.predict_proba(X_scaled)[0][1]
            gb_prob  = self.gb_model.predict_proba(X_scaled)[0][1]
            ensemble = (rf_prob * 0.5 + gb_prob * 0.5)
            confidence = abs(ensemble - 0.5) * 200  # 0-100

            return {
                "probability": round(float(ensemble), 4),
                "rf_probability": round(float(rf_prob), 4),
                "gb_probability": round(float(gb_prob), 4),
                "confidence": round(float(confidence), 1),
                "signal": "WIN" if ensemble > 0.55 else ("LOSS" if ensemble < 0.45 else "NEUTRAL"),
                "active": True,
                "model_accuracy": self.accuracy,
            }
        except Exception as e:
            logger.warning(f"ML predict error: {e}")
            return {"probability": 0.5, "confidence": 0, "active": False}

    def ml_score_contribution(self, indicators: dict) -> int:
        """Retorna contribuição ao score: +1, 0, ou -1"""
        pred = self.predict(indicators)
        if not pred.get("active"):
            return 0
        p = pred["probability"]
        return 1 if p > 0.6 else (-1 if p < 0.4 else 0)

    # ─── Persistência ────────────────────────────────────────────

    def _save_models(self):
        try:
            data = {"rf": self.rf_model, "gb": self.gb_model, "scaler": self.scaler,
                    "accuracy": self.accuracy, "last_trained": self.last_trained}
            with open(MODELS_DIR / "apex_models.pkl", "wb") as f:
                pickle.dump(data, f)
        except Exception as e:
            logger.error(f"Erro ao salvar modelos: {e}")

    def _load_models(self):
        model_file = MODELS_DIR / "apex_models.pkl"
        if not model_file.exists():
            return
        try:
            with open(model_file, "rb") as f:
                data = pickle.load(f)
            self.rf_model    = data["rf"]
            self.gb_model    = data["gb"]
            self.scaler      = data["scaler"]
            self.accuracy    = data.get("accuracy", 0)
            self.last_trained = data.get("last_trained")
            self.trained     = True
            logger.info(f"✅ Modelos ML carregados (acc={self.accuracy:.2%})")
        except Exception as e:
            logger.warning(f"Erro ao carregar modelos ML: {e}")

    def _load_history(self) -> list:
        if not HISTORY_FILE.exists():
            return []
        try:
            with open(HISTORY_FILE) as f:
                return json.load(f)
        except Exception:
            return []

    def status(self) -> dict:
        return {
            "active": self.trained and SKLEARN_OK,
            "sklearn_available": SKLEARN_OK,
            "accuracy": self.accuracy,
            "last_trained": self.last_trained,
        }


ml_engine = MLEngine()
