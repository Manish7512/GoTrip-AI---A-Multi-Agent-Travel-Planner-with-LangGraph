/* ============================================================
   GoTrip AI — Frontend Fixed Version
   ============================================================ */

"use strict";

const $ = (id) => document.getElementById(id);

let currentTrip = {
    source: "",
    destination: "",
    days: 1,
    budget: 0,
    currency: "INR",
    style: "Balanced",
    interests: "",
    prompt: "",
    travel_date: ""
};

let currentRoute = [];
let currentResult = null;
let currentDay = 0;
let isGenerating = false;


/* ============================================================
   HELPERS
   ============================================================ */

function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}


function showToast(message, duration = 3000) {
    const toast = $("toast");

    if (!toast) {
        console.log(message);
        return;
    }

    toast.textContent = message;
    toast.classList.add("show");

    clearTimeout(showToast.timer);

    showToast.timer = setTimeout(() => {
        toast.classList.remove("show");
    }, duration);
}


/* ============================================================
   THREAD
   ============================================================ */

function getThreadId() {
    let id =
        localStorage.getItem(
            "gotrip_thread_id"
        );

    if (!id) {
        id =
            window.crypto?.randomUUID?.() ||
            `gotrip-${Date.now()}-${Math.random()
                .toString(36)
                .slice(2)}`;

        localStorage.setItem(
            "gotrip_thread_id",
            id
        );
    }

    return id;
}


function updateThreadIdUI() {
    const element =
        $("threadIdDisplay");

    if (!element) {
        return;
    }

    const id =
        getThreadId();

    element.textContent =
        id;

    element.title =
        id;
}


async function copyThreadId() {
    try {

        await navigator.clipboard.writeText(
            getThreadId()
        );

        showToast(
            "Thread ID copied."
        );

    } catch {

        showToast(
            "Unable to copy Thread ID."
        );
    }
}


function resetConversation() {

    localStorage.removeItem(
        "gotrip_thread_id"
    );

    updateThreadIdUI();

    showToast(
        "New conversation started."
    );
}


/* ============================================================
   BUDGET
   ============================================================ */

function parseBudget(value) {

    if (
        typeof value === "number"
    ) {

        return Number.isFinite(value)
            ? value
            : 0;
    }

    let text =
        String(value ?? "")
            .trim()
            .toLowerCase()
            .replace(/₹/g, "")
            .replace(/inr/g, "")
            .replace(/rs\.?/g, "")
            .replace(/,/g, "");

    if (!text) {
        return 0;
    }

    const lakh =
        text.match(
            /([\d.]+)\s*(lakh|lac|lacs|lakhs)\b/
        );

    if (lakh) {

        return (
            Number(lakh[1]) *
            100000
        );
    }

    const thousand =
        text.match(
            /([\d.]+)\s*(k|thousand)\b/
        );

    if (thousand) {

        return (
            Number(thousand[1]) *
            1000
        );
    }

    const million =
        text.match(
            /([\d.]+)\s*(m|million)\b/
        );

    if (million) {

        return (
            Number(million[1]) *
            1000000
        );
    }

    const numeric =
        Number(
            text.replace(
                /[^\d.]/g,
                ""
            )
        );

    return Number.isFinite(
        numeric
    )
        ? numeric
        : 0;
}


function formatINR(value) {

    const number =
        Number(value);

    if (
        !Number.isFinite(number) ||
        number <= 0
    ) {

        return "Budget flexible";
    }

    return `₹${number.toLocaleString(
        "en-IN",
        {
            maximumFractionDigits: 0
        }
    )}`;
}


/* ============================================================
   TRIP DATA
   ============================================================ */

function getTripData() {

    const source =
        $("source")?.value.trim() ||
        "";

    const destination =
        $("destination")?.value.trim() ||
        "";

    const daysValue =
        Number(
            $("days")?.value
        );

    const days =
        Number.isFinite(daysValue) &&
        daysValue >= 1
            ? Math.floor(daysValue)
            : 1;

    const budget =
        parseBudget(
            $("budget")?.value
        );

    const style =
        $("style")?.value?.trim() ||
        "Balanced";

    const interests =
        $("interests")?.value?.trim() ||
        "";

    const prompt =
        $("prompt")?.value?.trim() ||
        "";

    const travelDate =
        $("travelDate")?.value ||
        $("travel_date")?.value ||
        "";

    currentTrip = {
        source,
        destination,
        days,
        budget,
        currency: "INR",
        style,
        interests,
        prompt,
        travel_date: travelDate
    };

    return currentTrip;
}


function buildUserPrompt(trip) {

    if (trip.prompt) {
        return trip.prompt;
    }

    return `
Plan a ${trip.days}-day trip from
${trip.source} to ${trip.destination}.

Travel date:
${trip.travel_date || "Not specified"}

Budget:
₹${trip.budget.toLocaleString("en-IN")}

Travel style:
${trip.style}

Interests:
${trip.interests || "General travel"}

Create a practical travel plan with
transportation, accommodation, activities,
food experiences, route and estimated budget.
`.trim();
}


function buildPayload(trip) {

    return {

        source:
            trip.source,

        destination:
            trip.destination,

        days:
            trip.days,

        budget:
            trip.budget,

        currency:
            trip.currency,

        style:
            trip.style,

        interests:
            trip.interests,

        prompt:
            buildUserPrompt(trip),

        travel_date:
            trip.travel_date ||
            null,

        thread_id:
            getThreadId()
    };
}


/* ============================================================
   VALIDATION
   ============================================================ */

function validateTrip(trip) {

    if (!trip.source) {

        throw new Error(
            "Please enter the starting location."
        );
    }

    if (!trip.destination) {

        throw new Error(
            "Please enter the destination."
        );
    }

    if (
        trip.source.trim().toLowerCase() ===
        trip.destination.trim().toLowerCase()
    ) {

        throw new Error(
            "Starting location and destination must be different."
        );
    }

    if (
        !trip.budget ||
        trip.budget <= 0
    ) {

        throw new Error(
            "Please enter a valid budget."
        );
    }

    if (
        !Number.isInteger(trip.days) ||
        trip.days < 1 ||
        trip.days > 365
    ) {

        throw new Error(
            "Trip duration must be between 1 and 365 days."
        );
    }
}


/* ============================================================
   BACKEND
   ============================================================ */

async function callTravelBackend(trip) {

    validateTrip(trip);

    const payload =
        buildPayload(trip);

    console.log(
        "GoTrip API request:",
        payload
    );

    const response =
        await fetch(
            "/api/travel",
            {
                method: "POST",

                headers: {
                    "Content-Type":
                        "application/json",

                    "Accept":
                        "application/json"
                },

                body:
                    JSON.stringify(
                        payload
                    )
            }
        );

    let data;

    try {

        data =
            await response.json();

    } catch {

        throw new Error(
            "Server returned an invalid JSON response."
        );
    }

    console.log(
        "GoTrip API response:",
        data
    );

    if (
        !response.ok ||
        data.success === false
    ) {

        throw new Error(
            data.error ||
            `Request failed with status ${response.status}.`
        );
    }

    return data;
}


/* ============================================================
   SUMMARY
   ============================================================ */

function updateTripSummary(trip) {

    const title =
        $("tripTitle");

    const meta =
        $("tripMeta");

    if (title) {

        title.textContent =
            trip.destination
                ? `${trip.destination} Explorer`
                : "Your Journey";
    }

    if (meta) {

        const datePart =
            trip.travel_date
                ? ` · ${trip.travel_date}`
                : "";

        meta.textContent =
            `${trip.source} → ${trip.destination} · ` +
            `${trip.days} days · ` +
            `${trip.style} · ` +
            `${formatINR(trip.budget)}` +
            datePart;
    }
}


/* ============================================================
   SCORE
   ============================================================ */

function updateAIScore(score) {

    const element =
        $("score");

    if (!element) {
        return;
    }

    const number =
        Number(score);

    element.textContent =
        Number.isFinite(number)
            ? Math.round(number)
            : "—";
}


/* ============================================================
   AGENTS
   ============================================================ */

function setAgentState(
    agent,
    state
) {

    const row =
        document.querySelector(
            `[data-agent="${agent}"]`
        );

    if (!row) {
        return;
    }

    row.classList.remove(
        "working",
        "done"
    );

    if (
        state === "Working"
    ) {

        row.classList.add(
            "working"
        );
    }

    if (
        state === "Done"
    ) {

        row.classList.add(
            "done"
        );
    }

    const label =
        row.querySelector(
            ".agent-state"
        );

    if (label) {

        label.textContent =
            state;
    }
}


function resetAgents() {

    [
        "flight",
        "hotel",
        "weather",
        "itinerary",
        "final"
    ].forEach(
        agent => {

            setAgentState(
                agent,
                "Ready"
            );
        }
    );
}


