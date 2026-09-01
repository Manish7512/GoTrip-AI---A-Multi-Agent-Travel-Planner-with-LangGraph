import asyncio

from mcp_client import get_all_tools, serp_mcp_call


async def main():
    tools = await get_all_tools()

    tool_names = {
        tool.name
        for tool in tools
    }

    assert "search_google_flights" in tool_names
    assert "search_trip_flights" in tool_names

    result = await serp_mcp_call(
        "search_trip_flights",
        {
            "source": "Delhi",
            "destination": "Dubai",
            "travel_date": "2026-09-15",
            "days": 2,
            "currency": "INR",
        },
    )

    assert result

    print("SERP FLIGHT MCP OK")


if __name__ == "__main__":
    asyncio.run(main())
