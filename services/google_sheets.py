import os
import json
from datetime import datetime, timedelta
from typing import Optional
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
SHEET_TITLE = "Dépenses Bastien"

_spreadsheet_id: Optional[str] = None
_sheet_url: Optional[str] = None


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
        else:
            raise RuntimeError("Token expiré. Envoie /connecter_calendar")
    return creds


def _get_or_create_spreadsheet(creds: Credentials) -> tuple[str, str]:
    global _spreadsheet_id, _sheet_url

    if _spreadsheet_id:
        return _spreadsheet_id, _sheet_url

    env_id = os.getenv("GOOGLE_SHEET_ID")
    if env_id:
        _spreadsheet_id = env_id
        _sheet_url = f"https://docs.google.com/spreadsheets/d/{env_id}"
        return _spreadsheet_id, _sheet_url

    # Cherche dans Drive les fichiers créés par cette app
    try:
        drive_svc = build("drive", "v3", credentials=creds)
        results = drive_svc.files().list(
            q=f"name='{SHEET_TITLE}' and mimeType='application/vnd.google-apps.spreadsheet' and trashed=false",
            fields="files(id)",
        ).execute()
        files = results.get("files", [])
        if files:
            _spreadsheet_id = files[0]["id"]
            _sheet_url = f"https://docs.google.com/spreadsheets/d/{_spreadsheet_id}"
            return _spreadsheet_id, _sheet_url
    except Exception:
        pass

    # Crée un nouveau spreadsheet avec deux onglets
    svc = build("sheets", "v4", credentials=creds)
    spreadsheet = svc.spreadsheets().create(body={
        "properties": {"title": SHEET_TITLE},
        "sheets": [
            {"properties": {"title": "Dépenses", "sheetId": 0, "index": 0}},
            {"properties": {"title": "Paramètres", "sheetId": 1, "index": 1}},
        ],
    }).execute()

    _spreadsheet_id = spreadsheet["spreadsheetId"]
    _sheet_url = f"https://docs.google.com/spreadsheets/d/{_spreadsheet_id}"

    # En-têtes
    svc.spreadsheets().values().batchUpdate(
        spreadsheetId=_spreadsheet_id,
        body={"valueInputOption": "RAW", "data": [
            {"range": "Dépenses!A1:D1", "values": [["Date", "Montant (CHF)", "Catégorie", "Description"]]},
            {"range": "Paramètres!A1:B1", "values": [["Clé", "Valeur"]]},
        ]},
    ).execute()

    # Mise en forme
    svc.spreadsheets().batchUpdate(
        spreadsheetId=_spreadsheet_id,
        body={"requests": [
            {
                "repeatCell": {
                    "range": {"sheetId": 0, "startRowIndex": 0, "endRowIndex": 1},
                    "cell": {"userEnteredFormat": {
                        "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                        "backgroundColor": {"red": 0.16, "green": 0.71, "blue": 0.96},
                        "horizontalAlignment": "CENTER",
                    }},
                    "fields": "userEnteredFormat",
                }
            },
            {
                "updateSheetProperties": {
                    "properties": {"sheetId": 0, "gridProperties": {"frozenRowCount": 1}},
                    "fields": "gridProperties.frozenRowCount",
                }
            },
            {
                "repeatCell": {
                    "range": {"sheetId": 1, "startRowIndex": 0, "endRowIndex": 1},
                    "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                    "fields": "userEnteredFormat.textFormat.bold",
                }
            },
            {
                "updateDimensionProperties": {
                    "range": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 4},
                    "properties": {"pixelSize": 150},
                    "fields": "pixelSize",
                }
            },
        ]},
    ).execute()

    return _spreadsheet_id, _sheet_url


def _ensure_settings_tab(svc) -> None:
    """Crée l'onglet Paramètres s'il n'existe pas (migration anciens sheets)."""
    global _spreadsheet_id
    if not _spreadsheet_id:
        return
    metadata = svc.spreadsheets().get(spreadsheetId=_spreadsheet_id).execute()
    for sheet in metadata.get("sheets", []):
        if sheet["properties"]["title"] == "Paramètres":
            return
    svc.spreadsheets().batchUpdate(
        spreadsheetId=_spreadsheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": "Paramètres"}}}]},
    ).execute()
    svc.spreadsheets().values().update(
        spreadsheetId=_spreadsheet_id,
        range="Paramètres!A1:B1",
        valueInputOption="RAW",
        body={"values": [["Clé", "Valeur"]]},
    ).execute()


