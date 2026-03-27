"""
APEX LIQUIDITY AI — News Analyzer
Coleta notícias e calcula sentimento com NLP (VADER + TextBlob).
"""
import asyncio
import httpx
from datetime import datetime
from typing import Optional
from loguru import logger

from config.api_keys import NEWS_API_KEY, FINNHUB_API_KEY


class NewsAnalyzer:

    def __init__(self):
        self._cache: dict = {}
        self._cache_time: dict = {}
        self.CACHE_TTL = 900  # 15 minutos

    async def get_sentiment(self, symbol: str) -> dict:
        """Retorna score de sentimento para o ativo (-1 a +1)."""
        cache_key = f"sentiment_{symbol}"
        if cache_key in self._cache_time:
            elapsed = (datetime.utcnow() - self._cache_time[cache_key]).seconds
            if elapsed < self.CACHE_TTL:
                return self._cache[cache_key]

        news = await self._fetch_news(symbol)
        sentiment = self._analyze_batch(news, symbol)

        self._cache[cache_key] = sentiment
        self._cache_time[cache_key] = datetime.utcnow()
        return sentiment

    async def _fetch_news(self, symbol: str) -> list:
        """Busca notícias de múltiplas fontes."""
        news = []

        # NewsAPI
        if NEWS_API_KEY != "COLE_AQUI":
            try:
                query_map = {
                    "EURUSD": "euro dollar forex ECB",
                    "XAUUSD": "gold price XAU",
                    "SP500": "S&P 500 stocks market",
                    "NAS100": "Nasdaq technology stocks",
                    "BTCUSDT": "Bitcoin BTC crypto",
                    "ETHUSDT": "Ethereum ETH crypto",
                    "US30": "Dow Jones industrial",
                }
                q = query_map.get(symbol, symbol)
                async with httpx.AsyncClient(timeout=8) as c:
                    r = await c.get("https://newsapi.org/v2/everything", params={
                        "q": q, "language": "en", "sortBy": "publishedAt",
                        "pageSize": 10, "apiKey": NEWS_API_KEY
                    })
                    if r.status_code == 200:
                        articles = r.json().get("articles", [])
                        for a in articles:
                            news.append({
                                "title": a.get("title", ""),
                                "description": a.get("description", ""),
                                "source": a.get("source", {}).get("name", ""),
                                "published": a.get("publishedAt", ""),
                            })
            except Exception as e:
                logger.debug(f"NewsAPI error: {e}")

        # Finnhub como fallback
        if len(news) == 0 and FINNHUB_API_KEY != "COLE_AQUI":
            try:
                async with httpx.AsyncClient(timeout=8) as c:
                    r = await c.get("https://finnhub.io/api/v1/news", params={
                        "category": "forex", "token": FINNHUB_API_KEY
                    })
                    if r.status_code == 200:
                        for a in r.json()[:10]:
                            news.append({"title": a.get("headline", ""), "description": a.get("summary", "")})
            except Exception as e:
                logger.debug(f"Finnhub news error: {e}")

        return news

    def _analyze_batch(self, articles: list, symbol: str) -> dict:
        """Analisa sentimento de uma lista de artigos."""
        if not articles:
            return {"score": 0, "label": "NEUTRAL", "impact": "BAIXO",
                    "score_contribution": 0, "count": 0, "articles": []}

        scores = []
        analyzed = []

        for article in articles:
            text = f"{article.get('title','')} {article.get('description','')}"
            score = self._vader_score(text, symbol)
            scores.append(score)
            label = "POSITIVO" if score > 0.1 else ("NEGATIVO" if score < -0.1 else "NEUTRO")
            analyzed.append({
                "title": article.get("title", "")[:100],
                "score": round(score, 3),
                "label": label,
                "source": article.get("source", ""),
                "published": article.get("published", ""),
            })

        avg_score = sum(scores) / len(scores) if scores else 0
        impact = "ALTO" if abs(avg_score) > 0.5 else ("MÉDIO" if abs(avg_score) > 0.2 else "BAIXO")
        label = "POSITIVO" if avg_score > 0.1 else ("NEGATIVO" if avg_score < -0.1 else "NEUTRAL")

        # Contribuição ao score do motor de decisão (-1, 0, +1)
        score_contribution = 1 if avg_score > 0.3 else (-1 if avg_score < -0.3 else 0)

        return {
            "score": round(avg_score, 3),
            "label": label,
            "impact": impact,
            "score_contribution": score_contribution,
            "count": len(articles),
            "articles": analyzed[:5],  # Top 5 para o dashboard
        }

    def _vader_score(self, text: str, symbol: str) -> float:
        """
        Score de sentimento baseado em palavras-chave financeiras.
        VADER simplificado sem dependência externa.
        """
        text_lower = text.lower()

        positive_words = [
            "bullish", "rally", "surge", "gain", "rise", "higher", "strong",
            "growth", "beat", "record", "upside", "positive", "recovery",
            "outperform", "buy", "upgrade", "boost", "profit"
        ]
        negative_words = [
            "bearish", "fall", "drop", "decline", "loss", "lower", "weak",
            "miss", "recession", "risk", "crash", "downside", "negative",
            "sell", "downgrade", "inflation", "crisis", "fear"
        ]

        pos = sum(1 for w in positive_words if w in text_lower)
        neg = sum(1 for w in negative_words if w in text_lower)
        total = pos + neg

        if total == 0:
            return 0.0
        return (pos - neg) / total


news_analyzer = NewsAnalyzer()
