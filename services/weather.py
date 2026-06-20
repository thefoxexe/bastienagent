import os
import asyncio
import aiohttp

OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"


async def _fetch_city(session: aiohttp.ClientSession, city_query: str, api_key: str) -> str:
    try:
        params = {"q": city_query, "appid": api_key, "units": "metric", "lang": "fr"}
        async with session.get(OPENWEATHER_URL, params=params) as resp:
            if resp.status != 200:
                return f"⚠️ {city_query} : erreur {resp.status}"
            data = await resp.json()
        # Nom affiché = retour API (plus fiable que notre query)
        name = data.get("name", city_query.split(",")[0])
        desc = data["weather"][0]["description"].capitalize()
        temp = round(data["main"]["temp"])
        feels = round(data["main"]["feels_like"])
        icon = _weather_icon(data["weather"][0]["main"])
        return f"{icon} *{name}* : {temp}°C _(ressenti {feels}°C)_ — {desc}"
    except Exception as e:
        return f"⚠️ {city_query} : {e}"


async def get_weather(city: str = None) -> str:
    api_key = os.getenv("OPENWEATHER_API_KEY", "")
    if not api_key:
        return "⚠️ Clé API météo manquante"

    async with aiohttp.ClientSession() as session:
        if city:
            # Ville spécifique demandée par l'utilisateur
            return await _fetch_city(session, city, api_key)

        # Par défaut : Sion et Genève (code pays ,CH pour éviter ambiguïté USA)
        # Séparateur | pour ne pas confondre avec la virgule du code pays
        raw = os.getenv("WEATHER_CITIES", "Sion,CH|Geneva,CH")
        cities = [c.strip() for c in raw.split("|") if c.strip()]
        results = await asyncio.gather(*[_fetch_city(session, c, api_key) for c in cities])
        return "\n".join(results)


def _weather_icon(condition: str) -> str:
    return {
        "Clear": "☀️",
        "Clouds": "☁️",
        "Rain": "🌧️",
        "Drizzle": "🌦️",
        "Thunderstorm": "⛈️",
        "Snow": "❄️",
        "Mist": "🌫️",
        "Fog": "🌫️",
        "Haze": "🌫️",
    }.get(condition, "🌡️")
