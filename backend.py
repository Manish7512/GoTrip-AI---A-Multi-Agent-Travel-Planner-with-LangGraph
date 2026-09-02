# G O T R I P  -  BACKEND
# ============================================================
#
# Architecture:
#
# START
#   ↓
# route_agent       -> Python only
#   ↓
# flight_agent      -> Serp Flight MCP only
#   ↓
# hotel_agent       -> Tavily MCP only
#   ↓
# weather_agent     -> Weather MCP only
#   ↓
# itinerary_agent   -> ONE LLM CALL
#   ↓
# final_agent       -> Python formatter only
#   ↓
# END
#
# LLM:
# openai/gpt-oss-120b
#
# Normal LLM calls per trip:
# 1
#
# ============================================================

import json
import os
import re
import operator
import uuid
from collections import Counter
from datetime import datetime, timedelta
from typing import Annotated, List, TypedDict, Any

import certifi

from dotenv import load_dotenv

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from pydantic import BaseModel, Field

from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    SystemMessage,
)

from langchain_groq import ChatGroq

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from langgraph.graph import (
    END,
    START,
    StateGraph,
)

from mcp_client import (
    tavily_mcp_search,
    serp_mcp_call,
    weather_mcp_call,
)


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")


if not GROQ_API_KEY:
    raise ValueError(
        "GROQ_API_KEY is missing. "
        "Please check your .env file."
    )


def required_env(name: str) -> str:

    value = os.getenv(name)

    if not value:
        raise ValueError(
            f"{name} is missing from .env"
        )

    return value


def database_url() -> str:

    value = required_env(
        "DATABASE_URL"
    )

    if "sslmode=" not in value:

        value += (
            ("&" if "?" in value else "?")
            + "sslmode=require"
        )

    return value


# ============================================================
# LLM
# ============================================================

# SHARED LLM CLIENT
# ============================================================

llm = ChatGroq(
    model="openai/gpt-oss-120b",
    groq_api_key=GROQ_API_KEY,
    temperature=0.1,
)


# ============================================================
# TRAVEL STATE
# ============================================================

class TravelState(TypedDict):

    messages: Annotated[
        list[AnyMessage],
        operator.add
    ]

    source: str

    destination: str

    planning_destination: str

    travel_date: str | None

    days: int

    budget: float

    currency: str

    style: str

    interests: str

    user_prompt: str

    user_query: str

    flight_results: str

    hotel_results: str

    weather_results: str

    itinerary: dict

    route: list[dict]

    score: int

    final_answer: str

    llm_calls: int


# ============================================================
# STRUCTURED OUTPUT SCHEMAS
# ============================================================

class RouteItem(BaseModel):

    name: str = Field(
        description="Location name."
    )

    type: str = Field(
        description=(
            "source, stop, or destination."
        )
    )


class Activity(BaseModel):

    time: str = Field(
        description=(
            "Activity time in 24-hour HH:MM format. "
            "Use HH:MM-HH:MM only for a time range."
        )
    )

    activity: str = Field(
        description="Recommended activity."
    )

    transport: str = Field(
        description="Transportation method."
    )

    estimated_cost: float = Field(
        description="Estimated activity cost."
    )

    currency: str = Field(
        description="Currency of estimated cost."
    )


class DayPlan(BaseModel):

    day: int

    title: str

    location: str

    route: str

    activities: List[Activity]

    day_budget: float


class Itinerary(BaseModel):

    title: str

    summary: str

    route: List[RouteItem]

    days: List[DayPlan]


# ============================================================
# GENERAL HELPERS
# ============================================================

def trip_return_date(
    travel_date: str,
    days: int,
):

    start_date = datetime.strptime(
        str(travel_date),
        "%Y-%m-%d"
    ).date()

    return (
        start_date
        + timedelta(days=max(int(days) - 1, 1))
    )


def compact_text(
    value: Any,
    limit: int = 2000
) -> str:

    """
    Convert MCP output into compact text.

    This is extremely important for Groq TPM limits.
    """

    if value is None:

        return ""

    if isinstance(value, str):

        return value[:limit]

    try:

        text = json.dumps(
            value,
            ensure_ascii=False
        )

    except Exception:

        text = str(value)

    return text[:limit]


def compact_flight_data(
    value: Any,
    limit: int = 6000,
) -> str:
    """
    Keep the exact flight fields needed by the itinerary LLM,
    while avoiding the huge raw SerpApi payload.

    Both outbound and return legs are preserved.
    """

    data = extract_json(value)

    if not isinstance(data, dict):
        return compact_text(value, limit)

    def compact_option(option: Any) -> dict:
        if not isinstance(option, dict):
            return {}

        segments = option.get("flights", [])
        compact_segments = []

        if isinstance(segments, list):
            for segment in segments[:4]:
                if not isinstance(segment, dict):
                    continue

                dep = segment.get("departure_airport") or {}
                arr = segment.get("arrival_airport") or {}

                compact_segments.append({
                    "airline": segment.get("airline"),
                    "flight_number": segment.get("flight_number"),
                    "departure": {
                        "airport": dep.get("id") or dep.get("name"),
                        "time": dep.get("time"),
                    },
                    "arrival": {
                        "airport": arr.get("id") or arr.get("name"),
                        "time": arr.get("time"),
                    },
                    "duration": segment.get("duration"),
                    "airplane": segment.get("airplane"),
                    "travel_class": segment.get("travel_class"),
                })

        return {
            "segments": compact_segments,
            "total_duration": option.get("total_duration"),
            "price": option.get("price"),
            "type": option.get("type"),
        }

    compact = {
        "status": data.get("status"),
        "outbound_date": data.get("outbound_date"),
        "return_date": data.get("return_date"),
        "outbound": {
            "status": (data.get("outbound") or {}).get("status"),
            "date": (data.get("outbound") or {}).get("date"),
            "best_flights": [
                compact_option(item)
                for item in ((data.get("outbound") or {}).get("best_flights") or [])[:3]
            ],
            "other_flights": [
                compact_option(item)
                for item in ((data.get("outbound") or {}).get("other_flights") or [])[:2]
            ],
        },
        "return": {
            "status": (data.get("return") or {}).get("status"),
            "date": (data.get("return") or {}).get("date"),
            "best_flights": [
                compact_option(item)
                for item in ((data.get("return") or {}).get("best_flights") or [])[:3]
            ],
            "other_flights": [
                compact_option(item)
                for item in ((data.get("return") or {}).get("other_flights") or [])[:2]
            ],
        },
    }

    text = json.dumps(
        compact,
        ensure_ascii=False,
        indent=2,
    )

    return text[:limit]


def flight_options_from_leg(
    leg_data: Any
) -> list[dict]:

    if not isinstance(
        leg_data,
        dict
    ):

        return []

    options = []

    for key in (
        "best_flights",
        "other_flights"
    ):

        values = leg_data.get(
            key,
            []
        )

        if isinstance(
            values,
            list
        ):

            options.extend(
                item
                for item in values
                if isinstance(
                    item,
                    dict
                )
            )

    return options


def extract_hhmm(
    value: Any
) -> str:

    text = str(
        value or ""
    ).strip()

    match = re.search(
        r"\b(\d{1,2}):(\d{2})\b",
        text
    )

    if not match:
        return ""

    return (
        f"{int(match.group(1)):02d}:"
        f"{match.group(2)}"
    )


def flight_activity_time_minutes(
    activity: dict
) -> int | None:

    time_text = str(
        activity.get(
            "time",
            ""
        )
    )

    match = re.search(
        r"\b(\d{1,2}):(\d{2})\b",
        time_text
    )

    if not match:
        return None

    hours = int(
        match.group(1)
    )

    minutes = int(
        match.group(2)
    )

    if (
        hours > 23
        or minutes > 59
    ):

        return None

    return (
        hours * 60
        + minutes
    )


def activity_mentions_flight(
    activity: Any
) -> bool:

    if not isinstance(
        activity,
        dict
    ):

        return False

    text = " ".join(
        str(
            activity.get(
                key,
                ""
            )
        )
        for key in (
            "transport",
            "activity"
        )
    )

    return (
        "flight"
        in text.casefold()
    )


def activity_mentions_return_flight(
    activity: Any,
    source: str
) -> bool:

    if not activity_mentions_flight(
        activity
    ):

        return False

    text = " ".join(
        str(
            activity.get(
                key,
                ""
            )
        )
        for key in (
            "activity",
            "transport"
        )
    ).casefold()

    return any(
        marker in text
        for marker in (
            "return",
            "back",
            "home",
            source.casefold()
        )
    )


def build_flight_activity(
    leg_data: Any,
    currency: str
) -> dict:

    options = flight_options_from_leg(
        leg_data
    )

    selected = (
        options[0]
        if options
        else None
    )

    if isinstance(
        selected,
        dict
    ):

        segments = selected.get(
            "flights",
            []
        )

        if isinstance(
            segments,
            list
        ) and segments:

            first_segment = (
                segments[0]
                if isinstance(
                    segments[0],
                    dict
                )
                else {}
            )

            last_segment = (
                segments[-1]
                if isinstance(
                    segments[-1],
                    dict
                )
                else first_segment
            )

            departure = (
                first_segment.get(
                    "departure_airport"
                )
                or {}
            )

            arrival = (
                last_segment.get(
                    "arrival_airport"
                )
                or {}
            )

            airline = str(
                first_segment.get(
                    "airline"
                )
                or ""
            ).strip()

            flight_number = str(
                first_segment.get(
                    "flight_number"
                )
                or ""
            ).strip()

            departure_time = extract_hhmm(
                departure.get(
                    "time"
                )
            )

            pieces = [
                item
                for item in (
                    airline,
                    flight_number
                )
                if item
            ]

            activity_text = (
                " ".join(pieces)
                if pieces
                else "Verified flight option"
            )

            dep_airport = (
                departure.get("id")
                or departure.get("name")
            )

            arr_airport = (
                arrival.get("id")
                or arrival.get("name")
            )

            if dep_airport and arr_airport:
                activity_text += (
                    f" from {dep_airport} "
                    f"to {arr_airport}"
                )

            price = selected.get(
                "price"
            )

            if not isinstance(
                price,
                (int, float)
            ):

                price = 0

            return {
                "time":
                    departure_time,

                "activity":
                    activity_text,

                "transport":
                    "Flight",

                "estimated_cost":
                    float(price),

                "currency":
                    currency,
            }

    return {
        "time": "",
        "activity": "Flight information to be confirmed.",
        "transport": "Flight",
        "estimated_cost": 0,
        "currency": currency,
    }


