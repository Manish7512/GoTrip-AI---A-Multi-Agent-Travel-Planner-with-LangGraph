from datetime import datetime, timedelta
import os
from typing import Any

import airportsdata
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
import requests


load_dotenv()

mcp = FastMCP("Serp Flight MCP Server")

SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")

if not SERPAPI_API_KEY:
    raise RuntimeError("SERPAPI_API_KEY is missing.")


def find_airport(
    airports: Any,
    location: str
):
    location_key = (
        location.casefold().strip()
    )

    if isinstance(
        airports,
        dict
    ):
        if "data" in airports:
            airports = airports["data"]
        elif "airports" in airports:
            airports = airports["airports"]

    if not isinstance(
        airports,
        list
    ):
        return None

    for airport in airports:
        if not isinstance(airport, dict):
            continue

        name = str(
            airport.get("airport_name", "")
        ).casefold().strip()

        city = str(
            airport.get("city_name", "")
        ).casefold().strip()

        city_code = str(
            airport.get("city_iata_code", "")
        ).casefold().strip()

        iata = str(
            airport.get("iata_code", "")
        ).casefold().strip()

        if location_key in {
            name,
            city,
            city_code,
            iata,
        }:
            return airport

    for airport in airports:
        if not isinstance(airport, dict):
            continue

        name = str(
            airport.get("airport_name", "")
        ).casefold()

        city = str(
            airport.get("city_name", "")
        ).casefold()

        if (
            location_key in name
            or location_key in city
        ):
            return airport

    return None


def resolve_airport(
    airports: Any,
    location: str
) -> dict | None:
    """Resolve an exact city/IATA/airport name."""

    city_aliases = {
        "delhi": "new delhi",
        "bombay": "mumbai",
        "calcutta": "kolkata",
        "madras": "chennai",
        "bangalore": "bengaluru",
    }

    record = find_airport(
        airports,
        location
    )

    if record:
        return {
            "iata_code": record.get("iata_code"),
            "airport_name": record.get("airport_name", ""),
            "city_name": record.get("city_name", ""),
        }

    key = str(
        location or ""
    ).strip().casefold()

    key = city_aliases.get(
        key,
        key
    )

    if not key:
        return None

    try:
        local_airports = airportsdata.load("IATA")
    except Exception:
        return None

    if (
        len(key) == 3
        and key.upper() in local_airports
    ):
        airport = local_airports[key.upper()]

        return {
            "iata_code": airport.get("iata"),
            "airport_name": airport.get("name", ""),
            "city_name": airport.get("city", ""),
        }

    city_matches = []

    for code, airport in local_airports.items():
        city = str(
            airport.get("city", "")
        ).casefold().strip()

        name = str(
            airport.get("name", "")
        ).casefold().strip()

        if key == name:
            return {
                "iata_code": code,
                "airport_name": airport.get("name", ""),
                "city_name": airport.get("city", ""),
            }

        if key == city:
            city_matches.append(
                (
                    code,
                    airport
                )
            )

    if city_matches:
        preferred_codes = (
            "DXB",
            "DEL",
            "BOM",
            "BLR",
            "HYD",
            "MAA",
            "CCU",
            "COK",
            "JFK",
            "LAX",
            "LHR",
            "CDG",
            "NRT",
            "SYD",
        )

        for preferred_code in preferred_codes:
            for code, airport in city_matches:
                if code == preferred_code:
                    return {
                        "iata_code": code,
                        "airport_name": airport.get("name", ""),
                        "city_name": airport.get("city", ""),
                    }

        code, airport = city_matches[0]

        return {
            "iata_code": code,
            "airport_name": airport.get("name", ""),
            "city_name": airport.get("city", ""),
        }

    return None


