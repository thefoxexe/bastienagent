import io
import os
import json
from datetime import datetime
from typing import Optional
import pytz
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload, MediaIoBaseDownload

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]
TOKEN_PATH = "google_token.json"
FOLDER_NAME = "Note Bastien Agent"
JOURNAL_DOC_NAME = "Journal Bastien"

# Marqueur unique qui délimite chaque entrée — utilisé pour la suppression
_ENTRY_MARKER = "\n\n◆" + "─" * 38 + "◆\n"

_DAYS_FR = {
    "Monday": "Lundi", "Tuesday": "Mardi", "Wednesday": "Mercredi",
    "Thursday": "Jeudi", "Friday": "Vendredi", "Saturday": "Samedi", "Sunday": "Dimanche",
}
_MONTHS_FR = {
    1: "janvier", 2: "février", 3: "mars", 4: "avril", 5: "mai", 6: "juin",
    7: "juillet", 8: "août", 9: "septembre", 10: "octobre", 11: "novembre", 12: "décembre",
}

_folder_id: Optional[str] = None
_journal_doc_id: Optional[str] = None


def _persist_refreshed_token(creds) -> None:
    try:
        token_data = json.loads(creds.to_json())
        os.environ["GOOGLE_TOKEN_JSON"] = json.dumps(token_data)
        with open(TOKEN_PATH, "w") as f:
            json.dump(token_data, f)
    except Exception:
        pass


def _get_credentials() -> Credentials:
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
            raise RuntimeError("Token expiré. Envoie /connecter_calendar")
    return creds


def _get_or_create_folder(drive_svc) -> str:
    global _folder_id
    if _folder_id:
        return _folder_id
    try:
        results = drive_svc.files().list(
            q=f"name='{FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
            fields="files(id)",
        ).execute()
        files = results.get("files", [])
        if files:
            _folder_id = files[0]["id"]
            return _folder_id
    except Exception:
        pass
    folder = drive_svc.files().create(
        body={"name": FOLDER_NAME, "mimeType": "application/vnd.google-apps.folder"},
        fields="id",
    ).execute()
    _folder_id = folder["id"]
    return _folder_id


def _get_or_create_journal_doc(drive_svc) -> str:
    global _journal_doc_id
    if _journal_doc_id:
        return _journal_doc_id
    try:
        results = drive_svc.files().list(
            q=f"name='{JOURNAL_DOC_NAME}' and mimeType='application/vnd.google-apps.document' and trashed=false",
            fields="files(id)",
        ).execute()
        files = results.get("files", [])
        if files:
            _journal_doc_id = files[0]["id"]
            return _journal_doc_id
    except Exception:
        pass
    folder_id = _get_or_create_folder(drive_svc)
    header = "JOURNAL DE BORD — BASTIEN\n"
    media = MediaInMemoryUpload(header.encode("utf-8"), mimetype="text/plain", resumable=False)
    file = drive_svc.files().create(
        body={
            "name": JOURNAL_DOC_NAME,
            "mimeType": "application/vnd.google-apps.document",
            "parents": [folder_id],
        },
        media_body=media,
        fields="id",
    ).execute()
    _journal_doc_id = file["id"]
    return _journal_doc_id


def _export_doc_text(drive_svc, doc_id: str) -> str:
    try:
        request = drive_svc.files().export_media(fileId=doc_id, mimeType="text/plain")
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buf.getvalue().decode("utf-8").strip()
    except Exception:
        return "JOURNAL DE BORD — BASTIEN"


def _upload_doc_text(drive_svc, doc_id: str, content: str) -> None:
    media = MediaInMemoryUpload(content.encode("utf-8"), mimetype="text/plain", resumable=False)
    drive_svc.files().update(fileId=doc_id, media_body=media).execute()


def append_journal_entry(content: str, summary: str = None) -> dict:
    """Ajoute une entrée datée au journal de bord unique."""
    creds = _get_credentials()
    drive_svc = build("drive", "v3", credentials=creds)
    doc_id = _get_or_create_journal_doc(drive_svc)

    existing_text = _export_doc_text(drive_svc, doc_id)

    tz = pytz.timezone(os.getenv("TIMEZONE", "Europe/Zurich"))
    now = datetime.now(tz)
    day_name = _DAYS_FR.get(now.strftime("%A"), "")
    date_str = f"{now.day} {_MONTHS_FR[now.month]} {now.year}"
    time_str = now.strftime("%H:%M")

    # Format propre : marqueur ◆───◆ + date en header + contenu + résumé optionnel
    header_line = f"{day_name} {date_str}  ·  {time_str}"
    entry = _ENTRY_MARKER + header_line + "\n\n" + content.strip()
    if summary:
        entry += f"\n\n▸ {summary.strip()}"

    _upload_doc_text(drive_svc, doc_id, existing_text + entry)

    return {
        "id": doc_id,
        "url": f"https://docs.google.com/document/d/{doc_id}",
        "date": date_str,
        "time": time_str,
    }


def delete_last_journal_entry() -> bool:
    """Supprime la dernière entrée du journal. Retourne True si suppression réussie."""
    creds = _get_credentials()
    drive_svc = build("drive", "v3", credentials=creds)
    doc_id = _get_or_create_journal_doc(drive_svc)

    existing_text = _export_doc_text(drive_svc, doc_id)

    idx = existing_text.rfind(_ENTRY_MARKER)
    if idx == -1:
        return False

    new_content = existing_text[:idx].rstrip()
    _upload_doc_text(drive_svc, doc_id, new_content)
    return True


def create_note_doc(title: str, content: str, summary: str = None) -> dict:
    """Crée un Google Doc dans le dossier Note Bastien Agent."""
    creds = _get_credentials()
    drive_svc = build("drive", "v3", credentials=creds)
    folder_id = _get_or_create_folder(drive_svc)

    if summary:
        full_text = f"RÉSUMÉ\n\n{summary}\n\n{'─' * 40}\n\nRETRANSCRIPTION COMPLÈTE\n\n{content}"
    else:
        full_text = content

    media = MediaInMemoryUpload(full_text.encode("utf-8"), mimetype="text/plain", resumable=False)
    file = drive_svc.files().create(
        body={
            "name": title,
            "mimeType": "application/vnd.google-apps.document",
            "parents": [folder_id],
        },
        media_body=media,
        fields="id",
    ).execute()

    doc_id = file["id"]
    return {"id": doc_id, "url": f"https://docs.google.com/document/d/{doc_id}", "title": title}
