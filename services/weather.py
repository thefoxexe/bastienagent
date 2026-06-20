import os
import aiohttp

OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"


async def get_weather(city: str = None) -> str:
    api_key = os.getenv("OPENWEATHER_API_KEY", "")
    city = city or os.getenv("CITY", "Geneva")

    if not api_key:
        return "⚠️ Météo indisponible (clé API manquante)"

    try:
        async with aiohttp.ClientSession() as session:
            params = {"q": city, "appid": api_key, "units": "metric", "lang": "fr"}
            async with session.get(OPENWEATHER_URL, params=params) as resp:
                if resp.status != 200:
                    return f"⚠️ Météo indisponible (erreur {resp.status})"
                data = await resp.json()

        desc = data["weather"][0]["description"].capitalize()
        temp = round(data["main"]["temp"])
        feels = round(data["main"]["feels_like"])
        humidity = data["main"]["humidity"]
        icon = _weather_icon(data["weather"][0]["main"])

        return (
            f"{icon} {desc}, {temp}°C (ressenti {feels}°C), "
            f"humidité {humidity}% — {city}"
        )
    except Exception as e:
        return f"⚠️ Météo indisponible ({e})"


def _weather_icon(condition: str) -> str:
    icons = {
        "Clear": "☀️",
        "Clouds": "☁️",
        "Rain": "🌧️",
        "Drizzle": "🌦️",
        "Thunderstorm": "⛈️",
        "Snow": "❄️",
        "Mist": "🌫️",
        "Fog": "🌫️",
    }
    return icons.get(condition, "🌡️")
