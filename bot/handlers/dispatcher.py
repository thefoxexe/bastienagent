"""Routes parsed AI actions to the right service calls."""
import os
from datetime import datetime
import pytz
from telegram import Update
from telegram.ext import ContextTypes

from services import tasks_db, google_calendar, weather as weather_svc
from services.claude_ai import generate_briefing_text


TIMEZONE = os.getenv("TIMEZONE", "Europe/Zurich")


async def dispatch(action: dict, update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = action.get("action", "chat")
    params = action.get("params", {})
    reply = action.get("reply", "")

    if name == "chat":
        await update.message.reply_text(reply, parse_mode="Markdown")

    elif name == "calendar_read_today":
        events = google_calendar.get_events_today(TIMEZONE)
        text = google_calendar.format_events_text(events, TIMEZONE)
        await update.message.reply_text(f"📅 *Agenda d'aujourd'hui*\n{text}", parse_mode="Markdown")

    elif name == "calendar_read_week":
        events = google_calendar.get_events_for_period(7, TIMEZONE)
        text = google_calendar.format_events_text(events, TIMEZONE)
        await update.message.reply_text(f"📅 *Agenda de la semaine*\n{text}", parse_mode="Markdown")

    elif name == "calendar_read_days":
        days = int(params.get("days", 3))
        events = google_calendar.get_events_for_period(days, TIMEZONE)
        text = google_calendar.format_events_text(events, TIMEZONE)
        await update.message.reply_text(f"📅 *Agenda ({days} jours)*\n{text}", parse_mode="Markdown")

    elif name == "calendar_create":
        try:
            start_iso = params["start_iso"]
            end_iso = params.get("end_iso")
            tz = pytz.timezone(TIMEZONE)
            start_dt = datetime.fromisoformat(start_iso).astimezone(tz)
            end_dt = datetime.fromisoformat(end_iso).astimezone(tz) if end_iso else None
            result = google_calendar.create_event(
                title=params["title"],
                start_dt=start_dt,
                end_dt=end_dt,
                location=params.get("location", ""),
                description=params.get("description", ""),
                timezone=TIMEZONE,
            )
            await update.message.reply_text(
                f"✅ Événement créé : *{result['title']}*\n"
                f"🕐 {start_dt.strftime('%d/%m/%Y à %H:%M')}",
                parse_mode="Markdown",
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Erreur : {e}")

    elif name == "calendar_delete":
        ok = google_calendar.delete_event(params.get("event_id", ""))
        if ok:
            await update.message.reply_text("✅ Événement supprimé.")
        else:
            await update.message.reply_text("❌ Événement introuvable.")

    elif name == "task_add":
        task_id = await tasks_db.add_task(params["title"])
        await update.message.reply_text(
            f"✅ Tâche ajoutée : *{params['title']}* (#{task_id})",
            parse_mode="Markdown",
        )

    elif name == "task_list":
        tasks = await tasks_db.list_tasks()
        if not tasks:
            await update.message.reply_text("✅ Aucune tâche en cours !")
        else:
            lines = [f"#{t['id']} {t['title']}" for t in tasks]
            await update.message.reply_text(
                "📋 *Tâches en cours :*\n" + "\n".join(f"• {l}" for l in lines),
                parse_mode="Markdown",
            )

    elif name == "task_done":
        ok = await tasks_db.complete_task(int(params["task_id"]))
        if ok:
            await update.message.reply_text(f"✅ Tâche #{params['task_id']} terminée !")
        else:
            await update.message.reply_text(f"❌ Tâche #{params['task_id']} introuvable.")

    elif name == "task_delete":
        ok = await tasks_db.delete_task(int(params["task_id"]))
        if ok:
            await update.message.reply_text(f"🗑️ Tâche #{params['task_id']} supprimée.")
        else:
            await update.message.reply_text(f"❌ Tâche #{params['task_id']} introuvable.")

    elif name == "note_add":
        note_id = await tasks_db.add_note(params["content"])
        await update.message.reply_text(
            f"📝 Note sauvegardée (#{note_id}) : _{params['content']}_",
            parse_mode="Markdown",
        )

    elif name == "note_list":
        notes = await tasks_db.list_notes()
        if not notes:
            await update.message.reply_text("📝 Aucune note.")
        else:
            lines = [f"#{n['id']} {n['content']}" for n in notes]
            await update.message.reply_text(
                "📝 *Tes notes :*\n" + "\n".join(f"• {l}" for l in lines),
                parse_mode="Markdown",
            )

    elif name == "weather":
        city = params.get("city")
        w = await weather_svc.get_weather(city)
        await update.message.reply_text(w)

    elif name == "briefing":
        await send_briefing(update.message.chat_id, context)

    else:
        if reply:
            await update.message.reply_text(reply, parse_mode="Markdown")
        else:
            await update.message.reply_text("Je n'ai pas compris. Peux-tu reformuler ?")


async def send_briefing(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    from services.weather import get_weather
    from services.google_calendar import get_events_today

    w = await get_weather()
    try:
        events = get_events_today(TIMEZONE)
    except Exception:
        events = []
    tasks = await tasks_db.list_tasks()

    text = generate_briefing_text(w, events, tasks, TIMEZONE)
    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
