from datetime import timedelta

from sqlalchemy import select, func, update, delete
from sqlalchemy.dialects.sqlite import insert

from database.models import async_session, Token, SocialLink, utcnow


async def register_launch(mint: str, dev: str, name: str, symbol: str, history_days: int) -> int:
    """Сохраняет запуск и возвращает число предыдущих запусков этого дева за history_days."""
    async with async_session() as session:
        since = utcnow() - timedelta(days=history_days)
        previous = await session.scalar(
            select(func.count()).select_from(Token)
            .where(Token.dev == dev, Token.mint != mint, Token.created_at >= since)
        )
        await session.execute(
            insert(Token).values(mint=mint, dev=dev, name=name[:200], symbol=symbol[:50])
            .on_conflict_do_nothing(index_elements=["mint"])
        )
        await session.commit()
        return previous or 0


async def set_token_status(mint: str, status: str, check: str | None = None, detail: str | None = None):
    async with async_session() as session:
        await session.execute(
            update(Token).where(Token.mint == mint)
            .values(status=status, reject_check=check, reject_detail=(detail or None) and detail[:300])
        )
        await session.commit()


async def claim_social_links(mint: str, links: list[str]) -> list[str]:
    """Регистрирует ссылки за токеном. Возвращает ссылки, которые уже принадлежат другим токенам."""
    if not links:
        return []
    async with async_session() as session:
        await session.execute(
            insert(SocialLink).values([{"url": link, "mint": mint} for link in links])
            .on_conflict_do_nothing(index_elements=["url"])
        )
        owners = await session.execute(select(SocialLink.url, SocialLink.mint).where(SocialLink.url.in_(links)))
        await session.commit()
        return [url for url, owner in owners if owner != mint]


async def cleanup_history(days: int):
    async with async_session() as session:
        since = utcnow() - timedelta(days=days)
        await session.execute(delete(Token).where(Token.created_at < since))
        await session.execute(delete(SocialLink).where(SocialLink.first_seen < since))
        await session.commit()


async def count_by_status(hours: int = 24) -> dict[str, int]:
    async with async_session() as session:
        since = utcnow() - timedelta(hours=hours)
        rows = await session.execute(
            select(Token.status, func.count()).where(Token.created_at >= since).group_by(Token.status)
        )
        return dict(rows.all())
