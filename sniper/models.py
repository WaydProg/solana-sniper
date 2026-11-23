from dataclasses import dataclass, field
from time import time

import config
from config import SOL_MINT, TOTAL_SUPPLY


@dataclass
class CheckResult:
    """Результат одной проверки. passed=None — проверку не удалось выполнить (API недоступен и т.п.)."""
    name: str
    passed: bool | None
    detail: str = ""

    @classmethod
    def ok(cls, name: str, detail: str = "") -> "CheckResult":
        return cls(name, True, detail)

    @classmethod
    def fail(cls, name: str, detail: str) -> "CheckResult":
        return cls(name, False, detail)

    @classmethod
    def skip(cls, name: str, detail: str) -> "CheckResult":
        return cls(name, None, detail)

    @classmethod
    def unavailable(cls, name: str, reason: str) -> "CheckResult":
        """Сторонний сервис не ответил: пропускаем или отсеиваем в зависимости от STRICT_EXTERNAL_API."""
        return cls(name, False if config.STRICT_EXTERNAL_API else None, f"Сервис недоступен: {reason}")


@dataclass
class TokenEvent:
    """Событие создания токена из вебсокета Pump.fun."""
    mint: str
    signature: str
    dev: str
    name: str
    symbol: str
    uri: str
    bonding_curve: str
    quote_mint: str
    dev_sol: float
    dev_tokens: float
    token_program: str
    is_mayhem: bool
    is_cashback: bool
    received_at: float = field(default_factory=time)

    @property
    def dev_hold_pct(self) -> float:
        return self.dev_tokens / TOTAL_SUPPLY * 100

    @classmethod
    def from_ws(cls, event: dict) -> "TokenEvent":
        quote_mint = event.get("quoteMint") or SOL_MINT
        # Для SOL-токенов сумма в solAmount; для прочих котировок SOL-суммы нет
        dev_sol = event.get("solAmount") if quote_mint == SOL_MINT else None
        return cls(
            mint=event["mint"],
            signature=event.get("signature", ""),
            dev=event.get("traderPublicKey", ""),
            name=(event.get("name") or "").strip(),
            symbol=(event.get("symbol") or "").strip(),
            uri=(event.get("uri") or "").strip(),
            bonding_curve=event.get("bondingCurveKey", ""),
            quote_mint=quote_mint,
            dev_sol=float(dev_sol or 0),
            dev_tokens=float(event.get("initialBuy") or 0),
            token_program=event.get("tokenProgram", ""),
            is_mayhem=bool(event.get("isMayhemMode")),
            is_cashback=bool(event.get("isCashbackEnabled")),
        )


@dataclass
class Socials:
    twitter: str | None = None
    telegram: str | None = None
    website: str | None = None

    def links(self) -> list[str]:
        return [link for link in (self.twitter, self.telegram, self.website) if link]


@dataclass
class TokenReport:
    event: TokenEvent
    results: list[CheckResult] = field(default_factory=list)
    socials: Socials = field(default_factory=Socials)
    metrics: dict = field(default_factory=dict)

    @property
    def failed(self) -> CheckResult | None:
        return next((r for r in self.results if r.passed is False), None)

    def add(self, result: CheckResult) -> bool:
        """Добавляет результат и возвращает True, если токен всё ещё проходит."""
        self.results.append(result)
        return result.passed is not False
