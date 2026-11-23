import asyncio
import aiohttp


class ApiError(Exception):
    """Внешний сервис недоступен или ответил ошибкой (таймаут, 429, 5xx)."""


def create_session() -> aiohttp.ClientSession:
    return aiohttp.ClientSession(
        headers={"User-Agent": "Mozilla/5.0 (solana-bot)"},
        connector=aiohttp.TCPConnector(limit=100, ttl_dns_cache=300),
    )


async def get_json(session: aiohttp.ClientSession, url: str, *, params: dict | None = None,
                   timeout: float = 5.0) -> tuple[int, object | None]:
    """
    GET-запрос с разбором JSON. Возвращает (статус, данные).
    Данные None, если ответ не 200 или не JSON. Сетевые ошибки, 429 и 5xx — ApiError.
    """
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
            if response.status == 429 or response.status >= 500:
                raise ApiError(f"{url} -> HTTP {response.status}")
            if response.status != 200:
                return response.status, None
            try:
                return response.status, await response.json(content_type=None)
            except ValueError:
                return response.status, None
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        raise ApiError(f"{url} -> {type(e).__name__}") from e
