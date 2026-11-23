"""
Конвейер фильтрации новых токенов. Проверки идут от дешевых к дорогим:

A. Данные create-события (мгновенно, без сети) + история дева из локальной БД.
B. Метаданные и соцсети (бесплатные API), затем mint-аккаунт и кошелек дева (3 RPC-вызова).
C. Окно наблюдения WATCH_WINDOW_SEC: сделки из вебсокета -> рыночные метрики,
   затем Block 0 / бандлы, Top 10 холдеров (RPC), RugCheck и GoPlus.

Подписка на сделки включается сразу после стадии A, чтобы не пропустить первые покупки.
"""
import asyncio
import logging
import time
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import aiohttp

import config
import database.requests as rq
from sniper import check_methods as checks
from sniper.clients import apis
from sniper.clients.helius import HeliusClient
from sniper.models import CheckResult, TokenEvent, TokenReport
from sniper.pump_fun import PumpStream

# Отсев на стадии A массовый, его пишем в лог только на уровне DEBUG
STAGE_A_NAMES = {"quote", "modes", "dev_buy", "dev_hold", "blacklist", "name", "metadata_uri", "dev_history"}


@dataclass
class PipelineStats:
    started_at: float = field(default_factory=time.time)
    seen: int = 0
    stage_a_passed: int = 0
    watched: int = 0
    passed: int = 0
    rejected: Counter = field(default_factory=Counter)


class TokenPipeline:
    def __init__(self, session: aiohttp.ClientSession, helius: HeliusClient,
                 on_pass: Callable[[TokenReport], Awaitable[None]], ws_url: str = config.PUMP_WS_URL):
        self.session = session
        self.helius = helius
        self.on_pass = on_pass
        self.stream = PumpStream(ws_url, self.handle_create)
        self.stats = PipelineStats()
        self.active_watches = 0
        self._tasks: set[asyncio.Task] = set()

    async def run(self):
        await asyncio.gather(self.stream.run(), self._maintenance())

    def handle_create(self, raw: dict):
        try:
            event = TokenEvent.from_ws(raw)
        except (KeyError, TypeError, ValueError) as e:
            logging.warning(f"Некорректное create-событие: {e!r}")
            return
        task = asyncio.create_task(self.process(event))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def process(self, event: TokenEvent) -> TokenReport:
        report = TokenReport(event)
        try:
            passed = await self._process(report)
        except Exception as e:
            logging.exception(f"Ошибка обработки токена {event.mint}")
            report.add(CheckResult.fail("internal_error", repr(e)))
            passed = False

        if passed:
            self.stats.passed += 1
            await rq.set_token_status(event.mint, "passed")
            logging.info(f"✅ {event.symbol} ({event.mint}) прошел все проверки")
            try:
                await self.on_pass(report)
            except Exception:
                logging.exception(f"Ошибка отправки уведомления по {event.mint}")
        else:
            failed = report.failed
            self.stats.rejected[failed.name] += 1
            await rq.set_token_status(event.mint, "rejected", failed.name, failed.detail)
            level = logging.DEBUG if failed.name in STAGE_A_NAMES else logging.INFO
            logging.log(level, f"❌ {event.symbol} ({event.mint[:8]}…): {failed.detail}")
        return report

    async def _process(self, report: TokenReport) -> bool:
        event = report.event
        self.stats.seen += 1
        previous_launches = await rq.register_launch(
            event.mint, event.dev, event.name, event.symbol, config.DEV_HISTORY_DAYS)

        # ---------- Стадия A ----------
        for result in checks.run_event_checks(event):
            if not report.add(result):
                return False
        if not report.add(checks.check_dev_history(previous_launches)):
            return False
        self.stats.stage_a_passed += 1

        if self.active_watches >= config.MAX_CONCURRENT_WATCHES:
            report.add(CheckResult.fail("overload", "Превышен лимит одновременных наблюдений"))
            return False

        self.active_watches += 1
        self.stats.watched += 1
        tracker = checks.TradeTracker(event)
        await self.stream.watch(event.mint, tracker.add)
        try:
            # ---------- Стадия B ----------
            if not await self._stage_b(report):
                return False
            # ---------- Окно наблюдения ----------
            await self._wait_window(event, tracker)
        finally:
            await self.stream.unwatch(event.mint)
            self.active_watches -= 1

        # ---------- Стадия C ----------
        return await self._stage_c(report, tracker)

    async def _stage_b(self, report: TokenReport) -> bool:
        event = report.event

        metadata = await apis.fetch_metadata(self.session, event.uri, config.METADATA_TIMEOUT_SEC)
        if not report.add(checks.check_metadata(metadata)):
            return False
        report.socials = checks.extract_socials(metadata)
        if not report.add(checks.check_socials_present(report.socials)):
            return False

        reused = await rq.claim_social_links(event.mint, report.socials.links())
        if not report.add(checks.check_reused_socials(reused)):
            return False

        social_results = await asyncio.gather(
            checks.check_twitter(self.session, report.socials),
            checks.check_telegram(self.session, report.socials),
        )
        if not all(report.add(r) for r in social_results):
            return False

        # Платные по кредитам Helius проверки — только для токенов, прошедших бесплатные
        mint_results, dev_results = await asyncio.gather(
            checks.check_mint(self.helius, event.mint),
            checks.check_dev_wallet(self.helius, event.dev),
        )
        return all(report.add(r) for r in [*mint_results, *dev_results])

    async def _wait_window(self, event: TokenEvent, tracker: checks.TradeTracker):
        deadline = event.received_at + config.WATCH_WINDOW_SEC
        while (remaining := deadline - time.time()) > 0:
            if config.REJECT_ON_DEV_SELL and tracker.dev_sold:
                return
            await asyncio.sleep(min(1.0, remaining))

    async def _stage_c(self, report: TokenReport, tracker: checks.TradeTracker) -> bool:
        event = report.event
        report.metrics = tracker.stats()

        if not report.add(checks.check_dev_sold(tracker)):
            return False
        if not all(report.add(r) for r in checks.evaluate_market(report.metrics)):
            return False

        block0, top10, rugcheck, goplus = await asyncio.gather(
            checks.check_block0(self.helius, event, tracker),
            checks.check_top_holders(self.helius, event),
            checks.check_rugcheck(self.session, event.mint),
            checks.check_goplus(self.session, event.mint),
        )
        return all(report.add(r) for r in [*block0, top10, *rugcheck, *goplus])

    async def _maintenance(self):
        while True:
            try:
                await rq.cleanup_history(config.DEV_HISTORY_DAYS)
            except Exception:
                logging.exception("Ошибка очистки истории")
            await asyncio.sleep(3600)

    def summary(self) -> str:
        s = self.stats
        uptime_min = (time.time() - s.started_at) / 60
        top = ", ".join(f"{name}: {count}" for name, count in s.rejected.most_common(8)) or "—"
        rpc = sum(self.helius.calls.values())
        return (f"За {uptime_min:.0f} мин: новых {s.seen}, прошли стадию A {s.stage_a_passed}, "
                f"наблюдалось {s.watched}, сейчас {self.active_watches}, прошли все {s.passed}. "
                f"RPC-вызовов: {rpc}. Причины отсева: {top}")
