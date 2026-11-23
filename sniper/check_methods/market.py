"""Стадия C: динамика торгов в окне наблюдения, Block 0 / бандлы и концентрация холдеров."""
import logging
from dataclasses import dataclass

import config
from sniper.clients.helius import HeliusClient
from sniper.clients.http import ApiError
from sniper.models import CheckResult, TokenEvent

# Сколько транзакций Block 0 максимум разбираем через getTransaction (экономия кредитов Helius)
MAX_BLOCK0_TX_LOOKUPS = 15
# Сколько страниц по 1000 подписей листаем назад до слота создания (спам неудачных tx снайперов)
MAX_SIGNATURE_PAGES = 4


@dataclass
class Trade:
    signature: str
    trader: str
    is_buy: bool
    sol: float
    tokens: float


def curve_progress(v_tokens_raw: float) -> float:
    """Прогресс бондинг-кривой в % по виртуальному резерву токенов (в минимальных единицах)."""
    v_tokens = v_tokens_raw / 10 ** config.TOKEN_DECIMALS
    sold = config.CURVE_INITIAL_VIRTUAL_TOKENS - v_tokens
    return max(0.0, min(100.0, sold / config.CURVE_REAL_TOKENS_FOR_SALE * 100))


class TradeTracker:
    """Копит сделки по токену, пришедшие из вебсокета, пока идет окно наблюдения."""

    def __init__(self, event: TokenEvent):
        self.event = event
        self.trades: dict[str, Trade] = {}
        # Чистая позиция кошельков в токенах: отличает держателей от wash-трейдинг ботов,
        # которые покупают и сразу продают тот же объем
        self.positions: dict[str, float] = {}
        self.bought: dict[str, float] = {}
        self.dev_sold = False
        # До первой сделки состояние кривой известно из закупа дева
        self.v_tokens_raw = (config.CURVE_INITIAL_VIRTUAL_TOKENS - event.dev_tokens) * 10 ** config.TOKEN_DECIMALS

    def add(self, raw: dict):
        signature = raw.get("signature")
        tx_type = raw.get("txType")
        if not signature or signature in self.trades or tx_type not in ("buy", "sell"):
            return
        trade = Trade(
            signature=signature,
            trader=raw.get("traderPublicKey", ""),
            is_buy=tx_type == "buy",
            sol=float(raw.get("solAmount") or raw.get("quoteAmount") or 0),
            tokens=float(raw.get("tokenAmount") or 0),
        )
        self.trades[signature] = trade
        self.positions[trade.trader] = self.positions.get(trade.trader, 0) + (trade.tokens if trade.is_buy else -trade.tokens)
        if trade.is_buy:
            self.bought[trade.trader] = self.bought.get(trade.trader, 0) + trade.tokens
        if raw.get("vTokensInBondingCurve") is not None:
            self.v_tokens_raw = float(raw["vTokensInBondingCurve"])
        if trade.trader == self.event.dev and not trade.is_buy:
            self.dev_sold = True

    def stats(self) -> dict:
        trades = list(self.trades.values())
        buys = [t for t in trades if t.is_buy]
        sells = [t for t in trades if not t.is_buy]
        # Покупатель считается, только если все еще держит хотя бы 10% купленного
        holders = {w for w, bought in self.bought.items()
                   if w != self.event.dev and self.positions.get(w, 0) > bought * 0.1}
        buyers = {t.trader for t in buys if t.trader != self.event.dev}
        return {
            "trades": len(trades),
            "volume_sol": sum(t.sol for t in trades),
            "buys": len(buys),
            "sells": len(sells),
            "unique_buyers": len(holders),
            "round_trip_wallets": len(buyers - holders),
            "buy_sell_ratio": len(buys) / len(sells) if sells else float("inf"),
            "curve_progress": curve_progress(self.v_tokens_raw),
        }


def check_dev_sold(tracker: TradeTracker) -> CheckResult:
    if config.REJECT_ON_DEV_SELL and tracker.dev_sold:
        return CheckResult.fail("dev_sold", "Дев продал токены в окне наблюдения")
    return CheckResult.ok("dev_sold", "Дев не продавал")


def evaluate_market(stats: dict) -> list[CheckResult]:
    results = []
    window = config.WATCH_WINDOW_SEC
    ratio = stats["buy_sell_ratio"]
    ratio_text = "∞" if ratio == float("inf") else f"{ratio:.2f}"
    checks = [
        ("volume", stats["volume_sol"] >= config.MIN_VOLUME_SOL,
         f"Объем {stats['volume_sol']:.2f} SOL за {window} с"),
        ("buyers", stats["unique_buyers"] >= config.MIN_UNIQUE_BUYERS,
         f"{stats['unique_buyers']} уникальных покупателей"),
        ("buy_sell", ratio >= config.MIN_BUY_SELL_RATIO,
         f"Buy/Sell {stats['buys']}/{stats['sells']} = {ratio_text}"),
        ("curve", config.MIN_CURVE_PROGRESS <= stats["curve_progress"] <= config.MAX_CURVE_PROGRESS,
         f"Бондинг-кривая {stats['curve_progress']:.1f}%"),
    ]
    for name, passed, detail in checks:
        results.append(CheckResult(name, passed, detail))
        if not passed:
            break
    return results


