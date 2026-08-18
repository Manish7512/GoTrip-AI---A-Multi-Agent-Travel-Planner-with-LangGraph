import json
import os
import operator
import re
import uuid

from typing import Annotated, List, TypedDict

import certifi
import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    SystemMessage,
)

from langchain_groq import ChatGroq

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph

from tools.flight_tool import search_flights
from tools.tavily_tool import tavily_search


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise ValueError(
        "GROQ_API_KEY is missing. Please check your .env file."
    )


def required_env(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise ValueError(f"{name} is missing from .env")

    return value


def database_url() -> str:
    value = required_env("DATABASE_URL")

    if "sslmode=" not in value:
        value += (
            ("&" if "?" in value else "?")
            + "sslmode=require"
        )

    return value


# ============================================================
# LLM
# ============================================================

llm = ChatGroq(
    model="openai/gpt-oss-120b",
    groq_api_key=GROQ_API_KEY,
    temperature=0.2,
)


# ============================================================
# TRAVEL STATE
# ============================================================

class TravelState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]

    source: str
    destination: str
    days: int
    budget: float
    currency: str
    style: str
    interests: str
    user_prompt: str
    user_query: str

    flight_results: str
    hotel_results: str

    # IMPORTANT:
    # Itinerary is now structured JSON/dict
    itinerary: dict

    route: list[dict]

    score: int
    final_answer: str

    llm_calls: int


# ============================================================
# PYDANTIC STRUCTURED OUTPUT SCHEMAS
# ============================================================

class RouteItem(BaseModel):
    name: str = Field(
        description="Name of the location."
    )

    type: str = Field(
        description="source, stop, or destination."
    )


class Activity(BaseModel):
    time: str = Field(
        description="Approximate time of the activity."
    )

    activity: str = Field(
        description="Description of the activity."
    )

    transport: str = Field(
        description="Transportation information."
    )

    estimated_cost: float = Field(
        description="Estimated cost of this activity."
    )

    currency: str = Field(
        description="Currency of the estimated cost."
    )


class DayPlan(BaseModel):
    day: int = Field(
        description="Day number, starting from 1."
    )

    title: str = Field(
        description="Short title for the day."
    )

    location: str = Field(
        description="Main location for the day."
    )

    route: str = Field(
        description="Route covered during the day."
    )

    activities: List[Activity] = Field(
        description="Activities planned for this day."
    )

    day_budget: float = Field(
        description="Estimated total budget for this day."
    )


class Itinerary(BaseModel):
    title: str
    summary: str
    route: List[RouteItem]
    days: List[DayPlan]


# ============================================================
# TRIP REQUEST TEXT
# ============================================================

def trip_request_text(state: TravelState) -> str:
    return f"""
Source city/location: {state["source"]}
Destination: {state["destination"]}
Duration: {state["days"]} days
Budget: {state["budget"]:.2f} {state["currency"]}
Travel style: {state["style"]}
Interests: {state["interests"] or "General travel"}

Additional user request:
{state["user_prompt"] or "No additional request."}
""".strip()


# ============================================================
# FLIGHT AGENT
# ============================================================

def flight_agent(state: TravelState):

    query = f"""
Find flight/transport options for a trip starting from
{state["source"]} and going to {state["destination"]}.

Trip:
{trip_request_text(state)}

Return useful transport information.

Do not invent live ticket prices.
""".strip()

    try:
        result = search_flights(query)

    except Exception as exc:
        result = f"Flight search unavailable: {exc}"

    return {
        "flight_results": str(result),

        "messages": [
            AIMessage(
                content="Flight Agent completed."
            )
        ],

        "llm_calls": (
            state.get("llm_calls", 0) + 1
        ),
    }


# ============================================================
# HOTEL AGENT
# ============================================================

def hotel_agent(state: TravelState):

    query = f"""
Best hotels/accommodation for a {state["days"]}-day trip to
{state["destination"]}, starting from {state["source"]}.

Budget: {state["budget"]:.2f} {state["currency"]}
Style: {state["style"]}
Interests: {state["interests"] or "General travel"}

Give practical accommodation suggestions and approximate
price ranges when reliable information is available.
""".strip()

    try:
        result = tavily_search(query)

    except Exception as exc:
        result = f"Hotel search unavailable: {exc}"

    return {
        "hotel_results": str(result),

        "messages": [
            AIMessage(
                content="Hotel Agent completed."
            )
        ],

        "llm_calls": (
            state.get("llm_calls", 0) + 1
        ),
    }