def trim_day_to_six_activities_preserving_flights(
    day: dict
) -> None:

    activities = day.get(
        "activities",
        []
    )

    if not isinstance(
        activities,
        list
    ):

        day["activities"] = []
        return

    while len(activities) > 6:

        removable_index = None

        for index in range(
            len(activities) - 1,
            -1,
            -1
        ):

            activity = activities[index]

            if activity_mentions_flight(
                activity
            ):

                continue

            removable_index = index
            break

        if removable_index is None:
            break

        removed = activities.pop(
            removable_index
        )

        print(
            "Removed non-flight activity after "
            "flight injection:",
            removed.get("activity")
            if isinstance(removed, dict)
            else removed
        )

    day["activities"] = activities


def ensure_required_flight_activities(
    itinerary: dict,
    flight_data: Any,
    currency: str,
    source: str,
) -> None:

    if not isinstance(
        itinerary,
        dict
    ):

        return

    days = itinerary.get(
        "days",
        []
    )

    if not isinstance(
        days,
        list
    ) or not days:

        return

    flight_data = (
        flight_data
        if isinstance(flight_data, dict)
        else {}
    )

    outbound_data = (
        flight_data.get("outbound")
        or {}
    )

    return_data = (
        flight_data.get("return")
        or {}
    )

    first_day = days[0]

    if isinstance(
        first_day,
        dict
    ):

        activities = first_day.get(
            "activities",
            []
        )

        if not isinstance(
            activities,
            list
        ):

            activities = []

        if not any(
            activity_mentions_flight(activity)
            for activity in activities
        ):

            activities.insert(
                0,
                build_flight_activity(
                    outbound_data,
                    currency
                )
            )

            first_day["activities"] = activities

            trim_day_to_six_activities_preserving_flights(
                first_day
            )

    final_day = days[-1]

    if not isinstance(
        final_day,
        dict
    ):

        return

    final_activities = final_day.get(
        "activities",
        []
    )

    if not isinstance(
        final_activities,
        list
    ):

        final_activities = []

    if len(days) == 1:

        has_return_flight = any(
            activity_mentions_return_flight(
                activity,
                source
            )
            for activity in final_activities
        )

    else:

        has_return_flight = any(
            activity_mentions_flight(activity)
            for activity in final_activities
        )

    if has_return_flight:
        final_day["activities"] = final_activities
        return

    return_activity = build_flight_activity(
        return_data,
        currency
    )

    return_minutes = flight_activity_time_minutes(
        return_activity
    )

    inserted = False

    if return_minutes is not None:

        for index, activity in enumerate(
            final_activities
        ):

            activity_minutes = (
                flight_activity_time_minutes(
                    activity
                )
            )

            if (
                activity_minutes is not None
                and return_minutes < activity_minutes
            ):

                final_activities.insert(
                    index,
                    return_activity
                )

                inserted = True
                break

    if not inserted:

        final_activities.append(
            return_activity
        )

    final_day["activities"] = final_activities

    trim_day_to_six_activities_preserving_flights(
        final_day
    )


def extract_json(
    value: Any
):

    """
    Best-effort JSON extraction from MCP responses.
    """

    if value is None:

        return None

    if isinstance(value, (dict, list)):

        return value

    text = str(value).strip()

    if not text:

        return None

    try:

        return json.loads(text)

    except Exception:
        pass

    # Try to extract JSON object/list from text.
    start_positions = []

    object_start = text.find("{")

    list_start = text.find("[")

    if object_start >= 0:
        start_positions.append(
            object_start
        )

    if list_start >= 0:
        start_positions.append(
            list_start
        )

    if not start_positions:

        return None

    start = min(
        start_positions
    )

    for end in range(
        len(text),
        start,
        -1
    ):

        candidate = text[
            start:end
        ]

        try:

            return json.loads(
                candidate
            )

        except Exception:
            continue

    return None


def safe_json(
    value: Any,
    limit: int = 2000
) -> str:

    try:

        return json.dumps(
            value,
            ensure_ascii=False
        )[:limit]

    except Exception:

        return str(value)[:limit]


# ============================================================
# TRIP REQUEST
# ============================================================

def trip_request_text(
    state: TravelState
) -> str:

    return f"""
Source: {state["source"]}
Destination: {state["destination"]}
Planning destination: {state.get("planning_destination", state["destination"])}
Travel date: {state.get("travel_date") or "Not specified"}
Duration: {state["days"]} days
Budget: {state["budget"]:.2f} {state["currency"]}
Style: {state["style"]}
Interests: {state["interests"] or "General travel"}
User request: {state["user_prompt"] or "No additional request"}
""".strip()


# ============================================================
# ROUTE AGENT
# ============================================================
#
# NO LLM
#
# Route generation is deterministic.
# This saves one LLM call.
# ============================================================

BROAD_DESTINATION_DEFAULTS = {

    "europe": "Paris",

    "asia": "Tokyo",

    "africa": "Cape Town",

    "north america": "New York",

    "south america": "Rio de Janeiro",

    "central america": "Mexico City",

    "middle east": "Dubai",

    "oceania": "Sydney",

    "australia": "Sydney",

    "uk": "London",

    "united kingdom": "London",

    "usa": "New York",

    "united states": "New York",

    "schengen": "Paris",
}


def route_agent(
    state: TravelState
):

    source = str(
        state["source"]
    ).strip()

    destination = str(
        state["destination"]
    ).strip()

    # --------------------------------------------------------
    # DEFAULT PLANNING DESTINATION
    # --------------------------------------------------------

    planning_destination = destination

    destination_key = (
        destination.casefold()
    )

    if destination_key in BROAD_DESTINATION_DEFAULTS:

        planning_destination = (
            BROAD_DESTINATION_DEFAULTS[
                destination_key
            ]
        )

    # --------------------------------------------------------
    # ROUTE
    # --------------------------------------------------------

    route = [

        {
            "name": source,
            "type": "source"
        },

        {
            "name": planning_destination,
            "type": "destination"
        }
    ]

    # --------------------------------------------------------
    # IMPORTANT
    # --------------------------------------------------------
    #
    # We intentionally DO NOT ask the LLM to create
    # intermediate cities.
    #
    # This keeps:
    #
    # - token usage low
    # - route deterministic
    # - destination stable
    # - itinerary geographically consistent
    #
    # --------------------------------------------------------

    print(
        "\nROUTE:",
        route
    )

    return {

        "route": route,

        "planning_destination":
            planning_destination,

        "messages": [
            AIMessage(
                content=(
                    "Route generated without LLM."
                )
            )
        ],

        "llm_calls": state.get(
            "llm_calls",
            0
        )
    }


def compact_hotel_results(value: Any, limit: int = 8) -> str:
    """Normalize Tavily/MCP hotel search results into concise hotel suggestions."""

    data = extract_json(value)
    hotels = []

    def add_hotel(name, content="", url="", score=None):
        if not name:
            return

        name = str(name).strip()
        content = str(content or "").strip()

        # Ignore generic search/article titles where possible.
        generic_terms = (
            "guide to",
            "ultimate guide",
            "best hotels",
            "top 10 hotels",
            "what are top hotels",
        )

        if any(term in name.casefold() for term in generic_terms):
            # Still inspect the content for actual hotel names.
            pass

        hotels.append({
            "name": name,
            "content": content[:700],
            "url": str(url or ""),
            "score": score,
        })

    def collect(node):
        if node is None:
            return

        if isinstance(node, str):
            nested = extract_json(node)
            if nested is not None:
                collect(nested)
            return

        if isinstance(node, list):
            for item in node:
                if len(hotels) >= limit:
                    break
                collect(item)
            return

        if not isinstance(node, dict):
            return

        # MCP/Tavily wrapper
        if isinstance(node.get("results"), list):
            collect(node["results"])
            return

        # MCP text wrapper
        if isinstance(node.get("text"), str):
            collect(node["text"])
            return

        # Direct search result
        title = node.get("title") or node.get("name")

        if title:
            add_hotel(
                name=title,
                content=node.get("content") or node.get("description"),
                url=node.get("url"),
                score=node.get("score"),
            )
            return

        for value in node.values():
            if len(hotels) >= limit:
                break
            collect(value)

    collect(data)

    # Remove duplicate titles.
    unique = []
    seen = set()

    for hotel in hotels:
        key = hotel["name"].casefold()

        if key in seen:
            continue

        seen.add(key)
        unique.append(hotel)

    return safe_json(
        {
            "status": "success" if unique else "unavailable",
            "results": unique[:limit],
        },
        6000,
    )

# ============================================================
# FLIGHT AGENT
# ============================================================
#
# NO LLM
#

# Serp Flight MCP performs the Google Flights search.
# ============================================================

