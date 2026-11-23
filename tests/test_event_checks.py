import pytest

from sniper.check_methods import run_event_checks, check_dev_history
from sniper.models import TokenEvent


def first_failure(raw: dict):
    return next((r for r in run_event_checks(TokenEvent.from_ws(raw)) if r.passed is False), None)


def test_good_event_passes(raw_event):
    assert first_failure(raw_event) is None


def test_usdc_quote_rejected_even_without_sol_amount(raw_event):
    raw_event.update(quoteMint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", solAmount=None)
    assert first_failure(raw_event).name == "quote"


@pytest.mark.parametrize("field", ["isMayhemMode", "isCashbackEnabled"])
def test_modes_rejected(raw_event, field):
    raw_event[field] = True
    assert first_failure(raw_event).name == "modes"


@pytest.mark.parametrize("sol", [0.05, 10.0])
def test_dev_buy_bounds(raw_event, sol):
    raw_event["solAmount"] = sol
    assert first_failure(raw_event).name == "dev_buy"


def test_dev_hold_pct(raw_event):
    raw_event["initialBuy"] = 150_000_000
    assert first_failure(raw_event).name == "dev_hold"


@pytest.mark.parametrize("symbol,name", [("X", "Fine"), ("TOOLONGTICKER", "Fine"), ("OK", "Rug pull")])
def test_name_checks(raw_event, symbol, name):
    raw_event.update(symbol=symbol, name=name)
    assert first_failure(raw_event).name == "name"


def test_missing_uri(raw_event):
    raw_event["uri"] = ""
    assert first_failure(raw_event).name == "metadata_uri"


def test_dev_history():
    assert check_dev_history(0).passed
    assert check_dev_history(2).passed is False