# ============================================================
# ROUTE AGENT
# ============================================================

def build_route(state: TravelState):

    """
    Generate an intelligent travel route while keeping the
    number of intermediate destinations realistic.
    """

    fallback = [
        {
            "name": state["source"],
            "type": "source",
        },
        {
            "name": state["destination"],
            "type": "destination",
        },
    ]

    days = int(state["days"])

    # Examples:
    #
    # 1 day  -> 0 intermediate
    # 2 days -> 0 intermediate
    # 3 days -> 1 intermediate
    # 4 days -> 2 intermediate
    # 5 days -> 3 intermediate
    # 6+     -> max 4 intermediate

    max_intermediate_stops = min(
        max(days - 2, 0),
        4,
    )

    prompt = f"""
You are an intelligent travel route-planning agent.

Create the best practical travel route from the SOURCE to
the DESTINATION based on:

- trip duration
- interests
- travel style
- budget
- geography
- realistic transportation

SOURCE:
{state["source"]}

DESTINATION:
{state["destination"]}

DURATION:
{days} days

INTERESTS:
{state["interests"] or "General travel"}

TRAVEL STYLE:
{state.get("style", "General")}

BUDGET:
{state.get("budget", "Not specified")}
{state.get("currency", "INR")}

RULES:

1. The first stop MUST be the exact source:
   {state["source"]}

2. The last stop MUST be the exact destination:
   {state["destination"]}

3. You MAY add intermediate destinations if they genuinely
   improve the travel experience.

4. Intermediate destinations should consider:
   - Geographic logic
   - Travel time
   - Available transportation
   - Trip duration
   - User interests
   - Travel style
   - Budget

5. Maximum intermediate destinations:
   {max_intermediate_stops}

6. For short trips, prefer fewer destinations and more
   meaningful experiences.

7. Do not create an unrealistic route with excessive transfers.

8. Do not add a destination merely to make the itinerary
   look more interesting.

9. An intermediate destination is allowed when it is genuinely
   suitable for the user's interests or travel style.

10. Return ONLY the route information.
""".strip()

    try:

        # Use structured output for the route too.
        class RoutePlan(BaseModel):
            route: List[RouteItem]

        structured_route_llm = llm.with_structured_output(
            RoutePlan,
            method="json_schema",
            strict=True,
        )

        response = structured_route_llm.invoke([
            SystemMessage(
                content=(
                    "You are a precise travel route planner. "
                    "Return only the requested structured route."
                )
            ),
            HumanMessage(content=prompt),
        ])

        data = response.model_dump()

        raw_route = data.get("route", [])

        cleaned = []

        for item in raw_route:

            name = str(
                item.get("name", "")
            ).strip()

            if name:

                cleaned.append({
                    "name": name,
                    "type": str(
                        item.get("type", "stop")
                    ),
                })

        # --------------------------------------------------------
        # Enforce source
        # --------------------------------------------------------

        if (
            not cleaned
            or cleaned[0]["name"].casefold()
            != state["source"].casefold()
        ):
            cleaned.insert(
                0,
                fallback[0],
            )

        # --------------------------------------------------------
        # Enforce destination
        # --------------------------------------------------------

        if (
            cleaned[-1]["name"].casefold()
            != state["destination"].casefold()
        ):
            cleaned.append(
                fallback[-1]
            )

        # --------------------------------------------------------
        # Remove duplicate adjacent stops
        # --------------------------------------------------------

        final_route = []

        for item in cleaned:

            if (
                not final_route
                or final_route[-1]["name"].casefold()
                != item["name"].casefold()
            ):
                final_route.append(item)

        # --------------------------------------------------------
        # Limit intermediate destinations
        # --------------------------------------------------------

        source = final_route[0]

        destination = final_route[-1]

        intermediate = final_route[1:-1]

        intermediate = intermediate[
            :max_intermediate_stops
        ]

        final_route = [
            source,
            *intermediate,
            destination,
        ]

        print(
            "Generated route:",
            final_route,
        )

        return {
            "route": final_route,

            "messages": [
                AIMessage(
                    content="Route generated successfully."
                )
            ],

            "llm_calls": (
                state.get("llm_calls", 0) + 1
            ),
        }

    except Exception as exc:

        print(
            "Route agent fallback:",
            exc,
        )

        return {
            "route": fallback,

            "messages": [
                AIMessage(
                    content=(
                        "Route fallback generated "
                        "successfully."
                    )
                )
            ],

            "llm_calls": (
                state.get("llm_calls", 0) + 1
            ),
        }


