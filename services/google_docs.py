import os
import json
from typing import Optional
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]
TOKEN_PATH = "google_token.json"
FOLDER_NAME = "Note Bastien Agent"

_folder_id: Optional[str] = None


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
            creds.refresh(Request())
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


def create_note_doc(title: str, content: str, summary: str = None) -> dict:
    """Crée un Google Doc dans le dossier Note Bastien Agent.
    Le doc contient le résumé en premier, puis le texte complet.
    Utilise l'import Drive (pas besoin du scope documents).
    """
    creds = _get_credentials()
    drive_svc = build("drive", "v3", credentials=creds)
    folder_id = _get_or_create_folder(drive_svc)

    if summary:
        full_text = (
            f"RÉSUMÉ\n\n{summary}\n\n"
            f"{'─' * 40}\n\n"
            f"RETRANSCRIPTION COMPLÈTE\n\n{content}"
        )
    else:
        full_text = content

    media = MediaInMemoryUpload(
        full_text.encode("utf-8"),
        mimetype="text/plain",
        resumable=False,
    )

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
