import os
import requests
from dotenv import load_dotenv

load_dotenv()

key = os.getenv("OPEN_WEATHER_API_KEY")

print("Key loaded:", bool(key))
print("Key length:", len(key) if key else 0)

response = requests.get(
    "https://api.openweathermap.org/data/2.5/weather",
    params={
        "q": "Paris",
        "appid": key,
        "units": "metric"
    },
    timeout=15
)

print("Status:", response.status_code)
print("Response:", response.json())