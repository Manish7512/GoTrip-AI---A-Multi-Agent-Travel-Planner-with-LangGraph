import asyncio
from backend import run_travel_agent

async def main():
    result = await run_travel_agent(
        source="Delhi",
        destination="Dubai",
        days=2,
        budget=50000,
        currency="INR",
        style="Balanced",
        interests="food, sightseeing",
        prompt="Plan a practical 2-day Dubai trip.",
        travel_date="2026-09-15",
        thread_id="debug-test-trip"
    )

    print("\n===== TRIP RESULT =====")
    print(type(result))
    print(result)

asyncio.run(main())
