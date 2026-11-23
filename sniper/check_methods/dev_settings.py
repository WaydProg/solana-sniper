"""Стадия A: мгновенные проверки по данным create-события, без сетевых запросов."""
from collections.abc import Callable

import config
from sniper.models import CheckResult, TokenEvent


def check_quote(event: TokenEvent) -> CheckResult:
    if event.quote_mint not in config.ALLOWED_QUOTE_MINTS:
        return CheckResult.fail("quote", f"Котировка не в SOL ({event.quote_mint[:6]}…)")
    return CheckResult.ok("quote")


def check_modes(event: TokenEvent) -> CheckResult:
    if event.is_mayhem:
        return CheckResult.fail("modes", "Включен MayhemMode")
    if event.is_cashback:
        return CheckResult.fail("modes", "Включен Cashback режим")
    return CheckResult.ok("modes")


def check_dev_buy(event: TokenEvent) -> CheckResult:
    if event.dev_sol < config.MIN_DEV_SOL:
        return CheckResult.fail("dev_buy", f"Слишком малый закуп дева: {event.dev_sol:.2f} SOL")
    if event.dev_sol > config.MAX_DEV_SOL:
        return CheckResult.fail("dev_buy", f"Слишком большой закуп дева: {event.dev_sol:.2f} SOL")
    return CheckResult.ok("dev_buy", f"Закуп дева {event.dev_sol:.2f} SOL")


def check_dev_hold(event: TokenEvent) -> CheckResult:
    if event.dev_hold_pct > config.MAX_DEV_HOLD_PCT:
        return CheckResult.fail("dev_hold", f"Дев держит {event.dev_hold_pct:.1f}% эмиссии")
    return CheckResult.ok("dev_hold", f"Дев держит {event.dev_hold_pct:.1f}% эмиссии")


def check_blacklist(event: TokenEvent) -> CheckResult:
    if event.dev in config.DEV_BLACKLIST:
        return CheckResult.fail("blacklist", f"Разработчик в черном списке: {event.dev}")
    return CheckResult.ok("blacklist")


def check_name(event: TokenEvent) -> CheckResult:
    if not config.MIN_SYMBOL_LEN <= len(event.symbol) <= config.MAX_SYMBOL_LEN:
        return CheckResult.fail("name", f"Некорректная длина тикера ({len(event.symbol)} симв.)")
    name, symbol = event.name.lower(), event.symbol.lower()
    for word in config.FORBIDDEN_WORDS:
        if word in name or word in symbol:
            return CheckResult.fail("name", f"Запрещенное слово в названии: {word}")
    return CheckResult.ok("name")


def check_uri(event: TokenEvent) -> CheckResult:
    if not event.uri.startswith("http"):
        return CheckResult.fail("metadata_uri", "Отсутствует мета-ссылка (URI)")
    return CheckResult.ok("metadata_uri")


def check_dev_history(previous_launches: int) -> CheckResult:
    if previous_launches > config.MAX_DEV_PREVIOUS_LAUNCHES:
        return CheckResult.fail(
            "dev_history",
            f"Серийный деплоер: {previous_launches} запусков за {config.DEV_HISTORY_DAYS} дн.",
        )
    return CheckResult.ok("dev_history", f"Прошлых запусков дева: {previous_launches}")


# Порядок важен: сначала самые частые причины отсева
EVENT_CHECKS: list[Callable[[TokenEvent], CheckResult]] = [
    check_quote,
    check_modes,
    check_dev_buy,
    check_dev_hold,
    check_blacklist,
    check_name,
    check_uri,
]


def run_event_checks(event: TokenEvent) -> list[CheckResult]:
    """Выполняет проверки по порядку до первой неудачной."""
    results = []
    for check in EVENT_CHECKS:
        result = check(event)
        results.append(result)
        if result.passed is False:
            break
    return results