async def flight_agent(
    state: TravelState
):
    """
    Retrieve real outbound and return flight data.

    IMPORTANT:
    - Never invent flight details.
    - A round-trip Google Flights search returns outbound options.
    - SerpApi requires a second request with departure_token to get
      the corresponding return options.
    - If that second request is unavailable, fall back to an
      independent one-way return search for the exact return date.
    """

    print("\nINSIDE FLIGHT AGENT\n")

    source = state["source"].strip()
    destination = state.get(
        "planning_destination",
        state["destination"]
    ).strip()
    travel_date = state.get("travel_date")

    if not travel_date:
        result = {
            "status": "unavailable",
            "reason": "Travel date was not provided.",
            "outbound": {},
            "return": {},
        }

        return {
            "flight_results": json.dumps(
                result, ensure_ascii=False
            ),
            "messages": [
                AIMessage(
                    content="Flight information unavailable because travel date is missing."
                )
            ],
            "llm_calls": state.get("llm_calls", 0),
        }

    try:
        datetime.strptime(
            travel_date,
            "%Y-%m-%d"
        ).date()
    except ValueError:
        result = {
            "status": "unavailable",
            "reason": "Flight travel date must be YYYY-MM-DD.",
            "outbound": {},
            "return": {},
        }

        return {
            "flight_results": json.dumps(
                result, ensure_ascii=False
            ),
            "messages": [
                AIMessage(content="Invalid flight travel date.")
            ],
            "llm_calls": state.get("llm_calls", 0),
        }

    try:
        print(f"SOURCE: {source}")
        print(f"DESTINATION: {destination}")
        print(f"OUTBOUND DATE: {travel_date}")
        print(
            "RETURN DATE:",
            trip_return_date(
                travel_date,
                state["days"]
            ).isoformat()
        )

        flight_result = await serp_mcp_call(
            "search_trip_flights",
            {
                "source": source,
                "destination": destination,
                "travel_date": travel_date,
                "days": int(state["days"]),
                "currency": state.get(
                    "currency",
                    "INR"
                ),
            }
        )

        flight_data = extract_json(
            flight_result
        )

        if isinstance(flight_data, list):
            for item in flight_data:
                if (
                    isinstance(item, dict)
                    and item.get("text")
                ):
                    parsed = extract_json(
                        item["text"]
                    )

                    if parsed:
                        flight_data = parsed
                        break

        if not isinstance(
            flight_data,
            dict
        ):
            raise ValueError(
                "Serp Flight MCP returned an unsupported response."
            )

        print("\n========== STRUCTURED FLIGHT DATA ==========")
        print(safe_json(flight_data, 14000))
        print("=============================================\n")

        return {
            "flight_results": json.dumps(
                flight_data,
                ensure_ascii=False
            ),
            "messages": [
                AIMessage(
                    content=(
                        "Outbound and return flight information "
                        "retrieved from Google Flights through SerpApi."
                    )
                )
            ],
            "llm_calls": state.get("llm_calls", 0),
        }

    except Exception as exc:
        print("Flight Agent Error:", exc)

        result = {
            "status": "unavailable",
            "reason": str(exc),
            "outbound": {},
            "return": {},
        }

        return {
            "flight_results": json.dumps(
                result,
                ensure_ascii=False
            ),
            "messages": [
                AIMessage(
                    content="Flight information could not be retrieved."
                )
            ],
            "llm_calls": state.get("llm_calls", 0),
        }


# ============================================================
# HOTEL AGENT
# ============================================================
#
# NO LLM
#
# Tavily MCP performs the search.
# Return structured search results to the frontend.
# ============================================================

async def hotel_agent(
    state: TravelState
):

    destination = state.get(
        "planning_destination",
        state["destination"]
    )

    query = f"""
Best hotels and accommodation in {destination}.

Trip duration:
{state["days"]} days

Budget:
{state["budget"]} {state["currency"]}

Travel style:
{state["style"]}

Interests:
{state["interests"] or "General travel"}

Find practical hotel/accommodation options.

Return the actual Tavily search results.
Do not summarize the results.
Do not invent hotel names.
Do not invent prices.
Do not invent availability.
""".strip()

    try:

        result = await tavily_mcp_search(
            query
        )

        # ====================================================
        # NORMALIZE TAVILY RESPONSE
        # ====================================================

        hotel_results = []

        def collect_results(value):

            if value is None:
                return

            if (
                isinstance(value, dict)
                and isinstance(
                    value.get("results"),
                    list
                )
            ):
                for item in value["results"]:
                    collect_results(item)

                return

            if (
                isinstance(value, dict)
                and isinstance(
                    value.get("text"),
                    str
                )
            ):

                try:

                    nested = json.loads(
                        value["text"]
                    )

                    collect_results(
                        nested
                    )

                except Exception:
                    pass

                return

            if isinstance(
                value,
                list
            ):

                for item in value:
                    collect_results(item)

                return

            if isinstance(
                value,
                dict
            ):

                if (
                    value.get("title")
                    or value.get("name")
                ):
                    hotel_results.append(
                        value
                    )

        collect_results(
            result
        )

        # ====================================================
        # HOTEL NAME EXTRACTION
        #
        # Deterministic Python preprocessing.
        # NO LLM CALL.
        # ====================================================

        extracted_hotels = []

        seen = set()

        def save_hotel(
            name,
            source
        ):

            name = str(
                name or ""
            ).strip()

            # Remove markdown / bullets.
            name = re.sub(
                r"^[#*\-–—👉\s]+",
                "",
                name
            )

            name = re.sub(
                r"[#*\-–—👉\s]+$",
                "",
                name
            )

            name = name.strip()

            if not name:
                return

            # Remove trailing punctuation.
            name = name.rstrip(
                ".,:;–—-"
            ).strip()

            if not name:
                return

            key = name.casefold()

            source_url = str(
                source.get("url")
                or ""
            ).casefold()

            if any(
                blocked_domain in source_url
                for blocked_domain in (
                    "youtube.com",
                    "youtu.be",
                    "facebook.com",
                )
            ):
                return

            generic_names = {
                "budget hotel",
                "budget hotels",
                "hotel",
                "hotels",
                "mid-range hotel",
                "mid-range hotels",
                "mid range hotel",
                "mid range hotels",
                "search hotel",
                "search hotels",
                "search dubai hotel",
                "search dubai hotels",
                "the best areas & hotel",
                "the best areas & hotels",
            }

            if key in generic_names:
                return

            # ------------------------------------------------
            # Reject obvious article/search-result titles.
            # ------------------------------------------------

            blocked_phrases = (
                "best hotels",
                "top hotels",
                "cheap hotels",
                "hotels in ",
                "hotel in ",
                "where to stay",
                "accommodation in",
                "travelling cost",
                "traveling cost",
                "travel guide",
                "travel tips",
                "tips and advice",
                "updated 2026 promos",
                "updated 2025 promos",
                "search hotels",
                "find hotels",
                "hotel information",
                "hotel deals",
                "hotel prices",
                "hotels & homes",
                "hoteles",
                "logotipo",
                "courtesy",
                "tripadvisor",
                "booking.com",
                "expedia",
                "youtube",
                "facebook",
            )

            if any(
                phrase in key
                for phrase in blocked_phrases
            ):
                return

            # ------------------------------------------------
            # Reject sentence-like text.
            # ------------------------------------------------

            sentence_words = (
                " is ",
                " are ",
                " has ",
                " have ",
                " offers ",
                " includes ",
                " located ",
                " because ",
                " which ",
                " that ",
                " when ",
                " where ",
                " looking for ",
                " check availability ",
            )

            padded = f" {key} "

            if any(
                word in padded
                for word in sentence_words
            ):
                return

            # ------------------------------------------------
            # Reasonable hotel-name length.
            # ------------------------------------------------

            if len(name) < 4:
                return

            if len(name) > 100:
                return

            # ------------------------------------------------
            # Hotel/property indicators.
            #
            # Also include major hotel brands whose names
            # don't contain "hotel" or "resort".
            # ------------------------------------------------

            hotel_keywords = (
                "hotel",
                "resort",
                "inn",
                "suites",
                "rotana",
                "residence",
                "residences",
                "apartments",
                "hostel",
                "palace",
                "lodge",
                "villa",
                "villas",
                "retreat",
                "manor",
                "heritage",
                "ritz-carlton",
                "ritz carlton",
                "oberoi",
                "taj ",
                "fairmont",
                "raffles",
                "hyatt",
                "marriott",
                "hilton",
                "radisson",
                "four seasons",
                "st. regis",
                "st regis",
                "leela",
                "aman",
                "six senses",
                "alila",
                "anantara",
                "westin",
                "sheraton",
                "novotel",
                "ibis",
                "jumeirah",
                "address",
                "atlantis",
            )

            if not any(
                keyword in key
                for keyword in hotel_keywords
            ):
                return

            # ------------------------------------------------
            # Deduplicate.
            # ------------------------------------------------

            if key in seen:
                return

            seen.add(key)

            extracted_hotels.append(
                {
                    "title": name,
                    "content": str(
                        source.get("content")
                        or source.get("description")
                        or ""
                    ).strip()[:500],
                    "url": str(
                        source.get("url")
                        or ""
                    ).strip(),
                    "image": str(
                        source.get("image")
                        or ""
                    ).strip()
                }
            )

        # ====================================================
        # EXTRACT FROM EACH TAVILY ARTICLE
        # ====================================================

        for item in hotel_results:

            if not isinstance(
                item,
                dict
            ):
                continue

            title = str(
                item.get("title")
                or item.get("name")
                or ""
            ).strip()

            content = str(
                item.get("content")
                or item.get("description")
                or ""
            ).strip()

            source_text = (
                f"{title}\n{content}"
            )

            # ------------------------------------------------
            # 1. Markdown headings
            #
            # ### The Oberoi, Mumbai
            # ### SUJÁN Sher Bagh
            # ### Samode Palace
            # ------------------------------------------------

            heading_pattern = (
                r"(?:^|\s)#{2,6}\s*"
                r"([A-Z][A-Za-z0-9&' .\-]{3,100}?)"
                r"(?=\s+(?:Featured|Address|Price|Read|"
                r"Hot List|Gold List|Check|"
                r"Book|View)|\s*$)"
            )

            for match in re.findall(
                heading_pattern,
                source_text
            ):

                candidate = (
                    match
                    .strip()
                )

                save_hotel(
                    candidate,
                    item
                )

            # ------------------------------------------------
            # 2. Category-based recommendations
            #
            # For luxury: The Oberoi, Mumbai
            # For a honeymoon: The Oberoi Amarvilas, Agra
            # For a wedding: Fairmont Udaipur Palace, Rajasthan
            # ------------------------------------------------

            category_pattern = (
                r"(?:For\s+)?"
                r"(?:luxury|honeymoon|wedding|"
                r"safari|budget|mid[- ]range|"
                r"boutique|affordable luxury|nicer)"
                r"\s*:\s*"
                r"([A-Z][A-Za-z0-9&' .\-]+?)"
                r"(?=\s*(?:,|\.|;|\n|"
                r"\s+Featured|\s+Read|\s+Check))"
            )

            for match in re.findall(
                category_pattern,
                source_text,
                flags=re.IGNORECASE
            ):

                candidate = (
                    match
                    .strip()
                )

                save_hotel(
                    candidate,
                    item
                )

            # ------------------------------------------------
            # 3. "Click to Book ..."
            # ------------------------------------------------

            click_pattern = (
                r"(?:Click to Book|Book)\s+"
                r"(?:the\s+)?"
                r"([A-Z][A-Za-z0-9&' .\-]{3,100}?)"
                r"(?=\s*(?:\.|,|;|\n|$))"
            )

            for match in re.findall(
                click_pattern,
                source_text,
                flags=re.IGNORECASE
            ):

                save_hotel(
                    match,
                    item
                )

            # ------------------------------------------------
            # 4. Explicit property names
            #
            # The Westin Dubai Mina Seyahi Beach Resort
            # Al Bandar Rotana Dubai Creek
            # Royal Orchid Beach Resort & Spa
            # ------------------------------------------------

            explicit_property_pattern = (
                r"\b("
                r"[A-Z][A-Za-z0-9&' .\-]{2,90}"
                r"(?:Hotel|Resort|Inn|Suites|"
                r"Rotana|Residence|Residences|"
                r"Apartments|Hostel|Palace|"
                r"Lodge|Villa|Villas|Retreat|"
                r"Manor|Beach Resort)"
                r"(?:\s*&\s*[A-Za-z][A-Za-z0-9&' .\-]*)?"
                r")"
            )

            for match in re.findall(
                explicit_property_pattern,
                source_text
            ):

                save_hotel(
                    match,
                    item
                )

        # ====================================================
        # FALLBACK
        #
        # If deterministic extraction found nothing,
        # return no hotel names rather than displaying
        # article titles as hotels.
        # ====================================================

        hotel_data = {

            "status":
                "success"
                if extracted_hotels
                else "no_results",

            "destination":
                destination,

            "results":
                extracted_hotels[:8]

        }

        print(
            "\nEXTRACTED HOTEL DATA:"
        )

        print(
            json.dumps(
                hotel_data,
                ensure_ascii=False,
                indent=2
            )[:5000]
        )

    except Exception as exc:

        print(
            "Hotel Agent Error:",
            exc
        )

        hotel_data = {

            "status":
                "unavailable",

            "destination":
                destination,

            "results":
                [],

            "reason":
                str(exc)

        }

    return {

        "hotel_results":
            json.dumps(
                hotel_data,
                ensure_ascii=False
            ),

        "messages": [

            AIMessage(
                content=(
                    "Hotel information retrieved "
                    "without LLM."
                )
            )

        ],

        "llm_calls":
            state.get(
                "llm_calls",
                0
            )
    }
