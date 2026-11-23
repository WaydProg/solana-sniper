from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

import database.requests as rq
from config import LIST_ADMINS_ID
from app.notifier import Notifier
from sniper.pipeline import TokenPipeline
import app.keyboards as kb

router = Router()
# Бот отвечает только администраторам
router.message.filter(F.from_user.id.in_(set(LIST_ADMINS_ID)))


@router.message(CommandStart())
async def start(message: Message, notifier: Notifier):
    state = "на паузе" if notifier.paused else "включены"
    await message.answer(
        "Мониторинг новых токенов Pump.fun работает.\n"
        f"Уведомления {state}.\n\n"
        "/stats — статистика фильтров\n"
        "/pause — приостановить уведомления\n"
        "/resume — возобновить уведомления",
        reply_markup=kb.main_menu,
    )


@router.message(Command("stats"))
@router.message(F.text == "📊 Статистика")
async def stats(message: Message, pipeline: TokenPipeline):
    by_status = await rq.count_by_status(hours=24)
    stream_state = "подключен" if pipeline.stream.connected.is_set() else "переподключается"
    await message.answer(
        f"Вебсокет: {stream_state}\n\n"
        f"{pipeline.summary()}\n\n"
        f"За 24 ч в базе: " + (", ".join(f"{k}: {v}" for k, v in by_status.items()) or "пусто")
    )


@router.message(Command("pause"))
@router.message(F.text == "⏸ Пауза")
async def pause(message: Message, notifier: Notifier):
    notifier.paused = True
    await message.answer("Уведомления приостановлены. Мониторинг продолжает работать.")


@router.message(Command("resume"))
@router.message(F.text == "▶️ Продолжить")
async def resume(message: Message, notifier: Notifier):
    notifier.paused = False
    await message.answer("Уведомления возобновлены.")
