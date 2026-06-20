import os
import json
from datetime import datetime, timedelta
from typing import Optional
import pytz
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]
TOKEN_PATH = "google_token.json"


def _get_service():
    creds = None

    # Priorité 1 : variable d'environnement (pour Railway/Render)
    token_json_env = os.getenv("GOOGLE_TOKEN_JSON")
    if token_json_env:
        try:
            creds = Credentials.from_authorized_user_info(json.loads(token_json_env), SCOPES)
        except Exception:
            pass

    # Priorité 2 : fichier local (généré par OAuth callback)
    if creds is None:
        raise RuntimeError(
            "Google Calendar pas encore connecté. "
            "Envoie /connecter_calendar au bot."
        )

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Sauvegarder le token rafraîchi
            if not token_json_env:
                with open(TOKEN_PATH, "w") as f:
                    f.write(creds.to_json())
        else:
            raise RuntimeError("Token Google expiré. Relance gen_auth_url.py.")

    return build("calendar", "v3", credentials=creds)


def get_events_today(timezone: str = "Europe/Zurich") -> list[dict]:
    tz = pytz.timezone(timezone)
    now = datetime.now(tz)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return _get_events(start, end, timezone)


def get_events_for_period(days: int = 7, timezone: str = "Europe/Zurich") -> list[dict]:
    tz = pytz.timezone(timezone)
    now = datetime.now(tz)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=days)
    return _get_events(start, end, timezone)


def _get_events(start: datetime, end: datetime, timezone: str) -> list[dict]:
    try:
        service = _get_service()
        result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=start.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = []
        for item in result.get("items", []):
            start_raw = item["start"].get("dateTime", item["start"].get("date"))
            end_raw = item["end"].get("dateTime", item["end"].get("date"))
            events.append(
                {
                    "id": item["id"],
                    "title": item.get("summary", "(sans titre)"),
                    "start": start_raw,
                    "end": end_raw,
                    "location": item.get("location", ""),
                    "description": item.get("description", ""),
                    "all_day": "date" in item["start"],
                }
            )
        return events
    except Exception as e:
        raise RuntimeError(f"Erreur Google Calendar : {e}")


def create_event(
    title: str,
    start_dt: datetime,
    end_dt: Optional[datetime] = None,
    location: str = "",
    description: str = "",
    timezone: str = "Europe/Zurich",
) -> dict:
    if end_dt is None:
        end_dt = start_dt + timedelta(hours=1)

    service = _get_service()
    event = {
        "summary": title,
        "location": location,
        "description": description,
        "start": {
            "dateTime": start_dt.isoformat(),
            "timeZone": timezone,
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": timezone,
        },
    }
    created = service.events().insert(calendarId="primary", body=event).execute()
    return {"id": created["id"], "title": title, "start": start_dt.isoformat()}


def delete_event(event_id: str) -> bool:
    try:
        service = _get_service()
        service.events().delete(calendarId="primary", eventId=event_id).execute()
        return True
    except Exception:
        return False


def format_events_text(events: list[dict], timezone: str = "Europe/Zurich") -> str:
    if not events:
        return "Aucun événement."
    tz = pytz.timezone(timezone)
    lines = []
    for e in events:
        if e["all_day"]:
            time_str = "Toute la journée"
        else:
            try:
                dt = datetime.fromisoformat(e["start"]).astimezone(tz)
                time_str = dt.strftime("%H:%M")
            except Exception:
                time_str = e["start"]
        loc = f" 📍 {e['location']}" if e["location"] else ""
        lines.append(f"• {time_str} — {e['title']}{loc}")
    return "\n".join(lines)
