"""Стадия B: ончейн-проверки mint-аккаунта и кошелька дева через Solana RPC (Helius)."""
import asyncio
import time

import config
from sniper.clients.helius import HeliusClient
from sniper.clients.http import ApiError
from sniper.models import CheckResult


def extension_risk(extension: dict) -> str | None:
    """Опасное расширение Token-2022 (блокирует продажу или даёт автору контроль над балансами)."""
    name = extension.get("extension")
    state = extension.get("state") or {}
    if name == "transferHook" and (state.get("programId") or state.get("authority")):
        return "Transfer hook (произвольная логика при переводе)"
    if name == "permanentDelegate" and state.get("delegate"):
        return "Permanent delegate (автор может списать токены)"
    if name == "nonTransferable":
        return "Токен непередаваемый"
    if name == "defaultAccountState" and state.get("accountState") != "initialized":
        return "Новые аккаунты заморожены по умолчанию"
    if name == "pausableConfig" and state.get("authority"):
        return "Переводы можно поставить на паузу"
    return None


def transfer_fee_bps(extensions: list[dict]) -> int:
    for extension in extensions:
        if extension.get("extension") == "transferFeeConfig":
            state = extension.get("state") or {}
            fees = [(state.get(key) or {}).get("transferFeeBasisPoints", 0)
                    for key in ("olderTransferFee", "newerTransferFee")]
            return max(fees)
    return 0


def evaluate_mint(info: dict | None) -> list[CheckResult]:
    if info is None:
        return [CheckResult.fail("authorities", "Mint-аккаунт не найден")]

    if info.get("mintAuthority"):
        return [CheckResult.fail("authorities", "Mint Authority не отозван — можно допечатать токены")]
    if info.get("freezeAuthority"):
        return [CheckResult.fail("authorities", "Freeze Authority не отозван — можно заморозить токены")]
    results = [CheckResult.ok("authorities", "Mint/Freeze authority отозваны")]

    extensions = info.get("extensions") or []
    risks = [risk for risk in map(extension_risk, extensions) if risk]
    if risks:
        results.append(CheckResult.fail("sellable", risks[0]))
        return results
    results.append(CheckResult.ok("sellable"))

    fee = transfer_fee_bps(extensions)
    if fee > config.MAX_TRANSFER_FEE_BPS:
        results.append(CheckResult.fail("tax", f"Налог на перевод {fee / 100:.2f}%"))
    else:
        results.append(CheckResult.ok("tax", "Налог на перевод 0%"))
    return results


async def check_mint(helius: HeliusClient, mint: str) -> list[CheckResult]:
    try:
        info = await helius.get_mint_info(mint)
        if info is None:
            # Событие из вебсокета может опередить RPC-ноду на пару сотен мс
            await asyncio.sleep(1.5)
            info = await helius.get_mint_info(mint)
    except ApiError as e:
        # Без проверки authorities токен пропускать нельзя
        return [CheckResult.fail("authorities", f"RPC недоступен: {e}")]
    return evaluate_mint(info)


def evaluate_dev_wallet(balance_sol: float, signatures: list[dict], now: float | None = None,
                        page_limit: int = 1000) -> list[CheckResult]:
    now = now or time.time()
    results = []

    if balance_sol < config.MIN_DEV_SOL_BALANCE:
        results.append(CheckResult.fail("dev_balance", f"На кошельке дева {balance_sol:.2f} SOL"))
        return results
    results.append(CheckResult.ok("dev_balance", f"Баланс дева {balance_sol:.2f} SOL"))

    times = [s["blockTime"] for s in signatures if s.get("blockTime")]
    if not times:
        results.append(CheckResult.skip("dev_age", "Нет истории транзакций"))
        return results

    # Если страница заполнена, самая старая подпись дает лишь нижнюю границу возраста
    age_min = (now - min(times)) / 60
    full_page = len(signatures) >= page_limit
    if age_min >= config.MIN_DEV_WALLET_AGE_MIN:
        results.append(CheckResult.ok("dev_age", f"Возраст кошелька дева {age_min / 60:.1f} ч" + ("+" if full_page else "")))
    elif full_page:
        results.append(CheckResult.skip("dev_age", f"{page_limit}+ транзакций менее чем за {age_min:.0f} мин"))
    else:
        results.append(CheckResult.fail("dev_age", f"Кошельку дева {age_min:.0f} мин"))
    return results


async def check_dev_wallet(helius: HeliusClient, dev: str) -> list[CheckResult]:
    try:
        balance, signatures = await asyncio.gather(
            helius.get_balance_sol(dev),
            helius.get_signatures(dev, limit=1000),
        )
    except ApiError as e:
        return [CheckResult.fail("dev_wallet", f"RPC недоступен: {e}")]
    return evaluate_dev_wallet(balance, signatures)
