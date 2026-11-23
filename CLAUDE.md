# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Telegram bot (aiogram 3) that watches new Pump.fun token launches on Solana, runs them through a staged filter pipeline (the criteria come from `План разработки.md`), and sends tokens that pass to admin users with a full check report. Code comments, log messages and user-facing texts are in Russian.

Only free APIs are allowed: Helius RPC (free tier ≈ 10 RPS / ~1M credits per month), pumpdev.io websocket, IPFS gateways, fxtwitter, Telegram Bot API, RugCheck, GoPlus. Do not add paid services.

## Commands

- Python 3.14 venv in `.venv`; deps in `requirements.txt` (`.venv/bin/pip install -r requirements.txt`).
- Run: `.venv/bin/python bot.py`
- Dry run (no Telegram, notifications go to the log): `.venv/bin/python bot.py --dry-run --duration 180`. Add `--debug` to also log stage-A rejections.
- Tests (offline, use a temp DB): `.venv/bin/python -m pytest`. Single test: `.venv/bin/python -m pytest tests/test_market.py::test_block0`
- Secrets come from `.env`: `BOT_TOKEN`, `helius_token`. `test.py`/`test.json` are gitignored scratch files.

## Architecture

`sniper/pipeline.py` (`TokenPipeline`) is the core. It owns `PumpStream` (`sniper/pump_fun.py`), which uses one websocket both for `subscribeNewToken` and for per-token `subscribeTokenTrade`, and restores subscriptions after a reconnect. Each create event gets its own task, so the websocket reader never waits on network checks.

Stages go from cheap to expensive, to save Helius credits:
- **A**: event fields (`check_methods/dev_settings.py`) plus serial-deployer detection from the local DB history.
- Trade subscription starts right after A passes, so early trades are captured.
- **B**: metadata and socials (`socials.py`), then the mint account, Token-2022 extensions and the dev wallet (`onchain.py`, 3 RPC calls).
- **Watch window** of `WATCH_WINDOW_SEC`. It ends early if the dev sells.
- **C**: market metrics from `TradeTracker` (`market.py`), then Block 0 / bundle detection, top-10 holders, RugCheck and GoPlus (`security.py`).

Every check returns a `CheckResult` (`sniper/models.py`): `passed=True/False`, or `None` when it was skipped or the service was unavailable. Processing stops at the first `False`. If a third-party API is down, the check is skipped unless `STRICT_EXTERNAL_API=True`. Security-critical RPC checks (authorities, block0, top10) fail closed.

Every threshold lives in `config.py`.

Non-obvious details:
- **Event format.** Create events can be quoted in USDC. `solAmount` exists only for SOL quotes. All mints are Token-2022. `bondingCurveKey` in trade events is unreliable (often empty); use the one from the create event. `vTokensInBondingCurve` is in raw units (6 decimals).
- **Block 0.** Found by comparing the `slot` from `getSignaturesForAddress(bonding_curve)` with the slot of the create signature. Signature pages are followed back past sniper spam. Buyers are resolved from the trade stream, or else via `getTransaction` (capped).
- **Buyers and volume.** "Unique buyers" counts only wallets still holding ≥10% of what they bought. Wash-trading bots buy and sell the same amount, and curve progress reflects the net SOL inflow.
- **Sellability and tax.** The honeypot/tax checks read Token-2022 extensions from the mint account (transfer hook, permanent delegate, non-transferable, default frozen state, transfer fee). They do not simulate a sale.
- **Twitter.** X accounts are checked through fxtwitter; X community links can't be verified and are skipped. Telegram groups are checked with Bot API `getChatMemberCount`.
- **Metadata.** Fetched in parallel from several gateways. `pump.mypinata.cloud` is fast; `ipfs.io` and `dweb.link` rate-limit.
- **Database** (`database/`, SQLite): the `tokens` table holds dev launch history (cleaned after `DEV_HISTORY_DAYS`). `social_links` maps each link to the first mint that used it, so reused socials flag clones.
- **Telegram** (`app/`): monitoring starts at boot. Handlers respond only to `LIST_ADMINS_ID` (`/start`, `/stats`, `/pause`, `/resume`). `pipeline` and `notifier` are injected through `dp.start_polling(...)` kwargs. Notifications use HTML with escaping.

Tests use fakes in `tests/fakes.py` (`FakeHelius`, `FakeStream`) and a recording aiogram session in `tests/test_handlers.py`. The router is module-global and can be attached to only one `Dispatcher`.
