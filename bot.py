import argparse
import asyncio
import logging
from contextlib import suppress

from aiogram import Bot, Dispatcher

import config
from app.handlers import router
from app.notifier import Notifier
from database.models import async_main
from sniper.clients.helius import HeliusClient
from sniper.clients.http import create_session
from sniper.pipeline import TokenPipeline


async def log_stats(pipeline: TokenPipeline, interval: int = 60):
    while True:
        await asyncio.sleep(interval)
        logging.info(pipeline.summary())


async def main(dry_run: bool, duration: float | None):
    await async_main()

    async with create_session() as session:
        helius = HeliusClient(session, config.HELIUS_RPC_URL, config.HELIUS_MAX_RPS)
        bot = None if dry_run else Bot(token=config.BOT_TOKEN)
        notifier = Notifier(bot, config.LIST_ADMINS_ID)
        pipeline = TokenPipeline(session, helius, notifier.send)

        tasks = [asyncio.create_task(pipeline.run()), asyncio.create_task(log_stats(pipeline))]
        dp = None
        if bot:
            dp = Dispatcher()
            dp.include_router(router)
            tasks.append(asyncio.create_task(
                dp.start_polling(bot, pipeline=pipeline, notifier=notifier, handle_signals=False)))
        else:
            logging.info("Режим dry-run: Telegram отключен, уведомления пишутся в лог")

        try:
            done, _ = await asyncio.wait(tasks, timeout=duration, return_when=asyncio.FIRST_EXCEPTION)
            for task in done:
                task.result()
        finally:
            if dp:
                with suppress(RuntimeError):
                    await dp.stop_polling()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            logging.info(pipeline.summary())
            logging.info(f"RPC по методам: {dict(helius.calls)}")
            if bot:
                await bot.session.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Pump.fun sniper-фильтр с уведомлениями в Telegram")
    parser.add_argument("--dry-run", action="store_true", help="без Telegram, отчеты по токенам пишутся в лог")
    parser.add_argument("--duration", type=float, help="остановиться через N секунд (для тестовых прогонов)")
    parser.add_argument("--debug", action="store_true", help="логировать и отсев на стадии A")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    for noisy in ("websockets", "aiogram.event", "aiosqlite", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    try:
        asyncio.run(main(args.dry_run, args.duration))
    except KeyboardInterrupt:
        logging.info('exit')
