/* ============================================================
   GoTrip AI — Frontend v3
   Source + Destination + Dynamic Route
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
    prompt: ""
};

let currentRoute = [];
let currentResult = null;
let currentDay = 0;
let isGenerating = false;


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

    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => {
        toast.classList.remove("show");
    }, duration);
}


function getThreadId() {
    let id = localStorage.getItem("gotrip_thread_id");

    if (!id) {
        id =
            crypto?.randomUUID?.() ||
            `gotrip-${Date.now()}-${Math.random().toString(36).slice(2)}`;

        localStorage.setItem("gotrip_thread_id", id);
    }

    return id;
}


function updateThreadIdUI() {
    const element = $("threadIdDisplay");
    if (!element) return;

    element.textContent = getThreadId();
    element.title = getThreadId();
}


async function copyThreadId() {
    try {
        await navigator.clipboard.writeText(getThreadId());
        showToast("Thread ID copied.");
    } catch {
        showToast("Unable to copy Thread ID.");
    }
}


function resetConversation() {
    localStorage.removeItem("gotrip_thread_id");
    updateThreadIdUI();
    showToast("New conversation started.");
}


function parseBudget(value) {
    if (typeof value === "number") {
        return Number.isFinite(value) ? value : 0;
    }

    let text = String(value ?? "")
        .trim()
        .toLowerCase()
        .replace(/₹/g, "")
        .replace(/inr/g, "")
        .replace(/rs\.?/g, "")
        .replace(/,/g, "");

    if (!text) return 0;

    const lakh = text.match(/([\d.]+)\s*(lakh|lac|lacs|lakhs)\b/);
    if (lakh) return Number(lakh[1]) * 100000;

    const thousand = text.match(/([\d.]+)\s*(k|thousand)\b/);
    if (thousand) return Number(thousand[1]) * 1000;

    const million = text.match(/([\d.]+)\s*(m|million)\b/);
    if (million) return Number(million[1]) * 1000000;

    const numeric = Number(text.replace(/[^\d.]/g, ""));
    return Number.isFinite(numeric) ? numeric : 0;
}


function formatINR(value) {
    const number = Number(value);

    if (!Number.isFinite(number) || number <= 0) {
        return "Budget flexible";
    }

    return `₹${number.toLocaleString("en-IN", {
        maximumFractionDigits: 0
    })}`;
}


function getTripData() {
    const source = $("source")?.value.trim() || "";
    const destination = $("destination")?.value.trim() || "";

    const daysValue = Number($("days")?.value);
    const days =
        Number.isFinite(daysValue) && daysValue >= 1
            ? Math.floor(daysValue)
            : 1;

    const budget = parseBudget($("budget")?.value);

    const style = $("style")?.value?.trim() || "Balanced";
    const interests = $("interests")?.value?.trim() || "";
    const prompt = $("prompt")?.value?.trim() || "";

    currentTrip = {
        source,
        destination,
        days,
        budget,
        currency: "INR",
        style,
        interests,
        prompt
    };

    return currentTrip;
}


function buildUserPrompt(trip) {
    if (trip.prompt) {
        return trip.prompt;
    }

    return `
Plan a ${trip.days}-day trip from ${trip.source} to ${trip.destination}.

Budget: ₹${trip.budget.toLocaleString("en-IN")}
Travel style: ${trip.style}
Interests: ${trip.interests || "General travel"}

Create a practical travel plan with transportation, accommodation,
activities, food experiences, route and estimated budget.
`.trim();
}


function buildPayload(trip) {
    return {
        source: trip.source,
        destination: trip.destination,
        days: trip.days,
        budget: trip.budget,
        currency: trip.currency,
        style: trip.style,
        interests: trip.interests,
        prompt: buildUserPrompt(trip),
        thread_id: getThreadId()
    };
}


function validateTrip(trip) {
    if (!trip.source) {
        throw new Error("Please enter the starting location.");
    }

    if (!trip.destination) {
        throw new Error("Please enter the destination.");
    }

    if (
        trip.source.trim().toLowerCase() ===
        trip.destination.trim().toLowerCase()
    ) {
        throw new Error("Starting location and destination must be different.");
    }

    if (!trip.budget || trip.budget <= 0) {
        throw new Error("Please enter a valid budget.");
    }
}


async function callTravelBackend(trip) {
    validateTrip(trip);

    const payload = buildPayload(trip);

    console.log("GoTrip API request:", payload);

    const response = await fetch("/api/travel", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "Accept": "application/json"
        },
        body: JSON.stringify(payload)
    });

    let data;

    try {
        data = await response.json();
    } catch {
        throw new Error("Server returned an invalid JSON response.");
    }

    console.log("GoTrip API response:", data);

    if (!response.ok || data.success === false) {
        throw new Error(
            data.error ||
            `Request failed with status ${response.status}.`
        );
    }

    return data;
}


function updateTripSummary(trip) {
    const title = $("tripTitle");
    const meta = $("tripMeta");

    if (title) {
        title.textContent =
            trip.destination
                ? `${trip.destination} Explorer`
                : "Your Journey";
    }

    if (meta) {
        meta.textContent =
            `${trip.source} → ${trip.destination} · ${trip.days} days · ${trip.style} · ${formatINR(trip.budget)}`;
    }
}


function updateAIScore(score) {
    const element = $("score");
    if (!element) return;

    const number = Number(score);

    element.textContent =
        Number.isFinite(number)
            ? Math.round(number)
            : "—";
}


function setAgentState(agent, state) {
    const row =
        document.querySelector(`[data-agent="${agent}"]`);

    if (!row) return;

    row.classList.remove("working", "done");

    if (state === "Working") {
        row.classList.add("working");
    }

    if (state === "Done") {
        row.classList.add("done");
    }

    const label = row.querySelector(".agent-state");
    if (label) label.textContent = state;
}


function resetAgents() {
    ["flight", "hotel", "itinerary", "final"]
        .forEach(agent => setAgentState(agent, "Ready"));
}


async function animateAgents() {
    const agents = ["flight", "hotel", "itinerary", "final"];

    resetAgents();

    for (const agent of agents) {
        setAgentState(agent, "Working");
        await new Promise(resolve => setTimeout(resolve, 220));
        setAgentState(agent, "Done");
    }
}


function renderRoute(route) {
    currentRoute = Array.isArray(route)
        ? route
            .map(item => {
                if (typeof item === "string") {
                    return { name: item, type: "stop" };
                }

                return {
                    name: String(item?.name || "").trim(),
                    type: item?.type || "stop"
                };
            })
            .filter(item => item.name)
        : [];

    const map = $("routeMap");
    const points = $("routePoints");
    const svg = $("routeSvg");
    const bottom = $("routeBottom");
    const empty = $("routeEmpty");

    if (!map || !points || !bottom) return;

    points.innerHTML = "";
    bottom.innerHTML = "";

    if (svg) {
        svg.innerHTML = "";
    }

    if (!currentRoute.length) {
        if (empty) empty.hidden = false;
        bottom.innerHTML = "<span>No route returned.</span>";
        return;
    }

    if (empty) empty.hidden = true;

    const width = 700;
    const height = 300;
    const left = 55;
    const right = 55;
    const usableWidth = width - left - right;

    const positions = currentRoute.map((_, index) => {
        const x =
            currentRoute.length === 1
                ? width / 2
                : left + usableWidth * index / (currentRoute.length - 1);

        const y =
            height * 0.58 -
            Math.sin(index * 1.35) * 48;

        return { x, y };
    });

    positions.forEach((position, index) => {
        const stop = currentRoute[index];

        const point = document.createElement("div");
        point.className = "map-point dynamic-point";

        point.style.left =
            `${(position.x / width) * 100}%`;

        point.style.top =
            `${(position.y / height) * 100}%`;

        point.innerHTML = `
            <i></i>
            <span>${escapeHtml(stop.name)}</span>
        `;

        points.appendChild(point);
    });

    if (svg && positions.length > 1) {
        let path = `M ${positions[0].x} ${positions[0].y}`;

        for (let i = 1; i < positions.length; i++) {
            const previous = positions[i - 1];
            const current = positions[i];
            const midpoint = (previous.x + current.x) / 2;

            path +=
                ` C ${midpoint} ${previous.y - 35}, ` +
                `${midpoint} ${current.y - 35}, ` +
                `${current.x} ${current.y}`;
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

    currentRoute.forEach((stop, index) => {
        const label = document.createElement("span");
        label.textContent =
            index === 0
                ? `● ${stop.name}`
                : `→ ${stop.name}`;

        bottom.appendChild(label);
    });
}


function renderBudget(data) {
    const request = data.request || currentTrip;

    const estimated = $("estimatedBudget");
    const status = $("budgetStatus");
    const flight = $("flightBudget");
    const hotel = $("hotelBudget");
    const activities = $("activityBudget");

    if (estimated) {
        estimated.textContent = formatINR(request.budget);
    }

    // No fake numeric breakdown is displayed.
    // The backend/LLM response is the source of truth.
    if (flight) flight.textContent = "See itinerary";
    if (hotel) hotel.textContent = "See itinerary";
    if (activities) activities.textContent = "See itinerary";

    if (status) {
        status.textContent = "Trip budget";
    }

    [
        ["flightBudgetBar", 34],
        ["hotelBudgetBar", 33],
        ["activityBudgetBar", 33]
    ].forEach(([id, width]) => {
        const bar = $(id);
        if (bar) bar.style.width = `${width}%`;
    });
}


function formatAIResponse(text) {
    if (!text) {
        return "<p>No response was returned.</p>";
    }

    let html = escapeHtml(text);

    html = html.replace(
        /```([\s\S]*?)```/g,
        "<pre>$1</pre>"
    );

    html = html.replace(
        /^### (.*?)$/gm,
        "<h4>$1</h4>"
    );

    html = html.replace(
        /^## (.*?)$/gm,
        "<h3>$1</h3>"
    );

    html = html.replace(
        /^# (.*?)$/gm,
        "<h2>$1</h2>"
    );

    html = html.replace(
        /\*\*(.*?)\*\*/g,
        "<strong>$1</strong>"
    );

    html = html.replace(
        /^[-•]\s+(.*?)$/gm,
        "<li>$1</li>"
    );

    html = html.replace(
        /^\d+\.\s+(.*?)$/gm,
        "<li>$1</li>"
    );

    html = html.replace(/\n{2,}/g, "</p><p>");
    html = html.replace(/\n/g, "<br>");

    return `<div class="ai-text"><p>${html}</p></div>`;
}