# ============================================================
# WEATHER AGENT
# ============================================================
#
# NO LLM
#
# Weather MCP output is passed directly in compact form.
# ============================================================

async def weather_agent(state: TravelState):

    print("\nINSIDE WEATHER AGENT\n")

    destination = state.get(
        "planning_destination",
        state["destination"]
    )

    travel_date = state.get("travel_date")
    days = int(state["days"])

    start_date = datetime.strptime(
        str(travel_date),
        "%Y-%m-%d"
    ).date()

    trip_dates = [
        (
            start_date
            + timedelta(days=offset)
        ).isoformat()
        for offset in range(days)
    ]

    trip_end_date = trip_return_date(
        travel_date,
        days
    ).isoformat()

    try:

        # ----------------------------------------------------
        # CURRENT WEATHER
        # ----------------------------------------------------

        current_weather = await weather_mcp_call(
            "get_current_weather",
            {
                "city": destination
            }
        )

        current_data = extract_json(current_weather)

        # MCP may return:
        # [{"type": "text", "text": "{...}"}]
        if isinstance(current_data, list):
            for item in current_data:
                if isinstance(item, dict) and item.get("text"):
                    parsed = extract_json(item["text"])
                    if parsed:
                        current_data = parsed
                        break

        if not isinstance(current_data, dict):
            current_data = {
                "status": "unavailable"
            }

        # ----------------------------------------------------
        # FORECAST
        # ----------------------------------------------------

        forecast = await weather_mcp_call(
            "get_forecast",
            {
                "city": destination,
                "days": min(max(days, 5), 7)
            }
        )

        forecast_data = extract_json(forecast)

        if isinstance(forecast_data, list):
            for item in forecast_data:
                if isinstance(item, dict) and item.get("text"):
                    parsed = extract_json(item["text"])
                    if parsed:
                        forecast_data = parsed
                        break

        # ----------------------------------------------------
        # NORMALIZE FORECAST
        # ----------------------------------------------------

        available_forecast = []

        if isinstance(forecast_data, dict):

            raw_forecast = forecast_data.get(
                "forecast",
                []
            )

            if isinstance(raw_forecast, list):
                available_forecast = raw_forecast

        # ----------------------------------------------------
        # AGGREGATE FORECAST BY TRIP DATE
        # ----------------------------------------------------

        forecast_by_date = {}

        for item in available_forecast:

            if not isinstance(item, dict):
                continue

            forecast_date = (
                str(item.get("datetime", ""))
                .split(" ", 1)[0]
            )

            if not forecast_date:
                continue

            forecast_by_date.setdefault(
                forecast_date,
                []
            ).append(item)

        per_day_forecast = []

        for date_value in trip_dates:

            entries = forecast_by_date.get(
                date_value,
                []
            )

            if not entries:

                per_day_forecast.append(
                    {
                        "date": date_value,
                        "status": (
                            "forecast_unavailable_too_far_ahead"
                        )
                    }
                )

                continue

            temperatures = [
                float(item["temperature"])
                for item in entries
                if item.get("temperature") is not None
            ]

            humidities = [
                float(item["humidity"])
                for item in entries
                if item.get("humidity") is not None
            ]

            rain_probabilities = [
                float(item.get("rain_probability", 0) or 0)
                for item in entries
            ]

            conditions = [
                str(
                    item.get("weather")
                    or item.get("condition")
                    or ""
                ).strip()
                for item in entries
            ]

            conditions = [
                condition
                for condition in conditions
                if condition
            ]

            summary = {
                "date": date_value,
                "status": "forecast_available",
                "source": "forecast",
            }

            if temperatures:
                summary["temp_min_c"] = round(
                    min(temperatures),
                    1
                )
                summary["temp_max_c"] = round(
                    max(temperatures),
                    1
                )

            if conditions:
                summary["condition"] = (
                    Counter(conditions)
                    .most_common(1)[0][0]
                )

            if humidities:
                summary["humidity"] = round(
                    sum(humidities)
                    / len(humidities)
                )

            if rain_probabilities:
                summary["rain_probability"] = round(
                    max(rain_probabilities),
                    2
                )

            per_day_forecast.append(
                summary
            )

        # ----------------------------------------------------
        # FINAL CLEAN WEATHER DATA
        # ----------------------------------------------------

        weather_data = {
            "destination": destination,
            "travel_date": travel_date,
            "trip_end_date": trip_end_date,
            "today_actual_weather": current_data,
            "per_day_forecast": per_day_forecast,
        }

        weather_text = safe_json(
            weather_data,
            5000
        )

        print("\nCOMPACT WEATHER:")
        print(weather_text)

    except Exception as exc:

        print(
            "Weather Agent Error:",
            exc
        )

        weather_text = safe_json(
            {
                "status": "unavailable",
                "destination": destination,
                "reason": str(exc),
            },
            1500
        )

    return {
        "weather_results": weather_text,

        "messages": [
            AIMessage(
                content=(
                    "Weather information retrieved "
                    "without LLM."
                )
            )
        ],

        "llm_calls": state.get(
            "llm_calls",
            0
        )
    }


# ============================================================
# ITINERARY AGENT
# ============================================================
#
# THIS IS THE ONLY LLM CALL
# ============================================================

