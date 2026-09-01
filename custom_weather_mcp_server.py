from mcp.server.fastmcp import FastMCP
import requests
import os
from dotenv import load_dotenv

load_dotenv()

mcp = FastMCP("Weather MCP Server")

OPEN_WEATHER_API_KEY = os.getenv("OPEN_WEATHER_API_KEY")

if not OPEN_WEATHER_API_KEY:
    raise RuntimeError("OPEN_WEATHER_API_KEY is missing.")

@mcp.tool()
def get_current_weather(city: str):
    
    response = requests.get(
        "https://api.openweathermap.org/data/2.5/weather",
        params={
            "q": city,
            "appid": OPEN_WEATHER_API_KEY,
            "units": "metric"
        },
        timeout=15
    )
    
    data = response.json()
    
    if response.status_code != 200:
        return data
    
    return {
        "city": data["name"],
        "source": "current_weather",
        "temperature_c": data["main"]["temp"],
        "feels_like_c": data["main"]["feels_like"],
        "humidity": data["main"]["humidity"],
        "condition": data["weather"][0]["description"],
        "wind_speed": data["wind"]["speed"]
    }

# @mcp.tool()   
# def get_forecast(city: str):
    
#     url = (
#         "https://api.openweathermap.org/data/2.5/forecast"
#     )
    
#     params = {
#         "q": city,
#         "appid": OPEN_WEATHER_API_KEY,
#         "units": "metric"
#     }
    
#     response = requests.get(
#         url,
#         params=params
#     )
    
#     data = response.json()
    
#     forecast = []
    
    
#     # Return First 5 Forecast Entries
    
#     for item in data["list"][:5]:
        
#         forecast.append(
#             {
#                 "datetime": item["dt_txt"],
#                 "temperature": item["main"]["temp"],
#                 "weather": item["weather"][0]["description"]
#             }
#         )
        
#     return {
#         "city": city,
#         "forecast": forecast
#     }
    
    
    
    
@mcp.tool()
def get_forecast(city: str, days: int = 5):

    url = (
        "https://api.openweathermap.org/data/2.5/forecast"
    )

    params = {
        "q": city,
        "appid": OPEN_WEATHER_API_KEY,
        "units": "metric"
    }

    response = requests.get(
        url,
        params=params,
        timeout=15
    )

    data = response.json()

    if response.status_code != 200:
        return data

    forecast = []

    # OpenWeather's free forecast endpoint returns the
    # available 5-day window at 3-hour intervals. Return
    # the whole window so callers can match future trip
    # dates without accidentally truncating useful entries.
    forecast_items = data.get(
        "list",
        []
    )

    for item in forecast_items:

        forecast.append(
            {
                "datetime": item["dt_txt"],
                "temperature": item["main"]["temp"],
                "feels_like": item["main"]["feels_like"],
                "humidity": item["main"]["humidity"],
                "weather": item["weather"][0]["description"],
                "wind_speed": item["wind"]["speed"],
                "rain_probability": item.get("pop", 0)
            }
        )

    return {
        "city": data["city"]["name"],
        "country": data["city"]["country"],
        "requested_days": days,
        "source": "openweather_5_day_3_hour_forecast",
        "forecast_window_start": (
            forecast[0]["datetime"]
            if forecast
            else None
        ),
        "forecast_window_end": (
            forecast[-1]["datetime"]
            if forecast
            else None
        ),
        "forecast": forecast
    }    
    

    
if __name__ == "__main__":
    mcp.run()
