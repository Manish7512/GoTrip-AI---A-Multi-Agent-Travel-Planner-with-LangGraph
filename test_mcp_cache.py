import asyncio

from mcp_client import (
    tavily_mcp_search,
    weather_mcp_call,
    serp_mcp_call,
)


async def main():

    print("TEST 1: Tavily")

    await tavily_mcp_search(
        "budget hotels in Dubai"
    )

    print("Tavily OK")


    print("\nTEST 2: Weather")

    await weather_mcp_call(
        "get_current_weather",
        {"city": "Dubai"},
    )

    print("Weather OK")


    print("\nTEST 3: Serp Flight")

    await serp_mcp_call(
        "search_trip_flights",
        {
            "source": "Delhi",
            "destination": "Dubai",
            "travel_date": "2026-09-15",
            "days": 2,
            "currency": "INR",
        },
    )

    print("Serp Flight OK")


    print("\nTEST 4: Weather again")

    await weather_mcp_call(
        "get_current_weather",
        {"city": "Tokyo"},
    )

    print("Weather 2 OK")


    print("\nALL MCP CACHE TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
