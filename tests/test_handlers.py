"""Обработчики Telegram через настоящий Dispatcher aiogram, но без сетевых запросов."""
import asyncio
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import SendMessage
from aiogram.types import Update, Message, User, Chat

import config
from app.handlers import router
from app.notifier import Notifier, format_report
from sniper.models import CheckResult, Socials, TokenReport
from sniper.pipeline import TokenPipeline

ADMIN_ID = config.LIST_ADMINS_ID[0]

# Роутер модульный и подключается к диспетчеру только один раз
dp = Dispatcher()
dp.include_router(router)


class RecordingSession(BaseSession):
    """Сессия aiogram, которая записывает запросы к Bot API вместо отправки."""

    def __init__(self):
        super().__init__()
        self.requests = []

    async def make_request(self, bot, method, timeout=None):
        self.requests.append(method)
        if isinstance(method, SendMessage):
            return Message(message_id=1, date=datetime.now(), chat=Chat(id=method.chat_id, type="private"),
                           text=method.text)
        return True

    async def stream_content(self, *args, **kwargs):
        yield b""

    async def close(self):
        pass


def make_update(text: str, user_id: int) -> Update:
    user = User(id=user_id, is_bot=False, first_name="U")
    return Update(update_id=1, message=Message(
        message_id=1, date=datetime.now(), chat=Chat(id=user_id, type="private"), from_user=user, text=text))


def run_commands(*texts: str, user_id: int = ADMIN_ID):
    session = RecordingSession()
    bot = Bot(token="123456:TEST", session=session)
    notifier = Notifier(bot, [ADMIN_ID])
    pipeline = TokenPipeline(None, type("H", (), {"calls": {}})(), notifier.send)

    async def feed():
        for text in texts:
            await dp.feed_update(bot, make_update(text, user_id), pipeline=pipeline, notifier=notifier)

    asyncio.run(feed())
    return [r.text for r in session.requests if isinstance(r, SendMessage)], notifier


def test_start_and_stats():
    replies, _ = run_commands("/start", "/stats", "📊 Статистика")
    assert "Мониторинг новых токенов" in replies[0]
    assert "Вебсокет" in replies[1] and "Причины отсева" in replies[1]
    assert len(replies) == 3


def test_pause_resume():
    replies, notifier = run_commands("/pause")
    assert notifier.paused and "приостановлены" in replies[0]
    replies, notifier = run_commands("⏸ Пауза", "▶️ Продолжить")
    assert not notifier.paused


def test_non_admin_ignored():
    replies, _ = run_commands("/start", "/stats", user_id=999)
    assert replies == []


def test_notification_html_is_escaped(event):
    event.name = "<b>evil</b> & *co_in*"
    report = TokenReport(event, results=[CheckResult.ok("dev_buy", "Закуп дева 1.00 SOL"),
                                         CheckResult.skip("rugcheck", "Сервис недоступен: timeout")],
                         socials=Socials(twitter="https://x.com/project"))
    report.metrics = {"curve_progress": 20.0, "volume_sol": 7.5, "unique_buyers": 25, "buys": 30, "sells": 5,
                      "buy_sell_ratio": 6.0}
    text = format_report(report)
    assert "&lt;b&gt;evil&lt;/b&gt; &amp; *co_in*" in text
    assert "⚠️ Сервис недоступен" in text

    session = RecordingSession()
    notifier = Notifier(Bot(token="123456:TEST", session=session), [1, 2])
    asyncio.run(notifier.send(report))
    assert len(session.requests) == 2 and session.requests[0].parse_mode == "HTML"
    notifier.paused = True
    asyncio.run(notifier.send(report))
    assert len(session.requests) == 2