async function animateAgents() {

    const agents = [
        "flight",
        "hotel",
        "weather",
        "itinerary",
        "final"
    ];

    resetAgents();

    for (
        const agent of agents
    ) {

        setAgentState(
            agent,
            "Working"
        );

        await new Promise(
            resolve =>
                setTimeout(
                    resolve,
                    220
                )
        );

        setAgentState(
            agent,
            "Done"
        );
    }
}


/* ============================================================
   ROUTE
   ============================================================ */

function renderRoute(route) {

    currentRoute =
        Array.isArray(route)
            ? route
                .map(item => {

                    if (
                        typeof item ===
                        "string"
                    ) {

                        return {
                            name: item,
                            type: "stop"
                        };
                    }

                    return {

                        name:
                            String(
                                item?.name ||
                                ""
                            ).trim(),

                        type:
                            item?.type ||
                            "stop"
                    };
                })
                .filter(
                    item =>
                        item.name
                )
            : [];

    const points =
        $("routePoints");

    const svg =
        $("routeSvg");

    const bottom =
        $("routeBottom");

    const empty =
        $("routeEmpty");

    if (
        !points ||
        !bottom
    ) {

        return;
    }

    points.innerHTML =
        "";

    bottom.innerHTML =
        "";

    if (svg) {
        svg.innerHTML =
            "";
    }

    if (
        !currentRoute.length
    ) {

        if (empty) {
            empty.hidden =
                false;
        }

        bottom.innerHTML =
            "<span>No route returned.</span>";

        return;
    }

    if (empty) {
        empty.hidden =
            true;
    }

    const width =
        700;

    const height =
        300;

    const left =
        55;

    const right =
        55;

    const usableWidth =
        width -
        left -
        right;

    const positions =
        currentRoute.map(
            (
                _,
                index
            ) => {

                const x =
                    currentRoute.length ===
                    1

                        ? width / 2

                        : left +
                          usableWidth *
                          index /
                          (
                              currentRoute.length -
                              1
                          );

                const y =
                    height * 0.58 -
                    Math.sin(
                        index * 1.35
                    ) * 48;

                return {
                    x,
                    y
                };
            }
        );

    positions.forEach(
        (
            position,
            index
        ) => {

            const stop =
                currentRoute[index];

            const point =
                document.createElement(
                    "div"
                );

            point.className =
                "map-point dynamic-point";

            point.style.left =
                `${
                    (
                        position.x /
                        width
                    ) *
                    100
                }%`;

            point.style.top =
                `${
                    (
                        position.y /
                        height
                    ) *
                    100
                }%`;

            point.innerHTML = `
                <i></i>
                <span>
                    ${escapeHtml(
                        stop.name
                    )}
                </span>
            `;

            points.appendChild(
                point
            );
        }
    );

    if (
        svg &&
        positions.length > 1
    ) {

        let path =
            `M ${positions[0].x} ${positions[0].y}`;

        for (
            let i = 1;
            i < positions.length;
            i++
        ) {

            const previous =
                positions[i - 1];

            const current =
                positions[i];

            const midpoint =
                (
                    previous.x +
                    current.x
                ) / 2;

            path +=
                ` C ${midpoint} ${
                    previous.y - 35
                }, ` +
                `${midpoint} ${
                    current.y - 35
                }, ` +
                `${current.x} ${
                    current.y
                }`;
        }

        svg.innerHTML = `
            <path
                d="${path}"
                fill="none"
                stroke="currentColor"
                stroke-width="3"
                stroke-linecap="round"
                stroke-dasharray="7 9"
            />
        `;
    }

    currentRoute.forEach(
        (
            stop,
            index
        ) => {

            const label =
                document.createElement(
                    "span"
                );

            label.textContent =
                index === 0
                    ? `● ${stop.name}`
                    : `→ ${stop.name}`;

            bottom.appendChild(
                label
            );
        }
    );
}


/* ============================================================
   SAFE JSON
   ============================================================ */

function safeJsonParse(value) {

    if (
        value === null ||
        value === undefined
    ) {

        return null;
    }

    if (
        typeof value ===
        "object"
    ) {

        return value;
    }

    if (
        typeof value !==
        "string"
    ) {

        return null;
    }

    const text =
        value.trim();

    if (!text) {
        return null;
    }

    try {

        return JSON.parse(
            text
        );

    } catch {

        return null;
    }
}


/* ============================================================
   MCP PARSER
   ============================================================ */

