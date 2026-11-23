import logging
from html import escape

from aiogram import Bot

import app.keyboards as kb
from sniper.models import TokenReport

# Эти проверки не несут информации в отчете, если прошли (рыночные метрики уже в шапке)
QUIET_CHECKS = {"quote", "modes", "blacklist", "name", "metadata_uri", "metadata", "socials_reused",
                "sellable", "dev_sold", "volume", "buyers", "buy_sell", "curve"}


def format_report(report: TokenReport) -> str:
    event, metrics = report.event, report.metrics
    lines = [
        f"🔥 <b>Новый токен прошел фильтры</b>",
        "",
        f"<b>{escape(event.name)}</b> (${escape(event.symbol)})",
        f"<code>{event.mint}</code>",
    ]
    if metrics:
        ratio = metrics["buy_sell_ratio"]
        lines += [
            "",
            f"📈 Кривая: <b>{metrics['curve_progress']:.1f}%</b> | Объем: <b>{metrics['volume_sol']:.2f} SOL</b>",
            f"👥 Покупателей: <b>{metrics['unique_buyers']}</b> | Buy/Sell: <b>{metrics['buys']}/{metrics['sells']}</b>"
            + ("" if ratio == float("inf") else f" ({ratio:.2f})"),
        ]

    details = []
    for result in report.results:
        if not result.detail or (result.passed and result.name in QUIET_CHECKS):
            continue
        icon = "✅" if result.passed else "⚠️"
        details.append(f"{icon} {escape(result.detail)}")
    if details:
        lines += ["", *details]
    return "\n".join(lines)


class Notifier:
    def __init__(self, bot: Bot | None, admins: list[int]):
        self.bot = bot
        self.admins = admins
        self.paused = False

    async def send(self, report: TokenReport):
        text = format_report(report)
        if self.bot is None:
            logging.info("[dry-run] Уведомление:\n" + text)
            return
        if self.paused:
            logging.info(f"Уведомления на паузе, {report.event.symbol} не отправлен")
            return
        for user_id in self.admins:
            try:
                await self.bot.send_message(
                    chat_id=user_id,
                    text=text,
                    reply_markup=kb.create_src_token(report.event.mint, report.socials),
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
            except Exception as e:
                logging.error(f"Ошибка при отправке сообщения {user_id}: {e}")
