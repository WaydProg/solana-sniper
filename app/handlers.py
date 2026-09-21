import logging
import asyncio
from aiogram import Router, Bot
from aiogram.filters import CommandStart
from aiogram.types import Message

from config import LIST_ADMINS_ID
from sniper.pump_fun import listen_pump_fun
import app.keyboards as kb

router = Router()

async def send_new_token_notification(bot: Bot, user_id: int, event: dict):
    try:
        await bot.send_message(
            chat_id=user_id,
            text=f"🔥 **Новый токен!**\n\nИмя: {event['name']}\nСимвол: {event['symbol']}",
            reply_markup=await kb.create_src_token(event['name'], event['mint']),
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.error(f"Ошибка при отправке сообщения: {e}")

is_listening = False

@router.message(CommandStart())
async def start(message: Message, bot: Bot):
    global is_listening
    await message.answer("Мониторинг новых токенов запущен! Ожидайте уведомлений.")

    if not is_listening:
        is_listening = True
        
        async def handle_new_token(event):
            for user_id in LIST_ADMINS_ID:
                await send_new_token_notification(bot, user_id, event)

        asyncio.create_task(listen_pump_fun(handle_new_token))