import asyncio
from backend import create_travel_graph

async def main():
    pool, travel_graph = await create_travel_graph()

    print("LANGGRAPH INITIALIZATION OK")
    print("GRAPH TYPE:", type(travel_graph))

    await pool.close()
    print("POOL CLOSED")

asyncio.run(main())
