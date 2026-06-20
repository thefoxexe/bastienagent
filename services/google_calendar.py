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

    token_json_env = os.getenv("GOOGLE_TOKEN_JSON")
    if token_json_env:
        try:
            creds = Credentials.from_authorized_user_info(json.loads(token_json_env), SCOPES)
        except Exception:
            pass

    if creds is None and os.path.exists(TOKEN_PATH):
        try:
            with open(TOKEN_PATH) as f:
                data = json.load(f)
            if "refresh_token" in data and "client_id" in data:
                creds = Credentials(
                    token=data.get("token"),
                    refresh_token=data["refresh_token"],
                    token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
                    client_id=data["client_id"],
                    client_secret=data["client_secret"],
                    scopes=data.get("scopes", SCOPES),
                )
            else:
                creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        except Exception:
            pass

    if creds is None:
        raise RuntimeError("Google Calendar pas encore connecté. Envoie /connecter_calendar au bot.")

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            if not token_json_env and os.path.exists(TOKEN_PATH):
                with open(TOKEN_PATH, "w") as f:
                    f.write(creds.to_json())
        else:
            raise RuntimeError("Token Google expiré. Envoie /connecter_calendar pour te reconnecter.")

    return build("calendar", "v3", credentials=creds)


def _get_all_calendar_ids(service) -> list[str]:
    """Retourne tous les IDs de calendriers actifs de l'utilisateur."""
    try:
        result = service.calendarList().list().execute()
        return [
            cal["id"]
            for cal in result.get("items", [])
            if not cal.get("deleted") and cal.get("selected", True)
        ]
    except Exception:
        return ["primary"]


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
        calendar_ids = _get_all_calendar_ids(service)

        all_events = []
        seen_ids = set()

        for cal_id in calendar_ids:
            try:
                result = (
                    service.events()
                    .list(
                        calendarId=cal_id,
                        timeMin=start.isoformat(),
                        timeMax=end.isoformat(),
                        singleEvents=True,
                        orderBy="startTime",
                    )
                    .execute()
                )
                for item in result.get("items", []):
                    if item["id"] in seen_ids:
                        continue
                    seen_ids.add(item["id"])
                    start_raw = item["start"].get("dateTime", item["start"].get("date"))
                    end_raw = item["end"].get("dateTime", item["end"].get("date"))
                    all_events.append({
                        "id": item["id"],
                        "title": item.get("summary", "(sans titre)"),
                        "start": start_raw,
                        "end": end_raw,
                        "location": item.get("location", ""),
                        "description": item.get("description", ""),
                        "all_day": "date" in item["start"],
                    })
            except Exception:
                continue

        # Trier par heure de début
        tz_obj = pytz.timezone(timezone)
        def sort_key(e):
            try:
                return datetime.fromisoformat(e["start"]).astimezone(tz_obj)
            except Exception:
                return datetime.min.replace(tzinfo=pytz.utc)

        all_events.sort(key=sort_key)
        return all_events

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
        "start": {"dateTime": start_dt.isoformat(), "timeZone": timezone},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": timezone},
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