def itinerary_agent(
    state: TravelState
):

    print(
        "\nINSIDE ITINERARY AGENT\n"
    )

    route = state.get(
        "route",
        []
    )

    route_text = " → ".join(
        item["name"]
        for item in route
    )

    days = int(
        state["days"]
    )

    itinerary_return_date = (
        trip_return_date(
            state["travel_date"],
            days
        )
    ).isoformat()

    # --------------------------------------------------------
    # COMPACT DATA
    # --------------------------------------------------------
    # Keep MCP data small to reduce Groq token usage.
    # --------------------------------------------------------

    flight_info = compact_flight_data(
        state.get(
            "flight_results",
            ""
        ),
        6000
    )

    hotel_data = extract_json(
        state.get(
            "hotel_results",
            ""
        )
    )

    hotel_candidates = []

    if isinstance(
        hotel_data,
        dict
    ):

        results = hotel_data.get(
            "results",
            []
        )

        if isinstance(
            results,
            list
        ):

            for item in results[:8]:

                if not isinstance(
                    item,
                    dict
                ):
                    continue

                name = str(
                    item.get("name")
                    or item.get("title")
                    or ""
                ).strip()

                if not name:
                    continue

                hotel_candidates.append(
                    {
                        "name": name,
                        "url": str(
                            item.get("url")
                            or ""
                        ).strip()
                    }
                )

    hotel_info = safe_json(
        {
            "destination": state.get(
                "planning_destination",
                state["destination"]
            ),
            "hotels": hotel_candidates
        },
        1600
    )

    weather_info = compact_text(
        state.get(
            "weather_results",
            ""
        ),
        2200
    )

    # --------------------------------------------------------
    # SINGLE LLM PROMPT
    # --------------------------------------------------------

    prompt = f"""
You are the ONLY reasoning model in a travel planning
system.

Create a complete, practical and realistic EXACTLY
{days}-day itinerary.

The structured trip duration is authoritative.
If the user's free-text request contains a different
number of days, ALWAYS use {days} days.

============================================================
USER REQUEST
============================================================

{trip_request_text(state)}

============================================================
TRIP DETAILS
============================================================

SOURCE:
{state["source"]}

ORIGINAL DESTINATION:
{state["destination"]}

PLANNING DESTINATION:
{state.get("planning_destination", state["destination"])}

DURATION:
{days} days

BUDGET:
{state["budget"]} {state["currency"]}

TRAVEL STYLE:
{state["style"]}

INTERESTS:
{state["interests"] or "General travel"}

============================================================
ROUTE
============================================================

{route_text}

Use this route as the authoritative route.

Do not invent additional destinations.

============================================================
FLIGHT DATA
============================================================

{flight_info}

============================================================
HOTEL DATA
============================================================

{hotel_info}

============================================================
WEATHER DATA
============================================================

{weather_info}

The today_actual_weather field describes conditions right
now and must never be used to describe the trip dates.
Only use each day's entry under per_day_forecast for that
day's weather. If a day's status is
forecast_unavailable_too_far_ahead, do not state any
specific weather fact for that day. You may note general
seasonal expectations only if you already know them;
otherwise omit weather-based reasoning for that day.

============================================================
STRICT GROUNDING RULES
============================================================

Use supplied MCP data as the source of truth for
specific factual claims.

DO NOT invent:

- flight numbers
- airlines for specific flights
- departure times
- arrival times
- flight prices
- flight duration
- confirmed flight availability
- hotel availability
- hotel booking confirmation
- restaurant reservations
- ticket availability
- VIP access
- private tours
- private cruises
- weather values
- temperature
- rainfall
- humidity
- rain probability
- real-time prices

If information is unavailable, do not make a specific
claim about it.

Hotel names may ONLY be used if they appear in
HOTEL DATA.

Flight information may ONLY be used if supported by
FLIGHT DATA.

IMPORTANT FLIGHT SAFETY RULE:

FLIGHT DATA comes from SerpApi Google Flights.

Specific flight information may ONLY be used when it
appears in:

- best_flights
- other_flights

Never invent:

- flight number
- airline
- departure time
- arrival time
- flight duration
- price
- aircraft
- layovers
- airport
- availability

If FLIGHT DATA has:

- status = "unavailable"

or

- both best_flights and other_flights are empty

then do not create a specific flight.

If air travel is necessary, use only:

"Flight information to be confirmed."

Do not attach a specific airline, flight number,
time, duration, price, or aircraft to that statement.

If a specific flight is present in best_flights or
other_flights, use ONLY the values supplied in that
flight record.

The flight data contains separate OUTBOUND and RETURN
sections when available.

OUTBOUND FLIGHT RULE:
- If outbound flight data is available, use its exact
  departure and arrival date/time when representing the
  outbound flight.
- Never convert or alter the supplied time.

RETURN FLIGHT RULE:
- If return flight data is available, include the return
  journey in the itinerary on the return date.
- Use the exact return departure and arrival date/time
  supplied by the RETURN flight data.
- Never invent a return flight.
- Never reuse the outbound time for the return flight.
- Never omit the return journey when verified return
  flight data is available.

The dedicated flight section will display the supplied
flight information separately.

Weather-related factual statements may ONLY be based on
WEATHER DATA.

============================================================
ITINERARY RULES
============================================================

Create EXACTLY {days} days.

Day numbers MUST be:

1, 2, 3, ... {days}

NEVER create Day 0.

NEVER create Day {days + 1}.

Every day MUST contain:

- day
- title
- location
- route
- activities
- day_budget

Each day SHOULD contain 5 to 6 meaningful, well-paced
activities so the day feels full and enjoyable without
being rushed.

NEVER generate fewer than 4 or more than 6 activities
for a day.

NEVER invent an activity merely to reach the target
activity count.

If verified transportation information is unavailable,
do not create a fabricated transportation activity.

Every activity MUST contain:

- time
- activity
- transport
- estimated_cost
- currency

TIME FORMAT RULE:
- Use 24-hour HH:MM.
- Examples: 06:00, 09:30, 14:00, 23:30.
- Never output 6:0, 6:00 AM, 9.30, or other inconsistent formats.
- For a time range use HH:MM-HH:MM.
- For verified flights, copy the exact HH:MM portion from
  the supplied flight timestamp.
- Do not create a flight time when flight data is unavailable.

TRIP DATE RULE:
- Day 1 corresponds to the outbound travel date.
- The final day corresponds to the return date:
  {itinerary_return_date}.
- Do not place a return flight on an earlier date.
- If an overnight outbound flight arrives on Day 2, use the
  actual arrival time only on the arrival date.

DAY-BY-DAY FLIGHT ACTIVITY RULE:
- Day 1's activities list MUST include one activity
  representing the outbound/departure flight as the first
  activity of the day.
- The final day's (Day {days}) activities list MUST include
  one activity representing the return flight as an activity
  of that day, placed at the appropriate time.
- This is in addition to, and consistent with, the dedicated
  Flight Information section. The flight must be represented
  as one of that day's activities, not skipped.
- If FLIGHT DATA has a verified outbound or return option,
  use its exact time, airline, and flight number in the
  activity and time fields according to the flight safety
  rules above.
- If no verified flight data exists for that leg, the
  activity field MUST be exactly:
  "Flight information to be confirmed."
  Set transport to "Flight" and do not invent a specific
  time, airline, flight number, duration, aircraft, airport,
  or price. Use 0 for estimated_cost unless a verified price
  is supplied.

Make the schedule geographically practical.

Avoid unnecessary backtracking.

Respect:

- budget
- travel style
- interests
- weather
- route
- transportation
- realistic sightseeing time

============================================================
WEATHER LOGIC
============================================================

Use the supplied weather data intelligently.

For each itinerary day, use only that day's matching entry
from per_day_forecast.

If weather is favorable:

Prefer appropriate outdoor sightseeing.

If weather is unfavorable:

Prefer indoor activities or weather-safe alternatives.

Do NOT invent weather values.

============================================================
BUDGET LOGIC
============================================================

Keep daily spending reasonably aligned with:

{state["budget"]} {state["currency"]}

The sum of day_budget values should be a reasonable
estimate for activities during the trip.

Do NOT include international flight costs in day_budget
unless an actual price is explicitly supplied.

Do NOT fabricate real-time prices.

Estimated costs must be clearly treated as estimates.

============================================================
TRAVEL STYLE
============================================================

Respect the user's travel style:

{state["style"]}

However, do not make every activity expensive simply
because the style is Luxury.

Choose activities that provide good value and fit the
user's interests.

============================================================
FINAL VALIDATION BEFORE OUTPUT
============================================================

Before returning the structured result, verify:

1. Exactly {days} day objects exist.

2. Day numbers are exactly:
   1 through {days}.

3. Every day contains:
   - day
   - title
   - location
   - route
   - activities
   - day_budget

4. Every day contains between 4 and 6 activities.

5. Prefer 5 to 6 activities per day.

6. Day 1 contains a departure/outbound flight activity.

7. The final day contains a return flight activity.

8. Every activity contains:
   - time
   - activity
   - transport
   - estimated_cost
   - currency

9. No fabricated flight information.

10. No fabricated hotel availability.

11. No fabricated weather information.

12. No fabricated reservations.

13. No fabricated real-time prices.

14. Do not change the supplied route.

15. Do not change the user's destination.

Return ONLY the structured Itinerary object.
""".strip()

    # --------------------------------------------------------
    # ONE STRUCTURED LLM CALL
    # --------------------------------------------------------

    try:

        structured_llm = llm.with_structured_output(
            Itinerary,
            method="json_schema",
            strict=True
        )

        response = structured_llm.invoke(
            [
                SystemMessage(
                    content=(
                        "You are a highly accurate travel "
                        "itinerary generator. "
                        "Generate only the requested "
                        "structured itinerary. "
                        "Use supplied information for "
                        "specific factual claims. "
                        "Never fabricate unavailable "
                        "travel information."
                    )
                ),

                HumanMessage(
                    content=prompt
                )
            ]
        )

        # ----------------------------------------------------
        # CONVERT RESPONSE
        # ----------------------------------------------------

        itinerary = response.model_dump()

        generated_days = itinerary.get(
            "days",
            []
        )

        # ----------------------------------------------------
        # VALIDATE NUMBER OF DAYS
        # ----------------------------------------------------

        if len(generated_days) != days:

            raise ValueError(
                f"Expected {days} days, "
                f"got {len(generated_days)}."
            )

        # ----------------------------------------------------
        # PYTHON-SIDE NORMALIZATION
        # ----------------------------------------------------
        # No second LLM call.
        # ----------------------------------------------------

        for index, day in enumerate(
            generated_days,
            start=1
        ):

            # Force sequential day number.
            day["day"] = index

            activities = day.get(
                "activities",
                []
            )

            # ------------------------------------------------
            # TOO MANY ACTIVITIES
            # ------------------------------------------------
            # The model may occasionally return more than 6.
            # Do not waste another LLM call fixing this.
            # Keep the first 6 activities.
            # ------------------------------------------------

            if len(activities) > 6:
                
                print(
                    f"Day {index}: LLM returned "
                    f"{len(activities)} activities. "
                    f"Trimming to 6 locally."
                )

                day["activities"] = (
                    activities[:6]
                )

            # ------------------------------------------------
            # TOO FEW ACTIVITIES
            # ------------------------------------------------
            # Do not fabricate activities.
            # ------------------------------------------------

            elif len(activities) < 4:

                raise ValueError(
                    f"Day {index} contains only "
                    f"{len(activities)} activities. "
                    f"At least 4 are required."
                )

        # ----------------------------------------------------
        # REQUIRED FLIGHT ACTIVITIES
        # ----------------------------------------------------
        # Deterministically enforce the outbound and return
        # flight activities without making another LLM call.
        # ----------------------------------------------------

        ensure_required_flight_activities(
            itinerary=itinerary,
            flight_data=extract_json(
                state.get(
                    "flight_results",
                    ""
                )
            ),
            currency=state.get(
                "currency",
                "INR"
            ),
            source=state.get(
                "source",
                ""
            ),
        )

        # ----------------------------------------------------
        # ROUTE MUST COME FROM PYTHON
        # ----------------------------------------------------

        itinerary["route"] = route

        # ----------------------------------------------------
        # COUNT EXACTLY ONE LLM CALL
        # ----------------------------------------------------

        llm_calls = (
            state.get(
                "llm_calls",
                0
            ) + 1
        )

        # ----------------------------------------------------
        # DEBUG OUTPUT
        # ----------------------------------------------------

        print(
            "\n========== GENERATED ITINERARY =========="
        )

        print(
            json.dumps(
                itinerary,
                indent=2,
                ensure_ascii=False
            )
        )

        print(
            "LLM CALLS:",
            llm_calls
        )

        print(
            "==========================================\n"
        )

        # ----------------------------------------------------
        # RETURN
        # ----------------------------------------------------
        
        
        return {
            
            "route": route,

            "itinerary": itinerary,

            "messages": [],

            "llm_calls": llm_calls
        }

    # --------------------------------------------------------
    # NO ADDITIONAL LLM FALLBACK
    # --------------------------------------------------------

    except Exception as exc:

        print(
            "\nITINERARY LLM ERROR:",
            exc
        )

        raise RuntimeError(
            "Itinerary generation failed. "
            "No additional LLM fallback was executed "
            "to protect the Groq token limit. "
            f"Error: {exc}"
        ) from exc

