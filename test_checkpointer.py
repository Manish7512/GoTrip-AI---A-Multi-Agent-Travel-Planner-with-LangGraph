import asyncio
import os

from dotenv import load_dotenv
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

load_dotenv()

async def main():
    database_url = os.getenv("DATABASE_URL")

    pool = AsyncConnectionPool(
        conninfo=database_url,
        min_size=1,
        max_size=2,
        open=False,
    )

    try:
        await pool.open(wait=True, timeout=10)
        print("POOL OK")

        checkpointer = AsyncPostgresSaver(pool)

        print("CHECKPOINTER CREATED")

        await checkpointer.setup()

        print("CHECKPOINTER SETUP OK")

    except Exception as e:
        print("CHECKPOINTER ERROR:", repr(e))
        raise

    finally:
        await pool.close()
        print("POOL CLOSED")

asyncio.run(main())
