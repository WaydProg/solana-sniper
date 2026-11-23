import asyncio

import config
from sniper.check_methods.market import (TradeTracker, curve_progress, evaluate_market, check_block0,
                                         check_dev_sold, evaluate_top_holders, parse_buyers_from_tx,
                                         check_top_holders)
from tests.fakes import FakeHelius, make_trades, PROGRESS_20_V_TOKENS


def test_curve_progress():
    assert curve_progress(config.CURVE_INITIAL_VIRTUAL_TOKENS * 10 ** 6) == 0
    assert round(curve_progress(PROGRESS_20_V_TOKENS), 1) == 20.0
    assert curve_progress(0) == 100


def test_tracker_stats(event):
    tracker = TradeTracker(event)
    for trade in make_trades(event.mint) + make_trades(event.mint)[:3]:  # дубликаты игнорируются
        tracker.add(trade)
    stats = tracker.stats()
    assert stats["trades"] == 27
    assert stats["unique_buyers"] == 25
    assert round(stats["volume_sol"], 2) == 7.6
    assert stats["buy_sell_ratio"] == 12.5
    assert round(stats["curve_progress"], 1) == 20.0
    assert all(r.passed for r in evaluate_market(stats))


def test_initial_curve_progress_from_dev_buy(event):
    stats = TradeTracker(event).stats()
    assert 4 < stats["curve_progress"] < 5
    assert stats["buy_sell_ratio"] == float("inf")


def test_market_rejects_low_volume(event):
    tracker = TradeTracker(event)
    for trade in make_trades(event.mint, buyers=5, sol=0.1):
        tracker.add(trade)
    results = evaluate_market(tracker.stats())
    assert results[-1].name == "volume" and results[-1].passed is False


def test_dev_sell_detected(event):
    tracker = TradeTracker(event)
    tracker.add({"signature": "s", "traderPublicKey": event.dev, "txType": "sell", "tokenAmount": 1, "solAmount": 1})
    assert tracker.dev_sold and check_dev_sold(tracker).passed is False


def test_block0(event):
    tracker = TradeTracker(event)
    for trade in make_trades(event.mint):
        tracker.add(trade)
    ok = asyncio.run(check_block0(FakeHelius(event, block0_buyers=2), event, tracker))
    assert [(r.name, r.passed) for r in ok] == [("block0", True), ("bundle", True)]

    bundle = asyncio.run(check_block0(FakeHelius(event, block0_buyers=6), event, tracker))
    assert bundle[-1].name == "bundle" and bundle[-1].passed is False


def test_block0_paginates_past_spam(event):
    tracker = TradeTracker(event)
    for trade in make_trades(event.mint):
        tracker.add(trade)
    results = asyncio.run(check_block0(FakeHelius(event, block0_buyers=6, spam_txs=2500), event, tracker))
    assert results[-1].name == "bundle" and results[-1].passed is False


def test_wash_traders_not_counted_as_buyers(event):
    tracker = TradeTracker(event)
    for i in range(10):
        tracker.add({"signature": f"b{i}", "traderPublicKey": f"Bot{i}", "txType": "buy", "tokenAmount": 1000, "solAmount": 1})
        tracker.add({"signature": f"s{i}", "traderPublicKey": f"Bot{i}", "txType": "sell", "tokenAmount": 1000, "solAmount": 1})
    tracker.add({"signature": "real", "traderPublicKey": "Holder", "txType": "buy", "tokenAmount": 1000, "solAmount": 1})
    stats = tracker.stats()
    assert stats["unique_buyers"] == 1
    assert stats["round_trip_wallets"] == 10


def test_block0_heavy_buy(event):
    tracker = TradeTracker(event)
    for trade in make_trades(event.mint):
        trade["tokenAmount"] = 60_000_000
        tracker.add(trade)
    results = asyncio.run(check_block0(FakeHelius(event, block0_buyers=2), event, tracker))
    assert results[0].name == "block0" and results[0].passed is False


def test_parse_buyers_from_tx():
    tx = {"meta": {"err": None,
                   "preTokenBalances": [{"mint": "M", "owner": "curve", "uiTokenAmount": {"uiAmount": 100.0}}],
                   "postTokenBalances": [{"mint": "M", "owner": "curve", "uiTokenAmount": {"uiAmount": 60.0}},
                                         {"mint": "M", "owner": "buyer", "uiTokenAmount": {"uiAmount": 40.0}},
                                         {"mint": "X", "owner": "other", "uiTokenAmount": {"uiAmount": 5.0}}]}}
    assert parse_buyers_from_tx(tx, "M", "curve") == [("buyer", 40.0)]
    assert parse_buyers_from_tx({"meta": {"err": "fail"}}, "M", "curve") == []


def test_top_holders(event):
    result = asyncio.run(check_top_holders(FakeHelius(event), event))
    assert result.passed, result.detail
    heavy = [("curve", 700_000_000), *[(f"w{i}", 30_000_000) for i in range(10)]]
    assert evaluate_top_holders(heavy, "curve").passed is False