def search_flights_serpapi(
    source_iata: str,
    destination_iata: str,
    travel_date: str,
    return_date: str | None = None,
    currency: str = "INR",
    flight_type: int = 1,
    departure_token: str | None = None,
):
    """
    Search Google Flights through SerpApi.

    flight_type:
        1 = round trip
        2 = one way
    """

    params = {
        "engine": "google_flights",
        "api_key": SERPAPI_API_KEY,
        "departure_id": source_iata,
        "arrival_id": destination_iata,
        "travel_class": "1",
        "type": str(flight_type),
        "currency": currency,
        "hl": "en",
        "gl": "in",
    }

    if departure_token:
        params["departure_token"] = departure_token
    else:
        params["outbound_date"] = travel_date

        if flight_type == 1:
            if not return_date:
                raise ValueError(
                    "return_date is required for a round-trip search."
                )

            params["return_date"] = return_date

    response = requests.get(
        "https://serpapi.com/search.json",
        params=params,
        timeout=30,
    )

    results = response.json()

    if response.status_code != 200:
        raise RuntimeError(
            str(results)
        )

    if results.get("error"):
        raise RuntimeError(
            str(results["error"])
        )

    return results


@mcp.tool()
def search_google_flights(
    source_iata: str,
    destination_iata: str,
    travel_date: str,
    return_date: str | None = None,
    currency: str = "INR",
    flight_type: int = 1,
    departure_token: str | None = None,
):
    """
    Low-level SerpApi Google Flights search.
    """

    return search_flights_serpapi(
        source_iata=source_iata,
        destination_iata=destination_iata,
        travel_date=travel_date,
        return_date=return_date,
        currency=currency,
        flight_type=flight_type,
        departure_token=departure_token,
    )


def first_verified_price(
    options: list
) -> float | None:

    for option in options:

        if not isinstance(
            option,
            dict
        ):

            continue

        raw = option.get(
            "price"
        )

        if isinstance(
            raw,
            (int, float)
        ) and raw >= 0:

            return float(raw)

        if isinstance(
            raw,
            str
        ):

            cleaned = (
                raw
                .replace(",", "")
                .replace("₹", "")
                .replace("$", "")
                .strip()
            )

            try:
                value = float(
                    cleaned
                )
            except ValueError:
                continue

            if value >= 0:
                return value

    return None


