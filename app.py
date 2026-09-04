from pathlib import Path
import re
import traceback

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, field_validator, model_validator

from backend import get_travel_state, run_travel_agent
# # This is allow to nested event loops for async calls in FastAPI
# import nest_asyncio
# nest_asyncio.apply()


BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="GoTrip AI",
    description="LangGraph multi-agent travel planner",
    version="3.0.0",
)

app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static",
)

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


class TravelRequest(BaseModel):
    """
    Preferred frontend payload:

    {
        "source": "Delhi",
        "destination": "Japan",
        "days": 7,
        "budget": 120000,
        "currency": "INR",
        "style": "Balanced",
        "interests": "Food, culture, photography",
        "prompt": "",
        "travel_date": "2026-09-15",
        "thread_id": "..."
    }
    """

    source: str
    destination: str
    days: int
    budget: float
    currency: str = "INR"
    style: str = "Balanced"
    interests: str = ""
    prompt: str = ""
    travel_date: str | None = None
    thread_id: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_payload(cls, values):
        if not isinstance(values, dict):
            return values

        values = dict(values)

        required_new_fields = (
            values.get("source"),
            values.get("destination"),
            values.get("days"),
            values.get("budget"),
        )

        if all(item is not None and item != "" for item in required_new_fields):
            return values

        message = str(values.get("message") or "").strip()
        if not message:
            return values

        # Example:
        # "Plan a 5-day trip from Delhi to Japan.
        #  Budget: ₹120000
        #  Travel style: Balanced
        #  Interests: food"
        route_match = re.search(
            r"(?:from)\s+(.+?)\s+(?:to)\s+(.+?)(?=\.\s*(?:Budget|Duration|Travel)|\n|$)",
            message,
            flags=re.IGNORECASE | re.DOTALL,
        )

        if route_match:
            values["source"] = route_match.group(1).strip()
            values["destination"] = route_match.group(2).strip().rstrip(".")
        else:
            destination_match = re.search(
                r"(?:trip|travel)\s+to\s+(.+?)(?=\.\s*(?:Budget|Travel)|\n|$)",
                message,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if destination_match:
                values["destination"] = destination_match.group(1).strip().rstrip(".")
            values.setdefault("source", "Not specified")

        days_match = re.search(
            r"(\d+)\s*-\s*day",
            message,
            flags=re.IGNORECASE,
        )
        if days_match:
            values["days"] = int(days_match.group(1))

        budget_match = re.search(
            r"Budget:\s*₹?\s*([\d,.]+)\s*(k|thousand|lakh|lac|lakhs)?",
            message,
            flags=re.IGNORECASE,
        )
        if budget_match:
            amount = float(budget_match.group(1).replace(",", ""))
            unit = (budget_match.group(2) or "").lower()

            if unit in {"k", "thousand"}:
                amount *= 1_000
            elif unit in {"lakh", "lac", "lakhs"}:
                amount *= 100_000

            values["budget"] = amount

        style_match = re.search(
            r"Travel\s+style:\s*(.+?)(?:\n|$)",
            message,
            flags=re.IGNORECASE,
        )
        if style_match:
            values["style"] = style_match.group(1).strip()

        interests_match = re.search(
            r"Interests:\s*(.+?)(?:\n|$)",
            message,
            flags=re.IGNORECASE,
        )
        if interests_match:
            values["interests"] = interests_match.group(1).strip()

        values["prompt"] = values.get("prompt") or message
        return values

    @field_validator("source", "destination")
    @classmethod
    def clean_location(cls, value: str) -> str:
        value = str(value).strip()
        if not value:
            raise ValueError("Location cannot be empty.")
        return value

    @field_validator("days")
    @classmethod
    def validate_days(cls, value: int) -> int:
        if value < 1 or value > 365:
            raise ValueError("Trip duration must be between 1 and 365 days.")
        return value

    @field_validator("budget")
    @classmethod
    def validate_budget(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("Budget must be greater than zero.")
        return value

    @field_validator("currency")
    @classmethod
    def clean_currency(cls, value: str) -> str:
        return str(value).strip().upper() or "INR"

    @field_validator("style")
    @classmethod
    def clean_style(cls, value: str) -> str:
        return str(value).strip() or "Balanced"


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={},
    )


@app.post("/api/travel")
async def travel_planner(request_data: TravelRequest):
    
    payload = request_data.model_dump()

    try:
        result = await run_travel_agent(
            **payload
        )

        return JSONResponse(
            content={
                "success": True,
                **result,
            }
        )

    except Exception as exc:
        print("Travel planner error:", exc)
        traceback.print_exc()

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(exc),
            },
        )


@app.post("/api/chat")
async def chat(request_data: dict):

    """
    Chat/refinement endpoint.
    It preserves the current trip context.
    """

    try:

        message = str(
            request_data.get(
                "message",
                ""
            )
        ).strip()

        if not message:

            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "Message cannot be empty.",
                },
            )

        thread_id = request_data.get(
            "thread_id"
        )

        saved_state = {}

        if thread_id:
            saved_state = await get_travel_state(
                str(thread_id)
            )

        source = str(
            request_data.get("source")
            or saved_state.get("source")
            or ""
        ).strip()

        destination = str(
            request_data.get("destination")
            or saved_state.get("destination")
            or ""
        ).strip()

        days = int(
            request_data.get("days")
            or saved_state.get("days")
            or 1
        )

        budget = float(
            request_data.get("budget")
            or saved_state.get("budget")
            or 1
        )

        currency = str(
            request_data.get("currency")
            or saved_state.get("currency")
            or "INR"
        )

        style = str(
            request_data.get("style")
            or saved_state.get("style")
            or "Balanced"
        )

        interests = str(
            request_data.get("interests")
            or saved_state.get("interests")
            or ""
        )

        travel_date = (
            request_data.get("travel_date")
            or saved_state.get("travel_date")
        )

        if not source or not destination:

            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": (
                        "Source and destination "
                        "are required for chat unless "
                        "thread_id points to a saved trip."
                    ),
                },
            )

        result = await run_travel_agent(
            source=source,
            destination=destination,
            days=days,
            budget=budget,
            currency=currency,
            style=style,
            interests=interests,
            prompt=message,
            travel_date=travel_date,
            thread_id=thread_id,
        )

        return {
            "success": True,
            "thread_id": result["thread_id"],
            "final_answer": result["final_answer"],
            "answer": result["final_answer"],
            "route": result["route"],
            "score": result["score"],
            "request": result["request"],
            "flight_results": result["flight_results"],
            "hotel_results": result["hotel_results"],
            "hotel_suggestions": result["hotel_suggestions"],
            "weather_results": result["weather_results"],
            "itinerary": result["itinerary"],
            "llm_calls": result["llm_calls"],
        }

    except Exception as exc:

        traceback.print_exc()

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(exc),
            },
        )

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "GoTrip AI",
        "version": "3.0.0",
    }


@app.get("/favicon.ico")
async def favicon():
    return JSONResponse(content={})


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
