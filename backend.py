import json
import os
import operator
import re
import uuid
from typing import Annotated, TypedDict

import certifi
import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph

from tools.flight_tool import search_flights
from tools.tavily_tool import tavily_search


load_dotenv()

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} is missing from .env")
    return value


def database_url() -> str:
    value = required_env("DATABASE_URL")
    if "sslmode=" not in value:
        value += ("&" if "?" in value else "?") + "sslmode=require"
    return value


llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    groq_api_key=required_env("GROQ_API_KEY"),
    temperature=0.2,
)


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
    itinerary: str
    route: list[dict]
    score: int
    final_answer: str

    llm_calls: int


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


def flight_agent(state: TravelState):
    query = f"""
Find flight/transport options for a trip starting from {state["source"]}
and going to {state["destination"]}.

Trip:
{trip_request_text(state)}

Return useful transport information. Do not invent live ticket prices.
""".strip()

    try:
        result = search_flights(query)
    except Exception as exc:
        result = f"Flight search unavailable: {exc}"

    return {
        "flight_results": str(result),
        "messages": [AIMessage(content="Flight Agent completed.")],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


def hotel_agent(state: TravelState):
    query = f"""
Best hotels/accommodation for a {state["days"]}-day trip to
{state["destination"]}, starting from {state["source"]}.

Budget: {state["budget"]:.2f} {state["currency"]}
Style: {state["style"]}
Interests: {state["interests"] or "General travel"}

Give practical accommodation suggestions and approximate price ranges
when reliable information is available.
""".strip()

    try:
        result = tavily_search(query)
    except Exception as exc:
        result = f"Hotel search unavailable: {exc}"

    return {
        "hotel_results": str(result),
        "messages": [AIMessage(content="Hotel Agent completed.")],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


def route_agent(state: TravelState):
    """
    Route is generated independently and always has a fallback.

    The fallback is critical: even if the LLM returns invalid JSON,
    the UI still receives:
        source -> destination
    instead of an empty route.
    """
    fallback = [
        {"name": state["source"], "type": "source"},
        {"name": state["destination"], "type": "destination"},
    ]

    prompt = f"""
You are a route-planning agent.

Create a logical travel route from the SOURCE to the DESTINATION.

SOURCE: {state["source"]}
DESTINATION: {state["destination"]}
DURATION: {state["days"]} days
INTERESTS: {state["interests"] or "General travel"}

Rules:
- The first stop MUST be the exact source.
- The last stop MUST be the exact destination.
- Add at most 4 sensible intermediate stops.
- Do not invent random countries.
- If the source and destination are far apart, choose realistic major stops
  only when they make geographic sense.
- Return ONLY valid JSON:
  {{"route":[{{"name":"Source","type":"source"}},{{"name":"Stop","type":"stop"}},{{"name":"Destination","type":"destination"}}]}}
""".strip()

    try:
        response = llm.invoke([
            SystemMessage(content="You are a precise travel route planner."),
            HumanMessage(content=prompt),
        ])

        text = response.content if isinstance(response.content, str) else str(response.content)

        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise ValueError("Route agent did not return JSON.")

        data = json.loads(match.group(0))
        raw_route = data.get("route", [])

        cleaned = []
        for item in raw_route:
            if isinstance(item, str):
                name = item.strip()
                if name:
                    cleaned.append({"name": name, "type": "stop"})
            elif isinstance(item, dict):
                name = str(item.get("name", "")).strip()
                if name:
                    cleaned.append({
                        "name": name,
                        "type": str(item.get("type", "stop")),
                    })

        # Enforce source and destination regardless of LLM output.
        names = [item["name"].casefold() for item in cleaned]

        if not cleaned or names[0] != state["source"].casefold():
            cleaned.insert(0, fallback[0])

        if cleaned[-1]["name"].casefold() != state["destination"].casefold():
            cleaned.append(fallback[-1])

        # Remove accidental duplicate adjacent stops.
        final_route = []
        for item in cleaned:
            if not final_route or final_route[-1]["name"].casefold() != item["name"].casefold():
                final_route.append(item)

        return {
            "route": final_route,
            "messages": [AIMessage(content="Route Agent completed.")],
            "llm_calls": state.get("llm_calls", 0) + 1,
        }

    except Exception as exc:
        print("Route agent fallback:", exc)

        return {
            "route": fallback,
            "messages": [AIMessage(content="Route Agent used source-to-destination fallback.")],
            "llm_calls": state.get("llm_calls", 0) + 1,
        }


def itinerary_agent(state: TravelState):
    route_text = " → ".join(item["name"] for item in state["route"])

    prompt = f"""
Create a practical {state["days"]}-day travel itinerary.

TRIP:
{trip_request_text(state)}

ROUTE:
{route_text}

FLIGHT INFORMATION:
{state["flight_results"]}

HOTEL INFORMATION:
{state["hotel_results"]}

Requirements:
- Respect the user's source, destination, duration, budget and style.
- Keep activities geographically sensible.
- Do not silently replace the user's destination.
- Include transportation between route stops.
- Mention estimated costs without pretending they are live prices.
- Organize by Day 1, Day 2, etc.
""".strip()

    response = llm.invoke([
        SystemMessage(content="You are an expert practical travel planner."),
        HumanMessage(content=prompt),
    ])

    return {
        "itinerary": str(response.content),
        "messages": [response],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


def calculate_score(state: TravelState) -> int:
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

    return min(score, 98)


def final_agent(state: TravelState):
    route_text = " → ".join(item["name"] for item in state["route"])
    score = calculate_score(state)

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

ITINERARY:
{state["itinerary"]}

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
- The budget is {state["budget"]:.2f} {state["currency"]}.
- Never change these values.
- Do not claim that a flight price is live unless the tool actually returned a live price.
""".strip()

    response = llm.invoke([
        SystemMessage(content="You are a professional travel-planning assistant."),
        HumanMessage(content=prompt),
    ])

    return {
        "final_answer": str(response.content),
        "score": score,
        "messages": [response],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


graph = StateGraph(TravelState)

graph.add_node("flight_agent", flight_agent)
graph.add_node("hotel_agent", hotel_agent)
graph.add_node("route_agent", route_agent)
graph.add_node("itinerary_agent", itinerary_agent)
graph.add_node("final_agent", final_agent)

graph.add_edge(START, "flight_agent")
graph.add_edge("flight_agent", "hotel_agent")
graph.add_edge("hotel_agent", "route_agent")
graph.add_edge("route_agent", "itinerary_agent")
graph.add_edge("itinerary_agent", "final_agent")
graph.add_edge("final_agent", END)


_conn = psycopg.connect(
    database_url(),
    autocommit=True,
    row_factory=dict_row,
)

checkpointer = PostgresSaver(_conn)
checkpointer.setup()

travel_graph = graph.compile(checkpointer=checkpointer)


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
    currency = currency.strip().upper() or "INR"
    style = style.strip() or "Balanced"
    interests = interests.strip()
    prompt = prompt.strip()

    if not source:
        raise ValueError("Source is required.")
    if not destination:
        raise ValueError("Destination is required.")
    if days < 1:
        raise ValueError("Days must be at least 1.")
    if budget <= 0:
        raise ValueError("Budget must be greater than zero.")

    if not thread_id:
        thread_id = f"user_{uuid.uuid4().hex}"

    config = {
        "configurable": {
            "thread_id": thread_id,
        }
    }

    state: TravelState = {
        "messages": [HumanMessage(content=prompt or trip_request_text({
            "source": source,
            "destination": destination,
            "days": days,
            "budget": budget,
            "currency": currency,
            "style": style,
            "interests": interests,
            "user_prompt": prompt,
            "user_query": "",
            "flight_results": "",
            "hotel_results": "",
            "itinerary": "",
            "route": [],
            "score": 0,
            "final_answer": "",
            "llm_calls": 0,
        }))],
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
        "itinerary": "",
        "route": [],
        "score": 0,
        "final_answer": "",
        "llm_calls": 0,
    }

    result = travel_graph.invoke(state, config=config)

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
        "final_answer": result.get("final_answer", ""),
        "flight_results": result.get("flight_results", ""),
        "hotel_results": result.get("hotel_results", ""),
        "itinerary": result.get("itinerary", ""),
        "route": result.get("route", []),
        "score": result.get("score", calculate_score(result)),
        "llm_calls": result.get("llm_calls", 0),
    }
