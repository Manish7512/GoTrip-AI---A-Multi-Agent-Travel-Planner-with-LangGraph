## Audit checklist

- [x] Known issue 1: `backend.py` `itinerary_agent()` relies on prompt text for outbound/return flight activities; Python validation only checks day/activity counts and never deterministically injects missing flight activities. Current refs: `backend.py:1788`, `backend.py:2353`, `backend.py:2374`, `backend.py:2392`.
- [x] Known issue 2: verified flight budget total is inaccurate because `serp_flight_mcp_server.py` does not tag return-leg price semantics or expose a server-side total, while `backend.py` and `static/script.js` use first-match recursive price lookup. Current refs: `serp_flight_mcp_server.py:356`, `serp_flight_mcp_server.py:426`, `serp_flight_mcp_server.py:451`, `backend.py:3440`, `static/script.js:3269`.
- [x] Known issue 3: weather last-day date uses `max(days - 1, 0)` while flight and itinerary return dates use `max(days - 1, 1)`, so 1-day trip weather does not match the actual return date. Current refs: `backend.py:816`, `backend.py:1537`, `backend.py:1815`, `serp_flight_mcp_server.py:325`.
- [x] Known issue 4: broad/silent exception handling can hide real failures. Current refs: `backend.py:282`, `backend.py:408`, `backend.py:452`, `backend.py:470`, `backend.py:994`, `backend.py:3480`, `backend.py:3533`, `serp_flight_mcp_server.py:131`, `serp_flight_mcp_server.py:403`.
- [x] Known issue 5: frontend duplicates backend parsing/pricing logic and can drift; confirmed duplicate flight price resolver plus duplicated flight/hotel/weather response unwrapping. Current refs: `backend.py:382`, `backend.py:3431`, `static/script.js:941`, `static/script.js:991`, `static/script.js:1814`, `static/script.js:2890`, `static/script.js:3269`.
- [x] Additional issue 6: missing or invalid `travel_date` can crash `itinerary_agent()` before its guarded LLM block, even though `TravelRequest.travel_date` is optional and `flight_agent()` handles missing dates as unavailable. Current refs: `app.py:61`, `backend.py:765`, `backend.py:1810`.
- [x] Additional issue 7: `mcp_client.py` sets `REQUEST_CA_BUNDLE` instead of `REQUESTS_CA_BUNDLE`, so requests-based MCP clients may not pick up the certifi CA bundle consistently. Current ref: `mcp_client.py:15`.
- [x] Additional issue 8: `templates/index.html` has no weather agent row, but `static/script.js` animates and resets a `weather` agent, so weather work is invisible in the agent status panel. Current refs: `templates/index.html:187`, `static/script.js:613`, `static/script.js:633`.
- [x] Issue A: Hotel cards display raw Tavily article titles (e.g., "Top Paris Luxury Hotel", "Ultimate Guide to Dubai Hotels") instead of extracted actual hotel names. Root cause: `final_agent()` was calling `add_hotel(title)` with the Tavily result title before extraction, and generic article titles passed the keyword filter. Current refs: `backend.py:3825-3829`.
- [x] Issue B: Flight cost double-counting when outbound comes from round-trip search (includes estimated return) but return falls back to independent one-way search. Summing these prices double-counts the return leg. Current refs: `serp_flight_mcp_server.py:597-612`.

## Fixed

