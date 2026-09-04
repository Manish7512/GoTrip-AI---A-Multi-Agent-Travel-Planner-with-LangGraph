# 🌍 GoTrip AI — Multi-Agent Travel Planner

**GoTrip AI** is a smart travel planner that brings together multiple AI agents and live travel data to turn a simple trip request into a practical itinerary.

Tell it **where you're going, when, your budget, travel style, and interests** — GoTrip AI handles the rest.

> ⚠️ Travel data, prices, availability, and weather are planning suggestions. Always verify details before booking.

---

## ✨ What It Does

- 🤖 **Multi-agent planning** with LangGraph
- 🗺️ **Route planning** with deterministic Python logic
- ✈️ **Live flight search** through SerpAPI / Google Flights
- 🏨 **Hotel discovery** through Tavily
- 🌤️ **Current weather + trip-date forecasts** through OpenWeather
- 🧠 **Personalized itinerary generation** with Groq
- 💰 **Budget-aware planning** with currency support
- 🎯 **Travel-style and interest-based recommendations**
- 💬 **Trip refinement** through `/api/chat`
- 💾 **Persistent trip context** with PostgreSQL + LangGraph checkpointing
- 🔌 **MCP-based tool integration**
- 📊 **Structured travel data and planning score**
- 🌐 **FastAPI backend + built-in frontend**
- 🔍 **Optional LangSmith tracing**
- 🧪 **MCP, database, graph, and end-to-end tests**
- 🐳 **Docker support**

---

## 🧩 How It Works

```text
User
 │
 ▼
FastAPI
 │
 ▼
LangGraph
 │
 ├── route_agent ──────► Python
 │
 ├── flight_agent ─────► Local MCP ─────► SerpAPI / Google Flights
 │
 ├── hotel_agent ──────► Remote MCP ─────► Tavily
 │
 ├── weather_agent ────► Custom Local MCP ─► OpenWeather
 │
 ├── itinerary_agent ──► Groq LLM
 │
 └── final_agent ───────► Python
 │
 ▼
Personalized Travel Plan
 │
 ▼
PostgreSQL Checkpoint
```

The workflow is intentionally simple:

```text
START
  ↓
Route
  ↓
Flights
  ↓
Hotels
  ↓
Weather
  ↓
Itinerary
  ↓
Final Answer
  ↓
END
```

---

## 🔌 MCP Servers

GoTrip AI uses three different MCP setups:

| MCP                | Type                 | Transport       | Purpose               |
| ------------------ | -------------------- | --------------- | --------------------- |
| ✈️ Serp Flight MCP | **Local MCP**        | `stdio`         | Google Flights search |
| 🏨 Tavily MCP      | **Remote MCP**       | Streamable HTTP | Hotel/web search      |
| 🌤️ Weather MCP     | **Custom Local MCP** | `stdio`         | OpenWeather data      |

### ✈️ Local MCP — Flight Search

Implemented in:

```text
serp_flight_mcp_server.py
```

Uses SerpAPI / Google Flights and provides tools such as:

```text
search_google_flights
search_trip_flights
```

### 🏨 Remote MCP — Tavily

Tavily runs as a remote MCP service and is accessed through:

```text
mcp_client.py
```

It is mainly used for hotel discovery and search.

### 🌤️ Custom Local MCP — Weather

Implemented in:

```text
custom_weather_mcp_server.py
```

This is a custom MCP server built for GoTrip AI and exposes:

```text
get_current_weather
get_forecast
```

using OpenWeather.

---

## 🧠 Why This Architecture?

GoTrip AI doesn't ask an LLM to do everything.

```text
Route & formatting       → Python
Live travel information  → MCP + APIs
Reasoning & itinerary    → Groq LLM
Persistence              → PostgreSQL
```

This keeps the system faster, more predictable, and easier to maintain.

The normal trip workflow uses **one primary LLM call** for itinerary generation.

---

## 🌦️ Weather Handling

Weather data is separated into:

```text
today_actual_weather
per_day_forecast
```

Current weather is kept separate from future trip forecasts.

When a requested date is outside the available forecast window, the system can return:

```text
forecast_unavailable_too_far_ahead
```

instead of pretending that a forecast exists.

---

## 🛡️ Grounded Travel Information

GoTrip AI is designed not to invent specific travel facts.

The itinerary agent avoids fabricating:

- Flight numbers
- Airlines
- Flight prices
- Departure/arrival times
- Flight durations
- Hotel availability
- Booking confirmations
- Restaurant reservations
- Ticket availability
- Weather values

When verified flight data is unavailable, the system can fall back to:

```text
Flight information to be confirmed.
```

---

## 💬 Refine Your Trip

After creating a trip, users can continue with:

```text
Make it cheaper.
```

```text
Add more food experiences.
```

```text
Replace the hotels.
```

```text
Make Day 2 less busy.
```

The `thread_id` keeps the trip context available for continued planning.

---

## 🌐 API

### `GET /`

Serves the GoTrip AI web application.

### `POST /api/travel`

Creates a new travel plan.

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

### `POST /api/chat`

Continues or refines an existing trip.

```json
{
  "message": "Make the trip more budget friendly.",
  "thread_id": "debug-test-trip"
}
```

### `GET /health`

Simple application health check:

```bash
curl http://127.0.0.1:8000/health
```

---

## 📦 Response

The travel API can return:

```text
final_answer
flight_results
hotel_results
hotel_suggestions
weather_results
itinerary
route
score
llm_calls
thread_id
```

The itinerary is structured using Pydantic models such as:

```text
RouteItem
Activity
DayPlan
Itinerary
```

---

## 📁 Project Structure

```text
GoTrip-AI/
│
├── app.py                         # FastAPI app & endpoints
├── backend.py                     # LangGraph, agents & TravelState
├── mcp_client.py                  # MCP client & tool helpers
│
├── serp_flight_mcp_server.py      # Local Flight MCP
├── custom_weather_mcp_server.py  # Custom Local Weather MCP
│
├── tools/
│   ├── __init__.py
│   └── tavily_tool.py             # Tavily helper
│
├── templates/
│   └── index.html                 # Frontend
│
├── static/
│   ├── script.js                  # Frontend logic
│   └── style.css                  # Frontend styling
│
├── test.py
├── test_trip.py
├── test_graph.py
├── test_pool.py
├── test_checkpointer.py
├── test_mcp_cache.py
├── test_serp_mcp.py
├── test_actual_response.py
├── test_issue6_travel_date.py
├── test_issues_fix.py
├── mcp_client_test.py
│
├── requirements.txt
├── Dockerfile
├── .env.example
├── .gitignore
├── CODEX_PROGRESS.md
├── LICENSE
└── README.md
```

---

## 🛠️ Tech Stack

**Backend**

- Python
- FastAPI
- Uvicorn

**AI**

- LangGraph
- LangChain
- Groq
- Pydantic

**MCP & Data**

- MCP / FastMCP
- SerpAPI / Google Flights
- Tavily
- OpenWeather

**Persistence**

- PostgreSQL
- LangGraph PostgreSQL Checkpointer

**Frontend**

- HTML
- CSS
- JavaScript
- Jinja2

**Observability & Deployment**

- LangSmith
- Docker

---

## ⚙️ Setup

### 1. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows:

```powershell
.venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configure `.env`

Copy the example:

```bash
cp .env.example .env
```

Add:

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

### 4. Start GoTrip AI

```bash
python app.py
```

Open:

```text
http://127.0.0.1:8000
```

No separate frontend server is required.

---

## 🐳 Docker

Build:

```bash
docker build -t gotrip-ai .
```

Run:

```bash
docker run -p 8000:8000 gotrip-ai
```

Open:

```text
http://localhost:8000
```

Provide API keys and database credentials through environment variables or your deployment platform's secret manager.

---

## 🧪 Testing

### Import check

```bash
python -c "import backend"
```

### LangGraph

```bash
python test_graph.py
```

### PostgreSQL pool

```bash
python test_pool.py
```

### PostgreSQL checkpointer

```bash
python test_checkpointer.py
```

### MCP cache

```bash
python test_mcp_cache.py
```

### Flight MCP

```bash
python test_serp_mcp.py
```

### End-to-end trip

```bash
python test_trip.py
```

### Travel-date handling

```bash
python test_issue6_travel_date.py
```

### Issue fixes

```bash
python test_issues_fix.py
```

### Response inspection

```bash
python test_actual_response.py
```

Tests that call external services require valid API keys and network access. Database tests require a working `DATABASE_URL`.

---

## 🔐 Security

Before deploying publicly:

- Keep API keys out of Git.
- Never commit `.env`.
- Use environment variables or a secret manager.
- Protect PostgreSQL credentials.
- Add authentication for public deployments.
- Add rate limiting.
- Validate user input.
- Monitor API quotas and external-service failures.

---

## ⚠️ Limitations

GoTrip AI currently does not:

- Make flight bookings
- Make hotel bookings
- Guarantee availability
- Guarantee prices
- Guarantee weather forecasts
- Provide booking confirmations
- Guarantee restaurant reservations

External APIs can return incomplete results, rate-limit requests, change response formats, or become temporarily unavailable.

Future weather availability is also limited by the forecast data provided by OpenWeather.

---

## 🚀 Future Improvements

- Multi-city trip planning
- Transportation recommendations
- Restaurant discovery
- Activity and attraction planning
- Budget optimization
- Currency conversion
- Visa and travel-document assistance
- Automatic itinerary replanning
- Real-time price monitoring
- Better hotel ranking
- More travel-data providers
- User preference memory
- Streaming agent progress
- User accounts and authentication
- Production monitoring
- Additional MCP tools
- Improved mobile experience

---

## 🎯 What This Project Demonstrates

GoTrip AI brings together several real-world AI engineering concepts:

- Multi-agent systems
- LangGraph orchestration
- Shared state
- Local MCP servers
- Custom MCP server development
- Remote MCP integration
- External API integration
- Structured LLM output
- Pydantic models
- Deterministic + AI workflows
- PostgreSQL persistence
- Stateful conversations
- FastAPI APIs
- Frontend/backend integration
- Data normalization
- Grounded AI responses
- MCP tool caching
- Integration testing
- Docker deployment
- LangSmith observability

---

## 👨‍💻 Author

### Manish Prajapati

GoTrip AI is built as a practical AI engineering project exploring how **agents, MCP, live data, structured LLMs, and persistent state** can work together in a real-world application.

---

## 📜 License

See the `LICENSE` file for the project's license terms.

---

# ⭐ GoTrip AI

> **Give it a destination. Get a trip worth taking.**