# ============================================================
# PER-DAY ITINERARY FALLBACK
# ============================================================

def generate_day_plan(
    state: TravelState,
    day_number: int,
    total_days: int,
    route_text: str,
) -> DayPlan:
    """
    Generate one day at a time.

    This fallback is used when Groq's native JSON-schema
    generation cannot complete the entire multi-day itinerary.
    """

    day_prompt = f"""
You are an expert travel itinerary planner.

Generate ONLY DAY {day_number} of {total_days}.

TRIP REQUEST:
{trip_request_text(state)}

SOURCE:
{state["source"]}

DESTINATION:
{state["destination"]}

DURATION:
{total_days} days

CURRENT DAY:
{day_number}

BUDGET:
{state["budget"]} {state["currency"]}

TRAVEL STYLE:
{state["style"]}

INTERESTS:
{state["interests"] or "General travel"}

AI-GENERATED ROUTE:
{route_text}

FLIGHT INFORMATION:
{state["flight_results"]}

HOTEL INFORMATION:
{state["hotel_results"]}

REQUIRED OUTPUT:

Return exactly ONE DayPlan object for day {day_number}.

The day MUST contain:
- day
- title
- location
- route
- activities
- day_budget

The day value MUST be {day_number}.

Each day MUST contain 3 to 5 activities.

Every activity MUST contain:
- time
- activity
- transport
- estimated_cost
- currency

RULES:

1. Do not generate any other day.
2. Do not generate Day 0.
3. Do not generate Day {total_days + 1}.
4. Make this day practical and geographically logical.
5. Do not unnecessarily repeat activities.
6. Include realistic transportation.
7. Prices are estimates only.
8. Do not invent exact flight numbers.
9. Do not invent reservation confirmations.
10. Do not invent live hotel availability.
11. Keep this day's estimated cost reasonable relative to
    the total trip budget.
12. ALWAYS include day_budget.
13. Complete every activity before returning.
14. Return ONLY the structured DayPlan object.
""".strip()

    structured_day_llm = llm.with_structured_output(
        DayPlan,
        method="json_schema",
        strict=True,
    )

    response = structured_day_llm.invoke([
        SystemMessage(
            content="""
You are a precise travel itinerary generator.

Return exactly one complete DayPlan.

Never omit:
day, title, location, route, activities, day_budget.

Every activity must contain:
time, activity, transport, estimated_cost, currency.

Generate 3 to 5 complete activities.
Do not truncate the response.
Return only the structured DayPlan.
""".strip()
        ),
        HumanMessage(content=day_prompt),
    ])

    day_data = response.model_dump()

    # Force the requested day number after successful validation.
    day_data["day"] = day_number

    required_day_fields = {
        "day",
        "title",
        "location",
        "route",
        "activities",
        "day_budget",
    }

    missing_day_fields = required_day_fields - set(day_data.keys())

    if missing_day_fields:
        raise ValueError(
            f"Day {day_number} is missing fields: "
            f"{sorted(missing_day_fields)}"
        )

    activities = day_data.get("activities", [])

    if not activities:
        raise ValueError(
            f"Day {day_number} contains no activities."
        )

    required_activity_fields = {
        "time",
        "activity",
        "transport",
        "estimated_cost",
        "currency",
    }

    for activity_index, activity in enumerate(
        activities,
        start=1,
    ):
        missing_activity_fields = (
            required_activity_fields - set(activity.keys())
        )

        if missing_activity_fields:
            raise ValueError(
                f"Day {day_number}, activity {activity_index} "
                f"is missing fields: "
                f"{sorted(missing_activity_fields)}"
            )

    return DayPlan.model_validate(day_data)


