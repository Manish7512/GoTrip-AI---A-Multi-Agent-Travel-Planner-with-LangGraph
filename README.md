# GoTrip AI - Multi-Agent Travel Planner

GoTrip AI is a FastAPI + LangGraph travel planner that coordinates focused agents for route, flights, hotels, weather, itinerary generation, and final response formatting.

It accepts a starting point, destination, date, duration, budget, travel style, interests, and optional prompt, then returns a grounded itinerary with supporting live travel data.

> Travel data, prices, weather, and AI-generated plans are planning suggestions. Verify details before booking.

## Architecture

```text
USER INPUT
  User travel request
        |
AI AGENTS
  route_agent       -> Python deterministic route
        |
  flight_agent      -> Serp Flight MCP local server
        |
  hotel_agent       -> Tavily MCP remote server
        |
  weather_agent     -> Custom Weather MCP local server
        |
  itinerary_agent   -> Groq LLM structured planner
        |
  final_agent       -> Python Markdown formatter
        |
PERSISTENCE & STATE
  PostgreSQL checkpointing
  LangGraph shared TravelState
```

External data-fetching agents call their data sources through MCP:

- Flights: `serp_flight_mcp_server.py` using SerpAPI Google Flights.
- Hotels: Tavily remote MCP via `mcp_client.py`.
- Weather: `custom_weather_mcp_server.py` using OpenWeather.

There is normally 1 LLM call per trip: structured itinerary generation in `itinerary_agent`.

## Project Structure

```text
app.py                         # FastAPI app and HTTP endpoints
backend.py                     # LangGraph state, agents, graph, runner
mcp_client.py                  # MultiServerMCPClient setup and tool helpers
serp_flight_mcp_server.py      # Local SerpAPI Google Flights MCP server
custom_weather_mcp_server.py   # Local OpenWeather MCP server
templates/index.html           # UI
static/script.js               # Frontend behavior and renderers
static/style.css               # Frontend styles
test_*.py                      # Import, graph, MCP, and integration smoke tests
```

## Environment

Create `.env` in the project root:

```env
GROQ_API_KEY=
SERPAPI_API_KEY=
TAVILY_API_KEY=
OPEN_WEATHER_API_KEY=
DATABASE_URL=
LANGSMITH_TRACING=
LANGSMITH_ENDPOINT=
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=
```

`DATABASE_URL` is used by the LangGraph PostgreSQL checkpointer. `backend.py` appends `sslmode=require` when the URL does not already include an SSL mode.

## Run Locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

Open:

```text
http://127.0.0.1:8000
```

FastAPI serves both the backend API and frontend assets.

## API

### `GET /`

Serves the web app.

### `POST /api/travel`

Example:

```json
{
  "source": "Delhi",
  "destination": "Dubai",
  "days": 2,
  "budget": 50000,
  "currency": "INR",
  "style": "Balanced",
  "interests": "food, sightseeing",
  "prompt": "Plan a practical 2-day Dubai trip.",
  "travel_date": "2026-09-15",
  "thread_id": "debug-test-trip"
}
```

Response fields include:

- `final_answer`
- `flight_results`
- `hotel_results`
- `weather_results` (JSON text with `today_actual_weather` for current conditions and `per_day_forecast` daily trip-date entries; future dates outside OpenWeather's free 5-day forecast window are marked `forecast_unavailable_too_far_ahead`)
- `itinerary`
- `route`
- `score`
- `llm_calls`
- `thread_id`

### `POST /api/chat`

Continues planning/refinement using the same trip context and thread ID.

### `GET /health`

```bash
curl http://127.0.0.1:8000/health
```

## Testing

Cheap import smoke check:

```bash
python -c "import backend"
```

Graph/checkpointer tests require `DATABASE_URL`:

```bash
python test_graph.py
python test_checkpointer.py
python test_pool.py
```

MCP and end-to-end tests require valid API keys and network access:

```bash
python test.py
python test_mcp_cache.py
python test_serp_mcp.py
python test_trip.py
```

`test_serp_mcp.py` confirms the Serp Flight MCP tools are registered and can perform a real trip flight search.

## Docker

```bash
docker build -t gotrip-ai .
docker run -p 8000:8000 gotrip-ai
```

Open:

```text
http://localhost:8000
```

## Notes

- GoTrip AI does not make bookings or guarantee availability.
- Flight data comes from SerpAPI Google Flights through the local MCP server.
- Hotel data comes from Tavily search results through MCP.
- Weather data comes from OpenWeather through the local weather MCP server.
- The frontend renders the structured data returned by the backend; no separate frontend dev server is required.
