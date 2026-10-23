import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.db.database import init_db, engine
from sqlalchemy import text


async def main():
    print("Testing connection to PostgreSQL in Docker on port 5433...")
    await init_db()
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;"))
        tables = [row[0] for row in res.fetchall()]
        print("\nSUCCESS! Successfully initialized database and created all tables:")
        for t in tables:
            print(f"  - {t}")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(main())