# ============================================================
# FINAL RESPONSE FORMATTER
# ============================================================
#
# NO LLM
#
# This formats the already-generated data into the final
# user-facing answer.
# ============================================================

def final_agent(
    state: TravelState
):

    print(
        "\nINSIDE FINAL AGENT\n"
    )

    itinerary = state.get(
        "itinerary",
        {}
    )

    title = itinerary.get(
        "title",
        f"{state['days']}-Day Trip"
    )

    summary = itinerary.get(
        "summary",
        ""
    )

    route = state.get(
        "route",
        []
    )

    # --------------------------------------------------------
    # ROUTE TEXT
    # --------------------------------------------------------

    route_text = " → ".join(
        item["name"]
        for item in route
    )

    # --------------------------------------------------------
    # BUILD MARKDOWN
    # --------------------------------------------------------

    parts = []

    parts.append(
        f"# {title}"
    )

    if summary:

        parts.append(
            summary
        )

    parts.append(
        f"**Route:** {route_text}"
    )

    parts.append(
        f"**Duration:** {state['days']} days"
    )

    parts.append(
        f"**Budget:** "
        f"{state['budget']:,.2f} "
        f"{state['currency']}"
    )

    parts.append(
        f"**Style:** {state['style']}"
    )

    if state["interests"]:

        parts.append(
            f"**Interests:** "
            f"{state['interests']}"
        )

    # --------------------------------------------------------
    # FLIGHT SECTION
    # --------------------------------------------------------

    parts.append(
        "\n## ✈️ Flight Information"
    )

    flight_data = (
        extract_json(
            state.get(
                "flight_results",
                ""
            )
        )
    )

    if isinstance(
        flight_data,
        dict
    ):

        status = flight_data.get(
            "status",
            ""
        )

        if status == "success":

            route_data = flight_data.get(
                "route",
                {}
            )

            outbound_data = flight_data.get(
                "outbound",
                {}
            )

            return_data = flight_data.get(
                "return",
                {}
            )

            flight_sections = [
                (
                    "Outbound",
                    outbound_data,
                    flight_data.get("outbound_date", "N/A"),
                ),
                (
                    "Return",
                    return_data,
                    flight_data.get("return_date", "N/A"),
                ),
            ]

            total_options = 0

            for _, section_data, _ in flight_sections:
                if not isinstance(section_data, dict):
                    continue

                total_options += len(
                    section_data.get(
                        "best_flights",
                        []
                    )
                    or []
                )

                total_options += len(
                    section_data.get(
                        "other_flights",
                        []
                    )
                    or []
                )

            parts.append(
                f"- Outbound date: "
                f"{flight_data.get('outbound_date', 'N/A')}"
            )

            parts.append(
                f"- Return date: "
                f"{flight_data.get('return_date', 'N/A')}"
            )

            parts.append(
                f"- Route: "
                f"{route_data.get('source_iata', 'N/A')} "
                f"→ "
                f"{route_data.get('destination_iata', 'N/A')}"
            )

            parts.append(
                f"- Flight options found: "
                f"{total_options}"
            )

            # ------------------------------------------------
            # FLIGHT OPTIONS
            # ------------------------------------------------

            for section_name, section_data, section_date in flight_sections:
                if not isinstance(section_data, dict):
                    continue

                best_flights = section_data.get(
                    "best_flights",
                    []
                )

                other_flights = section_data.get(
                    "other_flights",
                    []
                )

                options = (
                    (best_flights or [])
                    + (other_flights or [])
                )

                if not options:
                    parts.append(
                        f"- {section_name}: no verified options returned "
                        f"for {section_date}."
                    )
                    continue

                parts.append(
                    f"- {section_name} options for {section_date}:"
                )

                for index, flight in enumerate(
                    options[:3],
                    start=1
                ):

                    if not isinstance(
                        flight,
                        dict
                    ):
                        continue

                    segments = flight.get(
                        "flights",
                        []
                    )

                    if not segments:
                        continue

                    first_segment = segments[0]

                    last_segment = segments[-1]

                    airline = first_segment.get(
                        "airline",
                        "N/A"
                    )

                    flight_number = first_segment.get(
                        "flight_number",
                        "N/A"
                    )

                    departure = (
                        first_segment
                        .get(
                            "departure_airport",
                            {}
                        )
                        .get(
                            "time",
                            "N/A"
                        )
                    )

                    arrival = (
                        last_segment
                        .get(
                            "arrival_airport",
                            {}
                        )
                        .get(
                            "time",
                            "N/A"
                        )
                    )

                    duration = flight.get(
                        "total_duration",
                        "N/A"
                    )

                    price = flight.get(
                        "price",
                        "N/A"
                    )

                    parts.append(
                        f"  - Option {index}: "
                        f"{airline} {flight_number}, "
                        f"{departure} → {arrival}, "
                        f"duration {duration} min, "
                        f"price {price} "
                        f"{state['currency']}"
                    )

        elif status == "unavailable":

            parts.append(
                "- Flight information unavailable."
            )

            reason = flight_data.get(
                "reason"
            )

            if reason:

                parts.append(
                    f"- Reason: {reason}"
                )

        else:

            parts.append(
                "- Flight information unavailable."
            )

    else:

        parts.append(
            "- Flight information unavailable."
        )

        # --------------------------------------------------------
    # HOTEL SECTION
    # --------------------------------------------------------

    parts.append(
        "\n## 🏨 Hotel Information"
    )

    hotel_data = extract_json(
        state.get(
            "hotel_results",
            ""
        )
    )

    hotel_items = []

    def add_hotel(
        name,
        content="",
        url=""
    ):
        name = str(
            name or ""
        ).strip()

        if not name:
            return

        key = name.casefold()

        # ----------------------------------------------------
        # Ignore Tavily article/forum/search-result titles.
        # ----------------------------------------------------

        blocked_phrases = (
            "guide to",
            "best hotels",
            "top hotels",
            "where to stay",
            "accommodation in",
            "hotels in",
            "tips and advice",
            "travelling to",
            "traveling to",
            "hotel/apartment",
            "forum",
            "tripadvisor",
            "facebook",
        )

        if any(
            phrase in key
            for phrase in blocked_phrases
        ):
            return

        # ----------------------------------------------------
        # Only accept names that look like actual
        # accommodation properties.
        # ----------------------------------------------------

        hotel_keywords = (
            "hotel",
            "resort",
            "inn",
            "suites",
            "rotana",
            "residence",
            "apartments",
            "hostel",
        )

        if not any(
            keyword in key
            for keyword in hotel_keywords
        ):
            return

        hotel_items.append(
            {
                "name": name,
                "content": str(
                    content or ""
                ).strip(),
                "url": str(
                    url or ""
                ).strip(),
            }
        )

    def extract_hotel_names_from_text(
        text,
        url=""
    ):
        """
        Extract likely hotel/property names from Tavily
        article content using deterministic rules.

        No LLM call.
        """

        if not text:
            return

        text = " ".join(
            str(text).split()
        )

        found_names = set()

        def save_hotel_name(
            name,
            context=""
        ):
            name = str(
                name or ""
            ).strip()

            name = re.sub(
                r"^[#*\-–—👉\s]+",
                "",
                name
            )

            name = re.sub(
                r"[#*\-–—👉\s]+$",
                "",
                name
            ).strip()

            if not name:
                return

            key = name.casefold()

            # ------------------------------------------------
            # Reject obvious article/sentence text.
            # ------------------------------------------------

            blocked_phrases = (
                "guide",
                "best hotels",
                "top hotels",
                "where to stay",
                "accommodation",
                "tips and advice",
                "facebook",
                "tripadvisor",
                "click to book",
                "book your stay",
                "any of these",
                "the same hotel",
                "the best",
                "very good",
                "day before",
                "as soon as",
                "ahead as",
                "restaurant",
                "restaurants",
            )

            if any(
                phrase in key
                for phrase in blocked_phrases
            ):
                return

            # ------------------------------------------------
            # Reject sentence-like fragments.
            # ------------------------------------------------

            if len(name) < 4 or len(name) > 80:
                return

            if name.endswith(
                (".", ",", ":", ";")
            ):
                return

            padded = f" {key} "

            sentence_words = (
                " is ",
                " are ",
                " has ",
                " have ",
                " offers ",
                " includes ",
                " located ",
                " because ",
                " which ",
                " that ",
                " when ",
                " where ",
                " before ",
                " after ",
            )

            if any(
                word in padded
                for word in sentence_words
            ):
                return

            # ------------------------------------------------
            # A candidate must contain a recognizable
            # accommodation/property keyword.
            #
            # This intentionally rejects things such as:
            # "Rove City Center" if the source doesn't mark
            # it as a property in the surrounding pattern.
            # ------------------------------------------------

            property_keywords = (
                "hotel",
                "resort",
                "inn",
                "suites",
                "rotana",
                "residence",
                "residences",
                "apartments",
                "hostel",
                "villa",
                "lodge",
            )

            if not any(
                keyword in key
                for keyword in property_keywords
            ):
                return

            if key in found_names:
                return

            found_names.add(key)

            hotel_items.append(
                {
                    "name": name,
                    "content": str(
                        context or ""
                    ).strip()[:250],
                    "url": url,
                }
            )

        # ----------------------------------------------------
        # PATTERN 1
        #
        # Explicit hotel/property names in headings:
        #
        # ### Bvlgari Resort Dubai
        # ### Citymax Hotel Bur Dubai
        # ----------------------------------------------------

        heading_pattern = (
            r"(?:^|\s)#{2,6}\s*"
            r"([A-Z][A-Za-z0-9&' .&\-]{2,80}?"
            r"(?:Hotel|Resort|Inn|Suites|Rotana|"
            r"Residence|Residences|Apartments|"
            r"Hostel|Villa|Lodge)"
            r"(?:\s+[A-Z][A-Za-z0-9&' .&\-]{1,40})?)"
            r"(?=\s*(?:Featured|Address|Price|Read|"
            r"Hot List|Gold List|$))"
            )

        for match in re.findall(
            heading_pattern,
            text
        ):
            save_hotel_name(
                match,
                text[:400]
            )

        # ----------------------------------------------------
        # PATTERN 2
        #
        # Category + explicit property:
        #
        # Budget: Citymax Hotel Bur Dubai
        # Luxury: Bvlgari Resort Dubai
        # Nicer: Ambassador Hotel
        #
        # The property keyword is mandatory.
        # ----------------------------------------------------

        category_pattern = (
            r"(?:Budget|Mid-range|Midrange|Luxury|"
            r"Affordable luxury|Nicer(?:\s*\([^)]*\))?|"
            r"Boutique)"
            r"\s*[–—:-]\s*"
            r"([A-Z][A-Za-z0-9&' .\-]{2,70}"
            r"(?:Hotel|Resort|Inn|Suites|Rotana|"
            r"Residence|Residences|Apartments|"
            r"Hostel|Villa|Lodge))"
            r"(?=\s*[–—:-]|[.,;]|$)"
        )

        for match in re.findall(
            category_pattern,
            text
        ):
            save_hotel_name(
                match,
                text[:400]
            )

        # ----------------------------------------------------
        # PATTERN 3
        #
        # "Click to Book the Cove Rotana Resort"
        #
        # Property keyword is mandatory.
        # ----------------------------------------------------

        click_pattern = (
            r"(?:Click to Book|Book)"
            r"\s+(?:the\s+)?"
            r"([A-Z][A-Za-z0-9&' .\-]{2,70}"
            r"(?:Hotel|Resort|Inn|Suites|Rotana|"
            r"Residence|Residences|Apartments|"
            r"Hostel|Villa|Lodge))"
            r"(?=\s|[.,;]|$)"
        )

        for match in re.findall(
            click_pattern,
            text,
            flags=re.IGNORECASE
        ):
            save_hotel_name(
                match,
                text[:400]
            )

        # ----------------------------------------------------
        # PATTERN 4
        #
        # Explicit property names in normal sentences.
        #
        # Example:
        # "The Westin Dubai Mina Seyahi Beach Resort & Marina"
        # ----------------------------------------------------

        explicit_property_pattern = (
            r"\b"
            r"([A-Z][A-Za-z0-9&' .\-]{2,80}"
            r"(?:Hotel|Resort|Inn|Suites|Rotana|"
            r"Residence|Residences|Apartments|"
            r"Hostel|Villa|Lodge))"
            r"(?=\s+(?:is|offers|has|located|"
            r"for|with|and)\b|[.,;]|$)"
        )

        for match in re.findall(
            explicit_property_pattern,
            text
        ):
            save_hotel_name(
                match,
                text[:400]
            )
    def collect_hotel_items(value):

        if value is None:
            return

        if isinstance(value, dict):

            # Standard Tavily result list.
            if isinstance(
                value.get("results"),
                list
            ):

                for item in value["results"]:
                    collect_hotel_items(item)

                return

            # MCP text wrapper.
            if isinstance(
                value.get("text"),
                str
            ):

                nested = extract_json(
                    value["text"]
                )

                if nested is not None:
                    collect_hotel_items(
                        nested
                    )

                return

            # Direct search result.
            if (
                value.get("title")
                or value.get("name")
            ):

                title = str(
                    value.get("title")
                    or value.get("name")
                    or ""
                ).strip()

                content = str(
                    value.get("content")
                    or value.get("description")
                    or ""
                ).strip()

                url = str(
                    value.get("url")
                    or ""
                ).strip()

                # First try the actual result title.
                add_hotel(
                    title,
                    content,
                    url
                )

                # Then extract hotel names embedded
                # inside travel articles.
                extract_hotel_names_from_text(
                    content,
                    url
                )

                return

        if isinstance(value, list):

            for item in value:
                collect_hotel_items(item)

    collect_hotel_items(
        hotel_data
    )

    # --------------------------------------------------------
    # REMOVE DUPLICATES
    # --------------------------------------------------------

    unique_hotels = []
    seen = set()

    for hotel in hotel_items:

        name = str(
            hotel.get("name")
            or ""
        ).strip()

        key = name.casefold()

        if (
            not name
            or key in seen
        ):
            continue

        seen.add(key)

        unique_hotels.append(
            hotel
        )

    # --------------------------------------------------------
    # ADD CLEAN HOTEL DATA TO LLM CONTEXT
    # --------------------------------------------------------

    if unique_hotels:

        for hotel in unique_hotels[:8]:

            name = hotel["name"]
            url = hotel.get(
                "url",
                ""
            )

            parts.append(
                f"- **{name}**"
            )

            if url:

                parts.append(
                    f"  [View details]({url})"
                )

    else:

        parts.append(
            "Hotel information unavailable."
        )

    # --------------------------------------------------------
    # WEATHER SECTION
    # --------------------------------------------------------

    parts.append(
        "\n## 🌤️ Weather Information"
    )

    weather_data = extract_json(
        state.get(
            "weather_results",
            ""
        )
    )

    if isinstance(weather_data, dict):

        today_actual_weather = weather_data.get(
            "today_actual_weather",
            {}
        )

        per_day_forecast = weather_data.get(
            "per_day_forecast",
            []
        )

        if (
            isinstance(today_actual_weather, dict)
            and today_actual_weather
            and today_actual_weather.get("status") != "unavailable"
        ):
            parts.append(
                f"- **Today actual weather "
                f"({today_actual_weather.get('city', weather_data.get('destination', 'Destination'))}):** "
                f"{today_actual_weather.get('temperature_c', 'N/A')}°C, "
                f"feels like {today_actual_weather.get('feels_like_c', 'N/A')}°C, "
                f"{today_actual_weather.get('condition', 'N/A')}, "
                f"humidity {today_actual_weather.get('humidity', 'N/A')}%, "
                f"wind {today_actual_weather.get('wind_speed', 'N/A')} m/s. "
                f"This is not used as a trip-date forecast."
            )

        if isinstance(per_day_forecast, list):
            forecast_items = per_day_forecast
        else:
            forecast_items = []

        if forecast_items:
            parts.append(
                f"- Trip forecast window: "
                f"{weather_data.get('travel_date', 'N/A')} "
                f"to "
                f"{weather_data.get('trip_end_date', 'N/A')}."
            )

            for item in forecast_items:
                if not isinstance(item, dict):
                    continue

                if item.get("status") == "forecast_available":
                    parts.append(
                        f"- {item.get('date', '')}: "
                        f"{item.get('condition', 'N/A')}, "
                        f"{item.get('temp_min_c', 'N/A')}°C-"
                        f"{item.get('temp_max_c', 'N/A')}°C, "
                        f"humidity {item.get('humidity', 'N/A')}%, "
                        f"rain probability "
                        f"{round(float(item.get('rain_probability', 0)) * 100)}%."
                    )
                else:
                    parts.append(
                        f"- {item.get('date', '')}: "
                        f"trip-date forecast unavailable "
                        f"because the trip is too far ahead."
                    )

        if not forecast_items:
            parts.append(
                "- Trip-date forecast unavailable."
            )

    else:

        weather_text = state.get(
            "weather_results",
            ""
        )

        if weather_text:
            parts.append(
                str(weather_text)[:2500]
            )
        else:
            parts.append(
                "Weather information unavailable."
            )
            
            
        # --------------------------------------------------------
    # BUDGET SUMMARY
    # --------------------------------------------------------

    total_budget = float(
        state.get(
            "budget",
            0
        ) or 0
    )

    currency = state.get(
        "currency",
        "INR"
    )

    # --------------------------------------------------------
    # Determine whether a VERIFIED flight price exists.
    #
    # Never estimate or invent a flight price here.
    # --------------------------------------------------------

    flight_data = extract_json(
        state.get(
            "flight_results",
            ""
        )
    )

    def find_heuristic_flight_price(value):
        if value is None:
            return None

        if isinstance(value, dict):

            # Explicit fare/price fields only.
            for key in (
                "price",
                "fare",
                "flight_price",
                "total_price",
                "amount"
            ):

                raw = value.get(key)

                if isinstance(
                    raw,
                    (int, float)
                ) and raw >= 0:
                    return float(raw)

                if isinstance(
                    raw,
                    str
                ):

                    cleaned = (
                        raw
                        .replace(",", "")
                        .replace("₹", "")
                        .replace("$", "")
                        .strip()
                    )

                    try:
                        return float(
                            cleaned
                        )
                    except (
                        TypeError,
                        ValueError
                    ):
                        # Optional fare fields may be non-numeric labels.
                        pass

            # Search nested flight records.
            for nested in value.values():

                result = find_heuristic_flight_price(
                    nested
                )

                if result is not None:
                    return result

        elif isinstance(value, list):

            for item in value:

                result = find_heuristic_flight_price(
                    item
                )

                if result is not None:
                    return result

        return None

    verified_flight_price = None

    if isinstance(
        flight_data,
        dict
    ):

        raw_total_verified_price = flight_data.get(
            "total_verified_price"
        )

        if isinstance(
            raw_total_verified_price,
            (int, float)
        ) and raw_total_verified_price >= 0:

            verified_flight_price = float(
                raw_total_verified_price
            )

    if verified_flight_price is None:

        verified_flight_price = (
            find_heuristic_flight_price(
                flight_data
            )
        )

    # --------------------------------------------------------
    # Calculate on-ground itinerary spending.
    # --------------------------------------------------------

    planned_ground_cost = 0.0

    for day in itinerary.get(
        "days",
        []
    ):

        try:
            planned_ground_cost += float(
                day.get(
                    "day_budget",
                    0
                ) or 0
            )
        except (
            TypeError,
            ValueError
        ):
            pass

    parts.append(
        "\n## 💰 Budget Summary"
    )

    parts.append(
        f"- **Total trip budget:** "
        f"{total_budget:,.2f} {currency}"
    )

    if verified_flight_price is not None:

        remaining_after_flight = (
            total_budget
            - verified_flight_price
        )

        parts.append(
            f"- **Verified flight cost:** "
            f"{verified_flight_price:,.2f} "
            f"{currency}"
        )

        parts.append(
            f"- **Budget remaining after flight:** "
            f"{remaining_after_flight:,.2f} "
            f"{currency}"
        )

    else:

        parts.append(
            "- **Flight cost:** "
            "Not available / not verified"
        )

        parts.append(
            "- **Flight cost is NOT included "
            "in the calculated on-ground budget.**"
        )

    parts.append(
        f"- **Planned on-ground itinerary spending:** "
        f"{planned_ground_cost:,.2f} {currency}"
    )

    if verified_flight_price is not None:

        remaining_total = (
            total_budget
            - verified_flight_price
            - planned_ground_cost
        )

        parts.append(
            f"- **Estimated unallocated budget:** "
            f"{remaining_total:,.2f} {currency}"
        )

    else:

        on_ground_remaining = (
            total_budget
            - planned_ground_cost
        )

        parts.append(
            f"- **Unallocated on-ground budget:** "
            f"{on_ground_remaining:,.2f} {currency}"
        )

        parts.append(
            "- **Important:** This remaining amount "
            "does not represent the remaining total-trip "
            "budget because the flight fare could not "
            "be verified."
        )

    # --------------------------------------------------------
    # DAILY ITINERARY
    # --------------------------------------------------------
    parts.append(
        "\n## 🗓️ Daily Itinerary"
    )

    for day in itinerary.get(
        "days",
        []
    ):

        day_number = day.get(
            "day"
        )

        title = day.get(
            "title",
            ""
        )

        location = day.get(
            "location",
            ""
        )

        day_route = day.get(
            "route",
            ""
        )

        day_budget = day.get(
            "day_budget",
            0
        )

        parts.append(
            f"\n### Day {day_number}: {title}"
        )

        if location:

            parts.append(
                f"**Location:** {location}"
            )

        if day_route:

            parts.append(
                f"**Route:** {day_route}"
            )

        for activity in day.get(
            "activities",
            []
        ):

            parts.append(
                f"- **{activity.get('time', '')}** — "
                f"{activity.get('activity', '')} "
                f"({activity.get('transport', '')}) "
                f"— ~"
                f"{activity.get('estimated_cost', 0):,.2f} "
                f"{activity.get('currency', state['currency'])}"
            )

        parts.append(
            f"**Day budget:** "
            f"~{day_budget:,.2f} "
            f"{state['currency']}"
        )

    # --------------------------------------------------------
    # IMPORTANT NOTES
    # --------------------------------------------------------

    parts.append(
        "\n## ℹ️ Important Notes"
    )

    parts.append(
        "- Prices are estimates unless explicitly "
        "provided as verified data."
    )

    parts.append(
        "- Flight schedule samples do not guarantee "
        "route-specific availability."
    )

    parts.append(
        "- Hotel information is based on the supplied "
        "search results."
    )

    parts.append(
        "- Weather information is based only on the "
        "weather MCP response."
    )

    final_answer = "\n\n".join(
        parts
    )

    return {

        "final_answer":
            final_answer,

        "score":
            calculate_score(state),

        "messages": [
            AIMessage(
                content=(
                    "Final response formatted without LLM."
                )
            )
        ],

        "llm_calls":
            state.get(
                "llm_calls",
                0
            )
    }