- Known issue 1: Added deterministic outbound/return flight activity construction and injection in `backend.py`, preserving flight activities when trimming days back to six activities. Commit: this fix commit.
- Known issue 2: Added return-leg `price_type` and `total_verified_price` in `serp_flight_mcp_server.py`, then made backend markdown and frontend budget resolution prefer that value before old heuristic fallback. Commit: this fix commit.
- Known issue 3: Added shared `trip_return_date()` helper in `backend.py` and used it for flight logging, weather `trip_end_date`, and itinerary return-date prompting. Commit: this fix commit.
- Known issue 4: Broad/silent exception handling reduced — backend.py and serp_flight_mcp_server.py narrow except clauses, add logging, and re-raise or return meaningful error values. Commit: 41d907c.
- Additional issue 6: Defaulted travel_date to today in run_travel_agent() when None, so all downstream agents (itinerary_agent, weather_agent) receive valid dates. Commit: 2ac678a.
- Known issue 5: Audited duplicated logic between backend (extract_json, flight price heuristic, hotel extraction) and frontend (parseMCPResponse, flight price resolution, hotel rendering). Confirmed three key duplications: (1) MCP response JSON unwrapping — backend simpler, frontend more defensive; (2) flight price recursion — logic twins, must stay in sync; (3) hotel filtering/display — server-side, low risk. Added detailed notes in CODEX_PROGRESS for next session. Commit: this commit.
- Issue A: Removed `add_hotel(title)` call in `final_agent()` that was adding Tavily article titles directly. Now only uses `extract_hotel_names_from_text()` which requires strict regex patterns (markdown headings, category labels, explicit property names with hotel keywords in structured text, not just generic titles). Commit: c4483a6.
- Issue B: Added tracking of whether outbound originated from round-trip search. When return falls back to one-way, re-fetches outbound with genuine one-way search (flight_type=2) to get true component price before summing with return price. This prevents double-counting the estimated return cost that was included in the original round-trip outbound price. Commit: af340d4.

## In progress

(none)

## Not started

(all issues are complete)

## Notes for next session

- Started on target branch `agents/act-as-the-senior-software-engineer-responsible` after pruning stale worktree metadata and fast-forwarding it to local `main` commit `f61bd5a`, which contains the FastAPI + MCP architecture referenced by the task.
- Pre-existing user/local change: `.DS_Store` is modified and should be ignored unless the user asks otherwise.
- Files read end to end for audit on the fast-forwarded branch: `app.py`, `backend.py`, `mcp_client.py`, `serp_flight_mcp_server.py`, `custom_weather_mcp_server.py`, `static/script.js`, `templates/index.html`.
- Duplication to keep mirrored: backend `extract_json()`/frontend `parseMCPResponse()`, backend final-agent flight price resolution/frontend budget flight price resolution, backend final-agent hotel extraction/frontend hotel normalization.

### Known issue 5 (duplicated logic): audit results

**Confirmed: duplicated logic exists and currently stays in sync. Do NOT refactor.**

1. **MCP JSON unwrapping (`backend.py:947` vs `static/script.js:991`):**
   - Backend `extract_json()`: simple direct parse, then linear search for { or [ with backward-scan probing.
   - Frontend `parseMCPResponse()`: more sophisticated—handles MCP objects with `.text` property, markdown code fences, double-encoded JSON, and uses lastIndexOf for both { and [.
   - **Keep separate.** Frontend is more defensive; backend is minimal. Both work; changing one without the other breaks response parsing consistency.

2. **Flight price resolution (`backend.py:4035` vs `static/script.js:3269`):**
   - Backend `find_heuristic_flight_price()`: recursive dict/list walk, checks 5 explicit keys ("price", "fare", "flight_price", "total_price", "amount"), strips ₹/$, then recurses.
   - Frontend `findHeuristicFlightPrice()`: nearly identical recursive logic, same 5 keys, same string-cleaning regex (handles , and ₹/$).
   - **Watch closely.** Both sides are logic twins; if one side needs to add a new price key or change string-cleaning logic, **apply the same change to both** or the budget display will drift.
   - Backend uses this in final_agent (line 4112); frontend uses it in renderResults (line 3420).

3. **Hotel extraction/normalization (`backend.py:3410` vs `static/script.js` hotel rendering):**
   - Backend: Tavily result filtering by keyword (line 3410+); blocks phrases like "guide to", "forum", requires hotel keywords.
   - Frontend: Normalizes hotel names and pricing on render (static/script.js, hotel-specific formatting).
   - **Status:** Minimal risk; filtering happens server-side, frontend just displays. If hotel keyword blocklist changes, update both.

**Recommendation for next fix session:**

- If touching flight price keys or string-cleaning, grep both files and update both.
- If adding MCP response parsing (e.g., new markdown code fence variant), update frontend first (parseMCPResponse is the source of truth), then backport to backend if needed.
- If Tavily hotel filtering changes, update CODEX_PROGRESS.md with the new rules so the next session knows.
