## Audit checklist

- [x] Known issue 1: `backend.py` `itinerary_agent()` relies on prompt text for outbound/return flight activities; Python validation only checks day/activity counts and never deterministically injects missing flight activities. Current refs: `backend.py:1788`, `backend.py:2353`, `backend.py:2374`, `backend.py:2392`.
- [x] Known issue 2: verified flight budget total is inaccurate because `serp_flight_mcp_server.py` does not tag return-leg price semantics or expose a server-side total, while `backend.py` and `static/script.js` use first-match recursive price lookup. Current refs: `serp_flight_mcp_server.py:356`, `serp_flight_mcp_server.py:426`, `serp_flight_mcp_server.py:451`, `backend.py:3440`, `static/script.js:3269`.
- [ ] Known issue 3: weather last-day date uses `max(days - 1, 0)` while flight and itinerary return dates use `max(days - 1, 1)`, so 1-day trip weather does not match the actual return date. Current refs: `backend.py:816`, `backend.py:1537`, `backend.py:1815`, `serp_flight_mcp_server.py:325`.
- [ ] Known issue 4: broad/silent exception handling can hide real failures. Current refs: `backend.py:282`, `backend.py:408`, `backend.py:452`, `backend.py:470`, `backend.py:994`, `backend.py:3480`, `backend.py:3533`, `serp_flight_mcp_server.py:131`, `serp_flight_mcp_server.py:403`.
- [ ] Known issue 5: frontend duplicates backend parsing/pricing logic and can drift; confirmed duplicate flight price resolver plus duplicated flight/hotel/weather response unwrapping. Current refs: `backend.py:382`, `backend.py:3431`, `static/script.js:941`, `static/script.js:991`, `static/script.js:1814`, `static/script.js:2890`, `static/script.js:3269`.
- [ ] Additional issue 6: missing or invalid `travel_date` can crash `itinerary_agent()` before its guarded LLM block, even though `TravelRequest.travel_date` is optional and `flight_agent()` handles missing dates as unavailable. Current refs: `app.py:61`, `backend.py:765`, `backend.py:1810`.
- [ ] Additional issue 7: `mcp_client.py` sets `REQUEST_CA_BUNDLE` instead of `REQUESTS_CA_BUNDLE`, so requests-based MCP clients may not pick up the certifi CA bundle consistently. Current ref: `mcp_client.py:15`.
- [ ] Additional issue 8: `templates/index.html` has no weather agent row, but `static/script.js` animates and resets a `weather` agent, so weather work is invisible in the agent status panel. Current refs: `templates/index.html:187`, `static/script.js:613`, `static/script.js:633`.

## Fixed

- Known issue 1: Added deterministic outbound/return flight activity construction and injection in `backend.py`, preserving flight activities when trimming days back to six activities. Commit: this fix commit.
- Known issue 2: Added return-leg `price_type` and `total_verified_price` in `serp_flight_mcp_server.py`, then made backend markdown and frontend budget resolution prefer that value before old heuristic fallback. Commit: this fix commit.

## In progress

- Known issue 3: shared trip return-date helper/date convention.

## Not started

- Known issue 4: broad/silent exception handling audit.
- Known issue 5: duplicated backend/frontend parsing and pricing notes.
- Additional issue 6: optional/missing travel date crash in `itinerary_agent()`.
- Additional issue 7: `REQUESTS_CA_BUNDLE` typo in `mcp_client.py`.
- Additional issue 8: missing weather agent row in `templates/index.html`.

## Notes for next session

- Started on target branch `agents/act-as-the-senior-software-engineer-responsible` after pruning stale worktree metadata and fast-forwarding it to local `main` commit `f61bd5a`, which contains the FastAPI + MCP architecture referenced by the task.
- Pre-existing user/local change: `.DS_Store` is modified and should be ignored unless the user asks otherwise.
- Files read end to end for audit on the fast-forwarded branch: `app.py`, `backend.py`, `mcp_client.py`, `serp_flight_mcp_server.py`, `custom_weather_mcp_server.py`, `static/script.js`, `templates/index.html`.
- Duplication to keep mirrored: backend `extract_json()`/frontend `parseMCPResponse()`, backend final-agent flight price resolution/frontend budget flight price resolution, backend final-agent hotel extraction/frontend hotel normalization.
