"""Интеграция с публичными API Polymarket.

Источники:
- Gamma API: https://gamma-api.polymarket.com
- Data API: https://data-api.polymarket.com

Документация:
- https://docs.polymarket.com/api-reference/introduction
- https://docs.polymarket.com/api-reference/core/get-current-positions-for-a-user
- https://docs.polymarket.com/api-reference/core/get-user-activity
- https://docs.polymarket.com/api-reference/search/search-markets-events-and-profiles
- https://docs.polymarket.com/api-reference/events/list-events
"""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any

LOGGER = logging.getLogger(__name__)

GAMMA_API_BASE = "https://gamma-api.polymarket.com"
DATA_API_BASE = "https://data-api.polymarket.com"
POLYMARKET_PROFILE_URL = "https://polymarket.com/@nurly1"
POLYMARKET_PROFILE_USERNAME = os.getenv("POLYMARKET_PROFILE_USERNAME", "nurly1")

# Значение по умолчанию можно переопределить через POLYMARKET_PROFILE_ADDRESS.
# Если переменная не задана, бот попробует получить адрес через public-search.
DEFAULT_PROFILE_ADDRESS = "0x70702d4f3b26db557632751063a4f5b96b8f09de"


@dataclass(slots=True)
class Position:
    position_key: str
    market_name: str
    price: float
    amount: float
    pnl: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def fetch_polymarket_positions() -> list[dict[str, Any]]:
    """Возвращает текущие позиции пользователя из Data API."""

    user_address = get_profile_address()
    response = _get_json(
        f"{DATA_API_BASE}/positions",
        {"user": user_address, "sizeThreshold": "0"},
    )

    positions: list[dict[str, Any]] = []
    for item in _extract_items(response):
        market_name = (
            item.get("title")
            or item.get("marketName")
            or item.get("market")
            or item.get("question")
            or item.get("name")
            or "Без названия"
        )
        current_value = _to_float(
            item.get("currentValue")
            or item.get("redeemable")
            or item.get("cashPnl")
            or item.get("amount")
        )
        avg_price = _to_float(
            item.get("avgPrice")
            or item.get("price")
            or item.get("initialValue")
        )
        size = _to_float(
            item.get("size")
            or item.get("shares")
            or item.get("amount")
            or item.get("quantity")
        )
        pnl = _to_float(item.get("cashPnl") or item.get("curPnl") or item.get("pnl"))
        position_key = str(
            item.get("asset")
            or item.get("conditionId")
            or item.get("proxyWallet")
            or item.get("slug")
            or f"{market_name}-{avg_price}-{size}"
        )

        if size == 0 and current_value == 0:
            continue

        positions.append(
            Position(
                position_key=position_key,
                market_name=market_name,
                price=avg_price if avg_price else current_value,
                amount=size if size else current_value,
                pnl=pnl,
            ).to_dict()
        )

    LOGGER.info("Fetched %s live positions from Polymarket", len(positions))
    return positions


def fetch_recent_activity(limit: int = 20) -> list[dict[str, Any]]:
    """Возвращает свежую активность пользователя из Data API."""

    user_address = get_profile_address()
    response = _get_json(
        f"{DATA_API_BASE}/activity",
        {"user": user_address, "limit": str(limit), "offset": "0"},
    )

    activities: list[dict[str, Any]] = []
    for item in _extract_items(response):
        title = (
            item.get("title")
            or item.get("marketTitle")
            or item.get("question")
            or item.get("slug")
            or "Сделка без названия"
        )
        activities.append(
            {
                "activity_id": str(
                    item.get("id")
                    or item.get("transactionHash")
                    or item.get("txHash")
                    or item.get("timestamp")
                    or title
                ),
                "market_name": title,
                "price": _to_float(item.get("price") or item.get("avgPrice")),
                "amount": _to_float(
                    item.get("amount")
                    or item.get("size")
                    or item.get("shares")
                    or item.get("quantity")
                ),
                "side": str(item.get("side") or item.get("type") or "trade"),
                "timestamp": str(
                    item.get("timestamp")
                    or item.get("createdAt")
                    or item.get("time")
                    or ""
                ),
            }
        )

    LOGGER.info("Fetched %s activity rows from Polymarket", len(activities))
    return activities


