# ✈️ GoTrip AI - A Multi-Agent Travel Planner with LangGraph

**GoTrip AI** is a multi-agent AI travel planner built with **FastAPI, LangGraph, LangChain, Groq/Llama, PostgreSQL, and JavaScript**.

It takes the user's **starting point, destination, duration, budget, travel style, interests, and optional instructions** and combines travel research with AI planning to create a personalized trip.

## ✨ Features

- ✈️ **Flight Research** using AviationStack API integration
- 🏨 **Hotel Research** powered by Tavily web search
- 🧠 **Multi-Agent Orchestration** with LangGraph stateful workflows
- 📝 **AI Itinerary Generation** using Groq/Llama-powered planning
- 🗺️ **Dynamic Route Planning** from source to destination
- 💰 **Budget-Aware Recommendations** based on user-defined constraints
- 🌐 **FastAPI REST API** for frontend-backend communication
- 💾 **Persistent Trip State** using PostgreSQL and LangGraph checkpointing
- 💬 **Context-Aware AI Chat** with thread-based conversation state
- 🖥️ **Dynamic Frontend Rendering** using JavaScript and REST API responses

> ⚠️ AI-generated routes, recommendations, estimated costs, and travel information are planning suggestions and should be verified before booking.

## ▶️ How to Run

Follow these steps to run GoTrip AI locally.

```text
1. Create and activate a virtual environment

macOS / Linux:
python3 -m venv .venv
source .venv/bin/activate

Windows:
.venv\Scripts\activate


2. Install dependencies

pip install -r requirements.txt


3. Configure environment variables

Create a .env file in the project root:

GROQ_API_KEY=your_groq_api_key
DATABASE_URL=your_postgresql_url
TAVILY_API_KEY=your_tavily_api_key


4. Start the FastAPI server

python app.py

Or:

uvicorn app:app --reload

The server will start at:
http://127.0.0.1:8000


5. Open GoTrip AI

Open this URL in your browser:
http://127.0.0.1:8000




## 🧠 How It Works

```text
User
  ↓
HTML + CSS + JavaScript
  ↓
POST /api/travel
  ↓
FastAPI
  ↓
LangGraph
  ↓
✈️ Flight Agent
  ↓
🏨 Hotel Agent
  ↓
✨ Itinerary Agent
  │
  └── 🗺️ Route Builder
  ↓
✓ Final Agent
  ↓
JSON Response
  ↓
Frontend
  ↓
Route + Itinerary + Budget + Results
````

### Important

The **Route Builder is not a separate agent**.

GoTrip AI currently has four AI agents:

```text
✈️ Flight Agent
🏨 Hotel Agent
✨ Itinerary Agent
✓ Final Agent
```

Route generation is handled inside the itinerary-planning workflow.

## 🏗️ Architecture

### Frontend

```text
templates/
└── index.html       # Main application UI

static/
├── script.js        # API calls, form handling and UI logic
└── style.css        # Application styling
```

The frontend collects the user's trip details, sends them to the FastAPI backend, and dynamically renders the returned results.

### Backend

```text
app.py              # FastAPI application and API endpoints
backend.py          # LangGraph workflow and AI agents

tools/
├── flight_tool.py  # Flight/transport search integration
└── tavily_tool.py  # Web/search integration
```

## 🤖 AI Workflow

```text
START
  ↓
✈️ Flight Agent
  ↓
🏨 Hotel Agent
  ↓
✨ Itinerary Agent
  │
  └── 🗺️ Route Builder
  ↓
✓ Final Agent
  ↓
END
```

### ✈️ Flight Agent

Searches for flight or transportation information based on the source, destination, duration, and trip requirements.

### 🏨 Hotel Agent

Uses web search to research accommodation options relevant to the destination, budget, and travel style.

### 🗺️ Route Builder

Generates a source-to-destination route that is used by the itinerary workflow and displayed in the frontend.

The Route Builder is a **helper function, not a separate LangGraph agent**.

### ✨ Itinerary Agent

Combines the trip requirements, generated route, flight information, and hotel research to create a day-by-day travel plan.

### ✓ Final Agent

Combines the generated information into the final user-facing travel response.

## 🔌 API

### `GET /`

Serves the main GoTrip AI web application.

### `POST /api/travel`

Main trip-planning endpoint.

Example request:

```json
{
  "source": "Delhi",
  "destination": "Japan",
  "days": 7,
  "budget": 120000,
  "currency": "INR",
  "style": "Balanced",
  "interests": "Food, culture",
  "prompt": "",
  "thread_id": null
}
```

The response contains the generated travel plan and supporting information such as:

- Final answer
- Flight results
- Hotel results
- Route
- Itinerary
- AI score
- LLM call information
- Thread ID

### `POST /api/chat`

Allows the user to continue asking travel-related questions while retaining the existing trip context.

### `GET /health`

Checks whether the backend is running.

```bash
curl http://127.0.0.1:8000/health
```

## 📁 Project Structure

```text
GoTrip-AI/
│
├── app.py
├── backend.py
├── requirements.txt
├── Dockerfile
├── .dockerignore
├── .gitignore
│
├── templates/
│   └── index.html
│
├── static/
│   ├── script.js
│   └── style.css
│
├── tools/
│   ├── flight_tool.py
│   └── tavily_tool.py
│
└── test.py
```

## 🛠️ Technology Stack

| Layer                  | Technology                        |
| ---------------------- | --------------------------------- |
| 🖥️ Frontend            | HTML, CSS, JavaScript             |
| ⚡ Backend             | FastAPI                           |
| 🚀 Server              | Uvicorn                           |
| 🤖 Agent Orchestration | LangGraph                         |
| 🔗 AI Framework        | LangChain                         |
| 🧠 LLM                 | Groq / Llama                      |
| ✈️ Flight Search       | AviationStack                     |
| 🔎 Web Search          | Tavily                            |
| 🗄️ Database            | PostgreSQL                        |
| 💾 Checkpointing       | LangGraph PostgreSQL Checkpointer |
| 🐳 Containerization    | Docker                            |

