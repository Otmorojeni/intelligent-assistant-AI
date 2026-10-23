import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from src.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency для получения асинхронной сессии БД."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Инициализация расширений PostgreSQL и схемы таблиц."""
    from src.db.models import Base

    async with engine.begin() as conn:
        # Включаем pg_trgm для быстрого нечеткого поиска опечаток
        try:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
            logger.info("Extension 'pg_trgm' enabled successfully.")
        except Exception as e:
            logger.warning(f"Could not enable pg_trgm: {e}")

        # Создаем таблицы
        await conn.run_sync(Base.metadata.create_all)
        logger.info("All database tables created successfully.")
