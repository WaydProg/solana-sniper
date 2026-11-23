import os
from datetime import datetime, timezone

from sqlalchemy import String, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{os.path.join(PROJECT_DIR, 'db.sqlite3')}")

engine = create_async_engine(url=DATABASE_URL, connect_args={"timeout": 30})

async_session = async_sessionmaker(engine, expire_on_commit=False)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(AsyncAttrs, DeclarativeBase):
    pass


class Token(Base):
    """Каждый увиденный запуск токена — нужен для истории девов."""
    __tablename__ = "tokens"

    mint: Mapped[str] = mapped_column(String(64), primary_key=True)
    dev: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(200))
    symbol: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    status: Mapped[str] = mapped_column(String(16), default="new")  # new / rejected / passed
    reject_check: Mapped[str | None] = mapped_column(String(64))
    reject_detail: Mapped[str | None] = mapped_column(String(300))


class SocialLink(Base):
    """Первый токен, использовавший ссылку на соцсеть."""
    __tablename__ = "social_links"

    url: Mapped[str] = mapped_column(String(300), primary_key=True)
    mint: Mapped[str] = mapped_column(String(64))
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


async def async_main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
