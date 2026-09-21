import os
import asyncio
import logging
from aiogram import Bot, Dispatcher

from app.handlers import router
from database.models import async_main
from app.handlers import send_new_token_notification

from config import BOT_TOKEN
from config import LIST_ADMINS_ID
from sniper.pump_fun import listen_pump_fun

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

async def main():
    dp.include_router(router)
    await async_main()
    await dp.start_polling(bot)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info('exit')