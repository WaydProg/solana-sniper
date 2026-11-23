from sniper.check_methods.onchain import evaluate_mint, evaluate_dev_wallet
from sniper.check_methods.security import evaluate_rugcheck, evaluate_goplus

PUMP_MINT = {
    "decimals": 6,
    "mintAuthority": None,
    "freezeAuthority": None,
    "extensions": [
        {"extension": "metadataPointer", "state": {"authority": None}},
        {"extension": "tokenMetadata", "state": {"updateAuthority": None}},
    ],
}


def names_and_status(results):
    return [(r.name, r.passed) for r in results]


def test_pump_mint_is_clean():
    assert names_and_status(evaluate_mint(PUMP_MINT)) == [("authorities", True), ("sellable", True), ("tax", True)]


def test_mint_authority_rejected():
    assert evaluate_mint({**PUMP_MINT, "freezeAuthority": "Abc"})[0].passed is False
    assert evaluate_mint(None)[0].passed is False


def test_dangerous_extensions():
    hook = {**PUMP_MINT, "extensions": [{"extension": "transferHook", "state": {"programId": "Hook"}}]}
    inert_hook = {**PUMP_MINT, "extensions": [{"extension": "transferHook", "state": {"programId": None, "authority": None}}]}
    assert evaluate_mint(hook)[-1].name == "sellable" and evaluate_mint(hook)[-1].passed is False
    assert all(r.passed for r in evaluate_mint(inert_hook))


def test_transfer_fee():
    fee = {**PUMP_MINT, "extensions": [{"extension": "transferFeeConfig", "state": {
        "olderTransferFee": {"transferFeeBasisPoints": 0},
        "newerTransferFee": {"transferFeeBasisPoints": 250},
    }}]}
    assert evaluate_mint(fee)[-1].name == "tax" and evaluate_mint(fee)[-1].passed is False


def test_dev_wallet():
    now = 1_000_000.0
    old = [{"blockTime": now - 60}, {"blockTime": now - 5 * 3600}]
    fresh = [{"blockTime": now - 60}, {"blockTime": now - 600}]
    assert names_and_status(evaluate_dev_wallet(2.0, old, now)) == [("dev_balance", True), ("dev_age", True)]
    assert evaluate_dev_wallet(2.0, fresh, now)[-1].passed is False
    assert evaluate_dev_wallet(0.1, old, now)[0].passed is False
    # Полная страница подписей за 10 минут — возраст неизвестен, не отсеиваем
    assert evaluate_dev_wallet(2.0, fresh, now, page_limit=2)[-1].passed is None


def test_rugcheck():
    clean = {"risks": [], "score": 1, "lpLockedPct": 100}
    danger = {"risks": [{"name": "Single holder ownership", "score": 5067, "level": "danger"}], "score": 5068}
    ignored = {"risks": [{"name": "Low Liquidity", "score": 900, "level": "danger"}], "score": 901, "lpLockedPct": 100}
    unlocked = {"risks": [], "score": 1, "lpLockedPct": 20}
    assert all(r.passed for r in evaluate_rugcheck(clean))
    assert evaluate_rugcheck(danger)[0].passed is False
    assert all(r.passed for r in evaluate_rugcheck(ignored))
    assert evaluate_rugcheck(unlocked)[-1].passed is False


def test_goplus():
    clean = {
        "balance_mutable_authority": {"authority": [], "status": "0"},
        "closable": {"authority": [], "status": "0"},
        "default_account_state": "1",
        "freezable": {"authority": [], "status": "0"},
        "mintable": {"authority": [], "status": "0"},
        "non_transferable": "0",
        "transfer_fee": {},
        "transfer_fee_upgradable": {"authority": [], "status": "0"},
        "transfer_hook": [],
        "transfer_hook_upgradable": {"authority": [], "status": "0"},
    }
    assert evaluate_goplus(clean).passed
    assert evaluate_goplus({**clean, "mintable": {"status": "1"}}).passed is False
    assert evaluate_goplus({**clean, "transfer_hook": ["Hook"]}).passed is False