def generate_complete_itinerary_day_by_day(
    state: TravelState,
    route: list[dict],
    days: int,
) -> dict:
    """
    Robust fallback that generates each day independently and
    assembles the final Itinerary object in Python.
    """

    route_text = " → ".join(
        item["name"]
        for item in route
    )

    generated_days = []

    for day_number in range(1, days + 1):

        print(
            f"Generating itinerary day {day_number}/{days}..."
        )

        day_plan = generate_day_plan(
            state=state,
            day_number=day_number,
            total_days=days,
            route_text=route_text,
        )

        generated_days.append(
            day_plan.model_dump()
        )

    if len(generated_days) != days:
        raise ValueError(
            f"Expected exactly {days} days, but generated "
            f"{len(generated_days)} days."
        )

    for index, day_data in enumerate(
        generated_days,
        start=1,
    ):
        day_data["day"] = index

        if "day_budget" not in day_data:
            raise ValueError(
                f"Day {index} is missing day_budget."
            )

    total_budget = sum(
        float(day_data.get("day_budget", 0))
        for day_data in generated_days
    )

    itinerary = {
        "title": (
            f"{days}-Day {state['style']} Trip to "
            f"{state['destination']}"
        ),
        "summary": (
            f"A practical {days}-day trip from "
            f"{state['source']} to {state['destination']} "
            f"focused on {state['interests'] or 'general travel'}."
        ),
        "route": route,
        "days": generated_days,
    }

    print(
        "\n========== DAY-BY-DAY FALLBACK ITINERARY =========="
    )

    print(
        json.dumps(
            itinerary,
            indent=2,
            ensure_ascii=False,
        )
    )

    print(
        f"Total estimated day budgets: "
        f"{total_budget:.2f} {state['currency']}"
    )

    print(
        "====================================================\n"
    )

    return itinerary


# ============================================================
# ITINERARY AGENT
# ============================================================

