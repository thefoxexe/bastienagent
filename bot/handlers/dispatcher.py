"""Routes parsed AI actions to the right service calls."""
import os
from datetime import datetime
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from services import tasks_db, google_calendar, weather as weather_svc
from services.claude_ai import generate_briefing_text

TIMEZONE = os.getenv("TIMEZONE", "Europe/Zurich")

_CALENDAR_ERROR_KEYBOARD = InlineKeyboardMarkup([[
    InlineKeyboardButton("🔗 Connecter Google Calendar", callback_data="connecter_calendar")
]])

_BRIEFING_KEYBOARD = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("📅 Agenda", callback_data="agenda"),
        InlineKeyboardButton("✅ Tâches", callback_data="taches"),
        InlineKeyboardButton("📝 Notes", callback_data="notes"),
    ]
])


def _calendar_error_msg(e: Exception) -> str:
    msg = str(e)
    if "pas encore connecté" in msg or "connecter_calendar" in msg:
        return None  # handled specially
    return f"❌ Erreur calendrier : {msg}"


async def dispatch(action: dict, update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = action.get("action", "chat")
    params = action.get("params", {})
    reply = action.get("reply", "")
    msg = update.message

    if name == "chat":
        await msg.reply_text(reply or "Je suis là !", parse_mode="Markdown")

    elif name in ("calendar_read_today", "calendar_read_week", "calendar_read_days"):
        try:
            if name == "calendar_read_today":
                events = google_calendar.get_events_today(TIMEZONE)
                title = "Agenda d'aujourd'hui"
            elif name == "calendar_read_week":
                events = google_calendar.get_events_for_period(7, TIMEZONE)
                title = "Agenda de la semaine"
            else:
                days = int(params.get("days", 3))
                events = google_calendar.get_events_for_period(days, TIMEZONE)
                title = f"Agenda ({days} jours)"
            text = google_calendar.format_events_text(events, TIMEZONE)
            await msg.reply_text(f"📅 *{title}*\n{text}", parse_mode="Markdown")
        except Exception as e:
            await _send_calendar_error(msg, e)

    elif name == "calendar_create":
        try:
            tz = pytz.timezone(TIMEZONE)
            start_dt = datetime.fromisoformat(params["start_iso"]).astimezone(tz)
            end_iso = params.get("end_iso")
            end_dt = datetime.fromisoformat(end_iso).astimezone(tz) if end_iso else None
            result = google_calendar.create_event(
                title=params["title"],
                start_dt=start_dt,
                end_dt=end_dt,
                location=params.get("location", ""),
                description=params.get("description", ""),
                timezone=TIMEZONE,
            )
            await msg.reply_text(
                f"✅ Événement créé : *{result['title']}*\n"
                f"🕐 {start_dt.strftime('%d/%m/%Y à %H:%M')}",
                parse_mode="Markdown",
            )
        except Exception as e:
            await _send_calendar_error(msg, e)

    elif name == "calendar_delete":
        try:
            ok = google_calendar.delete_event(params.get("event_id", ""))
            if ok:
                await msg.reply_text("✅ Événement supprimé.")
            else:
                await msg.reply_text("❌ Événement introuvable. Vérifie l'ID.")
        except Exception as e:
            await _send_calendar_error(msg, e)

    elif name == "task_add":
        try:
            task_id = await tasks_db.add_task(params["title"])
            await msg.reply_text(
                f"✅ Tâche ajoutée : *{params['title']}* (#{task_id})",
                parse_mode="Markdown",
            )
        except Exception as e:
            await msg.reply_text(f"❌ Impossible d'ajouter la tâche : {e}")

    elif name == "task_list":
        try:
            tasks = await tasks_db.list_tasks()
            if not tasks:
                await msg.reply_text("🎉 Aucune tâche en cours, tu es à jour !")
            else:
                lines = "\n".join(f"• #{t['id']} {t['title']}" for t in tasks)
                await msg.reply_text(f"📋 *Tâches en cours :*\n{lines}", parse_mode="Markdown")
        except Exception as e:
            await msg.reply_text(f"❌ Impossible de lire les tâches : {e}")

    elif name == "task_done":
        try:
            ok = await tasks_db.complete_task(int(params["task_id"]))
            if ok:
                await msg.reply_text(f"✅ Tâche #{params['task_id']} terminée ! Bien joué 💪")
            else:
                await msg.reply_text(f"❌ Tâche #{params['task_id']} introuvable. Envoie /taches pour voir les IDs.")
        except Exception as e:
            await msg.reply_text(f"❌ Erreur : {e}")

    elif name == "task_delete":
        try:
            ok = await tasks_db.delete_task(int(params["task_id"]))
            if ok:
                await msg.reply_text(f"🗑️ Tâche #{params['task_id']} supprimée.")
            else:
                await msg.reply_text(f"❌ Tâche #{params['task_id']} introuvable.")
        except Exception as e:
            await msg.reply_text(f"❌ Erreur : {e}")

    elif name == "note_add":
        try:
            note_id = await tasks_db.add_note(params["content"])
            await msg.reply_text(
                f"📝 Note sauvegardée (#{note_id}) :\n_{params['content']}_",
                parse_mode="Markdown",
            )
        except Exception as e:
            await msg.reply_text(f"❌ Impossible de sauvegarder la note : {e}")

    elif name == "note_list":
        try:
            notes = await tasks_db.list_notes()
            if not notes:
                await msg.reply_text("📝 Aucune note pour l'instant.")
            else:
                lines = "\n".join(f"• #{n['id']} {n['content']}" for n in notes)
                await msg.reply_text(f"📝 *Tes notes :*\n{lines}", parse_mode="Markdown")
        except Exception as e:
            await msg.reply_text(f"❌ Impossible de lire les notes : {e}")

    elif name == "weather":
        try:
            w = await weather_svc.get_weather(params.get("city"))
            await msg.reply_text(w)
        except Exception as e:
            await msg.reply_text(f"❌ Météo indisponible : {e}")

    elif name == "briefing":
        await send_briefing(msg.chat_id, context)

    else:
        await msg.reply_text(reply or "Je n'ai pas compris, peux-tu reformuler ?")


async def _send_calendar_error(msg, e: Exception):
    err = str(e)
    if "pas encore connecté" in err or "connecter_calendar" in err:
        await msg.reply_text(
            "📅 Google Calendar n'est pas connecté.\nClique sur le bouton pour le connecter :",
            reply_markup=_CALENDAR_ERROR_KEYBOARD,
        )
    else:
        await msg.reply_text(f"❌ Erreur calendrier : {err}")


async def send_briefing(chat_id: int, context):
    w = await weather_svc.get_weather()
    try:
        events = google_calendar.get_events_today(TIMEZONE)
    except Exception:
        events = []
    tasks = await tasks_db.list_tasks()

    text = generate_briefing_text(w, events, tasks, TIMEZONE)
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="Markdown",
        reply_markup=_BRIEFING_KEYBOARD,
    )