def parse_buyers_from_tx(tx: dict, mint: str, bonding_curve: str) -> list[tuple[str, float]]:
    """Кошельки, у которых в транзакции вырос баланс токена (кроме бондинг-кривой)."""
    meta = (tx or {}).get("meta") or {}
    if meta.get("err"):
        return []

    def balances(key):
        result = {}
        for entry in meta.get(key) or []:
            if entry.get("mint") != mint:
                continue
            owner = entry.get("owner")
            amount = float((entry.get("uiTokenAmount") or {}).get("uiAmount") or 0)
            result[owner] = result.get(owner, 0) + amount
        return result

    pre, post = balances("preTokenBalances"), balances("postTokenBalances")
    buyers = []
    for owner, amount in post.items():
        delta = amount - pre.get(owner, 0)
        if owner and owner != bonding_curve and delta > 0:
            buyers.append((owner, delta))
    return buyers


async def check_block0(helius: HeliusClient, event: TokenEvent, tracker: TradeTracker) -> list[CheckResult]:
    """
    Покупки в том же слоте, что и создание токена (Block 0), — почти всегда бандл дева через Jito
    или заранее подготовленные снайперы. Считаем их долю в эмиссии и число кошельков.
    """
    try:
        create_slot = await helius.get_signature_slot(event.signature)
        if create_slot is None:
            return [CheckResult.skip("block0", "Не найден слот создания токена")]

        signatures: list[dict] = []
        for _ in range(MAX_SIGNATURE_PAGES):
            page = await helius.get_signatures(
                event.bonding_curve, limit=1000, before=signatures[-1]["signature"] if signatures else None)
            signatures += page
            if len(page) < 1000 or page[-1]["slot"] < create_slot:
                break
    except ApiError as e:
        return [CheckResult.fail("block0", f"RPC недоступен: {e}")]

    if not signatures or signatures[-1]["slot"] > create_slot:
        return [CheckResult.skip("block0", "Слишком много транзакций, Block 0 вне выборки")]

    block0 = [s["signature"] for s in signatures
              if s["slot"] == create_slot and s.get("err") is None and s["signature"] != event.signature]

    buyers: dict[str, float] = {}
    lookups = 0
    for signature in block0:
        trade = tracker.trades.get(signature)
        if trade:
            if trade.is_buy:
                buyers[trade.trader] = buyers.get(trade.trader, 0) + trade.tokens
            continue
        if lookups >= MAX_BLOCK0_TX_LOOKUPS:
            continue
        lookups += 1
        try:
            tx = await helius.get_transaction(signature)
        except ApiError as e:
            logging.warning(f"Не удалось получить транзакцию Block 0 {signature[:8]}: {e}")
            continue
        for owner, tokens in parse_buyers_from_tx(tx, event.mint, event.bonding_curve):
            buyers[owner] = buyers.get(owner, 0) + tokens

    dev_extra = buyers.pop(event.dev, 0)
    block0_tokens = event.dev_tokens + dev_extra + sum(buyers.values())
    block0_pct = block0_tokens / config.TOTAL_SUPPLY * 100
    wallets = len(buyers)

    results = []
    if block0_pct > config.MAX_BLOCK_0_BUY_PCT:
        results.append(CheckResult.fail("block0", f"В Block 0 выкуплено {block0_pct:.1f}% эмиссии"))
        return results
    results.append(CheckResult.ok("block0", f"Block 0: {block0_pct:.1f}% эмиссии"))

    if wallets > config.MAX_BUNDLE_WALLETS:
        results.append(CheckResult.fail("bundle", f"{wallets} кошельков купили в Block 0 (бандл)"))
    else:
        results.append(CheckResult.ok("bundle", f"Кошельков в Block 0: {wallets}"))
    return results


def evaluate_top_holders(holders: list[tuple[str | None, float]], bonding_curve: str) -> CheckResult:
    """holders — [(владелец, количество токенов)], отсортированные по убыванию."""
    real = [amount for owner, amount in holders if owner != bonding_curve and amount > 0]
    top10_pct = sum(real[:10]) / config.TOTAL_SUPPLY * 100
    if top10_pct > config.MAX_TOP10_HOLD_PCT:
        return CheckResult.fail("top10", f"Top 10 холдеров держат {top10_pct:.1f}%")
    return CheckResult.ok("top10", f"Top 10 холдеров: {top10_pct:.1f}%")


async def check_top_holders(helius: HeliusClient, event: TokenEvent) -> CheckResult:
    try:
        accounts = await helius.get_token_largest_accounts(event.mint)
        accounts = [a for a in accounts if int(a.get("amount") or 0) > 0]
        owners = await helius.get_token_account_owners([a["address"] for a in accounts]) if accounts else {}
    except ApiError as e:
        return CheckResult.fail("top10", f"RPC недоступен: {e}")

    holders = [(owners.get(a["address"]), int(a["amount"]) / 10 ** int(a.get("decimals", config.TOKEN_DECIMALS)))
               for a in accounts]
    return evaluate_top_holders(holders, event.bonding_curve)