# ============================================================
# SCORE
# ============================================================

def calculate_score(
    state: TravelState
) -> int:

    score = 80

    if state.get(
        "source",
        ""
    ).strip():

        score += 4

    if state.get(
        "destination",
        ""
    ).strip():

        score += 4

    if state.get(
        "budget",
        0
    ) > 0:

        score += 4

    if state.get(
        "interests",
        ""
    ).strip():

        score += 3

    if len(
        state.get(
            "route",
            []
        )
    ) >= 2:

        score += 3

    return min(
        score,
        98
    )


# ============================================================
# LANGGRAPH
# ============================================================

graph = StateGraph(
    TravelState
)


graph.add_node(
    "route_agent",
    route_agent
)

graph.add_node(
    "flight_agent",
    flight_agent
)

graph.add_node(
    "hotel_agent",
    hotel_agent
)

graph.add_node(
    "weather_agent",
    weather_agent
)

graph.add_node(
    "itinerary_agent",
    itinerary_agent
)

graph.add_node(
    "final_agent",
    final_agent
)


# ============================================================
# GRAPH FLOW
# ============================================================

graph.add_edge(
    START,
    "route_agent"
)

graph.add_edge(
    "route_agent",
    "flight_agent"
)

graph.add_edge(
    "flight_agent",
    "hotel_agent"
)

