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
Tu parles en français, tu es concis et chaleureux.
Tu as accès à son Google Calendar, ses tâches et ses notes.

RÈGLE IMPORTANTE : si le message contient PLUSIEURS demandes, retourne un TABLEAU JSON avec une action par élément.
Si une seule demande, retourne un objet JSON unique.

RÈGLE ANTI-DOUBLON : après une action de création ou modification (calendar_create, task_add, note_add, expense_add), ne jamais ajouter une action de lecture (calendar_read_today, task_list, note_list, expense_list) dans la même réponse. Retourne uniquement l'action de création.

Règle pour choisir entre tâche et événement calendrier :
- Si ça a une HEURE PRÉCISE → calendar_create (ex: "à 18h15", "demain matin à 9h")
- Si c'est conditionnel ou sans heure → task_add (ex: "si j'ai le temps", "quand je peux")
- Si c'est une DATE sans heure → task_add avec la date dans le titre

Format d'une action :
{
  "action": "string",
  "params": {},
  "reply": "string"
}

Actions disponibles :
- "chat" : conversation (params: {})
- "calendar_read_today" : agenda aujourd'hui (params: {})
- "calendar_read_week" : agenda semaine (params: {})
- "calendar_read_days" : agenda N jours (params: {"days": int})
- "calendar_create" : créer événement (params: {"title": str, "start_iso": str, "end_iso": str|null, "location": str, "description": str})
- "calendar_delete" : supprimer événement (params: {"event_id": str})
- "task_add" : ajouter tâche (params: {"title": str, "due_iso": str|null})
- "task_list" : lister tâches (params: {})
- "task_done" : tâche terminée (params: {"task_id": int})
- "task_delete" : supprimer tâche (params: {"task_id": int})
- "note_add" : ajouter note (params: {"content": str})
- "note_list" : lister notes (params: {})
- "weather" : météo (params: {"city": str|null})
- "briefing" : briefing complet (params: {})
- "expense_add" : noter une dépense (params: {"amount": float, "category": str, "description": str, "date_iso": str|null})
- "expense_list" : voir le résumé des dépenses (params: {"period": "today"|"week"|"month"|"year"})
- "settings" : afficher les paramètres du bot (params: {})
- "currency_convert" : convertir un montant entre devises (params: {"amount": float, "from_currency": str, "to_currency": str})
- "journal_add" : ajouter une entrée au journal personnel (params: {"content": str})
- "idea_add" : sauvegarder une idée (params: {"content": str})
- "idea_list" : voir toutes les idées sauvegardées (params: {})
- "write_assist" : rédiger un texte (email, message, lettre...) à la place de l'utilisateur — le champ "reply" contient le texte complet rédigé, prêt à copier. (params: {"type": str, "context": str})

Catégories de dépenses : Restaurant, Café, Courses, Transport, Loisirs, Santé, Shopping, Abonnements, Logement, Autre
Devise : CHF (francs suisses)

Dates/heures : format ISO 8601 avec timezone (ex: "2026-07-04T18:15:00+02:00").
Date et heure actuelle : {current_datetime}
Fuseau horaire : Europe/Zurich (UTC+2 en été).

IMPORTANT : retourne UNIQUEMENT le JSON (objet ou tableau), sans texte ni markdown."""


def parse_message(user_message: str, conversation_history: list = None) -> list[dict]:
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
        parsed = json.loads(raw)
        # Normalise toujours en liste
        if isinstance(parsed, dict):
            return [parsed]
        return parsed
    except json.JSONDecodeError:
        return [{"action": "chat", "params": {}, "reply": raw}]


def parse_receipt(image_bytes: bytes) -> dict | None:
    """Analyse une photo de quittance/facture et retourne les données de dépense."""
    import base64

    client = _get_client()

    # Détecte le format image
    if image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
        media_type = "image/png"
    elif image_bytes[:4] == b'%PDF':
        return None  # PDF non supporté sans conversion
    else:
        media_type = "image/jpeg"

    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": image_b64},
                },
                {
                    "type": "text",
                    "text": (
                        "C'est une quittance, facture ou reçu. "
                        "Extrais les informations et retourne UNIQUEMENT ce JSON (sans markdown) :\n"
                        "{\"amount\": float|null, \"category\": string, \"description\": string, \"date_iso\": string|null}\n"
                        "amount = montant TOTAL TTC en chiffres (null si illisible).\n"
                        "category = Restaurant|Café|Courses|Transport|Loisirs|Santé|Shopping|Abonnements|Logement|Autre\n"
                        "description = nom du commerce ou type d'achat, max 50 caractères.\n"
                        "date_iso = date ISO 8601 si visible sur le reçu, sinon null."
                    ),
                },
            ],
        }],
    )

    raw = response.content[0].text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def generate_briefing_text(
    weather: str,
    events: list[dict],
    tasks: list[dict],
    timezone: str = "Europe/Zurich",
) -> str:
    tz = pytz.timezone(timezone)
    now = datetime.now(tz)
    day_fr = {
        "Monday": "Lundi", "Tuesday": "Mardi", "Wednesday": "Mercredi",
        "Thursday": "Jeudi", "Friday": "Vendredi", "Saturday": "Samedi", "Sunday": "Dimanche",
    }
    month_fr = {
        1: "janvier", 2: "février", 3: "mars", 4: "avril", 5: "mai", 6: "juin",
        7: "juillet", 8: "août", 9: "septembre", 10: "octobre", 11: "novembre", 12: "décembre",
    }
    day_name = day_fr[now.strftime("%A")]
    date_str = f"{day_name} {now.day} {month_fr[now.month]} {now.year}"
    greeting = _time_greeting(now.hour)

    # Agenda
    if events:
        event_lines = []
        for e in events:
            if e["all_day"]:
                time_str = "Toute la journée"
            else:
                try:
                    dt = datetime.fromisoformat(e["start"]).astimezone(tz)
                    time_str = dt.strftime("%H:%M")
                except Exception:
                    time_str = ""
            loc = f"  📍 _{e['location']}_" if e["location"] else ""
            event_lines.append(f"  `{time_str}`  {e['title']}{loc}")
        events_block = "\n".join(event_lines)
    else:
        events_block = "  _Rien de prévu — journée libre !_"

    # Tâches
    if tasks:
        task_lines = [f"  ◦ {t['title']}" for t in tasks[:5]]
        if len(tasks) > 5:
            task_lines.append(f"  _... et {len(tasks) - 5} autres_")
        tasks_block = "\n".join(task_lines)
    else:
        tasks_block = "  _Aucune tâche — tout est à jour !_ 🎉"

    sep = "─────────────────"

    return (
        f"{'🌅' if now.hour < 12 else '🌇' if now.hour < 18 else '🌙'} *{greeting}, Bastien !*\n"
        f"📅 {date_str}\n"
        f"{sep}\n"
        f"🌤 *Météo*\n  {weather}\n"
        f"{sep}\n"
        f"📆 *Agenda du jour*\n{events_block}\n"
        f"{sep}\n"
        f"✅ *Tâches*\n{tasks_block}"
    )


def generate_summary(text: str) -> str:
    """Génère un résumé concis en 3-5 phrases d'un texte donné."""
    client = _get_client()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": (
            "Résume ce texte en 3 à 5 phrases maximum, en français, "
            "de façon claire et concise. Retourne uniquement le résumé, sans introduction.\n\n"
            f"Texte :\n{text}"
        )}],
    )
    return response.content[0].text.strip()


def _time_greeting(hour: int) -> str:
    if hour < 12:
        return "Bonjour"
    elif hour < 18:
        return "Bon après-midi"
    else:
        return "Bonsoir"
