"""Стадия C: аудит безопасности через бесплатные RugCheck и GoPlus API."""
import aiohttp

import config
from sniper.clients import apis
from sniper.clients.http import ApiError
from sniper.models import CheckResult

# Флаги GoPlus, где status == "1" означает, что у автора остался контроль над токеном
GOPLUS_AUTHORITY_FLAGS = {
    "mintable": "можно допечатать токены",
    "freezable": "можно заморозить аккаунты",
    "closable": "можно закрыть mint",
    "balance_mutable_authority": "автор может менять балансы",
    "transfer_fee_upgradable": "можно включить налог на перевод",
    "transfer_hook_upgradable": "можно добавить transfer hook",
    "default_account_state_upgradable": "можно замораживать новые аккаунты",
}


def evaluate_rugcheck(report: dict) -> list[CheckResult]:
    risks = [r for r in report.get("risks") or [] if r.get("name") not in config.RUGCHECK_IGNORED_RISKS]
    ignored_score = sum(int(r.get("score") or 0) for r in report.get("risks") or []
                        if r.get("name") in config.RUGCHECK_IGNORED_RISKS)
    score = int(report.get("score") or 0) - ignored_score
    dangers = [r["name"] for r in risks if r.get("level") == "danger"]

    if len(dangers) > config.MAX_RUGCHECK_DANGER_RISKS:
        return [CheckResult.fail("rugcheck", f"Критические риски RugCheck: {', '.join(dangers)}")]
    if score > config.MAX_RUGCHECK_SCORE:
        names = ", ".join(r["name"] for r in risks) or "—"
        return [CheckResult.fail("rugcheck", f"Риск-скор RugCheck {score} ({names})")]
    results = [CheckResult.ok("rugcheck", f"RugCheck: Good (скор {score})")]

    lp_locked = report.get("lpLockedPct")
    if lp_locked is not None and float(lp_locked) < config.MIN_LP_LOCKED_PCT:
        results.append(CheckResult.fail("lp_locked", f"LP сожжено/заблокировано лишь на {float(lp_locked):.0f}%"))
    else:
        results.append(CheckResult.ok("lp_locked", f"LP сожжено/заблокировано: {float(lp_locked):.0f}%" if lp_locked is not None else ""))
    return results


def evaluate_goplus(data: dict) -> CheckResult:
    for flag, description in GOPLUS_AUTHORITY_FLAGS.items():
        if str((data.get(flag) or {}).get("status", "0")) == "1":
            return CheckResult.fail("goplus", f"GoPlus: {description}")
    if str(data.get("non_transferable", "0")) == "1":
        return CheckResult.fail("goplus", "GoPlus: токен непередаваемый")
    if data.get("transfer_hook"):
        return CheckResult.fail("goplus", "GoPlus: установлен transfer hook")
    if data.get("transfer_fee"):
        return CheckResult.fail("goplus", f"GoPlus: налог на перевод {data['transfer_fee']}")
    return CheckResult.ok("goplus", "GoPlus: рисков не найдено")


async def check_rugcheck(session: aiohttp.ClientSession, mint: str) -> list[CheckResult]:
    if not config.USE_RUGCHECK:
        return []
    try:
        report = await apis.get_rugcheck_summary(session, mint)
    except ApiError as e:
        return [CheckResult.unavailable("rugcheck", str(e))]
    if report is None:
        return [CheckResult.unavailable("rugcheck", "отчет не найден")]
    return evaluate_rugcheck(report)


async def check_goplus(session: aiohttp.ClientSession, mint: str) -> list[CheckResult]:
    if not config.USE_GOPLUS:
        return []
    try:
        data = await apis.get_goplus_security(session, mint)
    except ApiError as e:
        return [CheckResult.unavailable("goplus", str(e))]
    if data is None:
        return [CheckResult.skip("goplus", "Токен еще не проиндексирован GoPlus")]
    return [evaluate_goplus(data)]