def get_setting(key: str) -> Optional[str]:
    creds = _get_credentials()
    sheet_id, _ = _get_or_create_spreadsheet(creds)
    svc = build("sheets", "v4", credentials=creds)
    _ensure_settings_tab(svc)
    result = svc.spreadsheets().values().get(
        spreadsheetId=sheet_id, range="Paramètres!A:B"
    ).execute()
    for row in result.get("values", [])[1:]:
        if len(row) >= 2 and row[0] == key:
            return row[1]
    return None


def set_setting(key: str, value: str) -> None:
    creds = _get_credentials()
    sheet_id, _ = _get_or_create_spreadsheet(creds)
    svc = build("sheets", "v4", credentials=creds)
    _ensure_settings_tab(svc)
    result = svc.spreadsheets().values().get(
        spreadsheetId=sheet_id, range="Paramètres!A:B"
    ).execute()
    rows = result.get("values", [])
    for i, row in enumerate(rows):
        if len(row) >= 1 and row[0] == key:
            row_num = i + 1
            svc.spreadsheets().values().update(
                spreadsheetId=sheet_id,
                range=f"Paramètres!A{row_num}:B{row_num}",
                valueInputOption="RAW",
                body={"values": [[key, value]]},
            ).execute()
            return
    svc.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range="Paramètres!A:B",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [[key, value]]},
    ).execute()


def get_budget() -> Optional[float]:
    try:
        val = get_setting("budget_mensuel")
        return float(val) if val else None
    except Exception:
        return None


def set_budget(amount: float) -> None:
    set_setting("budget_mensuel", str(amount))


def add_expense(amount: float, category: str, description: str, date_iso: str = None) -> dict:
    creds = _get_credentials()
    sheet_id, sheet_url = _get_or_create_spreadsheet(creds)
    svc = build("sheets", "v4", credentials=creds)

    try:
        dt = datetime.fromisoformat(date_iso) if date_iso else datetime.now()
    except Exception:
        dt = datetime.now()
    date_str = dt.strftime("%d/%m/%Y")

    svc.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range="Dépenses!A:D",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [[date_str, amount, category, description]]},
    ).execute()

    return {"date": date_str, "amount": amount, "category": category, "sheet_url": sheet_url}


def get_summary(period: str = "month") -> dict:
    creds = _get_credentials()
    sheet_id, sheet_url = _get_or_create_spreadsheet(creds)
    svc = build("sheets", "v4", credentials=creds)

    result = svc.spreadsheets().values().get(
        spreadsheetId=sheet_id, range="Dépenses!A:D"
    ).execute()
    rows = result.get("values", [])
    budget = get_budget()

    if len(rows) <= 1:
        return {"total": 0.0, "by_category": {}, "count": 0, "period": period, "sheet_url": sheet_url, "budget": budget}

    now = datetime.now()
    if period == "today":
        cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        cutoff = now - timedelta(days=7)
    elif period == "year":
        cutoff = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:  # month
        cutoff = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    total = 0.0
    by_category: dict[str, float] = {}
    count = 0

    for row in rows[1:]:
        if len(row) < 2:
            continue
        try:
            date_str = row[0]
            amount = float(str(row[1]).replace(",", ".").replace("CHF", "").replace("€", "").strip())
            category = row[2] if len(row) > 2 else "Autre"
            date = datetime.strptime(date_str, "%d/%m/%Y")
            if date < cutoff:
                continue
            total += amount
            by_category[category] = by_category.get(category, 0.0) + amount
            count += 1
        except (ValueError, IndexError):
            continue

    return {
        "total": total,
        "by_category": by_category,
        "count": count,
        "period": period,
        "sheet_url": sheet_url,
        "budget": budget,
    }