function extractDaySections(text) {
    const source = String(text || "");

    const matches = [
        ...source.matchAll(
            /(?:^|\n)\s*(?:#{1,4}\s*)?(?:Day|DAY)\s+(\d{1,2})(?:\s*[:\-–]\s*)?(.*?)(?=(?:\n\s*(?:#{1,4}\s*)?(?:Day|DAY)\s+\d{1,2}\b)|$)/gs
        )
    ];

    return matches.map(match => ({
        day: Number(match[1]),
        title: match[2].trim(),
        content: match[0].replace(
            /^\s*(?:#{1,4}\s*)?(?:Day|DAY)\s+\d{1,2}(?:\s*[:\-–]\s*)?/i,
            ""
        ).trim()
    }));
}


function renderItinerary(data) {
    const content = $("dayContent");
    const tabs = $("dayTabs");

    if (!content || !tabs) return;

    const itinerary = data.itinerary || data.answer || "";
    const sections = extractDaySections(itinerary);

    tabs.innerHTML = "";

    const totalDays = Math.max(
        1,
        Number(data.request?.days || currentTrip.days || 1)
    );

    const days = [];

    for (let day = 1; day <= totalDays; day++) {
        const found = sections.find(item => item.day === day);

        days.push(
            found || {
                day,
                title: "AI-planned day",
                content: itinerary
            }
        );
    }

    days.forEach((item, index) => {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent =
            `Day ${String(item.day).padStart(2, "0")}`;

        if (index === currentDay) {
            button.classList.add("selected");
        }

        button.addEventListener("click", () => {
            currentDay = index;

            document
                .querySelectorAll("#dayTabs button")
                .forEach(tab => tab.classList.remove("selected"));

            button.classList.add("selected");
            renderSelectedDay(days);
        });

        tabs.appendChild(button);
    });

    renderSelectedDay(days);

    function renderSelectedDay(allDays) {
        const item = allDays[currentDay] || allDays[0];

        content.innerHTML = `
            <div class="day-title">
                <span>${String(item.day).padStart(2, "0")}</span>
                <div>
                    <h3>${escapeHtml(item.title || "Travel day")}</h3>
                    <small>
                        ${escapeHtml(currentTrip.source)}
                        →
                        ${escapeHtml(currentTrip.destination)}
                    </small>
                </div>
            </div>

            <div class="ai-response">
                ${formatAIResponse(item.content)}
            </div>
        `;
    }
}


function displayTravelResult(data) {
    currentResult = data;

    if (data.request) {
        currentTrip = {
            ...currentTrip,
            ...data.request
        };
    }

    updateTripSummary(currentTrip);
    updateAIScore(data.score);
    renderRoute(data.route || []);
    renderBudget(data);
    renderItinerary(data);
}


async function generateTrip() {
    if (isGenerating) return;

    const trip = getTripData();

    try {
        validateTrip(trip);
    } catch (error) {
        showToast(error.message);
        return;
    }

    isGenerating = true;

    const button = $("generateBtn");
    const label = $("generateLabel");

    if (button) button.disabled = true;
    if (label) label.textContent = "Planning...";

    document.body.classList.add("generating");

    updateTripSummary(trip);
    resetAgents();

    try {
        const animation = animateAgents();
        const response = await callTravelBackend(trip);

        await animation;

        displayTravelResult(response);

        showToast("Trip generated successfully.");
        $("itinerary")?.scrollIntoView({
            behavior: "smooth",
            block: "start"
        });
    } catch (error) {
        console.error(error);
        resetAgents();
        showToast(error.message || "Unable to generate the trip.");
    } finally {
        isGenerating = false;
        document.body.classList.remove("generating");

        if (button) button.disabled = false;
        if (label) label.textContent = "Build my trip";
    }
}


function applyQuickPrompt(button) {
    const prompt = button.dataset.prompt || "";
    const destination = button.dataset.destination || "";
    const days = button.dataset.days || "";

    if ($("prompt")) $("prompt").value = prompt;
    if ($("destination") && destination) $("destination").value = destination;
    if ($("days") && days) $("days").value = days;

    showToast("Trip idea loaded. Set your source and budget, then build.");
}


async function regenerateTrip() {
    if (!currentTrip.source || !currentTrip.destination) {
        showToast("Generate a trip first.");
        return;
    }

    const prompt =
        `${buildUserPrompt(currentTrip)}

Generate a different route and alternative recommendations while preserving:
source, destination, duration, budget and travel style.`;

    const trip = {
        ...currentTrip,
        prompt
    };

    const button = $("regenerate");

    if (button) {
        button.disabled = true;
        button.textContent = "Generating...";
    }

    try {
        const response = await callTravelBackend(trip);
        displayTravelResult(response);
        showToast("Alternative itinerary generated.");
    } catch (error) {
        console.error(error);
        showToast(error.message || "Unable to regenerate.");
    } finally {
        if (button) {
            button.disabled = false;
            button.textContent = "↻ Regenerate";
        }
    }
}


async function sendChatMessage() {
    const input = $("chatInput");
    const messages = $("messages");

    if (!input || !messages) return;

    const message = input.value.trim();

    if (!message) return;

    if (!currentTrip.source || !currentTrip.destination) {
        showToast("Generate a trip before using the AI chat.");
        return;
    }

    messages.insertAdjacentHTML(
        "beforeend",
        `<div class="user-msg">${escapeHtml(message)}</div>`
    );

    input.value = "";

    const typingId = `typing-${Date.now()}`;

    messages.insertAdjacentHTML(
        "beforeend",
        `<div class="bot-msg" id="${typingId}">GoTrip AI is thinking...</div>`
    );

    try {
        const response = await fetch("/api/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                message,
                source: currentTrip.source,
                destination: currentTrip.destination,
                days: currentTrip.days,
                budget: currentTrip.budget,
                currency: currentTrip.currency,
                style: currentTrip.style,
                interests: currentTrip.interests,
                thread_id: getThreadId()
            })
        });

        const data = await response.json();

        if (!response.ok || data.success === false) {
            throw new Error(data.error || "Chat request failed.");
        }

        const typing = $(typingId);

        if (typing) {
            typing.innerHTML =
                formatAIResponse(data.answer);
        }

        if (data.route) {
            renderRoute(data.route);
        }
    } catch (error) {
        console.error(error);

        const typing = $(typingId);
        if (typing) {
            typing.textContent =
                error.message || "Unable to process message.";
        }
    }

    messages.scrollTop = messages.scrollHeight;
}


