import asyncio
from collections import Counter

import aiohttp
from aiolimiter import AsyncLimiter

from sniper.clients.http import ApiError


class HeliusClient:
    """JSON-RPC клиент Solana (Helius) с лимитом запросов и повтором при 429/5xx."""

    def __init__(self, session: aiohttp.ClientSession, url: str, max_rps: int, retries: int = 2):
        self.session = session
        self.url = url
        self.retries = retries
        self.limiter = AsyncLimiter(max_rps, 1)
        # Счетчик вызовов по методам — чтобы следить за расходом бесплатных кредитов
        self.calls: Counter[str] = Counter()

    async def call(self, method: str, params: list):
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        last_error = None

        for attempt in range(self.retries + 1):
            async with self.limiter:
                self.calls[method] += 1
                try:
                    async with self.session.post(self.url, json=payload,
                                                 timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status == 429 or response.status >= 500:
                            raise ApiError(f"{method} -> HTTP {response.status}")
                        data = await response.json(content_type=None)
                except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, ApiError) as e:
                    last_error = e
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue

            if "error" in data:
                raise ApiError(f"{method}: {data['error']}")
            return data.get("result")

        raise ApiError(f"{method}: {last_error!r}")

    async def get_mint_info(self, mint: str) -> dict | None:
        result = await self.call("getAccountInfo", [mint, {"encoding": "jsonParsed", "commitment": "confirmed"}])
        value = (result or {}).get("value")
        if not value:
            return None
        return value["data"]["parsed"]["info"]

    async def get_balance_sol(self, address: str) -> float:
        result = await self.call("getBalance", [address, {"commitment": "confirmed"}])
        return result["value"] / 1e9

    async def get_signatures(self, address: str, limit: int = 1000, before: str | None = None) -> list[dict]:
        options = {"limit": limit, "commitment": "confirmed"}
        if before:
            options["before"] = before
        return await self.call("getSignaturesForAddress", [address, options]) or []

    async def get_signature_slot(self, signature: str) -> int | None:
        result = await self.call("getSignatureStatuses", [[signature], {"searchTransactionHistory": True}])
        status = (result or {}).get("value", [None])[0]
        return status["slot"] if status else None

    async def get_transaction(self, signature: str) -> dict | None:
        return await self.call("getTransaction", [signature, {
            "encoding": "jsonParsed",
            "commitment": "confirmed",
            "maxSupportedTransactionVersion": 0,
        }])

    async def get_token_largest_accounts(self, mint: str) -> list[dict]:
        result = await self.call("getTokenLargestAccounts", [mint, {"commitment": "confirmed"}])
        return (result or {}).get("value", [])

    async def get_token_account_owners(self, accounts: list[str]) -> dict[str, str]:
        """Возвращает {token_account: owner} для списка токен-аккаунтов."""
        result = await self.call("getMultipleAccounts", [accounts, {"encoding": "jsonParsed", "commitment": "confirmed"}])
        owners = {}
        for address, value in zip(accounts, (result or {}).get("value", [])):
            try:
                owners[address] = value["data"]["parsed"]["info"]["owner"]
            except (TypeError, KeyError):
                continue
        return owners
