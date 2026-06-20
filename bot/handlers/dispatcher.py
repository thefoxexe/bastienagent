import os
from datetime import datetime
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from services import google_tasks, google_calendar, weather as weather_svc
from services.claude_ai import generate_briefing_text

TIMEZONE = os.getenv("TIMEZONE", "Europe/Zurich")

_CALENDAR_ERROR_KEYBOARD = InlineKeyboardMarkup([[
    InlineKeyboardButton("🔗 Connecter Google", callback_data="connecter_calendar"),
]])

_BRIEFING_KEYBOARD = InlineKeyboardMarkup([[
    InlineKeyboardButton("📅 Agenda", callback_data="agenda"),
    InlineKeyboardButton("✅ Tâches", callback_data="taches"),
    InlineKeyboardButton("📝 Notes", callback_data="notes"),
]])

_SETTINGS_KEYBOARD = InlineKeyboardMarkup([[
    InlineKeyboardButton("✏️ Modifier le budget", callback_data="set_budget"),
]])

_OUTILS_KEYBOARD = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("📓 Journal", callback_data="outils_journal"),
        InlineKeyboardButton("💡 Mes idées", callback_data="outils_ideas"),
    ],
    [
        InlineKeyboardButton("✍️ Rédiger un texte", callback_data="outils_write"),
    ],
])

_MONTHS_FR = {
    1: "janvier", 2: "février", 3: "mars", 4: "avril", 5: "mai", 6: "juin",
    7: "juillet", 8: "août", 9: "septembre", 10: "octobre", 11: "novembre", 12: "décembre",
}

_CAT_EMOJIS = {
    "restaurant": "🍽", "café": "☕", "coffee": "☕", "snack": "☕",
    "courses": "🛒", "alimentation": "🛒", "supermarché": "🛒",
    "transport": "🚗", "taxi": "🚗", "uber": "🚗", "train": "🚆",
    "loisirs": "🎮", "sortie": "🎉", "cinéma": "🎬",
    "santé": "💊", "pharmacie": "💊", "médecin": "🏥",
    "shopping": "👕", "vêtements": "👕",
    "abonnement": "📱", "abonnements": "📱",
    "logement": "🏠", "loyer": "🏠",
    "formation": "🎓",
}


def _cat_emoji(category: str) -> str:
    key = category.lower()
    for k, emoji in _CAT_EMOJIS.items():
        if k in key:
            return emoji
    return "💸"


def get_expense_keyboard(active: str = "month") -> InlineKeyboardMarkup:
    def btn(label, period):
        mark = " ✓" if period == active else ""
        return InlineKeyboardButton(f"{label}{mark}", callback_data=f"exp_{period}")
    return InlineKeyboardMarkup([
        [btn("Jour", "today"), btn("Semaine", "week")],
        [btn("Mois", "month"), btn("Année", "year")],
    ])


def format_expense_text(summary: dict) -> str:
    period_labels = {
        "today": "aujourd'hui",
        "week": "cette semaine",
        "month": "ce mois",
        "year": "cette année",
    }
    label = period_labels.get(summary["period"], "ce mois")

    if summary["count"] == 0:
        return f"💰 *Dépenses — {label}*\n\n_Aucune dépense enregistrée._"

    lines = [
        f"{_cat_emoji(cat)} {cat} · {amt:.2f} CHF"
        for cat, amt in sorted(summary["by_category"].items(), key=lambda x: -x[1])
    ]

    budget_line = ""
    budget = summary.get("budget")
    if budget and summary["period"] == "month":
        pct = (summary["total"] / budget) * 100
        if pct >= 100:
            icon, status = "🔴", "Budget dépassé !"
        elif pct >= 90:
            icon, status = "🚨", "Attention !"
        elif pct >= 70:
            icon, status = "⚠️", "Approche du budget"
        else:
            icon, status = "✅", f"{100 - pct:.0f}% restant"
        budget_line = f"\n\n{icon} *{summary['total']:.0f} / {budget:.0f} CHF* — _{status}_"

    return (
        f"💰 *Dépenses — {label}*\n"
        f"Total *{summary['total']:.2f} CHF* · {summary['count']} opération{'s' if summary['count'] > 1 else ''}\n\n"
        + "\n".join(lines)
        + budget_line
        + f"\n\n[📊 Voir le sheet]({summary['sheet_url']})"
    )