def itinerary_agent(state: TravelState):

    route_result = build_route(state)

    route = route_result["route"]

    route_text = " → ".join(
        item["name"]
        for item in route
    )

    days = int(state["days"])

    prompt = f"""
You are an expert AI travel planner.

Create a practical and enjoyable EXACTLY {days}-day
travel itinerary.

TRIP REQUEST:
{trip_request_text(state)}

SOURCE:
{state["source"]}

DESTINATION:
{state["destination"]}

DURATION:
{days} days

BUDGET:
{state["budget"]} {state["currency"]}

TRAVEL STYLE:
{state["style"]}

INTERESTS:
{state["interests"] or "General travel"}

AI-GENERATED ROUTE:
{route_text}

FLIGHT INFORMATION:
{state["flight_results"]}

HOTEL INFORMATION:
{state["hotel_results"]}

IMPORTANT PLANNING RULES:

1. Create EXACTLY {days} days.

2. The itinerary must contain:
   Day 1 through Day {days} only.

3. NEVER create Day 0.

4. NEVER create Day {days + 1}.

5. NEVER create any additional days.

6. The source and destination are the trip anchors.

7. Intermediate destinations from the AI-generated route
   are allowed.

8. Use intermediate destinations when they genuinely improve
   the travel experience and are realistic for the duration.

9. Do not add unnecessary additional cities.

10. Make the itinerary geographically logical.

11. Every day must have DIFFERENT activities.

12. Do not unnecessarily repeat attractions, restaurants,
    experiences, or activities.

13. Include realistic transportation between locations.

14. Consider the user's travel style and interests.

15. Stay within the user's total budget.

16. All prices are ESTIMATES.

17. Never present estimated prices as live prices.

18. Do not invent exact flight numbers.

19. Do not invent reservation confirmations.

20. Do not invent live hotel availability.

21. If flight or hotel information is supplied, use it only
    as reference information.

22. Make the itinerary practical rather than overcrowded.

23. The total estimated budget should be reasonably consistent
    with the user's requested budget.

24. Each day must contain meaningful activities.

25. The days array MUST contain exactly {days} objects.

IMPORTANT ROUTE INTERPRETATION:

The route may contain intermediate destinations.

For example, if the route is:

Mumbai → Reykjavik → USA

the itinerary may use:

Day 1: Mumbai → Reykjavik
Day 2: Reykjavik
Day 3: Reykjavik → USA
Day 4: USA

Do NOT assume that the intermediate destination is an error.
Use it intelligently when it fits the duration.
""".strip()

    try:

        # --------------------------------------------------------
        # NATIVE GROQ STRUCTURED OUTPUT
        # --------------------------------------------------------

        structured_llm = llm.with_structured_output(
            Itinerary,
            method="json_schema",
            strict=True,
        )

        response = structured_llm.invoke([
            SystemMessage(
                content=(
                    """
You are an expert travel itinerary planner.

Generate a COMPLETE travel itinerary that strictly follows the provided output schema.

CRITICAL OUTPUT RULES:

1. The "days" array MUST contain exactly the requested number of days.
2. EVERY day object MUST contain:
   - day
   - title
   - location
   - route
   - activities
   - day_budget
3. "day_budget" is REQUIRED for EVERY day, including the final travel/return day.
4. EVERY activity MUST contain:
   - time
   - activity
   - transport
   - estimated_cost
   - currency
5. Never omit a required field.
6. Never return null for required fields.
7. Each day MUST contain 3 to 5 activities.
8. The final day MUST contain at least 3 complete activities.
9. Complete ALL days before returning the response.
10. Never stop generation midway through a day.
11. Every day_budget MUST be present and represent the estimated total cost for that day.
12. day_budget MUST be included even if the day mainly consists of transportation.
13. Keep the total estimated spending reasonable relative to the user's total budget.
14. Do not invent live prices, flight numbers, reservations, or hotel availability.
15. Return ONLY the structured output.

FINAL VALIDATION BEFORE RETURNING:
- Number of days = requested number of days
- Day numbers are sequential
- Every day has day_budget
- Every day has 3-5 activities
- Every activity has all required fields
- Final day is complete
"""
                )
            ),

            HumanMessage(
                content=prompt
            ),
        ])

        # --------------------------------------------------------
        # Convert Pydantic object to dictionary
        # --------------------------------------------------------

        itinerary = response.model_dump()

        # --------------------------------------------------------
        # Validate number of days
        # --------------------------------------------------------

        generated_days = itinerary.get(
            "days",
            []
        )

        if len(generated_days) != days:

            raise ValueError(
                f"Expected exactly {days} days, "
                f"but model returned "
                f"{len(generated_days)} days."
            )

        # --------------------------------------------------------
        # Force correct day numbers
        # --------------------------------------------------------

        for index, day_data in enumerate(
            generated_days,
            start=1,
        ):
            day_data["day"] = index

        # --------------------------------------------------------
        # Always use route generated by build_route()
        # --------------------------------------------------------

        itinerary["route"] = route

        # --------------------------------------------------------
        # Debug
        # --------------------------------------------------------

        print(
            "\n========== GENERATED ITINERARY =========="
        )

        print(
            json.dumps(
                itinerary,
                indent=2,
                ensure_ascii=False,
            )
        )

        print(
            "==========================================\n"
        )

        return {
            "route": route,

            "itinerary": itinerary,

            # Do not put the Pydantic object into messages.
            "messages": [],

            "llm_calls": (
                state.get("llm_calls", 0)
                + route_result.get("llm_calls", 0)
                + 1
            ),
        }

    except Exception as exc:

        print(
            "Itinerary agent error:",
            exc,
        )

        print(
            "Attempting robust day-by-day itinerary fallback..."
        )

        try:

            fallback_itinerary = (
                generate_complete_itinerary_day_by_day(
                    state=state,
                    route=route,
                    days=days,
                )
            )

            return {
                "route": route,

                "itinerary": fallback_itinerary,

                "messages": [],

                "llm_calls": (
                    state.get("llm_calls", 0)
                    + route_result.get("llm_calls", 0)
                    + days
                ),
            }

        except Exception as fallback_exc:

            print(
                "Day-by-day itinerary fallback failed:",
                fallback_exc,
            )

            raise RuntimeError(
                "Both the normal itinerary generation and the "
                "day-by-day fallback failed. "
                f"Original error: {exc}. "
                f"Fallback error: {fallback_exc}"
            ) from fallback_exc


# ============================================================
# SCORE
# ============================================================

def calculate_score(
    state: TravelState,
) -> int:

    score = 80

    if state["source"].strip():
        score += 4

    if state["destination"].strip():
        score += 4

    if state["budget"] > 0:
        score += 4

    if state["interests"].strip():
        score += 3

    if len(state["route"]) >= 2:
        score += 3

    return min(
        score,
        98,
    )


# ============================================================
# FINAL AGENT
# ============================================================

