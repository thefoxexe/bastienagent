import os
import json
from datetime import datetime
from typing import Optional
import pytz
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]
TOKEN_PATH = "google_token.json"


def _persist_refreshed_token(creds) -> None:
    try:
        token_data = json.loads(creds.to_json())
        os.environ["GOOGLE_TOKEN_JSON"] = json.dumps(token_data)
        with open(TOKEN_PATH, "w") as f:
            json.dump(token_data, f)
    except Exception:
        pass


_NOTES_LIST_TITLE = "Notes Bastien"
_notes_list_id: Optional[str] = None

# Cache position → task ID for the last list call
_task_cache: list[str] = []
_note_cache: list[str] = []


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
        raise RuntimeError("Google pas encore connecté. Envoie /connecter_calendar")

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                raise RuntimeError("Token Google révoqué. Envoie /connecter_calendar pour te reconnecter.")
            _persist_refreshed_token(creds)
        else:
            raise RuntimeError("Token Google expiré. Envoie /connecter_calendar")

    return build("tasks", "v1", credentials=creds)


def _get_notes_list_id(service) -> str:
    global _notes_list_id
    if _notes_list_id:
        return _notes_list_id

    result = service.tasklists().list().execute()
    for lst in result.get("items", []):
        if lst.get("title") == _NOTES_LIST_TITLE:
            _notes_list_id = lst["id"]
            return _notes_list_id

    # Créer la liste si elle n'existe pas
    created = service.tasklists().insert(body={"title": _NOTES_LIST_TITLE}).execute()
    _notes_list_id = created["id"]
    return _notes_list_id


def add_task(title: str, due_iso: Optional[str] = None) -> dict:
    service = _get_service()
    body = {"title": title}
    if due_iso:
        try:
            dt = datetime.fromisoformat(due_iso)
            # Google Tasks due doit être en UTC, format RFC3339
            body["due"] = dt.astimezone(pytz.utc).strftime("%Y-%m-%dT00:00:00.000Z")
        except Exception:
            pass
    task = service.tasks().insert(tasklist="@default", body=body).execute()
    return {"id": task["id"], "title": title}


def list_tasks() -> list[dict]:
    global _task_cache
    service = _get_service()
    result = service.tasks().list(
        tasklist="@default",
        showCompleted=False,
        showHidden=False,
    ).execute()
    items = result.get("items", [])
    _task_cache = [t["id"] for t in items]
    return [{"id": i + 1, "title": t.get("title", ""), "google_id": t["id"]} for i, t in enumerate(items)]


def complete_task(position: int) -> bool:
    service = _get_service()
    if not _task_cache or position < 1 or position > len(_task_cache):
        # Fallback : re-lister pour avoir les IDs
        list_tasks()
    if position < 1 or position > len(_task_cache):
        return False
    google_id = _task_cache[position - 1]
    try:
        service.tasks().patch(
            tasklist="@default",
            task=google_id,
            body={"status": "completed"},
        ).execute()
        return True
    except Exception:
        return False


def delete_task(position: int) -> bool:
    service = _get_service()
    if not _task_cache or position < 1 or position > len(_task_cache):
        list_tasks()
    if position < 1 or position > len(_task_cache):
        return False
    google_id = _task_cache[position - 1]
    try:
        service.tasks().delete(tasklist="@default", task=google_id).execute()
        return True
    except Exception:
        return False


def add_note(content: str) -> dict:
    service = _get_service()
    notes_list = _get_notes_list_id(service)
    task = service.tasks().insert(tasklist=notes_list, body={"title": content}).execute()
    return {"id": task["id"], "content": content}


def list_notes() -> list[dict]:
    global _note_cache
    service = _get_service()
    notes_list = _get_notes_list_id(service)
    result = service.tasks().list(
        tasklist=notes_list,
        showCompleted=False,
        showHidden=False,
    ).execute()
    items = result.get("items", [])
    _note_cache = [t["id"] for t in items]
    return [{"id": i + 1, "content": t.get("title", ""), "google_id": t["id"]} for i, t in enumerate(items)]


def delete_note(position: int) -> bool:
    service = _get_service()
    if not _note_cache or position < 1 or position > len(_note_cache):
        list_notes()
    if position < 1 or position > len(_note_cache):
        return False
    google_id = _note_cache[position - 1]
    notes_list = _get_notes_list_id(service)
    try:
        service.tasks().delete(tasklist=notes_list, task=google_id).execute()
        return True
    except Exception:
        return False


# ── Idées ──────────────────────────────────────────────────────────────────────

_IDEAS_LIST_TITLE = "Idées Bastien"
_ideas_list_id: Optional[str] = None
_idea_cache: list[str] = []


def _get_ideas_list_id(service) -> str:
    global _ideas_list_id
    if _ideas_list_id:
        return _ideas_list_id
    result = service.tasklists().list().execute()
    for lst in result.get("items", []):
        if lst.get("title") == _IDEAS_LIST_TITLE:
            _ideas_list_id = lst["id"]
            return _ideas_list_id
    created = service.tasklists().insert(body={"title": _IDEAS_LIST_TITLE}).execute()
    _ideas_list_id = created["id"]
    return _ideas_list_id


def add_idea(content: str) -> dict:
    service = _get_service()
    ideas_list = _get_ideas_list_id(service)
    task = service.tasks().insert(tasklist=ideas_list, body={"title": content}).execute()
    return {"id": task["id"], "content": content}


def list_ideas() -> list[dict]:
    global _idea_cache
    service = _get_service()
    ideas_list = _get_ideas_list_id(service)
    result = service.tasks().list(
        tasklist=ideas_list,
        showCompleted=False,
        showHidden=False,
    ).execute()
    items = result.get("items", [])
    _idea_cache = [t["id"] for t in items]
    return [{"id": i + 1, "content": t.get("title", ""), "google_id": t["id"]} for i, t in enumerate(items)]


def delete_idea(position: int) -> bool:
    service = _get_service()
    if not _idea_cache or position < 1 or position > len(_idea_cache):
        list_ideas()
    if position < 1 or position > len(_idea_cache):
        return False
    google_id = _idea_cache[position - 1]
    ideas_list = _get_ideas_list_id(service)
    try:
        service.tasks().delete(tasklist=ideas_list, task=google_id).execute()
        return True
    except Exception:
        return False