def fetch_latest_news(limit: int = 5) -> list[dict[str, Any]]:
    """Возвращает свежие/активные события Polymarket из Gamma API.

    Это не редакционные новости, а последние активные события/рынки Polymarket.
    """

    response = _get_json(
        f"{GAMMA_API_BASE}/events",
        {
            "limit": str(limit),
            "offset": "0",
            "closed": "false",
            "order": "createdAt",
            "ascending": "false",
        },
    )

    news_items: list[dict[str, Any]] = []
    for item in _extract_items(response):
        title = item.get("title") or item.get("slug") or "Событие Polymarket"
        news_items.append(
            {
                "news_id": str(item.get("id") or item.get("slug") or title),
                "title": title,
                "slug": item.get("slug") or "",
                "category": item.get("category") or "Без категории",
                "volume": _to_float(item.get("volume") or item.get("volume24hr")),
                "created_at": str(item.get("createdAt") or item.get("published_at") or ""),
                "url": _build_event_url(item),
            }
        )

    LOGGER.info("Fetched %s news/event rows from Gamma API", len(news_items))
    return news_items


def fetch_featured_markets(limit: int = 5) -> list[dict[str, Any]]:
    """Возвращает активные рынки с объемом для раздела обзора."""

    response = _get_json(
        f"{GAMMA_API_BASE}/markets",
        {
            "limit": str(limit),
            "offset": "0",
            "closed": "false",
            "order": "volume",
            "ascending": "false",
        },
    )

    markets: list[dict[str, Any]] = []
    for item in _extract_items(response):
        markets.append(
            {
                "name": item.get("question") or item.get("slug") or "Рынок",
                "price": _extract_market_price(item),
                "volume": _to_float(item.get("volume")),
                "url": _build_market_url(item),
            }
        )
    return markets


def fetch_tracked_leaders() -> list[dict[str, Any]]:
    """Базовый список наблюдаемых трейдеров для интерфейса."""

    return [
        {"name": "swisstony", "wallet": get_profile_address(), "status": "отслеживается"},
        {"name": "risk-manager", "wallet": "позже можно добавить", "status": "не добавлен"},
        {"name": "gmanas", "wallet": "позже можно добавить", "status": "не добавлен"},
    ]


def get_profile_address() -> str:
    """Определяет адрес кошелька профиля Polymarket."""

    configured = os.getenv("POLYMARKET_PROFILE_ADDRESS", "").strip()
    if configured:
        return configured

    resolved = _resolve_profile_address(POLYMARKET_PROFILE_USERNAME)
    if resolved:
        return resolved

    LOGGER.warning(
        "Could not resolve profile address for @%s, using fallback address",
        POLYMARKET_PROFILE_USERNAME,
    )
    return DEFAULT_PROFILE_ADDRESS


def _resolve_profile_address(username: str) -> str | None:
    response = _get_json(
        f"{GAMMA_API_BASE}/public-search",
        {
            "q": username,
            "search_profiles": "true",
            "limit_per_type": "10",
        },
    )

    profiles = response.get("profiles") if isinstance(response, dict) else None
    if not isinstance(profiles, list):
        return None

    username_lower = username.lower()
    for profile in profiles:
        pseudonym = str(profile.get("pseudonym") or "").lower()
        name = str(profile.get("name") or "").lower()
        if username_lower in {pseudonym, name}:
            wallet = profile.get("proxyWallet")
            if wallet:
                return str(wallet)

    first_profile = profiles[0] if profiles else None
    if first_profile and first_profile.get("proxyWallet"):
        return str(first_profile["proxyWallet"])
    return None


def _get_json(base_url: str, params: dict[str, str]) -> Any:
    query = urllib.parse.urlencode(params, doseq=True)
    url = f"{base_url}?{query}" if query else base_url
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; PolymarketTelegramBot/1.0)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _extract_items(response: Any) -> list[dict[str, Any]]:
    if isinstance(response, list):
        return [item for item in response if isinstance(item, dict)]
    if isinstance(response, dict):
        for key in ("data", "items", "results"):
            value = response.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _extract_market_price(item: dict[str, Any]) -> float:
    outcomes = item.get("outcomePrices")
    if isinstance(outcomes, str):
        try:
            parsed = json.loads(outcomes)
            if isinstance(parsed, list) and parsed:
                return _to_float(parsed[0])
        except json.JSONDecodeError:
            return 0.0
    if isinstance(outcomes, list) and outcomes:
        return _to_float(outcomes[0])
    return _to_float(item.get("price"))


def _build_event_url(item: dict[str, Any]) -> str:
    slug = item.get("slug")
    if slug:
        return f"https://polymarket.com/event/{slug}"
    return POLYMARKET_PROFILE_URL


def _build_market_url(item: dict[str, Any]) -> str:
    slug = item.get("slug")
    if slug:
        return f"https://polymarket.com/market/{slug}"
    return POLYMARKET_PROFILE_URL