def final_agent(state: TravelState):

    route_text = " → ".join(
        item["name"]
        for item in state["route"]
    )

    score = calculate_score(state)

    itinerary_json = json.dumps(
        state["itinerary"],
        indent=2,
        ensure_ascii=False,
    )

    prompt = f"""
Create the final GoTrip AI response.

USER REQUEST:
{trip_request_text(state)}

ROUTE:
{route_text}

FLIGHT RESULTS:
{state["flight_results"]}

HOTEL RESULTS:
{state["hotel_results"]}

STRUCTURED ITINERARY:
{itinerary_json}

Use these sections:

1. Trip Summary
2. Route
3. Flight / Transport
4. Hotel Suggestions
5. Day-by-Day Itinerary
6. Estimated Budget
7. Practical Recommendations

Important:

- The SOURCE is {state["source"]}.
- The DESTINATION is {state["destination"]}.
- The requested duration is {state["days"]} days.
- The budget is {state["budget"]:.2f} {state["currency"]}.
- Never change these values.
- Intermediate destinations from the route are allowed.
- Do not add extra days.
- Do not claim that a flight price is live unless the
  flight tool actually returned a live price.
- Clearly describe estimated prices as estimates.
- Keep the final response practical and readable.
""".strip()

    response = llm.invoke([
        SystemMessage(
            content=(
                "You are a professional travel-planning "
                "assistant."
            )
        ),

        HumanMessage(
            content=prompt
        ),
    ])

    return {
        "final_answer": str(
            response.content
        ),

        "score": score,

        "messages": [
            response
        ],

        "llm_calls": (
            state.get("llm_calls", 0) + 1
        ),
    }


# ============================================================
# LANGGRAPH
# ============================================================

graph = StateGraph(
    TravelState
)

graph.add_node(
    "flight_agent",
    flight_agent,
)

graph.add_node(
    "hotel_agent",
    hotel_agent,
)

graph.add_node(
    "itinerary_agent",
    itinerary_agent,
)

graph.add_node(
    "final_agent",
    final_agent,
)


graph.add_edge(
    START,
    "flight_agent",
)

graph.add_edge(
    "flight_agent",
    "hotel_agent",
)

graph.add_edge(
    "hotel_agent",
    "itinerary_agent",
)

graph.add_edge(
    "itinerary_agent",
    "final_agent",
)

graph.add_edge(
    "final_agent",
    END,
)


# ============================================================
# POSTGRES CHECKPOINTER
# ============================================================

_conn = psycopg.connect(
    database_url(),
    autocommit=True,
    row_factory=dict_row,
)

checkpointer = PostgresSaver(
    _conn
)

checkpointer.setup()

travel_graph = graph.compile(
    checkpointer=checkpointer
)


# ============================================================
# RUN TRAVEL AGENT
# ============================================================

def run_travel_agent(
    source: str,
    destination: str,
    days: int,
    budget: float,
    currency: str = "INR",
    style: str = "Balanced",
    interests: str = "",
    prompt: str = "",
    thread_id: str | None = None,
):

    source = source.strip()

    destination = destination.strip()

    currency = (
        currency.strip().upper()
        or "INR"
    )

    style = (
        style.strip()
        or "Balanced"
    )

    interests = interests.strip()

    prompt = prompt.strip()


    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

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
            "thread_id": thread_id,
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
Plan a trip from {source}
to {destination}
for {days} days.

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

        "source": source,

        "destination": destination,

        "days": int(days),

        "budget": float(budget),

        "currency": currency,

        "style": style,

        "interests": interests,

        "user_prompt": prompt,

        "user_query": prompt,

        "flight_results": "",

        "hotel_results": "",

        # IMPORTANT:
        # itinerary is now a dictionary
        "itinerary": {},

        "route": [],

        "score": 0,

        "final_answer": "",

        "llm_calls": 0,
    }


    # --------------------------------------------------------
    # RUN GRAPH
    # --------------------------------------------------------

    result = travel_graph.invoke(
        initial_state,
        config=config,
    )


    # --------------------------------------------------------
    # RESPONSE
    # --------------------------------------------------------

    return {

        "thread_id": thread_id,

        "request": {
            "source": source,
            "destination": destination,
            "days": int(days),
            "budget": float(budget),
            "currency": currency,
            "style": style,
            "interests": interests,
            "prompt": prompt,
        },

        "final_answer": result.get(
            "final_answer",
            "",
        ),

        "flight_results": result.get(
            "flight_results",
            "",
        ),

        "hotel_results": result.get(
            "hotel_results",
            "",
        ),

        "itinerary": result.get(
            "itinerary",
            {},
        ),

        "route": result.get(
            "route",
            [],
        ),

        "score": result.get(
            "score",
            calculate_score(result),
        ),

        "llm_calls": result.get(
            "llm_calls",
            0,
        ),
    }