function parseMCPResponse(value) {

    if (
        value === null ||
        value === undefined
    ) {

        return null;
    }

    if (
        typeof value ===
        "object"
    ) {

        if (
            typeof value.text ===
            "string"
        ) {

            const parsed =
                safeJsonParse(
                    value.text
                );

            if (
                parsed !== null
            ) {

                return parsed;
            }

            return parseMCPResponse(
                value.text
            );
        }

        if (
            Array.isArray(value)
        ) {

            for (
                const item of value
            ) {

                const parsed =
                    parseMCPResponse(
                        item
                    );

                if (
                    parsed !== null
                ) {

                    return parsed;
                }
            }
        }

        return value;
    }

    if (
        typeof value !==
        "string"
    ) {

        return null;
    }

    let text =
        value.trim();

    if (!text) {
        return null;
    }

    text =
        text
            .replace(
                /^```json\s*/i,
                ""
            )
            .replace(
                /^```\s*/i,
                ""
            )
            .replace(
                /\s*```$/i,
                ""
            )
            .trim();

    let parsed =
        safeJsonParse(
            text
        );

    if (
        parsed !== null
    ) {

        return parsed;
    }

    /*
     * Double encoded JSON.
     */
    try {

        const decoded =
            JSON.parse(
                text
            );

        if (
            typeof decoded ===
            "string"
        ) {

            parsed =
                safeJsonParse(
                    decoded
                );

            if (
                parsed !== null
            ) {

                return parsed;
            }
        }

    } catch {
        // Continue.
    }

    /*
     * Search for JSON object.
     */
    const objectStart =
        text.indexOf(
            "{"
        );

    const objectEnd =
        text.lastIndexOf(
            "}"
        );

    if (
        objectStart !== -1 &&
        objectEnd > objectStart
    ) {

        parsed =
            safeJsonParse(
                text.slice(
                    objectStart,
                    objectEnd + 1
                )
            );

        if (
            parsed !== null
        ) {

            return parsed;
        }
    }

    /*
     * Search for JSON array.
     */
    const arrayStart =
        text.indexOf(
            "["
        );

    const arrayEnd =
        text.lastIndexOf(
            "]"
        );

    if (
        arrayStart !== -1 &&
        arrayEnd > arrayStart
    ) {

        parsed =
            safeJsonParse(
                text.slice(
                    arrayStart,
                    arrayEnd + 1
                )
            );

        if (
            parsed !== null
        ) {

            return parsed;
        }
    }

    return null;
}


/* ============================================================
   AI RESPONSE FORMATTER
   ============================================================ */

function formatAIResponse(value) {

    if (
        value === null ||
        value === undefined
    ) {

        return "";
    }

    if (
        typeof value ===
        "object"
    ) {

        if (
            typeof value.answer ===
            "string"
        ) {

            value =
                value.answer;

        } else if (
            typeof value.content ===
            "string"
        ) {

            value =
                value.content;

        } else {

            value =
                JSON.stringify(
                    value,
                    null,
                    2
                );
        }
    }

    const text =
        String(value);

    return escapeHtml(text)
        .replace(
            /\*\*(.+?)\*\*/g,
            "<strong>$1</strong>"
        )
        .replace(
            /\*(.+?)\*/g,
            "<em>$1</em>"
        )
        .replace(
            /`([^`]+)`/g,
            "<code>$1</code>"
        )
        .replace(
            /\n/g,
            "<br>"
        );
}


/* ============================================================
   WEATHER NORMALIZER
   ============================================================ */

function normalizeWeatherData(value) {

    const data =
        parseMCPResponse(
            value
        );

    if (!data) {
        return null;
    }

    function unwrap(value) {

        if (
            value === null ||
            value === undefined
        ) {

            return null;
        }

        if (
            typeof value ===
            "string"
        ) {

            return parseMCPResponse(
                value
            );
        }

        if (
            typeof value ===
            "object"
        ) {

            if (
                typeof value.text ===
                "string"
            ) {

                return unwrap(
                    value.text
                );
            }

            if (
                Array.isArray(value)
            ) {

                for (
                    const item of value
                ) {

                    const result =
                        unwrap(
                            item
                        );

                    if (
                        result !== null
                    ) {

                        return result;
                    }
                }

                return null;
            }

            return value;
        }

        return null;
    }

    const root =
        unwrap(data) ||
        {};

    let current =
        null;

    let forecast =
        [];

    if (
        root.today_actual_weather !==
        undefined
    ) {

        const value =
            unwrap(
                root.today_actual_weather
            );

        if (
            value &&
            typeof value ===
                "object" &&
            !Array.isArray(value)
        ) {

            current =
                value;
        }

    } else if (
        root.current !==
        undefined
    ) {

        const value =
            unwrap(
                root.current
            );

        if (
            value &&
            typeof value ===
                "object" &&
            !Array.isArray(value)
        ) {

            if (
                value.city ||
                value.temperature_c !==
                    undefined ||
                value.condition
            ) {

                current =
                    value;
            }
        }
    }

    if (
        Array.isArray(
            root.per_day_forecast
        )
    ) {

        forecast =
            root.per_day_forecast;

    } else if (
        root.forecast !==
        undefined
    ) {

        const value =
            unwrap(
                root.forecast
            );

        if (
            value &&
            typeof value ===
                "object" &&
            !Array.isArray(value) &&
            Array.isArray(
                value.forecast
            )
        ) {

            forecast =
                value.forecast;

        } else if (
            Array.isArray(value)
        ) {

            forecast =
                value;
        }
    }

    if (
        !current &&
        root &&
        typeof root ===
            "object" &&
        (
            root.city ||
            root.today_actual_weather ||
            root.temperature_c !==
                undefined ||
            root.condition
        )
    ) {

        current =
            root;
    }

    return {

        destination:
            root.destination ||
            current?.city ||
            currentTrip.destination ||
            "Destination",

        current:
            current || {},

        forecast:
            Array.isArray(
                forecast
            )
                ? forecast
                : [],

        travelDate:
            root.travel_date ||
            "",

        tripEndDate:
            root.trip_end_date ||
            ""
    };
}


/* ============================================================
   WEATHER RENDERER
   ============================================================ */

function renderWeatherResults(value) {

    const element =
        $("weatherResults");

    if (!element) {
        return;
    }

    const weather =
        normalizeWeatherData(
            value
        );

    if (!weather) {

        element.innerHTML = `
            <div class="result-empty">
                Weather information unavailable.
            </div>
        `;

        return;
    }

    const current =
        weather.current ||
        {};

    const destination =
        weather.destination ||
        current.city ||
        current.name ||
        currentTrip.destination ||
        "Destination";

    const temperature =
        Number(
            current.temperature_c ??
            current.temp_c ??
            current.temperature
        );

    const feelsLike =
        Number(
            current.feels_like_c ??
            current.feels_like ??
            current.apparent_temperature
        );

    const humidity =
        Number(
            current.humidity ??
            current.humidity_percent
        );

    const wind =
        Number(
            current.wind_speed ??
            current.wind_speed_ms ??
            current.wind
        );

    const condition =
        current.condition ||
        current.description ||
        current.weather ||
        "Conditions unavailable";

    const forecast =
        Array.isArray(
            weather.forecast
        )
            ? weather.forecast
            : [];

    const forecastHtml =
        forecast.length
            ? `
                <div class="weather-forecast">

                    ${
                        forecast
                            .map(
                                item => {

                                    const forecastTemp =
                                        Number(
                                            item?.temperature_c ??
                                            item?.temp_c ??
                                            item?.temperature ??
                                            item?.temp
                                        );

                                    const forecastMin =
                                        Number(
                                            item?.temp_min_c
                                        );

                                    const forecastMax =
                                        Number(
                                            item?.temp_max_c
                                        );

                                    const forecastDate =
                                        item?.datetime ||
                                        item?.date ||
                                        item?.day ||
                                        "";

                                    const forecastCondition =
                                        item?.condition ||
                                        item?.description ||
                                        "";

                                    const unavailable =
                                        item?.status ===
                                        "forecast_unavailable_too_far_ahead";

                                    let tempLabel =
                                        "—";

                                    if (unavailable) {

                                        tempLabel =
                                            "Forecast unavailable";

                                    } else if (
                                        Number.isFinite(
                                            forecastMin
                                        ) &&
                                        Number.isFinite(
                                            forecastMax
                                        )
                                    ) {

                                        tempLabel =
                                            `${forecastMin.toFixed(
                                                1
                                            )}°C-${forecastMax.toFixed(
                                                1
                                            )}°C`;

                                    } else if (
                                        Number.isFinite(
                                            forecastTemp
                                        )
                                    ) {

                                        tempLabel =
                                            `${forecastTemp.toFixed(
                                                1
                                            )}°C`;
                                    }

                                    return `
                                        <div class="weather-day">

                                            <strong>
                                                ${escapeHtml(
                                                    String(
                                                        forecastDate
                                                    )
                                                )}
                                            </strong>

                                            <span>
                                                ${tempLabel}
                                            </span>

                                            ${
                                                forecastCondition &&
                                                !unavailable
                                                    ? `
                                                        <small>
                                                            ${escapeHtml(
                                                                String(
                                                                    forecastCondition
                                                                )
                                                            )}
                                                        </small>
                                                    `
                                                    : ""
                                            }

                                        </div>
                                    `;
                                }
                            )
                            .join("")
                    }

                </div>
            `
            : "";

    element.innerHTML = `
        <div class="weather-card">

            <div class="weather-main">

                <div class="weather-location">

                    <span class="weather-label">
                        TODAY ACTUAL WEATHER
                    </span>

                    <h3>
                        🌤️ ${escapeHtml(
                            String(
                                destination
                            )
                        )}
                    </h3>

                </div>

                <div class="weather-temperature">
                    ${
                        Number.isFinite(
                            temperature
                        )
                            ? `${temperature.toFixed(
                                1
                            )}°C`
                            : "—"
                    }
                </div>

                <div class="weather-condition">
                    ${escapeHtml(
                        String(
                            condition
                        )
                    )}
                </div>

            </div>

            <div class="weather-details">

                <div>

                    <span>
                        Feels like
                    </span>

                    <strong>
                        ${
                            Number.isFinite(
                                feelsLike
                            )
                                ? `${feelsLike.toFixed(
                                    1
                                )}°C`
                                : "—"
                        }
                    </strong>

                </div>

                <div>

                    <span>
                        Humidity
                    </span>

                    <strong>
                        ${
                            Number.isFinite(
                                humidity
                            )
                                ? `${humidity}%`
                                : "—"
                        }
                    </strong>

                </div>

                <div>

                    <span>
                        Wind
                    </span>

                    <strong>
                        ${
                            Number.isFinite(
                                wind
                            )
                                ? `${wind.toFixed(
                                    1
                                )} m/s`
                                : "—"
                        }
                    </strong>

                </div>

            </div>

            ${forecastHtml}

        </div>
    `;
}


/* ============================================================
   FLIGHT NORMALIZER
   ============================================================ */

function normalizeFlightData(value) {

    /*
     * Flight data can arrive from the backend as:
     *
     * 1. JSON object
     * 2. JSON string
     * 3. double-encoded JSON
     * 4. MCP { text: "..." } wrapper
     * 5. { flight_results: ... } wrapper
     * 6. { data: ... } / { result: ... } wrapper
     *
     * Find the actual flight object instead of assuming
     * one exact response shape.
     */

    const visited =
        new Set();

    function findFlightObject(node) {

        if (
            node === null ||
            node === undefined
        ) {

            return null;
        }

        if (
            typeof node ===
            "string"
        ) {

            const parsed =
                parseMCPResponse(
                    node
                );

            if (
                parsed === null ||
                parsed === node
            ) {

                return null;
            }

            return findFlightObject(
                parsed
            );
        }

        if (
            typeof node !==
            "object"
        ) {

            return null;
        }

        if (
            visited.has(node)
        ) {

            return null;
        }

        visited.add(node);

        /*
         * Actual SerpApi / GoTrip flight object.
         */
        if (
            Array.isArray(
                node.best_flights
            ) ||
            Array.isArray(
                node.other_flights
            ) ||
            node.status ===
                "schedule_samples_only" ||
            (
                node.route &&
                typeof node.route ===
                    "object" &&
                (
                    node.route.source_iata ||
                    node.route.destination_iata
                )
            )
        ) {

            return node;
        }

        /*
         * Common wrappers.
         */
        for (
            const key of [
                "flight_results",
                "flightResult",
                "flights",
                "result",
                "data",
                "content",
                "text",
                "response"
            ]
        ) {

            if (
                node[key] ===
                undefined
            ) {

                continue;
            }

            const found =
                findFlightObject(
                    node[key]
                );

            if (found) {
                return found;
            }
        }

        /*
         * MCP content arrays.
         */
        if (
            Array.isArray(node)
        ) {

            for (
                const item of node
            ) {

                const found =
                    findFlightObject(
                        item
                    );

                if (found) {
                    return found;
                }
            }

            return null;
        }

        /*
         * Last-resort recursive search.
         */
        for (
            const nested of
            Object.values(node)
        ) {

            if (
                !nested ||
                typeof nested !==
                    "object"
            ) {

                continue;
            }

            const found =
                findFlightObject(
                    nested
                );

            if (found) {
                return found;
            }
        }

        return null;
    }

    const parsed =
        parseMCPResponse(
            value
        );

    const result =
        findFlightObject(
            parsed ?? value
        );

    console.log(
        "[GoTrip] normalized flight data:",
        result
    );

    return result;
}


/* ============================================================
   FLIGHT RENDERER
   ============================================================ */

function renderFlightResults(value) {

    const element =
        $("flightResults");

    if (!element) {
        return;
    }

    const flight =
        normalizeFlightData(
            value
        );

    console.log(
        "[GoTrip] renderFlightResults input:",
        value
    );

    console.log(
        "[GoTrip] renderFlightResults normalized:",
        flight
    );

    if (
        !flight ||
        typeof flight !==
            "object"
    ) {

        element.innerHTML = `
            <div class="flight-unavailable">

                <div class="result-icon">
                    ✈️
                </div>

                <div>

                    <h3>
                        Flight information unavailable
                    </h3>

                    <p>
                        No flight data was returned by
                        the connected flight service.
                    </p>

                </div>

            </div>
        `;

        return;
    }


    function getFlightOptions(data) {

        if (
            !data ||
            typeof data !==
                "object"
        ) {

            return [];
        }

        const best =
            Array.isArray(
                data.best_flights
            )
                ? data.best_flights
                : [];

        const other =
            Array.isArray(
                data.other_flights
            )
                ? data.other_flights
                : [];

        return [
            ...best,
            ...other
        ];
    }


    function formatFlightDateTime(value) {

        const text =
            String(value || "").trim();

        const match =
            text.match(
                /^(\d{4})-(\d{2})-(\d{2})[ T](\d{1,2}):(\d{2})/
            );

        if (!match) {
            return text || "N/A";
        }

        const [, year, month, day, hours, minutes] = match;

        const months = [
            "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
        ];

        return `${day} ${months[Number(month) - 1]} ${year} · ${String(hours).padStart(2, "0")}:${minutes}`;
    }


    function formatDuration(
        minutes
    ) {

        const value =
            Number(
                minutes
            );

        if (
            !Number.isFinite(
                value
            ) ||
            value < 0
        ) {

            return "N/A";
        }

        const hours =
            Math.floor(
                value / 60
            );

        const mins =
            value % 60;

        return `${hours}h ${mins}m`;
    }


    function renderFlightCard(
        option
    ) {

        if (
            !option ||
            typeof option !==
                "object"
        ) {

            return "";
        }

        const segments =
            Array.isArray(
                option.flights
            )
                ? option.flights
                : [];

        if (
            !segments.length
        ) {

            return "";
        }

        const first =
            segments[0] ||
            {};

        const last =
            segments[
                segments.length - 1
            ] ||
            first;

        const departure =
            first.departure_airport ||
            {};

        const arrival =
            last.arrival_airport ||
            {};

        const airline =
            first.airline ||
            "Airline unavailable";

        const flightNumber =
            first.flight_number ||
            "";

        const departureId =
            departure.id ||
            departure.airport ||
            departure.name ||
            "N/A";

        const arrivalId =
            arrival.id ||
            arrival.airport ||
            arrival.name ||
            "N/A";

        const departureTime =
            formatFlightDateTime(
                departure.time
            );

        const arrivalTime =
            formatFlightDateTime(
                arrival.time
            );

        const duration =
            formatDuration(
                option.total_duration
            );

        const rawPrice =
            Number(
                option.price
            );

        const price =
            Number.isFinite(
                rawPrice
            )
                ? `₹${rawPrice.toLocaleString(
                    "en-IN"
                )}`
                : "Price unavailable";

        const travelClass =
            first.travel_class ||
            "";

        const airplane =
            first.airplane ||
            "";

        const legroom =
            first.legroom ||
            "";

        const stops =
            Math.max(
                segments.length - 1,
                0
            );

        return `
            <div class="flight-sample">

                <div>

                    <strong>
                        ${escapeHtml(
                            String(
                                airline
                            )
                        )}
                    </strong>

                    ${
                        flightNumber
                            ? `
                                <span>
                                    · ${escapeHtml(
                                        String(
                                            flightNumber
                                        )
                                    )}
                                </span>
                            `
                            : ""
                    }

                </div>

                <div>

                    <strong>
                        ${escapeHtml(
                            String(
                                departureId
                            )
                        )}
                    </strong>

                    ${escapeHtml(
                        String(
                            departureTime
                        )
                    )}

                    →

                    <strong>
                        ${escapeHtml(
                            String(
                                arrivalId
                            )
                        )}
                    </strong>

                    ${escapeHtml(
                        String(
                            arrivalTime
                        )
                    )}

                </div>

                <div>

                    Duration:

                    <strong>
                        ${escapeHtml(
                            duration
                        )}
                    </strong>

                    ·

                    ${
                        stops === 0
                            ? "Non-stop"
                            : `${stops} stop${
                                stops === 1
                                    ? ""
                                    : "s"
                            }`
                    }

                </div>

                <div>

                    Price:

                    <strong>
                        ${escapeHtml(
                            price
                        )}
                    </strong>

                </div>

                ${
                    travelClass
                        ? `
                            <div>
                                Class:
                                ${escapeHtml(
                                    String(
                                        travelClass
                                    )
                                )}
                            </div>
                        `
                        : ""
                }

                ${
                    airplane
                        ? `
                            <div>
                                Aircraft:
                                ${escapeHtml(
                                    String(
                                        airplane
                                    )
                                )}
                            </div>
                        `
                        : ""
                }

                ${
                    legroom
                        ? `
                            <div>
                                Legroom:
                                ${escapeHtml(
                                    String(
                                        legroom
                                    )
                                )}
                            </div>
                        `
                        : ""
                }

            </div>
        `;
    }


    function renderDirection(
        data,
        title,
        fallbackDate
    ) {

        if (
            !data ||
            typeof data !==
                "object"
        ) {

            return "";
        }

        const flights =
            getFlightOptions(
                data
            );

        const route =
            data.route ||
            {};

        const departure =
            data.departure_airport ||
            route.source_iata ||
            data.from ||
            "N/A";

        const arrival =
            data.arrival_airport ||
            route.destination_iata ||
            data.to ||
            "N/A";

        const date =
            data.date ||
            data.outbound_date ||
            data.return_date ||
            fallbackDate ||
            "Date unavailable";


        /*
         * Schedule-sample fallback.
         *
         * These records are deliberately shown as
         * schedule samples, not confirmed flights.
         */
        if (
            !flights.length &&
            data.status ===
                "schedule_samples_only"
        ) {

            const outbound =
                data.outbound ||
                {};

            const returning =
                data.return ||
                {};

            const samples =
                title
                    .toLowerCase()
                    .includes(
                        "return"
                    )
                    ? returning
                    : outbound;

            const departures =
                Array.isArray(
                    samples.departure_samples
                )
                    ? samples.departure_samples
                    : [];

            const arrivals =
                Array.isArray(
                    samples.arrival_samples
                )
                    ? samples.arrival_samples
                    : [];

            const sampleCount =
                departures.length +
                arrivals.length;

            return `
                <div class="flight-card">

                    <div class="flight-card-title">
                        ✈️ ${escapeHtml(
                            title
                        )}
                    </div>

                    <div class="flight-route">

                        <strong>
                            ${escapeHtml(
                                String(
                                    departure
                                )
                            )}
                        </strong>

                        <span>
                            →
                        </span>

                        <strong>
                            ${escapeHtml(
                                String(
                                    arrival
                                )
                            )}
                        </strong>

                    </div>

                    <div class="flight-date">
                        ${escapeHtml(
                            String(
                                date
                            )
                        )}
                    </div>

                    <div class="flight-empty">

                        ${
                            sampleCount
                                ? `
                                    ${sampleCount}
                                    airport schedule
                                    sample${
                                        sampleCount === 1
                                            ? ""
                                            : "s"
                                    } returned.

                                    These do not confirm a
                                    specific route, fare or
                                    booking.
                                `
                                : `
                                    No route-specific flight
                                    was verified for this date.
                                `
                        }

                    </div>

                </div>
            `;
        }


        if (
            !flights.length
        ) {

            return `
                <div class="flight-card">

                    <div class="flight-card-title">
                        ✈️ ${escapeHtml(
                            title
                        )}
                    </div>

                    <div class="flight-route">

                        <strong>
                            ${escapeHtml(
                                String(
                                    departure
                                )
                            )}
                        </strong>

                        <span>
                            →
                        </span>

                        <strong>
                            ${escapeHtml(
                                String(
                                    arrival
                                )
                            )}
                        </strong>

                    </div>

                    <div class="flight-date">
                        ${escapeHtml(
                            String(
                                date
                            )
                        )}
                    </div>

                    <div class="flight-empty">
                        ${
                            escapeHtml(
                                String(
                                    data.reason ||
                                    "No matching flights were returned."
                                )
                            )
                        }
                    </div>

                </div>
            `;
        }


        const visibleFlights =
            flights
                .slice(
                    0,
                    5
                )
                .map(
                    renderFlightCard
                )
                .filter(
                    Boolean
                );

        return `
            <div class="flight-card">

                <div class="flight-card-title">
                    ✈️ ${escapeHtml(
                        title
                    )}
                </div>

                <div class="flight-route">

                    <strong>
                        ${escapeHtml(
                            String(
                                departure
                            )
                        )}
                    </strong>

                    <span>
                        →
                    </span>

                    <strong>
                        ${escapeHtml(
                            String(
                                arrival
                            )
                        )}
                    </strong>

                </div>

                <div class="flight-date">
                    ${escapeHtml(
                        String(
                            date
                        )
                    )}
                </div>

                <div class="flight-sample-count">

                    Flights found:

                    <strong>
                        ${flights.length}
                    </strong>

                </div>

                <div class="flight-samples">

                    ${visibleFlights.join("")}

                </div>

                ${
                    flights.length > 5
                        ? `
                            <div class="flight-note">
                                Showing the first 5 flight
                                options.
                            </div>
                        `
                        : ""
                }

            </div>
        `;
    }


    /*
     * Preferred GoTrip response:
     * outbound and return are stored separately.
     *
     * IMPORTANT:
     * A SerpApi round-trip search initially returns outbound
     * choices. The backend performs the required second
     * departure_token request and stores the return choices
     * under flight.return.
     */
    const outbound =
        flight.outbound;

    const returning =
        flight.return;

    if (
        (
            outbound &&
            typeof outbound === "object"
        ) ||
        (
            returning &&
            typeof returning === "object"
        )
    ) {

        const html = [
            outbound
                ? renderDirection(
                    outbound,
                    "Outbound",
                    flight.outbound_date
                )
                : "",

            returning
                ? renderDirection(
                    returning,
                    "Return",
                    flight.return_date
                )
                : ""
        ]
            .filter(Boolean)
            .join("");

        element.innerHTML =
            html ||
            `
                <div class="flight-unavailable">
                    Flight information unavailable.
                </div>
            `;

        return;
    }


    /*
     * Backward compatibility for older backend responses
     * that expose only best_flights / other_flights.
     */
    const directFlights =
        getFlightOptions(
            flight
        );

    if (directFlights.length) {

        element.innerHTML =
            renderDirection(
                flight,
                "Flight options",
                flight.outbound_date
            );

        return;
    }


    /*
     * Structured unavailable result.
     */
    if (
        String(
            flight.status ||
            ""
        ).toLowerCase() ===
        "unavailable"
    ) {

        element.innerHTML = `
            <div class="flight-unavailable">

                <div class="result-icon">
                    ✈️
                </div>

                <div>

                    <h3>
                        Flight information unavailable
                    </h3>

                    <p>
                        ${escapeHtml(
                            String(
                                flight.reason ||
                                "No flight information is available."
                            )
                        )}
                    </p>

                </div>

            </div>
        `;

        return;
    }


    /*
     * Last fallback.
     */
    element.innerHTML = `
        <div class="flight-unavailable">

            <div class="result-icon">
                ✈️
            </div>

            <div>

                <h3>
                    Flight information unavailable
                </h3>

                <p>
                    The backend returned flight data in an
                    unsupported format.
                </p>

            </div>

        </div>
    `;
}


/* ============================================================
   HOTEL NORMALIZER
   ============================================================ */

function normalizeHotelData(value) {

    const data =
        parseMCPResponse(
            value
        );

    if (!data) {
        return [];
    }

    function collect(
        value
    ) {

        if (!value) {
            return [];
        }

        if (
            Array.isArray(value)
        ) {

            let results = [];

            for (
                const item of value
            ) {

                results.push(
                    ...collect(item)
                );
            }

            return results;
        }

        if (
            typeof value ===
            "string"
        ) {

            return collect(
                parseMCPResponse(
                    value
                )
            );
        }

        if (
            typeof value !==
            "object"
        ) {

            return [];
        }

        if (
            Array.isArray(
                value.results
            )
        ) {

            return collect(
                value.results
            );
        }

        if (
            typeof value.text ===
            "string"
        ) {

            return collect(
                value.text
            );
        }

        if (
            value.title ||
            value.name ||
            value.url
        ) {

            return [
                value
            ];
        }

        let results = [];

        for (
            const nested of
            Object.values(value)
        ) {

            results.push(
                ...collect(
                    nested
                )
            );
        }

        return results;
    }

    const hotels =
        collect(
            data
        );

    const seen =
        new Set();

    return hotels.filter(
        hotel => {

            const title =
                hotel?.title ||
                hotel?.name ||
                hotel?.url ||
                "";

            const key =
                String(
                    title
                )
                    .trim()
                    .toLowerCase();

            if (
                !key ||
                seen.has(key)
            ) {

                return false;
            }

            seen.add(
                key
            );

            return true;
        }
    );
}


/* ============================================================
   HOTEL RENDERER
   ============================================================ */

function renderHotelResults(value) {

    const element =
        $("hotelResults");

    if (!element) {
        return;
    }

    const hotels =
        normalizeHotelData(
            value
        );

    if (
        !hotels.length
    ) {

        element.innerHTML = `
            <div class="result-empty">
                No hotel information was returned.
            </div>
        `;

        return;
    }

    const visibleHotels =
        hotels.slice(
            0,
            8
        );

    element.innerHTML = `
        <div class="hotel-results">

            ${
                visibleHotels
                    .map(
                        hotel => {

                            const title =
                                hotel?.title ||
                                hotel?.name ||
                                "Hotel suggestion";

                            const url =
                                hotel?.url ||
                                "";

                            const content =
                                hotel?.content ||
                                hotel?.description ||
                                "";

                            const image =
                                hotel?.image ||
                                "";

                            return `
                                <div class="hotel-card">

                                    ${
                                        image
                                            ? `
                                                <img
                                                    src="${escapeHtml(
                                                        image
                                                    )}"
                                                    alt="${escapeHtml(
                                                        title
                                                    )}"
                                                    loading="lazy"
                                                >
                                            `
                                            : ""
                                    }

                                    <div class="hotel-card-body">

                                        <h3>
                                            ${escapeHtml(
                                                title
                                            )}
                                        </h3>

                                        ${
                                            content
                                                ? `
                                                    <p>
                                                        ${escapeHtml(
                                                            String(
                                                                content
                                                            ).slice(
                                                                0,
                                                                500
                                                            )
                                                        )}
                                                    </p>
                                                `
                                                : ""
                                        }

                                        ${
                                            url
                                                ? `
                                                    <a
                                                        href="${escapeHtml(
                                                            url
                                                        )}"
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                    >
                                                        View source ↗
                                                    </a>
                                                `
                                                : ""
                                        }

                                    </div>

                                </div>
                            `;
                        }
                    )
                    .join("")
            }

        </div>
    `;
}


/* ============================================================
   BUDGET
   ============================================================ */

function renderBudget(data) {

    const request =
        data?.request ||
        currentTrip;

    const estimated =
        $("estimatedBudget");

    const status =
        $("budgetStatus");

    const flight =
        $("flightBudget");

    const hotel =
        $("hotelBudget");

    const activities =
        $("activityBudget");

    let itinerary =
        data?.itinerary ||
        {};

    if (
        typeof itinerary ===
        "string"
    ) {

        itinerary =
            parseMCPResponse(
                itinerary
            ) ||
            {};
    }

    const days =
        Array.isArray(
            itinerary?.days
        )
            ? itinerary.days
            : [];

    const totalBudget =
        Number(
            request?.budget
        ) || 0;

    let totalDayBudget =
        0;

    days.forEach(
        day => {

            const amount =
                Number(
                    day?.day_budget
                );

            if (
                Number.isFinite(
                    amount
                ) &&
                amount > 0
            ) {

                totalDayBudget +=
                    amount;
            }
        }
    );

    if (estimated) {

        estimated.textContent =
            formatINR(
                totalBudget
            );
    }

    const flightData =
        normalizeFlightData(
            data?.flight_results
        );

    /*
     * Only use an explicitly supplied numeric
     * flight price. Never estimate one here.
     */
    function findVerifiedFlightPrice(
        value
    ) {

        if (!value) {
            return null;
        }

        if (
            Array.isArray(value)
        ) {

            for (
                const item of value
            ) {

                const result =
                    findVerifiedFlightPrice(
                        item
                    );

                if (
                    result !== null
                ) {

                    return result;
                }
            }

            return null;
        }

        if (
            typeof value !==
            "object"
        ) {

            return null;
        }

        for (
            const key of [
                "price",
                "fare",
                "flight_price",
                "total_price",
                "amount"
            ]
        ) {

            const raw =
                value[key];

            if (
                typeof raw ===
                    "number" &&
                Number.isFinite(
                    raw
                ) &&
                raw >= 0
            ) {

                return raw;
            }

            if (
                typeof raw ===
                "string"
            ) {

                const cleaned =
                    raw
                        .replace(
                            /,/g,
                            ""
                        )
                        .replace(
                            /[₹$]/g,
                            ""
                        )
                        .trim();

                const number =
                    Number(
                        cleaned
                    );

                if (
                    Number.isFinite(
                        number
                    ) &&
                    number >= 0
                ) {

                    return number;
                }
            }
        }

        for (
            const nested of
            Object.values(
                value
            )
        ) {

            const result =
                findVerifiedFlightPrice(
                    nested
                );

            if (
                result !== null
            ) {

                return result;
            }
        }

        return null;
    }

    const verifiedFlightPrice =
        findVerifiedFlightPrice(
            flightData
        );

    /*
     * FLIGHT
     */
    if (flight) {

        flight.textContent =
            verifiedFlightPrice !==
            null

                ? formatINR(
                    verifiedFlightPrice
                )

                : "Fare not verified";
    }

    /*
     * HOTEL
     */
    if (hotel) {

        const hotelData =
            normalizeHotelData(
                data?.hotel_results
            );

        hotel.textContent =
            hotelData.length

                ? `${hotelData.length} options`

                : "Unavailable";
    }

    /*
     * ON-GROUND SPENDING
     */
    if (activities) {

        activities.textContent =
            totalDayBudget > 0

                ? formatINR(
                    totalDayBudget
                )

                : "Not available";
    }

    /*
     * STATUS
     */
    if (status) {

        if (
            verifiedFlightPrice !==
            null
        ) {

            const remaining =
                totalBudget -
                verifiedFlightPrice -
                totalDayBudget;

            status.textContent =
                `On-ground: ${formatINR(
                    totalDayBudget
                )} · Remaining: ${formatINR(
                    remaining
                )}`;

        } else {

            const remainingOnGround =
                totalBudget -
                totalDayBudget;

            status.textContent =
                `Flight fare unverified · ` +
                `On-ground remaining: ${formatINR(
                    remainingOnGround
                )}`;
        }
    }

    /*
     * VISUAL BARS
     */
    const flightBar =
        $("flightBudgetBar");

    const hotelBar =
        $("hotelBudgetBar");

    const activityBar =
        $("activityBudgetBar");

    if (
        totalBudget > 0
    ) {

        const flightAmount =
            verifiedFlightPrice !==
            null

                ? verifiedFlightPrice

                : 0;

        const activityAmount =
            totalDayBudget;

        const hotelAmount =
            0;

        const flightPercent =
            Math.min(
                100,
                Math.max(
                    0,
                    (
                        flightAmount /
                        totalBudget
                    ) *
                    100
                )
            );

        const hotelPercent =
            Math.min(
                100,
                Math.max(
                    0,
                    (
                        hotelAmount /
                        totalBudget
                    ) *
                    100
                )
            );

        const activityPercent =
            Math.min(
                100,
                Math.max(
                    0,
                    (
                        activityAmount /
                        totalBudget
                    ) *
                    100
                )
            );

        if (flightBar) {

            flightBar.style.width =
                `${flightPercent}%`;
        }

        if (hotelBar) {

            hotelBar.style.width =
                `${hotelPercent}%`;
        }

        if (activityBar) {

            activityBar.style.width =
                `${activityPercent}%`;
        }
    }
}


/* ============================================================
   ITINERARY TIME NORMALIZER
   ============================================================ */

function formatItineraryTime(value) {
    if (value === null || value === undefined) {
        return "—";
    }

    let text = String(value).trim();

    if (!text) {
        return "—";
    }

    // Normalize Unicode dashes used in time ranges.
    text = text.replace(/[–—]/g, "-");

    // Normalize ISO/date-time strings to their HH:MM portion.
    const isoMatch = text.match(
        /\b\d{4}-\d{2}-\d{2}[ T](\d{1,2}):(\d{2})\b/
    );

    if (isoMatch) {
        return `${String(isoMatch[1]).padStart(2, "0")}:${isoMatch[2]}`;
    }

    function normalizeOne(part) {
        part = String(part).trim();

        const ampm = part.match(
            /^(\d{1,2})(?::(\d{1,2}))?\s*(AM|PM)$/i
        );

        if (ampm) {
            let hours = Number(ampm[1]);
            const minutes = Number(ampm[2] || 0);
            const suffix = ampm[3].toUpperCase();

            if (suffix === "AM" && hours === 12) {
                hours = 0;
            } else if (suffix === "PM" && hours !== 12) {
                hours += 12;
            }

            return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
        }

        const hm = part.match(/^(\d{1,2})(?::(\d{1,2}))?$/);

        if (hm) {
            const hours = Number(hm[1]);
            const minutes = Number(hm[2] || 0);

            if (
                hours >= 0 &&
                hours <= 23 &&
                minutes >= 0 &&
                minutes <= 59
            ) {
                return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
            }
        }

        return part;
    }

    const rangeParts = text.split(/\s*-\s*/);

    if (rangeParts.length === 2) {
        return `${normalizeOne(rangeParts[0])}-${normalizeOne(rangeParts[1])}`;
    }

    return normalizeOne(text);
}


/* ============================================================
   ITINERARY
   IMPORTANT:
   HTML uses id="dayContent"
   ============================================================ */

function renderItinerary(data) {

    const container = $("dayContent");

    if (!container) {
        return;
    }

    let itinerary = data?.itinerary ?? {};

    /*
     * Normalize itinerary response.
     */
    if (typeof itinerary === "string") {

        const parsed = parseMCPResponse(itinerary);

        itinerary =
            parsed && typeof parsed === "object"
                ? parsed
                : {};
    }

    /*
     * Handle wrapped responses.
     */
    if (!Array.isArray(itinerary?.days)) {

        const nested = parseMCPResponse(
            itinerary?.result ??
            itinerary?.data ??
            itinerary?.content ??
            itinerary?.text
        );

        if (nested && typeof nested === "object") {
            itinerary = nested;
        }
    }

    const days =
        Array.isArray(itinerary?.days)
            ? itinerary.days
            : [];

    if (!days.length) {

        container.innerHTML = `
            <div class="empty-state">

                <h3>Itinerary data unavailable</h3>

                <p>
                    No structured itinerary.days
                    field was received.
                </p>

            </div>
        `;

        return;
    }

    /*
     * Preserve complete itinerary.
     */
    if (
        currentResult &&
        typeof currentResult === "object"
    ) {
        currentResult.itinerary = itinerary;
    }

    const getTransportIcon = (transport) => {

        const value =
            String(transport || "").toLowerCase();

        if (
            value.includes("flight") ||
            value.includes("air")
        ) {
            return "✈️";
        }

        if (
            value.includes("walk")
        ) {
            return "🚶";
        }

        if (
            value.includes("metro") ||
            value.includes("subway") ||
            value.includes("train")
        ) {
            return "🚇";
        }

        if (
            value.includes("bus")
        ) {
            return "🚌";
        }

        if (
            value.includes("boat") ||
            value.includes("yacht") ||
            value.includes("cruise")
        ) {
            return "🛥️";
        }

        if (
            value.includes("hotel") ||
            value.includes("on-site")
        ) {
            return "🏨";
        }

        return "🚗";
    };

    const formatActivityCost = (activity) => {

        const cost =
            Number(activity?.estimated_cost);

        const currency =
            activity?.currency ||
            currentTrip.currency ||
            "INR";

        if (
            !Number.isFinite(cost) ||
            cost < 0
        ) {
            return "Estimated";
        }

        return `${currency} ${cost.toLocaleString(
            "en-IN",
            {
                maximumFractionDigits: 0
            }
        )}`;
    };

    container.innerHTML = `
        <div class="itinerary-all-days">

            ${
                days.map(
                    (day, index) => {

                        const dayNumber =
                            Number(day?.day) ||
                            index + 1;

                        const title =
                            day?.title ||
                            `Day ${dayNumber}`;

                        const location =
                            day?.location ||
                            currentTrip.destination ||
                            "";

                        const route =
                            day?.route ||
                            (
                                currentTrip.source &&
                                location
                                    ? `${currentTrip.source} → ${location}`
                                    : location
                            );

                        const activities =
                            Array.isArray(
                                day?.activities
                            )
                                ? day.activities
                                : [];

                        const budget =
                            Number(
                                day?.day_budget
                            );

                        const activitiesHtml =
                            activities.length

                                ? activities.map(
                                    (activity) => {

                                        const time =
                                            formatItineraryTime(
                                                activity?.time
                                            );

                                        const activityName =
                                            String(
                                                activity?.activity ||
                                                "Activity"
                                            ).trim();

                                        const transport =
                                            String(
                                                activity?.transport ||
                                                ""
                                            ).trim();

                                        const transportIcon =
                                            getTransportIcon(
                                                transport
                                            );

                                        const costText =
                                            formatActivityCost(
                                                activity
                                            );

                                        return `
                                            <div class="timeline-item">

                                                <span
                                                    class="timeline-dot"
                                                    aria-hidden="true"
                                                ></span>

                                                <div class="timeline-time">
                                                    ${escapeHtml(
                                                        time
                                                    )}
                                                </div>

                                                <div class="timeline-content">

                                                    <strong class="activity-title">
                                                        ${escapeHtml(
                                                            activityName
                                                        )}
                                                    </strong>

                                                    <div class="activity-meta">

                                                        ${
                                                            transport
                                                                ? `
                                                                    <span class="transport-chip">
                                                                        <span>
                                                                            ${transportIcon}
                                                                        </span>

                                                                        ${escapeHtml(
                                                                            transport
                                                                        )}
                                                                    </span>
                                                                `
                                                                : ""
                                                        }

                                                        <span class="cost-chip">
                                                            ${escapeHtml(
                                                                costText
                                                            )}
                                                        </span>

                                                    </div>

                                                </div>

                                            </div>
                                        `;
                                    }
                                ).join("")

                                : `
                                    <div class="result-empty">
                                        No activities were returned
                                        for this day.
                                    </div>
                                `;

                        return `
                            <article class="itinerary-day">

                                <div class="day-header">

                                    <div class="day-number">
                                        ${String(
                                            dayNumber
                                        ).padStart(
                                            2,
                                            "0"
                                        )}
                                    </div>

                                    <div class="day-heading">

                                        <h3>
                                            ${escapeHtml(
                                                String(
                                                    title
                                                )
                                            )}
                                        </h3>

                                        ${
                                            location
                                                ? `
                                                    <div class="day-location">
                                                        ${escapeHtml(
                                                            String(
                                                                location
                                                            )
                                                        )}
                                                    </div>
                                                `
                                                : ""
                                        }

                                    </div>

                                </div>

                                ${
                                    route
                                        ? `
                                            <div class="day-route">
                                                <span class="route-start">
                                                    ${escapeHtml(
                                                        String(
                                                            currentTrip.source ||
                                                            ""
                                                        )
                                                    )}
                                                </span>

                                                <span class="route-arrow">
                                                    →
                                                </span>

                                                <span class="route-end">
                                                    ${escapeHtml(
                                                        String(
                                                            location ||
                                                            route
                                                        )
                                                    )}
                                                </span>
                                            </div>
                                        `
                                        : ""
                                }

                                <div class="timeline">

                                    ${activitiesHtml}

                                </div>

                                ${
                                    Number.isFinite(
                                        budget
                                    ) && budget > 0
                                        ? `
                                            <div class="day-budget">

                                                <span>
                                                    Estimated day budget
                                                </span>

                                                <strong>
                                                    ${formatINR(
                                                        budget
                                                    )}
                                                </strong>

                                            </div>
                                        `
                                        : ""
                                }

                            </article>
                        `;
                    }
                ).join("")
            }

        </div>
    `;
}


/* ============================================================
COMPLETE BACKEND RESULT
   ============================================================ */

function renderAllBackendResults(data) {

    console.log(
        "[GoTrip] Rendering backend results:",
        data
    );

    const renderers = [

        [
            "flights",
            () =>
                renderFlightResults(
                    data?.flight_results
                )
        ],

        [
            "hotels",
            () =>
                renderHotelResults(
                    data?.hotel_results
                )
        ],

        [
            "weather",
            () =>
                renderWeatherResults(
                    data?.weather_results
                )
        ],

        [
            "itinerary",
            () =>
                renderItinerary(
                    data
                )
        ],

        [
            "budget",
            () =>
                renderBudget(
                    data
                )
        ],

        [
            "route",
            () =>
                renderRoute(
                    data?.route ||
                    []
                )
        ]

    ];

    for (
        const [
            name,
            renderer
        ]
        of renderers
    ) {

        try {

            renderer();

            console.log(
                `[GoTrip] ${name} renderer OK`
            );

        } catch (error) {

            console.error(
                `[GoTrip] ${name} renderer FAILED:`,
                error
            );
        }
    }
}


function displayTravelResult(data) {

    currentResult =
        data;

    console.log(
        "========== GOTRIP RESULT =========="
    );

    console.log(
        "FULL RESPONSE:",
        data
    );

    console.log(
        "REQUEST:",
        data?.request
    );

    console.log(
        "FLIGHTS:",
        data?.flight_results
    );

    console.log(
        "HOTELS:",
        data?.hotel_results
    );

    console.log(
        "WEATHER:",
        data?.weather_results
    );

    console.log(
        "ITINERARY:",
        data?.itinerary
    );

    console.log(
        "FINAL ANSWER:",
        data?.final_answer
    );

    console.log(
        "===================================="
    );

    /*
     * Synchronize request data from backend.
     */
    if (
        data?.request &&
        typeof data.request ===
            "object"
    ) {

        currentTrip = {
            ...currentTrip,
            ...data.request
        };

        currentTrip.days =
            Number(
                currentTrip.days
            ) || 1;

        currentTrip.budget =
            parseBudget(
                currentTrip.budget
            );
    }

    updateTripSummary(
        currentTrip
    );

    updateAIScore(
        data?.score
    );

    /*
     * Render every backend section exactly once.
     */
    renderAllBackendResults(
        data
    );

    /*
     * Make sure result containers are visible.
     */
    [
        "flightResults",
        "hotelResults",
        "weatherResults",
        "itinerary"
    ].forEach(
        id => {

            const element =
                $(id);

            if (element) {
                element.hidden =
                    false;
            }
        }
    );

    /*
     * Itinerary renderer displays all returned days.
     * Keep currentDay for backwards compatibility.
     */
    currentDay =
        0;

    console.log(
        "[GoTrip] All backend results rendered."
    );
}


/* ============================================================
   GENERATE
   ============================================================ */

async function generateTrip() {

    if (isGenerating) {
        return;
    }

    const trip =
        getTripData();

    try {

        validateTrip(
            trip
        );

    } catch (error) {

        showToast(
            error.message
        );

        return;
    }

    isGenerating =
        true;

    const button =
        $("generateBtn");

    const label =
        $("generateLabel");

    if (button) {

        button.disabled =
            true;
    }

    if (label) {

        label.textContent =
            "Planning...";
    }

    document.body.classList.add(
        "generating"
    );

    updateTripSummary(
        trip
    );

    resetAgents();

    try {

        const animation =
            animateAgents();

        const response =
            await callTravelBackend(
                trip
            );

        await animation;

        displayTravelResult(
            response
        );

        showToast(
            "Trip generated successfully."
        );

        $("itinerary")?.scrollIntoView({
            behavior:
                "smooth",

            block:
                "start"
        });

    } catch (error) {

        console.error(
            error
        );

        resetAgents();

        showToast(
            error.message ||
            "Unable to generate the trip."
        );

    } finally {

        isGenerating =
            false;

        document.body.classList.remove(
            "generating"
        );

        if (button) {

            button.disabled =
                false;
        }

        if (label) {

            label.textContent =
                "Build my trip";
        }
    }
}


/* ============================================================
   QUICK PROMPTS
   ============================================================ */

function applyQuickPrompt(
    button
) {

    const prompt =
        button.dataset.prompt ||
        "";

    const destination =
        button.dataset.destination ||
        "";

    const days =
        button.dataset.days ||
        "";

    if ($("prompt")) {

        $("prompt").value =
            prompt;
    }

    if (
        $("destination") &&
        destination
    ) {

        $("destination").value =
            destination;
    }

    if (
        $("days") &&
        days
    ) {

        $("days").value =
            days;
    }

    showToast(
        "Trip idea loaded. Set your source and budget, then build."
    );
}


/* ============================================================
   REGENERATE
   ============================================================ */

async function regenerateTrip() {

    if (
        !currentTrip.source ||
        !currentTrip.destination
    ) {

        showToast(
            "Generate a trip first."
        );

        return;
    }

    const prompt =
        `${buildUserPrompt(currentTrip)}

Generate a different route and alternative recommendations while preserving:
source, destination, duration, travel date, budget and travel style.`;

    const trip = {
        ...currentTrip,
        prompt
    };

    const button =
        $("regenerate");

    if (button) {

        button.disabled =
            true;

        button.textContent =
            "Generating...";
    }

    try {

        const response =
            await callTravelBackend(
                trip
            );

        displayTravelResult(
            response
        );

        showToast(
            "Alternative itinerary generated."
        );

    } catch (error) {

        console.error(
            error
        );

        showToast(
            error.message ||
            "Unable to regenerate."
        );

    } finally {

        if (button) {

            button.disabled =
                false;

            button.textContent =
                "↻ Regenerate";
        }
    }
}


/* ============================================================
   CHAT
   ============================================================ */

async function sendChatMessage() {

    const input =
        $("chatInput");

    const messages =
        $("messages");

    if (
        !input ||
        !messages
    ) {

        return;
    }

    const message =
        input.value.trim();

    if (!message) {
        return;
    }

    if (
        !currentTrip.source ||
        !currentTrip.destination
    ) {

        showToast(
            "Generate a trip before using the AI chat."
        );

        return;
    }

    messages.insertAdjacentHTML(
        "beforeend",
        `
            <div class="user-msg">
                ${escapeHtml(
                    message
                )}
            </div>
        `
    );

    input.value =
        "";

    const typingId =
        `typing-${Date.now()}`;

    messages.insertAdjacentHTML(
        "beforeend",
        `
            <div
                class="bot-msg"
                id="${typingId}"
            >
                GoTrip AI is thinking...
            </div>
        `
    );

    try {

        const response =
            await fetch(
                "/api/chat",
                {
                    method:
                        "POST",

                    headers: {

                        "Content-Type":
                            "application/json",

                        "Accept":
                            "application/json"
                    },

                    body:
                        JSON.stringify({

                            message,

                            source:
                                currentTrip.source,

                            destination:
                                currentTrip.destination,

                            days:
                                currentTrip.days,

                            budget:
                                currentTrip.budget,

                            currency:
                                currentTrip.currency,

                            style:
                                currentTrip.style,

                            interests:
                                currentTrip.interests,

                            travel_date:
                                currentTrip.travel_date ||
                                null,

                            thread_id:
                                getThreadId()
                        })
                }
            );

        let data;

        try {

            data =
                await response.json();

        } catch {

            throw new Error(
                "Server returned an invalid chat response."
            );
        }

        if (
            !response.ok ||
            data.success ===
                false
        ) {

            throw new Error(
                data.error ||
                "Chat request failed."
            );
        }

        if (
            data.thread_id
        ) {

            localStorage.setItem(
                "gotrip_thread_id",
                data.thread_id
            );

            updateThreadIdUI();
        }

        const typing =
            $(typingId);

        if (typing) {

            typing.innerHTML =
                formatAIResponse(
                    data.answer
                );
        }

        if (
            data.route
        ) {

            renderRoute(
                data.route
            );
        }

        if (
            data.score !==
            undefined
        ) {

            updateAIScore(
                data.score
            );
        }

        if (
            data.request
        ) {

            currentTrip = {
                ...currentTrip,
                ...data.request
            };

            updateTripSummary(
                currentTrip
            );
        }

        renderFlightResults(
            data?.flight_results
        );

        renderHotelResults(
            data?.hotel_results
        );

        renderWeatherResults(
            data?.weather_results
        );

        if (
            data?.itinerary
        ) {

            currentResult = {
                ...currentResult,
                ...data
            };

            renderItinerary(
                data
            );

            renderBudget(
                data
            );
        }

    } catch (error) {

        console.error(
            error
        );

        const typing =
            $(typingId);

        if (typing) {

            typing.textContent =
                error.message ||
                "Unable to process message.";
        }
    }

    messages.scrollTop =
        messages.scrollHeight;
}


/* ============================================================
   DAY NAVIGATION
   ============================================================ */

function renderCurrentDay() {

    if (!currentResult) {
        return;
    }

    renderItinerary(
        currentResult
    );
}


function nextDay() {

    const days =
        currentResult?.itinerary?.days;

    if (
        !Array.isArray(days) ||
        !days.length
    ) {

        return;
    }

    if (
        currentDay <
        days.length - 1
    ) {

        currentDay++;

        renderCurrentDay();
    }
}


function previousDay() {

    if (
        currentDay > 0
    ) {

        currentDay--;

        renderCurrentDay();
    }
}


/* ============================================================
   TRAVEL DATE
   ============================================================ */

function bindTravelDateInput() {

    const input =
        $("travelDate") ||
        $("travel_date");

    if (!input) {

        console.warn(
            "Travel date input not found."
        );

        return;
    }

    input.addEventListener(
        "change",
        () => {

            currentTrip.travel_date =
                input.value ||
                "";
        }
    );

    input.addEventListener(
        "input",
        () => {

            currentTrip.travel_date =
                input.value ||
                "";
        }
    );
}


/* ============================================================
   EVENT BINDINGS
   ============================================================ */

$("generateBtn")
    ?.addEventListener(
        "click",
        generateTrip
    );


$("copyThreadId")
    ?.addEventListener(
        "click",
        copyThreadId
    );


$("regenerate")
    ?.addEventListener(
        "click",
        regenerateTrip
    );


document
    .querySelectorAll(
        ".quick-chips button"
    )
    .forEach(
        button => {

            button.addEventListener(
                "click",
                () =>
                    applyQuickPrompt(
                        button
                    )
            );
        }
    );


$("chatToggle")
    ?.addEventListener(
        "click",
        () => {

            $("aiChat")
                ?.classList.add(
                    "open"
                );
        }
    );


$("closeChat")
    ?.addEventListener(
        "click",
        () => {

            $("aiChat")
                ?.classList.remove(
                    "open"
                );
        }
    );


$("sendChat")
    ?.addEventListener(
        "click",
        sendChatMessage
    );


$("chatInput")
    ?.addEventListener(
        "keydown",
        event => {

            if (
                event.key ===
                "Enter"
            ) {

                event.preventDefault();

                sendChatMessage();
            }
        }
    );


$("mapMode")
    ?.addEventListener(
        "click",
        () => {

            if (
                !currentRoute.length
            ) {

                showToast(
                    "Generate a trip to see the route."
                );

                return;
            }

            showToast(
                `${currentRoute.length} route stops · ` +
                currentRoute
                    .map(
                        item =>
                            item.name
                    )
                    .join(
                        " → "
                    )
            );
        }
    );


/* ============================================================
   FORM INPUTS
   ============================================================ */

$("days")
    ?.addEventListener(
        "input",
        () => {

            const raw =
                Number(
                    $("days").value ||
                    1
                );

            const value =
                Number.isFinite(
                    raw
                )

                    ? Math.max(
                        1,
                        Math.min(
                            365,
                            Math.floor(
                                raw
                            )
                        )
                    )

                    : 1;

            currentTrip.days =
                value;
        }
    );


$("source")
    ?.addEventListener(
        "input",
        () => {

            currentTrip.source =
                $("source")
                    .value
                    .trim();
        }
    );


$("destination")
    ?.addEventListener(
        "input",
        () => {

            currentTrip.destination =
                $("destination")
                    .value
                    .trim();
        }
    );


$("budget")
    ?.addEventListener(
        "input",
        () => {

            currentTrip.budget =
                parseBudget(
                    $("budget")
                        .value
                );
        }
    );


$("style")
    ?.addEventListener(
        "change",
        () => {

            currentTrip.style =
                $("style")
                    .value
                    .trim() ||
                "Balanced";
        }
    );


$("interests")
    ?.addEventListener(
        "input",
        () => {

            currentTrip.interests =
                $("interests")
                    .value
                    .trim();
        }
    );


$("prompt")
    ?.addEventListener(
        "input",
        () => {

            currentTrip.prompt =
                $("prompt")
                    .value
                    .trim();
        }
    );


$("travelDate")
    ?.addEventListener(
        "change",
        () => {

            currentTrip.travel_date =
                $("travelDate")
                    .value ||
                "";
        }
    );


$("travel_date")
    ?.addEventListener(
        "change",
        () => {

            currentTrip.travel_date =
                $("travel_date")
                    .value ||
                "";
        }
    );


$("nextDay")
    ?.addEventListener(
        "click",
        nextDay
    );


$("prevDay")
    ?.addEventListener(
        "click",
        previousDay
    );


/* ============================================================
   INITIALIZE
   ============================================================ */

function initialize() {

    updateThreadIdUI();

    resetAgents();

    bindTravelDateInput();

    updateTripSummary(
        currentTrip
    );

    updateAIScore(
        null
    );

    console.log(
        "GoTrip AI frontend initialized."
    );
}


/* ============================================================
   PUBLIC API
   ============================================================ */

window.GoTripAI = {

    generateTrip,

    getTripData,

    callTravelBackend,

    resetConversation,

    getThreadId,

    renderRoute,

    renderItinerary,

    renderAllBackendResults,

    nextDay,

    previousDay
};


initialize();
