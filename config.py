import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
helius_token = os.getenv('helius_token')
LIST_ADMINS_ID = [1473795067] #1019204243

PUMP_WS_URL = "wss://pumpdev.io/ws"
HELIUS_RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={helius_token}"

SOL_MINT = "So11111111111111111111111111111111111111112"
TOTAL_SUPPLY = 1_000_000_000
TOKEN_DECIMALS = 6

# Параметры бондинг-кривой Pump.fun (в целых токенах)
CURVE_INITIAL_VIRTUAL_TOKENS = 1_073_000_000
CURVE_REAL_TOKENS_FOR_SALE = 793_100_000

# Если сторонний API (RugCheck, GoPlus, fxtwitter, Telegram) недоступен:
# False — проверка пропускается с пометкой, True — токен отсеивается
STRICT_EXTERNAL_API = False

# Лимит запросов к Helius (бесплатный тариф: 10 RPS, ~1M кредитов/мес)
HELIUS_MAX_RPS = 8

# ---------- Стадия A: параметры из события вебсокета ----------
ALLOWED_QUOTE_MINTS = {SOL_MINT}

MIN_DEV_SOL = 0.2
MAX_DEV_SOL = 3.5
MAX_DEV_HOLD_PCT = 10.0

MIN_SYMBOL_LEN = 2
MAX_SYMBOL_LEN = 10

DEV_BLACKLIST = {
    "11111111111111111111111111111111",
}

FORBIDDEN_WORDS = ["test", "scam", "pump", "rug", "devbuy"]

# Сколько токенов дев мог запустить до текущего (по истории, которую видел бот)
# Серийные деплоеры — основной источник рагов на Pump.fun
MAX_DEV_PREVIOUS_LAUNCHES = 0
DEV_HISTORY_DAYS = 7

# ---------- Стадия B: метаданные, соцсети, ончейн ----------
METADATA_TIMEOUT_SEC = 4.0
# Запросы идут параллельно, побеждает первый валидный ответ.
# pump.mypinata.cloud — шлюз, где Pump.fun пинит метаданные (~0.4 с); ipfs.io и dweb.link
# часто отвечают 429/403 (Cloudflare), публичный gateway.pinata.cloud — 5-10 с.
IPFS_GATEWAYS = [
    "https://pump.mypinata.cloud/ipfs/",
    "https://ipfs.filebase.io/ipfs/",
    "https://4everland.io/ipfs/",
]

REQUIRE_SOCIALS = True
# Ссылка на соцсеть уже использовалась другим токеном — типичный признак клона
REJECT_REUSED_SOCIALS = True

MIN_TWITTER_AGE_DAYS = 7
MIN_TWITTER_FOLLOWERS = 100

MIN_TELEGRAM_MEMBERS = 50
# Приватные инвайт-ссылки (t.me/+...) нельзя проверить без вступления
TELEGRAM_ALLOW_PRIVATE = False

MIN_DEV_WALLET_AGE_MIN = 60
MIN_DEV_SOL_BALANCE = 0.5

# Максимальный налог на перевод (расширение Token-2022 transferFee), в базисных пунктах
MAX_TRANSFER_FEE_BPS = 0

# ---------- Стадия C: окно наблюдения за торгами ----------
WATCH_WINDOW_SEC = 30
MAX_CONCURRENT_WATCHES = 30

REJECT_ON_DEV_SELL = True

MIN_VOLUME_SOL = 5.0
MIN_UNIQUE_BUYERS = 20
MIN_BUY_SELL_RATIO = 1.5
MIN_CURVE_PROGRESS = 10.0
MAX_CURVE_PROGRESS = 85.0

MAX_BLOCK_0_BUY_PCT = 15.0
MAX_BUNDLE_WALLETS = 3
MAX_TOP10_HOLD_PCT = 20.0

# ---------- Аудит безопасности ----------
USE_RUGCHECK = True
MAX_RUGCHECK_SCORE = 500
MAX_RUGCHECK_DANGER_RISKS = 0
# Риски RugCheck, которые для токена на бондинг-кривой не несут смысла
RUGCHECK_IGNORED_RISKS = {"Low Liquidity", "Low amount of LP Providers"}
MIN_LP_LOCKED_PCT = 100.0

USE_GOPLUS = True