## 🔐 Environment Variables

Create a local `.env` file in the project root.

```env
GROQ_API_KEY=your_groq_api_key
DATABASE_URL=your_postgresql_url
TAVILY_API_KEY=your_tavily_api_key
```

Use the exact variable names required by the current tool implementations.

### Security

Never commit real credentials to GitHub.

Keep the following private:

```text
.env
API keys
Database credentials
Access tokens
```

Recommended `.gitignore`:

```gitignore
.venv/
venv/
env/
ENV/
env.bak/
venv.bak/
__pycache__/
*.py[cod]
.env
.env.*
.DS_Store
```

If a real API key is accidentally pushed to GitHub, revoke or rotate it immediately.

## 🚀 Local Setup

### 1. Clone the repository

```bash
git clone <your-repository-url>
cd GoTrip-AI
```

### 2. Create a virtual environment

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows:

```powershell
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure environment variables

Create `.env` in the project root and add the required API credentials.

### 5. Start the application

```bash
python app.py
```

Or:

```bash
uvicorn app:app --reload
```

### 6. Open the application

```text
http://127.0.0.1:8000
```

The current project uses FastAPI to serve both the frontend and backend, so a separate frontend development server is not required.

## 🐳 Docker

### Build the image

```bash
docker build -t gotrip-ai .
```

### Run the container

```bash
docker run -p 8000:8000 gotrip-ai
```

Open:

```text
http://localhost:8000
```

Inside the container, Uvicorn listens on:

```text
0.0.0.0:8000
```

Using `0.0.0.0` allows the application to accept connections from outside the container.

## 🔧 Development Guide

### 🎨 Frontend

For UI changes, modify:

```text
templates/index.html
static/script.js
static/style.css
```

### ⚡ API

For API or request/response changes, modify:

```text
app.py
```

### 🤖 AI Workflow

For agents, LangGraph state, prompts, route generation, or workflow changes, modify:

```text
backend.py
```

### 🔌 External Integrations

For flight or web-search integrations, modify:

```text
tools/
```

After backend changes, restart Uvicorn if necessary.

For frontend changes, refresh the browser. If old JavaScript or CSS is cached, use:

```text
macOS: Cmd + Shift + R
Windows/Linux: Ctrl + Shift + R
```

## 🧪 Testing

The project includes:

```text
test.py
```

It can be used for basic testing of backend functionality and integrations.

For API testing, tools such as Postman or the browser developer console can be used to inspect:

```text
POST /api/travel
POST /api/chat
GET /health
```

## 📊 Current Status

GoTrip AI is an **active development project / prototype**.

The core full-stack architecture is implemented:

```text
Frontend
   ↓
FastAPI
   ↓
LangGraph
   ↓
AI Agents
   ↓
External Search APIs
   ↓
PostgreSQL
```

The application can:

- Collect structured trip requirements.
- Search for travel information.
- Generate routes.
- Generate day-by-day itineraries.
- Maintain trip state through thread IDs.
- Return structured results to the frontend.
- Display the generated route and itinerary.

However, AI-generated travel plans, routes, recommendations, and estimated costs should be treated as **planning information rather than guaranteed booking information**.

## ⚠️ Current Limitations

- Flight and hotel information depends on the availability and accuracy of external APIs/search results.
- AI-generated routes are not equivalent to navigation or map-routing services.
- Estimated costs should be independently verified before booking.
- API rate limits can affect response time or temporarily prevent LLM requests.
- The current project is primarily designed as a development/prototype application rather than a complete booking platform.
- Real booking confirmation is not currently handled directly by GoTrip AI.

## 🔮 Future Improvements

Possible future improvements include:

- 🗺️ Interactive map integration
- ✈️ Real-time flight availability
- 🏨 Live hotel availability
- 🎫 Activity and attraction booking
- 🌦️ Weather-aware itinerary planning
- 💱 Automatic currency conversion
- 💰 Stronger budget-feasibility validation
- 🧭 More accurate geographic route validation
- 📄 PDF itinerary export
- 👤 User authentication
- 🗂️ Saved trip history
- 📊 Production monitoring and logging
- 🔁 Better API retry and rate-limit handling
- 🔐 Production-grade security
- ☁️ Cloud deployment

## 💡 Why LangGraph?

LangGraph allows GoTrip AI to divide travel planning into focused stages instead of asking a single LLM prompt to handle everything.

Each agent has a specific responsibility while sharing a common travel state.

This makes the application easier to:

- 🧩 Understand
- 🐛 Debug
- 🔄 Extend
- 📈 Scale
- 🔗 Connect with additional tools

Future agents or workflows could include:

```text
🌦️ Weather Agent
🛂 Visa Agent
🎫 Activity Agent
💰 Budget Optimization Agent
🚕 Local Transportation Agent
🍽️ Restaurant Agent
```

## 🎯 Project Goal

The goal of GoTrip AI is to make travel planning more convenient by bringing **travel research, AI reasoning, route generation, and itinerary planning** into a single application.

Instead of manually researching multiple websites, users can provide their trip requirements and receive a structured starting point for planning their journey.

## 👨‍💻 Project

**GoTrip AI — Multi-Agent AI Travel Planner**

Built with:

**Python • FastAPI • LangGraph • LangChain • Groq • PostgreSQL • JavaScript**

> ✈️ Plan smarter. 🗺️ Travel better. 🤖 Powered by AI.
