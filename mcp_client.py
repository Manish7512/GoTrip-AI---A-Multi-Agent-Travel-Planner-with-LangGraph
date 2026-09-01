import os
import sys
from pathlib import Path

import certifi
from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient


# ============================================================
# ENVIRONMENT
# ============================================================

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUEST_CA_BUNDLE"] = certifi.where()

load_dotenv()

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY", "")
OPEN_WEATHER_API_KEY = os.getenv("OPEN_WEATHER_API_KEY", "")


# ============================================================
# MCP CLIENT
# ============================================================

client = MultiServerMCPClient(
    {
        "tavily": {
            "transport": "streamable_http",
            "url": (
                "https://mcp.tavily.com/mcp/"
                f"?tavilyApiKey={TAVILY_API_KEY}"
            ),
        },

        "serp_flight": {
            "transport": "stdio",
            "command": sys.executable,
            "args": [
                str(
                    Path(__file__).resolve().parent
                    / "serp_flight_mcp_server.py"
                )
            ],
            "env": {
                "SERPAPI_API_KEY":
                    SERPAPI_API_KEY,
            },
        },

        "weather": {
            "transport": "stdio",
            "command": sys.executable,
            "args": [
                str(
                    Path(__file__).resolve().parent
                    / "custom_weather_mcp_server.py"
                )
            ],
            "env": {
                "OPEN_WEATHER_API_KEY":
                    OPEN_WEATHER_API_KEY,
            },
        },
    }
)


# ============================================================
# TOOL CACHE
# ============================================================

_tools = None
_tools_lock = None


async def get_all_tools():
    """
    Load MCP tools exactly once per Python process.

    All agents use this single cached tool collection.
    """

    global _tools
    global _tools_lock

    if _tools is not None:
        return _tools

    # Import lazily so the module remains lightweight.
    import asyncio

    if _tools_lock is None:
        _tools_lock = asyncio.Lock()

    async with _tools_lock:

        # Another coroutine may have initialized while
        # this coroutine was waiting for the lock.
        if _tools is not None:
            return _tools

        print("\nInitializing MCP tools...\n")

        _tools = await client.get_tools()

        print("\nAvailable MCP Tools:\n")

        for tool in _tools:
            print(f"  - {tool.name}")

        print()

        return _tools


# ============================================================
# TOOL LOOKUP
# ============================================================

async def get_tool(tool_name: str):
    """
    Return a cached MCP tool by name.
    """

    tools = await get_all_tools()

    for tool in tools:

        if tool.name == tool_name:
            return tool

    available = ", ".join(
        sorted(tool.name for tool in tools)
    )

    raise ValueError(
        f"MCP tool '{tool_name}' not found. "
        f"Available tools: {available}"
    )


# ============================================================
# TAVILY
# ============================================================

async def tavily_mcp_search(query: str):

    tool = await get_tool("tavily_search")

    return await tool.ainvoke(
        {
            "query": query
        }
    )


# ============================================================
# SERP FLIGHT
# ============================================================

async def serp_mcp_call(
    tool_name: str,
    tool_args: dict | None = None,
):
    if tool_name not in {
        "search_google_flights",
        "search_trip_flights",
    }:
        raise ValueError(
            f"Unknown Serp flight tool: {tool_name}"
        )

    tool = await get_tool(tool_name)

    return await tool.ainvoke(
        tool_args or {}
    )


# ============================================================
# WEATHER
# ============================================================

async def weather_mcp_call(
    tool_name: str,
    tool_args: dict | None = None,
):

    if tool_name not in {
        "get_current_weather",
        "get_forecast",
    }:

        raise ValueError(
            f"Unknown weather tool: {tool_name}"
        )

    tool = await get_tool(tool_name)

    return await tool.ainvoke(
        tool_args or {}
    )


# ============================================================
# EXPLICIT INITIALIZATION
# ============================================================

async def initialize_mcp():

    await get_all_tools()

    print("MCP INITIALIZATION OK")


async def initialize_weather_tools():

    tools = await get_all_tools()

    required = {
        "get_current_weather",
        "get_forecast",
    }

    available = {
        tool.name
        for tool in tools
    }

    missing = required - available

    if missing:

        raise RuntimeError(
            "Weather MCP tools missing: "
            + ", ".join(sorted(missing))
        )

    print("WEATHER MCP TOOLS OK")
