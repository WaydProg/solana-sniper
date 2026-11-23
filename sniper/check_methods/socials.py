"""Стадия B: метаданные токена и соцсети (IPFS, X через fxtwitter, Telegram Bot API)."""
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import aiohttp

import config
from sniper.clients import apis
from sniper.clients.http import ApiError
from sniper.models import CheckResult, Socials

TWITTER_HOSTS = {"x.com", "twitter.com", "mobile.twitter.com", "mobile.x.com"}
TELEGRAM_HOSTS = {"t.me", "telegram.me", "telegram.dog"}
TWITTER_RESERVED_PATHS = {"i", "home", "search", "intent", "hashtag", "share", "explore",
                          "notifications", "messages", "communities", "settings"}
TWITTER_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{1,15}$")
TELEGRAM_CHAT_RE = re.compile(r"^[A-Za-z0-9_]{4,32}$")


def normalize_url(value) -> str | None:
    """Приводит ссылку к каноничному виду, чтобы одинаковые ссылки совпадали при сравнении."""
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    if value.startswith("@"):
        value = f"x.com/{value[1:]}"
    if not re.match(r"^https?://", value, re.IGNORECASE):
        value = "https://" + value
    parsed = urlparse(value)
    host = parsed.netloc.lower().removeprefix("www.")
    if not host or "." not in host:
        return None
    if host in TWITTER_HOSTS:
        host = "x.com"
    elif host in TELEGRAM_HOSTS:
        host = "t.me"
    return f"https://{host}{parsed.path.rstrip('/')}"


def extract_socials(metadata: dict) -> Socials:
    """Собирает ссылки из метаданных и раскладывает их по типу по домену, а не по имени поля."""
    sources = [metadata]
    for nested in ("extensions", "properties"):
        if isinstance(metadata.get(nested), dict):
            sources.append(metadata[nested])

    socials = Socials()
    for source in sources:
        for key in ("twitter", "telegram", "website"):
            url = normalize_url(source.get(key))
            if not url:
                continue
            parsed = urlparse(url)
            host = parsed.netloc
            if host in ("x.com", "t.me") and not parsed.path.strip("/"):
                # Ссылка на главную X/Telegram — заглушка, а не соцсеть проекта
                continue
            if host == "x.com":
                socials.twitter = socials.twitter or url
            elif host == "t.me":
                socials.telegram = socials.telegram or url
            else:
                socials.website = socials.website or url
    return socials


def twitter_username(url: str) -> str | None:
    """Имя аккаунта из ссылки на профиль или твит. Для сообществ и прочих страниц — None."""
    parts = [p for p in urlparse(url).path.split("/") if p]
    if not parts or parts[0].lower() in TWITTER_RESERVED_PATHS:
        return None
    return parts[0] if TWITTER_USERNAME_RE.match(parts[0]) else None


def telegram_chat(url: str) -> tuple[str | None, bool]:
    """Возвращает (публичное имя чата, is_private)."""
    parts = [p for p in urlparse(url).path.split("/") if p]
    if not parts:
        return None, False
    if parts[0].startswith("+") or parts[0].lower() == "joinchat":
        return None, True
    if parts[0] == "s" and len(parts) > 1:
        parts = parts[1:]
    return (parts[0], False) if TELEGRAM_CHAT_RE.match(parts[0]) else (None, False)


def check_metadata(metadata: dict | None) -> CheckResult:
    if metadata is None:
        return CheckResult.fail("metadata", "Метаданные недоступны (ни один IPFS-шлюз не ответил)")
    return CheckResult.ok("metadata")


def check_socials_present(socials: Socials) -> CheckResult:
    if config.REQUIRE_SOCIALS and not (socials.twitter or socials.telegram or socials.website):
        return CheckResult.fail("socials", "У токена нет соцсетей (TG/Twitter/Website)")
    kinds = [k for k in ("twitter", "telegram", "website") if getattr(socials, k)]
    return CheckResult.ok("socials", "Соцсети: " + ", ".join(kinds))


def check_reused_socials(reused: list[str]) -> CheckResult:
    if config.REJECT_REUSED_SOCIALS and reused:
        return CheckResult.fail("socials_reused", f"Соцсеть уже использовалась другим токеном: {reused[0]}")
    return CheckResult.ok("socials_reused")


def parse_twitter_joined(joined: str) -> datetime | None:
    try:
        return datetime.strptime(joined, "%a %b %d %H:%M:%S %z %Y")
    except (TypeError, ValueError):
        return None


def evaluate_twitter_user(username: str, user: dict | None, now: datetime | None = None) -> CheckResult:
    if user is None:
        return CheckResult.fail("twitter", f"Аккаунт @{username} не существует")
    now = now or datetime.now(timezone.utc)
    followers = int(user.get("followers") or 0)
    joined = parse_twitter_joined(user.get("joined", ""))
    age_days = (now - joined).days if joined else None

    if age_days is not None and age_days < config.MIN_TWITTER_AGE_DAYS:
        return CheckResult.fail("twitter", f"@{username}: аккаунту {age_days} дн.")
    if followers < config.MIN_TWITTER_FOLLOWERS:
        return CheckResult.fail("twitter", f"@{username}: {followers} подписчиков")
    age = f"{age_days} дн." if age_days is not None else "возраст неизвестен"
    return CheckResult.ok("twitter", f"X @{username}: {followers} подп., {age}")


async def check_twitter(session: aiohttp.ClientSession, socials: Socials) -> CheckResult:
    if not socials.twitter:
        return CheckResult.skip("twitter", "")
    username = twitter_username(socials.twitter)
    if not username:
        # Сообщества X и прочие страницы нельзя проверить без платного API
        return CheckResult.skip("twitter", "Ссылка не на профиль (сообщество X и т.п.)")
    try:
        user = await apis.get_twitter_user(session, username)
    except ApiError as e:
        return CheckResult.unavailable("twitter", str(e))
    return evaluate_twitter_user(username, user)


async def check_telegram(session: aiohttp.ClientSession, socials: Socials) -> CheckResult:
    if not socials.telegram:
        return CheckResult.skip("telegram", "")
    chat, is_private = telegram_chat(socials.telegram)
    if is_private:
        if config.TELEGRAM_ALLOW_PRIVATE:
            return CheckResult.skip("telegram", "Приватная группа, проверить нельзя")
        return CheckResult.fail("telegram", "Telegram-группа закрыта (инвайт-ссылка)")
    if not chat:
        return CheckResult.fail("telegram", f"Некорректная ссылка на Telegram: {socials.telegram}")
    try:
        members = await apis.get_telegram_member_count(session, chat)
    except ApiError as e:
        return CheckResult.unavailable("telegram", str(e))
    if members is None:
        return CheckResult.fail("telegram", f"Telegram @{chat} не найден или закрыт")
    if members <= config.MIN_TELEGRAM_MEMBERS:
        return CheckResult.fail("telegram", f"В Telegram @{chat} всего {members} участников")
    return CheckResult.ok("telegram", f"Telegram @{chat}: {members} участников")
