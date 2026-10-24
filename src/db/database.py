import asyncio
import logging
import sys
import warnings
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from src.config import settings

if sys.platform == "win32":
    warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*WindowsSelectorEventLoopPolicy.*")
    warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*set_event_loop_policy.*")
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

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
        # Включаем pg_trgm и vector в изолированных savepoint, чтобы не прерывать транзакцию
        for ext in ("pg_trgm", "vector"):
            try:
                async with conn.begin_nested():
                    await conn.execute(text(f"CREATE EXTENSION IF NOT EXISTS {ext};"))
                logger.info("Extension '%s' enabled successfully.", ext)
            except Exception as e:
                logger.debug("Optional extension '%s' not available: %s", ext, e)

        # Создаем таблицы
        await conn.run_sync(Base.metadata.create_all)
        logger.info("All database tables created successfully.")