graph.add_edge(
    "hotel_agent",
    "weather_agent"
)

graph.add_edge(
    "weather_agent",
    "itinerary_agent"
)

graph.add_edge(
    "itinerary_agent",
    "final_agent"
)

graph.add_edge(
    "final_agent",
    END
)


# ============================================================
# POSTGRES CHECKPOINTER
# ============================================================

async def create_travel_graph():

    pool = AsyncConnectionPool(
        conninfo=database_url(),

        kwargs={
            "autocommit": True,
            "row_factory": dict_row,
        },

        min_size=1,
        max_size=4,
        open=False,
    )

    await pool.open(
        wait=True,
        timeout=10,
    )

    checkpointer = AsyncPostgresSaver(
        conn=pool
    )

    await checkpointer.setup()

    travel_graph = graph.compile(
        checkpointer=checkpointer
    )

    return pool, travel_graph


async def get_travel_state(
    thread_id: str
) -> dict:
    """
    Load the latest saved LangGraph state for a trip thread.
    """

    thread_id = str(
        thread_id or ""
    ).strip()

    if not thread_id:
        return {}

    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }

    pool, travel_graph = (
        await create_travel_graph()
    )

    try:
        snapshot = await travel_graph.aget_state(
            config
        )

    finally:
        await pool.close()

    values = getattr(
        snapshot,
        "values",
        {}
    )

    if isinstance(values, dict):
        return values

    return {}


# ============================================================
# RUN TRAVEL AGENT
# ============================================================

async def run_travel_agent(
    source: str,
    destination: str,
    days: int,
    budget: float,
    currency: str = "INR",
    style: str = "Balanced",
    interests: str = "",
    prompt: str = "",
    travel_date: str | None = None,
    thread_id: str | None = None
):

    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    source = str(
        source
    ).strip()

    destination = str(
        destination
    ).strip()

    currency = (
        str(
            currency
        )
        .strip()
        .upper()
        or "INR"
    )

    style = (
        str(
            style
        ).strip()
        or "Balanced"
    )

    interests = str(
        interests
    ).strip()

    prompt = str(
        prompt
    ).strip()

    if travel_date is not None:

        travel_date = str(
            travel_date
        ).strip()

        if not travel_date:

            travel_date = None

    days = int(
        days
    )

    budget = float(
        budget
    )

    if not source:

        raise ValueError(
            "Source is required."
        )

    if not destination:

        raise ValueError(
            "Destination is required."
        )

    if days < 1:

        raise ValueError(
            "Days must be at least 1."
        )

    if days > 365:

        raise ValueError(
            "Days cannot exceed 365."
        )

    if budget <= 0:

        raise ValueError(
            "Budget must be greater than zero."
        )

    # --------------------------------------------------------
    # THREAD
    # --------------------------------------------------------

    if not thread_id:

        thread_id = (
            f"user_{uuid.uuid4().hex}"
        )

    config = {

        "configurable": {

            "thread_id":
                thread_id
        }
    }

    # --------------------------------------------------------
    # INITIAL STATE
    # --------------------------------------------------------

    initial_state: TravelState = {

        "messages": [

            HumanMessage(
                content=(
                    prompt
                    or
                    f"""
Plan a {days}-day trip from {source}
to {destination}.

Travel date:
{travel_date or "Not specified"}

Budget:
{budget} {currency}

Style:
{style}

Interests:
{interests or "General travel"}
""".strip()
                )
            )
        ],

        "source":
            source,

        "destination":
            destination,

        "planning_destination":
            destination,

        "travel_date":
            travel_date,

        "days":
            days,

        "budget":
            budget,

        "currency":
            currency,

        "style":
            style,

        "interests":
            interests,

        "user_prompt":
            prompt,

        "user_query":
            prompt
            or
            f"""
Plan a {days}-day trip from {source}
to {destination}.

Travel date:
{travel_date or "Not specified"}

Budget:
{budget} {currency}

Style:
{style}

Interests:
{interests or "General travel"}
""".strip(),

        "flight_results":
            "",

        "hotel_results":
            "",

        "weather_results":
            "",

        "itinerary":
            {},

        "route":
            [],

        "score":
            0,

        "final_answer":
            "",

        "llm_calls":
            0
    }

    # --------------------------------------------------------
    # RUN GRAPH
    # --------------------------------------------------------

    pool, travel_graph = (
        await create_travel_graph()
    )

    try:

        result = await travel_graph.ainvoke(
            initial_state,
            config=config
        )

    finally:

        await pool.close()

    # --------------------------------------------------------
    # FINAL RESPONSE
    # --------------------------------------------------------

    return {

        "thread_id":
            thread_id,

        "request": {

            "source":
                source,

            "destination":
                destination,

            "days":
                days,

            "budget":
                budget,

            "currency":
                currency,

            "style":
                style,

            "interests":
                interests,

            "prompt":
                prompt,

            "travel_date":
                travel_date
        },

        "final_answer":
            result.get(
                "final_answer",
                ""
            ),

        "flight_results":
            result.get(
                "flight_results",
                ""
            ),

        "hotel_results":
            result.get(
                "hotel_results",
                ""
            ),

        "weather_results":
            result.get(
                "weather_results",
                ""
            ),

        "itinerary":
            result.get(
                "itinerary",
                {}
            ),

        "route":
            result.get(
                "route",
                []
            ),

        "score":
            result.get(
                "score"
            ) or calculate_score(
                result
            ),

        "llm_calls":
            result.get(
                "llm_calls",
                0
            )
    }


# ============================================================
# END OF BACKEND
# ============================================================
