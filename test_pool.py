import asyncio
import os

from dotenv import load_dotenv
from psycopg_pool import AsyncConnectionPool

load_dotenv()

async def main():
    database_url = os.getenv("DATABASE_URL")

    print("DATABASE_URL present:", bool(database_url))

    pool = AsyncConnectionPool(
        conninfo=database_url,
        min_size=1,
        max_size=2,
        open=False,
    )

    try:
        await pool.open(wait=True, timeout=10)
        print("POOL OPEN OK")

        async with pool.connection() as conn:
            cur = await conn.execute("SELECT 1")
            row = await cur.fetchone()
            print("QUERY OK:", row)

    except Exception as e:
        print("POOL ERROR:", repr(e))
        raise

    finally:
        await pool.close()
        print("POOL CLOSED")

asyncio.run(main())