async def dispatch_all(actions: list[dict], update: Update, context: ContextTypes.DEFAULT_TYPE):
    for action in actions:
        await dispatch(action, update, context)


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
                title = "Agenda — 7 jours"
            else:
                days = int(params.get("days", 3))
                events = google_calendar.get_events_for_period(days, TIMEZONE)
                title = f"Agenda — {days} jours"

            tz = pytz.timezone(TIMEZONE)
            if not events:
                text = f"📅 *{title}*\n\n_Rien de prévu — journée libre !_ 🎉"
            else:
                lines = []
                for e in events:
                    if e["all_day"]:
                        time_str = "Toute la journée"
                    else:
                        try:
                            dt = datetime.fromisoformat(e["start"]).astimezone(tz)
                            time_str = dt.strftime("%H:%M")
                        except Exception:
                            time_str = "?"
                    loc = f" · 📍_{e['location']}_" if e["location"] else ""
                    lines.append(f"*{time_str}*  {e['title']}{loc}")
                text = f"📅 *{title}*\n\n" + "\n".join(lines)
            await msg.reply_text(text, parse_mode="Markdown")
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
            date_str = start_dt.strftime("%d/%m/%Y")
            time_str = start_dt.strftime("%H:%M")
            link = result.get("link", "")
            link_part = f"\n[Voir dans Google Calendar]({link})" if link else ""
            await msg.reply_text(
                f"✅ *Ajouté au calendrier*\n"
                f"📌 *{result['title']}*\n"
                f"🗓 {date_str} à {time_str}"
                f"{link_part}",
                parse_mode="Markdown",
            )
        except Exception as e:
            await _send_calendar_error(msg, e)

    elif name == "calendar_delete":
        try:
            ok = google_calendar.delete_event(params.get("event_id", ""))
            await msg.reply_text("🗑 Événement supprimé." if ok else "❌ Événement introuvable.")
        except Exception as e:
            await _send_calendar_error(msg, e)

    elif name == "task_add":
        try:
            google_tasks.add_task(params["title"], params.get("due_iso"))
            await msg.reply_text(
                f"✅ *Tâche ajoutée*\n{params['title']}",
                parse_mode="Markdown",
            )
        except Exception as e:
            await msg.reply_text(f"❌ Impossible d'ajouter la tâche : {e}")

    elif name == "task_list":
        try:
            tasks = google_tasks.list_tasks()
            if not tasks:
                await msg.reply_text("📋 *Tâches*\n\n_Aucune tâche — tout est à jour !_ 🎉", parse_mode="Markdown")
            else:
                lines = [f"{t['id']}. {t['title']}" for t in tasks]
                await msg.reply_text(
                    f"📋 *Tâches* · {len(tasks)} en cours\n\n" + "\n".join(lines),
                    parse_mode="Markdown",
                )
        except Exception as e:
            await msg.reply_text(f"❌ Impossible de lire les tâches : {e}")

    elif name == "task_done":
        try:
            ok = google_tasks.complete_task(int(params["task_id"]))
            if ok:
                await msg.reply_text(f"✅ Tâche #{params['task_id']} terminée 💪", parse_mode="Markdown")
            else:
                await msg.reply_text(f"❌ Tâche #{params['task_id']} introuvable.")
        except Exception as e:
            await msg.reply_text(f"❌ Erreur : {e}")

    elif name == "task_delete":
        try:
            ok = google_tasks.delete_task(int(params["task_id"]))
            await msg.reply_text(
                f"🗑 Tâche #{params['task_id']} supprimée." if ok else f"❌ Tâche #{params['task_id']} introuvable."
            )
        except Exception as e:
            await msg.reply_text(f"❌ Erreur : {e}")

    elif name == "note_add":
        try:
            content = params["content"]
            google_tasks.add_note(content)
            doc_line = ""
            try:
                from services.google_docs import create_note_doc
                now = datetime.now(pytz.timezone(TIMEZONE))
                title = f"Note — {now.strftime('%d/%m/%Y %H:%M')}"
                doc = create_note_doc(title=title, content=content)
                doc_line = f"\n[Voir dans Docs]({doc['url']})"
            except Exception:
                pass
            await msg.reply_text(
                f"📝 *Note sauvegardée*\n_{content}_"
                f"{doc_line}",
                parse_mode="Markdown",
            )
        except Exception as e:
            await msg.reply_text(f"❌ Impossible de sauvegarder la note : {e}")

    elif name == "note_list":
        try:
            notes = google_tasks.list_notes()
            if not notes:
                await msg.reply_text("📝 *Notes*\n\n_Aucune note pour l'instant._", parse_mode="Markdown")
            else:
                lines = [f"{n['id']}. {n['content']}" for n in notes]
                await msg.reply_text(
                    f"📝 *Notes* · {len(notes)}\n\n" + "\n".join(lines),
                    parse_mode="Markdown",
                )
        except Exception as e:
            await msg.reply_text(f"❌ Impossible de lire les notes : {e}")

    elif name == "weather":
        try:
            w = await weather_svc.get_weather(params.get("city"))
            await msg.reply_text(f"🌤 *Météo*\n\n{w}", parse_mode="Markdown")
        except Exception as e:
            await msg.reply_text(f"❌ Météo indisponible : {e}")

    elif name == "briefing":
        await send_briefing(msg.chat_id, context)

    elif name == "expense_add":
        try:
            from services import google_sheets
            result = google_sheets.add_expense(
                amount=float(params["amount"]),
                category=params.get("category", "Autre"),
                description=params.get("description", ""),
                date_iso=params.get("date_iso"),
            )
            warning = ""
            try:
                summary = google_sheets.get_summary("month")
                budget = summary.get("budget")
                if budget:
                    pct = (summary["total"] / budget) * 100
                    if pct >= 100:
                        warning = f"\n\n🔴 *Budget dépassé !* {summary['total']:.0f} / {budget:.0f} CHF"
                    elif pct >= 80:
                        warning = f"\n\n⚠️ Budget à *{pct:.0f}%* — {summary['total']:.0f} / {budget:.0f} CHF"
            except Exception:
                pass
            await msg.reply_text(
                f"💸 *Dépense enregistrée*\n"
                f"{_cat_emoji(result['category'])} {result['category']} · *{result['amount']:.2f} CHF* · {result['date']}"
                f"{warning}\n\n"
                f"[Voir le sheet]({result['sheet_url']})",
                parse_mode="Markdown",
            )
        except Exception as e:
            await msg.reply_text(f"❌ Impossible d'enregistrer la dépense : {e}")

    elif name == "expense_list":
        try:
            from services import google_sheets
            period = params.get("period", "month")
            summary = google_sheets.get_summary(period)
            await msg.reply_text(
                format_expense_text(summary),
                parse_mode="Markdown",
                reply_markup=get_expense_keyboard(period),
            )
        except Exception as e:
            await msg.reply_text(f"❌ Impossible de lire les dépenses : {e}")

    elif name == "settings":
        try:
            from services import google_sheets
            budget = google_sheets.get_budget()
            budget_str = f"*{budget:.0f} CHF*" if budget else "_Non défini_"
            await msg.reply_text(
                f"⚙️ *Paramètres*\n\n💰 Budget mensuel : {budget_str}",
                parse_mode="Markdown",
                reply_markup=_SETTINGS_KEYBOARD,
            )
        except Exception as e:
            await msg.reply_text(f"❌ Erreur : {e}")

    elif name == "currency_convert":
        try:
            from services import currency as currency_svc
            res = await currency_svc.convert(
                float(params["amount"]),
                params["from_currency"],
                params["to_currency"],
            )
            await msg.reply_text(
                f"💱 *{res['amount']:.2f} {res['from_currency']} → {res['result']:.2f} {res['to_currency']}*\n"
                f"_{res['from_name']} → {res['to_name']}_\n"
                f"Taux : 1 {res['from_currency']} = {res['rate']:.4f} {res['to_currency']}",
                parse_mode="Markdown",
            )
        except Exception as e:
            await msg.reply_text(f"❌ Conversion impossible : {e}")

    elif name == "journal_add":
        try:
            from services.google_docs import append_journal_entry
            from services.claude_ai import generate_summary, clean_journal_text
            raw = params["content"]
            content = clean_journal_text(raw)
            summary = generate_summary(content) if len(content) > 300 else None
            result = append_journal_entry(content=content, summary=summary)
            preview = content[:200] + ("..." if len(content) > 200 else "")
            await msg.reply_text(
                f"📓 *Journal — {result['date']}*\n"
                f"_{preview}_\n\n"
                f"[Ouvrir le journal]({result['url']})",
                parse_mode="Markdown",
            )
        except Exception as e:
            await msg.reply_text(f"❌ Impossible de sauvegarder le journal : {e}")

    elif name == "idea_add":
        try:
            google_tasks.add_idea(params["content"])
            await msg.reply_text(
                f"💡 *Idée notée*\n_{params['content']}_",
                parse_mode="Markdown",
            )
        except Exception as e:
            await msg.reply_text(f"❌ Impossible de sauvegarder l'idée : {e}")

    elif name == "idea_list":
        try:
            ideas = google_tasks.list_ideas()
            if not ideas:
                await msg.reply_text("💡 *Idées*\n\n_Aucune idée pour l'instant._", parse_mode="Markdown")
            else:
                lines = [f"{i['id']}. {i['content']}" for i in ideas]
                await msg.reply_text(
                    f"💡 *Idées* · {len(ideas)}\n\n" + "\n".join(lines),
                    parse_mode="Markdown",
                )
        except Exception as e:
            await msg.reply_text(f"❌ Impossible de lire les idées : {e}")

    elif name == "write_assist":
        write_type = params.get("type", "texte")
        await msg.reply_text(
            f"✍️ *{write_type.capitalize()}*\n\n{reply}",
            parse_mode="Markdown",
        )

    else:
        await msg.reply_text(reply or "Je n'ai pas compris, reformule ?")


async def _send_calendar_error(msg, e: Exception):
    if "pas encore connecté" in str(e) or "connecter_calendar" in str(e):
        await msg.reply_text(
            "❌ *Google Calendar non connecté*\n_Clique ci-dessous pour autoriser l'accès._",
            parse_mode="Markdown",
            reply_markup=_CALENDAR_ERROR_KEYBOARD,
        )
    else:
        await msg.reply_text(f"❌ Erreur calendrier : {e}")


async def send_briefing(chat_id: int, context):
    w = await weather_svc.get_weather()
    try:
        events = google_calendar.get_events_today(TIMEZONE)
    except Exception:
        events = []
    try:
        tasks = google_tasks.list_tasks()
    except Exception:
        tasks = []
    text = generate_briefing_text(w, events, tasks, TIMEZONE)
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="Markdown",
        reply_markup=_BRIEFING_KEYBOARD,
    )
