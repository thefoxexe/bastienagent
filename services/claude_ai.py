import os
import json
from datetime import datetime
import pytz
import anthropic

_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


SYSTEM_PROMPT = """Tu es l'assistant personnel de Bastien Ryser, disponible via Telegram.
Tu parles principalement en français, tu es concis et direct.
Tu as accès à son Google Calendar, ses tâches et ses notes.

Quand l'utilisateur te parle, tu dois analyser son message et retourner un JSON structuré indiquant quelle action effectuer.

Format de réponse JSON OBLIGATOIRE :
{
  "action": "string",  // voir liste ci-dessous
  "params": {},        // paramètres spécifiques à l'action
  "reply": "string"    // message à afficher à l'utilisateur (confirmation, réponse, etc.)
}

Actions disponibles :
- "chat" : simple conversation, aucune action système (params: {})
- "calendar_read_today" : voir les événements d'aujourd'hui (params: {})
- "calendar_read_week" : voir les événements de la semaine (params: {})
- "calendar_read_days" : voir les événements sur N jours (params: {"days": int})
- "calendar_create" : créer un événement (params: {"title": str, "start_iso": str, "end_iso": str|null, "location": str, "description": str})
- "calendar_delete" : supprimer un événement (params: {"event_id": str})
- "task_add" : ajouter une tâche (params: {"title": str})
- "task_list" : lister les tâches (params: {})
- "task_done" : marquer une tâche comme faite (params: {"task_id": int})
- "task_delete" : supprimer une tâche (params: {"task_id": int})
- "note_add" : ajouter une note (params: {"content": str})
- "note_list" : lister les notes (params: {})
- "weather" : voir la météo (params: {"city": str|null})
- "briefing" : déclencher le briefing du matin maintenant (params: {})

Pour les dates/heures, utilise le format ISO 8601 avec timezone (ex: "2024-01-15T14:30:00+01:00").
La date et heure actuelle est : {current_datetime}
Fuseau horaire : Europe/Zurich.

IMPORTANT : retourne UNIQUEMENT le JSON, sans texte avant ou après, sans markdown."""


def parse_message(user_message: str, conversation_history: list = None) -> dict:
    tz = pytz.timezone("Europe/Zurich")
    now = datetime.now(tz).strftime("%Y-%m-%dT%H:%M:%S%z")
    system = SYSTEM_PROMPT.replace("{current_datetime}", now)

    messages = []
    if conversation_history:
        messages.extend(conversation_history[-6:])
    messages.append({"role": "user", "content": user_message})

    client = _get_client()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=system,
        messages=messages,
    )

    raw = response.content[0].text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"action": "chat", "params": {}, "reply": raw}


def generate_briefing_text(
    weather: str,
    events: list[dict],
    tasks: list[dict],
    timezone: str = "Europe/Zurich",
) -> str:
    tz = pytz.timezone(timezone)
    now = datetime.now(tz)
    day_fr = {
        "Monday": "Lundi",
        "Tuesday": "Mardi",
        "Wednesday": "Mercredi",
        "Thursday": "Jeudi",
        "Friday": "Vendredi",
        "Saturday": "Samedi",
        "Sunday": "Dimanche",
    }
    month_fr = {
        1: "janvier", 2: "février", 3: "mars", 4: "avril",
        5: "mai", 6: "juin", 7: "juillet", 8: "août",
        9: "septembre", 10: "octobre", 11: "novembre", 12: "décembre",
    }
    day_name = day_fr[now.strftime("%A")]
    date_str = f"{day_name} {now.day} {month_fr[now.month]} {now.year}"

    events_text = ""
    if events:
        for e in events:
            if e["all_day"]:
                time_str = "Toute la journée"
            else:
                try:
                    dt = datetime.fromisoformat(e["start"]).astimezone(tz)
                    time_str = dt.strftime("%H:%M")
                except Exception:
                    time_str = e["start"]
            loc = f" ({e['location']})" if e["location"] else ""
            events_text += f"  • {time_str} — {e['title']}{loc}\n"
    else:
        events_text = "  Aucun événement aujourd'hui.\n"

    tasks_text = ""
    if tasks:
        for t in tasks[:5]:
            tasks_text += f"  • {t['title']}\n"
        if len(tasks) > 5:
            tasks_text += f"  ... et {len(tasks) - 5} autres\n"
    else:
        tasks_text = "  Aucune tâche en cours. 🎉\n"

    greeting = _time_greeting(now.hour)

    return (
        f"🌅 *{greeting}, Bastien !*\n"
        f"📅 *{date_str}*\n\n"
        f"🌤 *Météo*\n{weather}\n\n"
        f"📆 *Agenda du jour*\n{events_text}\n"
        f"✅ *Tâches en cours*\n{tasks_text}"
    )


def _time_greeting(hour: int) -> str:
    if hour < 12:
        return "Bonjour"
    elif hour < 18:
        return "Bon après-midi"
    else:
        return "Bonsoir"