@mcp.tool()
def search_trip_flights(
    source: str,
    destination: str,
    travel_date: str,
    days: int,
    currency: str = "INR",
):
    """
    Retrieve outbound and return flight data for a trip.

    Preserves the round-trip departure_token flow and independent one-way
    fallbacks used by the GoTrip flight agent.
    """

    try:
        departure_date = datetime.strptime(
            travel_date,
            "%Y-%m-%d"
        ).date()
    except ValueError as exc:
        raise ValueError(
            "Flight travel date must be YYYY-MM-DD."
        ) from exc

    return_date = (
        departure_date
        + timedelta(days=max(int(days) - 1, 1))
    ).isoformat()

    source_airport = resolve_airport(None, source)
    destination_airport = resolve_airport(None, destination)

    if not source_airport:
        raise ValueError(
            f"Could not identify an airport for {source}."
        )

    if not destination_airport:
        raise ValueError(
            f"Could not identify an airport for {destination}."
        )

    source_iata = source_airport.get("iata_code")
    destination_iata = destination_airport.get("iata_code")

    if not source_iata:
        raise ValueError(
            f"No IATA code found for {source}."
        )

    if not destination_iata:
        raise ValueError(
            f"No IATA code found for {destination}."
        )

    round_trip_error = None

    try:
        initial = search_flights_serpapi(
            source_iata=source_iata,
            destination_iata=destination_iata,
            travel_date=travel_date,
            return_date=return_date,
            currency=currency,
            flight_type=1,
        )
    except Exception as exc:
        initial = {}
        round_trip_error = str(exc)

    outbound_best = (
        initial.get("best_flights", [])
        if isinstance(initial, dict)
        else []
    )

    outbound_other = (
        initial.get("other_flights", [])
        if isinstance(initial, dict)
        else []
    )

    if not outbound_best and not outbound_other:
        try:
            outbound_one_way = search_flights_serpapi(
                source_iata=source_iata,
                destination_iata=destination_iata,
                travel_date=travel_date,
                currency=currency,
                flight_type=2,
            )

            outbound_best = outbound_one_way.get(
                "best_flights",
                []
            )

            outbound_other = outbound_one_way.get(
                "other_flights",
                []
            )

        except Exception:
            pass

    return_best = []
    return_other = []
    return_error = None
    return_price_type = None

    outbound_candidates = (
        outbound_best + outbound_other
    )

    selected_outbound = (
        outbound_candidates[0]
        if outbound_candidates
        else None
    )

    departure_token = (
        selected_outbound.get("departure_token")
        if isinstance(selected_outbound, dict)
        else None
    )

    if departure_token:
        try:
            returning = search_flights_serpapi(
                source_iata=source_iata,
                destination_iata=destination_iata,
                travel_date=travel_date,
                return_date=return_date,
                currency=currency,
                flight_type=1,
                departure_token=departure_token,
            )

            return_best = returning.get(
                "best_flights",
                []
            )

            return_other = returning.get(
                "other_flights",
                []
            )

            if return_best or return_other:
                return_price_type = (
                    "round_trip_total"
                )

        except Exception as exc:
            return_error = str(exc)

    if not return_best and not return_other:
        try:
            return_one_way = search_flights_serpapi(
                source_iata=destination_iata,
                destination_iata=source_iata,
                travel_date=return_date,
                currency=currency,
                flight_type=2,
            )

            return_best = return_one_way.get(
                "best_flights",
                []
            )

            return_other = return_one_way.get(
                "other_flights",
                []
            )

            if return_best or return_other:
                return_price_type = (
                    "one_way"
                )

        except Exception as exc:
            if return_error:
                return_error += (
                    f"; one-way fallback: {exc}"
                )
            else:
                return_error = str(exc)

    outbound = {
        "status": (
            "success"
            if outbound_best or outbound_other
            else "unavailable"
        ),
        "route": {
            "source": source,
            "source_iata": source_iata,
            "destination": destination,
            "destination_iata": destination_iata,
        },
        "date": travel_date,
        "best_flights": outbound_best[:5],
        "other_flights": outbound_other[:5],
    }

    returning = {
        "status": (
            "success"
            if return_best or return_other
            else "unavailable"
        ),
        "route": {
            "source": destination,
            "source_iata": destination_iata,
            "destination": source,
            "destination_iata": source_iata,
        },
        "date": return_date,
        "price_type": return_price_type,
        "best_flights": return_best[:5],
        "other_flights": return_other[:5],
    }

    total_count = (
        len(outbound_best)
        + len(outbound_other)
        + len(return_best)
        + len(return_other)
    )

    outbound_price = first_verified_price(
        outbound_best + outbound_other
    )

    return_price = first_verified_price(
        return_best + return_other
    )

    total_verified_price = None

    if (
        return_price is not None
        and return_price_type == "round_trip_total"
    ):

        total_verified_price = return_price

    elif (
        outbound_price is not None
        and return_price is not None
        and return_price_type == "one_way"
    ):

        total_verified_price = (
            outbound_price
            + return_price
        )

    flight_result = {
        "status": (
            "success"
            if total_count > 0
            else "unavailable"
        ),
        "route": {
            "source": source,
            "source_iata": source_iata,
            "destination": destination,
            "destination_iata": destination_iata,
        },
        "outbound_date": travel_date,
        "return_date": return_date,
        "outbound": outbound,
        "return": returning,
        "total_verified_price": total_verified_price,
        "result_count": total_count,
    }

    if not total_count:
        reasons = [
            item for item in [
                round_trip_error,
                return_error,
            ] if item
        ]

        flight_result["reason"] = (
            "No verified outbound or return flight options were returned."
        )

        if reasons:
            flight_result["diagnostics"] = reasons

    return flight_result


if __name__ == "__main__":
    mcp.run()
