from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton 
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
import database.requests as rq

async def create_src_token(name: str, mint: str):
    keyboard = InlineKeyboardBuilder()

    keyboard.add(InlineKeyboardButton(text=name, url=f'https://pump.fun/coin/{mint}'))

    return keyboard.adjust(1).as_markup()