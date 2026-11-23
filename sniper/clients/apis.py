"""Бесплатные внешние API: IPFS-шлюзы, fxtwitter (X), Telegram Bot API, RugCheck, GoPlus."""
import asyncio
import re

import aiohttp

from config import BOT_TOKEN, IPFS_GATEWAYS
from sniper.clients.http import ApiError, get_json

IPFS_PATH_RE = re.compile(r"/ipfs/([A-Za-z0-9]{46,}(?:/[^?#]*)?)")


def metadata_urls(uri: str) -> list[str]:
    """Исходный URI плюс те же данные через альтернативные IPFS-шлюзы."""
    urls = [uri]
    match = IPFS_PATH_RE.search(uri)
    if match:
        urls += [gateway + match.group(1) for gateway in IPFS_GATEWAYS]
    return list(dict.fromkeys(urls))


async def fetch_metadata(session: aiohttp.ClientSession, uri: str, timeout: float) -> dict | None:
    """Запрашивает метаданные параллельно со всех шлюзов, возвращает первый валидный JSON."""

    async def fetch(url: str):
        try:
            _, data = await get_json(session, url, timeout=timeout)
            return data if isinstance(data, dict) else None
        except ApiError:
            return None

    tasks = [asyncio.create_task(fetch(url)) for url in metadata_urls(uri)]
    try:
        for next_done in asyncio.as_completed(tasks):
            data = await next_done
            if data is not None:
                return data
        return None
    finally:
        for task in tasks:
            task.cancel()


async def get_twitter_user(session: aiohttp.ClientSession, username: str) -> dict | None:
    """Профиль X через бесплатный fxtwitter API. None — аккаунт не существует."""
    status, data = await get_json(session, f"https://api.fxtwitter.com/{username}", timeout=6)
    if isinstance(data, dict):
        if data.get("code") == 200 and data.get("user"):
            return data["user"]
        if data.get("code") == 404:
            return None
    if status == 404:
        return None
    raise ApiError(f"fxtwitter: неожиданный ответ для @{username} (HTTP {status})")


async def get_telegram_member_count(session: aiohttp.ClientSession, chat: str) -> int | None:
    """Число участников публичного чата/канала. None — чат не найден или закрыт."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMemberCount"
    _, data = await get_json(session, url, params={"chat_id": f"@{chat}"}, timeout=5)
    if isinstance(data, dict) and data.get("ok"):
        return int(data["result"])
    return None


async def get_rugcheck_summary(session: aiohttp.ClientSession, mint: str) -> dict | None:
    _, data = await get_json(session, f"https://api.rugcheck.xyz/v1/tokens/{mint}/report/summary", timeout=10)
    return data if isinstance(data, dict) else None


async def get_goplus_security(session: aiohttp.ClientSession, mint: str) -> dict | None:
    _, data = await get_json(session, "https://api.gopluslabs.io/api/v1/solana/token_security",
                             params={"contract_addresses": mint}, timeout=8)
    if not isinstance(data, dict) or data.get("code") != 1:
        return None
    return (data.get("result") or {}).get(mint)
