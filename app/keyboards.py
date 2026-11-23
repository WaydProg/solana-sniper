from aiogram.types import InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from sniper.models import Socials


def create_src_token(mint: str, socials: Socials | None = None):
    keyboard = InlineKeyboardBuilder()

    keyboard.add(InlineKeyboardButton(text="Pump.fun", url=f'https://pump.fun/coin/{mint}'))
    keyboard.add(InlineKeyboardButton(text="Axiom", url=f'https://axiom.trade/meme/{mint}?chain=sol'))
    keyboard.add(InlineKeyboardButton(text="DexScreener", url=f'https://dexscreener.com/solana/{mint}'))
    keyboard.add(InlineKeyboardButton(text="RugCheck", url=f'https://rugcheck.xyz/tokens/{mint}'))

    if socials:
        for text, url in (("X", socials.twitter), ("Telegram", socials.telegram), ("Сайт", socials.website)):
            if url:
                keyboard.add(InlineKeyboardButton(text=text, url=url))

    return keyboard.adjust(2).as_markup()


main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="⏸ Пауза"), KeyboardButton(text="▶️ Продолжить")],
    ],
    resize_keyboard=True,
)
