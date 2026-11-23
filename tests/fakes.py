"""Подмены внешних сервисов для офлайн-тестов конвейера."""
import time
from collections import Counter

import config

DEV_TOKENS = 34_603_511.859652
PROGRESS_20_V_TOKENS = (config.CURVE_INITIAL_VIRTUAL_TOKENS - 0.2 * config.CURVE_REAL_TOKENS_FOR_SALE) * 10 ** 6


def make_trades(mint: str, buyers: int = 25, sells: int = 2, sol: float = 0.3) -> list[dict]:
    trades = [{
        "signature": f"buy{i}", "mint": mint, "traderPublicKey": f"Buyer{i}", "txType": "buy",
        "tokenAmount": 5_000_000, "solAmount": sol, "vTokensInBondingCurve": PROGRESS_20_V_TOKENS,
    } for i in range(buyers)]
    trades += [{
        "signature": f"sell{i}", "mint": mint, "traderPublicKey": f"Buyer{i}", "txType": "sell",
        "tokenAmount": 1_000_000, "solAmount": 0.05, "vTokensInBondingCurve": PROGRESS_20_V_TOKENS,
    } for i in range(sells)]
    return trades


class FakeStream:
    def __init__(self, trades: list[dict]):
        self.trades = trades
        self.watching: set[str] = set()

    async def watch(self, mint, handler):
        self.watching.add(mint)
        for trade in self.trades:
            if trade["mint"] == mint:
                handler(trade)

    async def unwatch(self, mint):
        self.watching.discard(mint)


class FakeHelius:
    def __init__(self, event, block0_buyers: int = 2, mint_info: dict | None = None, spam_txs: int = 5):
        self.event = event
        self.block0_buyers = block0_buyers
        # Неудачные транзакции снайперов после Block 0 — проверяем пагинацию подписей
        self.spam_txs = spam_txs
        self.calls = Counter()
        self.mint_info = mint_info if mint_info is not None else {
            "mintAuthority": None, "freezeAuthority": None, "extensions": []}

    async def get_mint_info(self, mint):
        return self.mint_info

    async def get_balance_sol(self, address):
        return 2.0

    async def get_signatures(self, address, limit=1000, before=None):
        if address == self.event.dev:
            return [{"signature": "old", "blockTime": time.time() - 30 * 24 * 3600}]
        sigs = [{"signature": f"later{i}", "slot": 101, "err": {"Custom": 3}} for i in range(self.spam_txs)]
        sigs += [{"signature": f"buy{i}", "slot": 100, "err": None} for i in range(self.block0_buyers)]
        sigs.append({"signature": self.event.signature, "slot": 100, "err": None})
        sigs.append({"signature": "prev", "slot": 99, "err": None})
        start = next(i + 1 for i, s in enumerate(sigs) if s["signature"] == before) if before else 0
        return sigs[start:start + limit]

    async def get_signature_slot(self, signature):
        return 100

    async def get_transaction(self, signature):
        return None

    async def get_token_largest_accounts(self, mint):
        accounts = [{"address": "curveAta", "amount": str(800_000_000 * 10 ** 6), "decimals": 6},
                    {"address": "devAta", "amount": str(int(DEV_TOKENS * 10 ** 6)), "decimals": 6}]
        accounts += [{"address": f"ata{i}", "amount": str(5_000_000 * 10 ** 6), "decimals": 6} for i in range(12)]
        return accounts

    async def get_token_account_owners(self, accounts):
        owners = {"curveAta": self.event.bonding_curve, "devAta": self.event.dev}
        return {a: owners.get(a, f"owner-{a}") for a in accounts}
