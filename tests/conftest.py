import asyncio
import os
import tempfile

# Тесты работают с отдельной временной БД, а не с db.sqlite3
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{os.path.join(tempfile.mkdtemp(), 'test.sqlite3')}"

import pytest

from database.models import async_main
from sniper.models import TokenEvent

asyncio.run(async_main())

CREATE_EVENT = {
    "signature": "CreateSig111",
    "mint": "Mint1111111111111111111111111111111111pump",
    "traderPublicKey": "Dev1111111111111111111111111111111111111111",
    "txType": "create",
    "name": "Franklin The Turtle",
    "symbol": "FRANKLIN",
    "uri": "https://ipfs.io/ipfs/QmQVRV6bmgYGcpwgjupekJQ5ZZNHwvPjDUc7To2VgLRpt1",
    "initialBuy": 34603511.859652,
    "bondingCurveKey": "Curve111111111111111111111111111111111111111",
    "vTokensInBondingCurve": 1073000000000000,
    "tokenProgram": "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
    "isMayhemMode": False,
    "isCashbackEnabled": False,
    "quoteMint": "So11111111111111111111111111111111111111112",
    "solAmount": 0.999719633,
}


@pytest.fixture
def raw_event() -> dict:
    return dict(CREATE_EVENT)


@pytest.fixture
def event(raw_event) -> TokenEvent:
    return TokenEvent.from_ws(raw_event)