// ============================================================
// EVENT BINDINGS
// ============================================================

$("generateBtn")?.addEventListener("click", generateTrip);
$("copyThreadId")?.addEventListener("click", copyThreadId);
$("regenerate")?.addEventListener("click", regenerateTrip);

document
    .querySelectorAll(".quick-chips button")
    .forEach(button => {
        button.addEventListener(
            "click",
            () => applyQuickPrompt(button)
        );
    });


$("chatToggle")?.addEventListener("click", () => {
    $("aiChat")?.classList.add("open");
});


$("closeChat")?.addEventListener("click", () => {
    $("aiChat")?.classList.remove("open");
});


$("sendChat")?.addEventListener("click", sendChatMessage);


$("chatInput")?.addEventListener("keydown", event => {
    if (event.key === "Enter") {
        event.preventDefault();
        sendChatMessage();
    }
});


$("mapMode")?.addEventListener("click", () => {
    if (!currentRoute.length) {
        showToast("Generate a trip to see the route.");
        return;
    }

    showToast(
        `${currentRoute.length} route stops · ${currentRoute.map(item => item.name).join(" → ")}`
    );
});


$("days")?.addEventListener("input", () => {
    const value = Math.max(
        1,
        Math.floor(Number($("days").value || 1))
    );

    currentTrip.days = value;
});


$("source")?.addEventListener("input", () => {
    currentTrip.source = $("source").value.trim();
});


$("destination")?.addEventListener("input", () => {
    currentTrip.destination = $("destination").value.trim();
});


$("budget")?.addEventListener("input", () => {
    currentTrip.budget = parseBudget($("budget").value);
});


function initialize() {
    updateThreadIdUI();
    resetAgents();

    // No destination, source, budget or route is hardcoded.
    updateTripSummary(currentTrip);
    updateAIScore(null);

    console.log("GoTrip AI v3 initialized.");
}


window.GoTripAI = {
    generateTrip,
    getTripData,
    callTravelBackend,
    resetConversation,
    getThreadId
};

initialize();