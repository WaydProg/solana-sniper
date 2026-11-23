import asyncio
import itertools

import pytest

import config
import database.requests as rq
from sniper.clients import apis
from sniper.models import TokenEvent
from sniper.pipeline import TokenPipeline
from tests.fakes import FakeHelius, FakeStream, make_trades

_counter = itertools.count()


@pytest.fixture
def fresh_raw(raw_event) -> dict:
    """Каждому тесту — уникальные mint и дев, чтобы не сработала история в общей БД."""
    n = next(_counter)
    raw_event.update(mint=f"Mint{n}pump", traderPublicKey=f"Dev{n}", signature=f"CreateSig{n}")
    return raw_event


@pytest.fixture
def online(monkeypatch):
    monkeypatch.setattr(config, "WATCH_WINDOW_SEC", 0)

    async def metadata(session, uri, timeout):
        # Уникальные ссылки, чтобы не сработала проверка повторного использования соцсетей
        n = next(_counter)
        return {"twitter": f"https://x.com/project{n}", "telegram": f"https://t.me/projectchat{n}"}

    async def twitter_user(session, username):
        return {"followers": 1000, "joined": "Thu Jan 11 05:47:40 +0000 2018"}

    async def tg_members(session, chat):
        return 500

    async def rugcheck(session, mint):
        return {"risks": [], "score": 1, "lpLockedPct": 100}

    async def goplus(session, mint):
        return {"mintable": {"status": "0"}}

    monkeypatch.setattr(apis, "fetch_metadata", metadata)
    monkeypatch.setattr(apis, "get_twitter_user", twitter_user)
    monkeypatch.setattr(apis, "get_telegram_member_count", tg_members)
    monkeypatch.setattr(apis, "get_rugcheck_summary", rugcheck)
    monkeypatch.setattr(apis, "get_goplus_security", goplus)


def run_pipeline(raw: dict, trades=None, **helius_kwargs):
    event = TokenEvent.from_ws(raw)
    notified = []

    async def on_pass(report):
        notified.append(report)

    async def run():
        pipeline = TokenPipeline(None, FakeHelius(event, **helius_kwargs), on_pass)
        pipeline.stream = FakeStream(make_trades(event.mint) if trades is None else trades)
        report = await pipeline.process(event)
        assert not pipeline.stream.watching, "подписка на сделки не снята"
        return pipeline, report

    pipeline, report = asyncio.run(run())
    return pipeline, report, notified


def test_good_token_passes_and_notifies(online, fresh_raw):
    pipeline, report, notified = run_pipeline(fresh_raw)
    assert report.failed is None, report.failed
    assert notified == [report]
    assert pipeline.stats.passed == 1
    assert {"authorities", "twitter", "telegram", "block0", "top10", "rugcheck", "goplus"} <= {r.name for r in report.results}


def test_dev_sell_rejects(online, fresh_raw):
    trades = make_trades(fresh_raw["mint"])
    trades.append({"signature": "devsell", "mint": fresh_raw["mint"], "traderPublicKey": fresh_raw["traderPublicKey"],
                   "txType": "sell", "tokenAmount": 1, "solAmount": 1})
    pipeline, report, notified = run_pipeline(fresh_raw, trades)
    assert report.failed.name == "dev_sold" and not notified
    assert pipeline.stats.rejected["dev_sold"] == 1


def test_bundle_rejects(online, fresh_raw):
    _, report, notified = run_pipeline(fresh_raw, block0_buyers=6)
    assert report.failed.name == "bundle" and not notified


def test_stage_a_reject_does_not_subscribe(online, fresh_raw):
    fresh_raw["isMayhemMode"] = True
    pipeline, report, _ = run_pipeline(fresh_raw)
    assert report.failed.name == "modes" and pipeline.stats.watched == 0


def test_serial_deployer_rejected(online, fresh_raw):
    asyncio.run(rq.register_launch("OlderMint", fresh_raw["traderPublicKey"], "old", "OLD", 7))
    _, report, _ = run_pipeline(fresh_raw)
    assert report.failed.name == "dev_history"


def test_reused_socials_rejected(online, fresh_raw, monkeypatch):
    async def metadata(session, uri, timeout):
        return {"twitter": "https://x.com/copied_project"}

    monkeypatch.setattr(apis, "fetch_metadata", metadata)
    _, first, _ = run_pipeline(fresh_raw)
    assert first.failed is None
    second_raw = {**fresh_raw, "mint": fresh_raw["mint"] + "2", "traderPublicKey": fresh_raw["traderPublicKey"] + "b"}
    _, second, _ = run_pipeline(second_raw)
    assert second.failed.name == "socials_reused"


def test_mint_authority_rejects(online, fresh_raw):
    _, report, _ = run_pipeline(fresh_raw, mint_info={"mintAuthority": "Auth", "freezeAuthority": None})
    assert report.failed.name == "authorities"


def test_external_api_down_is_skipped(online, fresh_raw, monkeypatch):
    from sniper.clients.http import ApiError

    async def down(session, mint):
        raise ApiError("timeout")

    monkeypatch.setattr(apis, "get_rugcheck_summary", down)
    _, report, notified = run_pipeline(fresh_raw)
    assert report.failed is None and notified
    assert next(r for r in report.results if r.name == "rugcheck").passed is None
