import asyncio
import os
import json
import logging
from aiohttp import web
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

ALLOWED_USER_ID = int(os.getenv("TELEGRAM_USER_ID", "0"))
PORT = int(os.getenv("PORT", "8080"))
_telegram_app = None

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📅 Agenda"), KeyboardButton("✅ Tâches"), KeyboardButton("📝 Notes")],
        [KeyboardButton("💸 Dépenses"), KeyboardButton("☀️ Briefing"), KeyboardButton("⚙️ Paramètres")],
        [KeyboardButton("🛠 Outils")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

_KEYBOARD_SHORTCUTS = {
    "📅 Agenda":        [{"action": "calendar_read_today", "params": {}, "reply": ""}],
    "✅ Tâches":        [{"action": "task_list", "params": {}, "reply": ""}],
    "📝 Notes":         [{"action": "note_list", "params": {}, "reply": ""}],
    "💸 Dépenses":      [{"action": "expense_list", "params": {"period": "month"}, "reply": ""}],
    "☀️ Briefing":      [{"action": "briefing", "params": {}, "reply": ""}],
    "⚙️ Paramètres":   [{"action": "settings", "params": {}, "reply": ""}],
}


def _is_authorized(update: Update) -> bool:
    return ALLOWED_USER_ID == 0 or update.effective_user.id == ALLOWED_USER_ID


def _get_base_url() -> str:
    for var in ("RENDER_EXTERNAL_URL", "RAILWAY_PUBLIC_DOMAIN"):
        val = os.getenv(var)
        if val:
            return val if val.startswith("http") else f"https://{val}"
    return os.getenv("BASE_URL", f"http://localhost:{PORT}")


def _calendar_connected() -> bool:
    return bool(os.getenv("GOOGLE_TOKEN_JSON")) or os.path.exists("google_token.json")


# ── Commandes Telegram ─────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    cal = "✅ Connecté" if _calendar_connected() else "❌ Non connecté — /connecter\\_calendar"
    await update.message.reply_text(
        "👋 Salut Bastien ! Je suis ton assistant personnel.\n\n"
        "Parle-moi naturellement :\n"
        "• _\"Qu'est-ce que j'ai aujourd'hui ?\"_\n"
        "• _\"Rdv dentiste mardi à 10h\"_\n"
        "• _\"J'ai dépensé 45 CHF au restaurant\"_\n"
        "• _\"Note : code wifi = abc123\"_\n\n"
        f"📅 Google Calendar : {cal}\n\n"
        "Les boutons en bas sont toujours disponibles 👇",
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD,
    )


async def cmd_debug_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    try:
        from services.google_calendar import _get_service, _get_all_calendar_ids
        from datetime import datetime
        import pytz

        service = _get_service()
        cal_ids = _get_all_calendar_ids(service)
        await update.message.reply_text(f"📋 Calendriers trouvés ({len(cal_ids)}) :\n" + "\n".join(f"• `{c}`" for c in cal_ids), parse_mode="Markdown")

        tz = pytz.timezone("Europe/Zurich")
        now = datetime.now(tz)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(hour=23, minute=59, second=59)

        total = 0
        for cal_id in cal_ids:
            result = service.events().list(
                calendarId=cal_id,
                timeMin=start.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True,
            ).execute()
            items = result.get("items", [])
            total += len(items)
            if items:
                names = ", ".join(i.get("summary", "?") for i in items)
                await update.message.reply_text(f"📅 `{cal_id[:30]}`\n→ {names}", parse_mode="Markdown")

        if total == 0:
            await update.message.reply_text("⚠️ Aucun événement trouvé dans aucun calendrier pour aujourd'hui.")
        else:
            await update.message.reply_text(f"✅ Total : {total} événement(s) trouvé(s)")
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur debug : {e}")


async def cmd_connecter_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id:
        await update.message.reply_text("❌ GOOGLE_CLIENT_ID manquant dans les variables d'environnement.")
        return
    base_url = _get_base_url()
    redirect_uri = f"{base_url}/oauth/callback"
    from urllib.parse import urlencode
    auth_url = "https://accounts.google.com/o/oauth2/auth?" + urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": "https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/tasks https://www.googleapis.com/auth/spreadsheets https://www.googleapis.com/auth/drive.file",
        "access_type": "offline",
        "prompt": "consent",
    })
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Connecter Google Calendar", url=auth_url)]])
    await update.message.reply_text(
        "Clique sur le bouton → connecte-toi avec Google → reviens automatiquement ✅",
        reply_markup=keyboard,
    )


async def cmd_agenda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    from bot.handlers.dispatcher import dispatch
    await dispatch({"action": "calendar_read_today", "params": {}, "reply": ""}, update, context)


async def cmd_taches(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    from bot.handlers.dispatcher import dispatch
    await dispatch({"action": "task_list", "params": {}, "reply": ""}, update, context)


async def cmd_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    from bot.handlers.dispatcher import dispatch
    await dispatch({"action": "note_list", "params": {}, "reply": ""}, update, context)


async def cmd_briefing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    from bot.handlers.dispatcher import dispatch
    await dispatch({"action": "briefing", "params": {}, "reply": ""}, update, context)


async def _process_text(user_text: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Traite un message texte (venant d'un texte ou d'un vocal transcrit)."""
    from services.claude_ai import parse_message
    from bot.handlers.dispatcher import dispatch_all
    history = context.user_data.get("history", [])
    actions = parse_message(user_text, history)
    history.append({"role": "user", "content": user_text})
    reply_summary = " | ".join(a.get("reply", "") for a in actions if a.get("reply"))
    history.append({"role": "assistant", "content": reply_summary})
    context.user_data["history"] = history[-12:]
    await dispatch_all(actions, update, context)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    user_text = update.message.text

    # Bouton Outils → sous-menu inline
    if user_text == "🛠 Outils":
        from bot.handlers.dispatcher import _OUTILS_KEYBOARD
        await update.message.reply_text(
            "🛠 *Outils*\n─────────────────\nQue veux-tu faire ?",
            parse_mode="Markdown",
            reply_markup=_OUTILS_KEYBOARD,
        )
        return

    # États d'attente
    if context.user_data.get("waiting_for") == "budget":
        try:
            clean = user_text.replace("'", "").replace(",", ".").replace(" ", "").replace("CHF", "").replace("chf", "")
            amount = float(clean)
            from services import google_sheets
            google_sheets.set_budget(amount)
            context.user_data.pop("waiting_for", None)
            context.user_data.pop("waiting_message_id", None)
            await update.message.reply_text(
                f"✅ *Budget mensuel défini : {amount:.0f} CHF*\n"
                f"Je t'alerterai quand tu approches de ce montant.",
                parse_mode="Markdown",
            )
        except ValueError:
            await update.message.reply_text("❌ Envoie juste un nombre (ex: 2000)")
        return

    if context.user_data.get("waiting_for") == "journal":
        context.user_data.pop("waiting_for", None)
        context.user_data.pop("waiting_message_id", None)
        from bot.handlers.dispatcher import dispatch_all
        await dispatch_all([{"action": "journal_add", "params": {"content": user_text}, "reply": ""}], update, context)
        return

    if context.user_data.get("waiting_for") == "idea":
        context.user_data.pop("waiting_for", None)
        context.user_data.pop("waiting_message_id", None)
        from bot.handlers.dispatcher import dispatch_all
        await dispatch_all([{"action": "idea_add", "params": {"content": user_text}, "reply": ""}], update, context)
        return

    if context.user_data.get("waiting_for") == "write_assist":
        context.user_data.pop("waiting_for", None)
        context.user_data.pop("waiting_message_id", None)
        await _process_text(f"Aide-moi à rédiger : {user_text}", update, context)
        return

    # Raccourcis clavier permanent
    if user_text in _KEYBOARD_SHORTCUTS:
        from bot.handlers.dispatcher import dispatch_all
        await update.message.chat.send_action("typing")
        await dispatch_all(_KEYBOARD_SHORTCUTS[user_text], update, context)
        return

    await update.message.chat.send_action("typing")
    try:
        await _process_text(user_text, update, context)
    except Exception as e:
        logger.error(f"Erreur : {e}", exc_info=True)
        await update.message.reply_text(f"⚠️ Erreur : {e}")


async def _set_waiting(context: ContextTypes.DEFAULT_TYPE, state: str, chat_id: int, text: str) -> None:
    """Efface le précédent message d'attente et définit un nouvel état."""
    prev_id = context.user_data.get("waiting_message_id")
    if prev_id and context.user_data.get("waiting_for"):
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=prev_id)
        except Exception:
            pass
    sent = await context.bot.send_message(chat_id, text, parse_mode="Markdown")
    context.user_data["waiting_for"] = state
    context.user_data["waiting_message_id"] = sent.message_id


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    voice_obj = update.message.voice or update.message.audio
    duration = getattr(voice_obj, "duration", 0) or 0
    if duration > 45:
        wait_msg = await update.message.reply_text("🎙️ _Transcription en cours (message long)..._", parse_mode="Markdown")
    else:
        wait_msg = await update.message.reply_text("🎙️ _J'écoute..._", parse_mode="Markdown")
    try:
        text, _ = await _transcribe_voice(update, context)
        if not text:
            await wait_msg.edit_text("❌ Je n'ai pas pu comprendre. Parle plus fort ou réessaie.")
            return

        await wait_msg.edit_text(f"🎤 _{text}_", parse_mode="Markdown")

        waiting = context.user_data.get("waiting_for")
        if waiting == "journal":
            context.user_data.pop("waiting_for", None)
            context.user_data.pop("waiting_message_id", None)
            from bot.handlers.dispatcher import dispatch_all
            await dispatch_all([{"action": "journal_add", "params": {"content": text}, "reply": ""}], update, context)
        elif waiting == "idea":
            context.user_data.pop("waiting_for", None)
            context.user_data.pop("waiting_message_id", None)
            from bot.handlers.dispatcher import dispatch_all
            await dispatch_all([{"action": "idea_add", "params": {"content": text}, "reply": ""}], update, context)
        elif waiting == "write_assist":
            context.user_data.pop("waiting_for", None)
            context.user_data.pop("waiting_message_id", None)
            await _process_text(f"Aide-moi à rédiger : {text}", update, context)
        else:
            await _process_text(text, update, context)
    except Exception as e:
        logger.error(f"Erreur vocal : {e}", exc_info=True)
        await wait_msg.edit_text(f"⚠️ Erreur transcription : {e}")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    wait_msg = await update.message.reply_text("🧾 _J'analyse la quittance..._", parse_mode="Markdown")
    try:
        import io
        from services.claude_ai import parse_receipt
        from services import google_sheets
        from bot.handlers.dispatcher import _cat_emoji

        photo = update.message.photo[-1]  # résolution maximale
        tg_file = await context.bot.get_file(photo.file_id)
        buf = io.BytesIO()
        await tg_file.download_to_memory(buf)
        image_bytes = buf.getvalue()

        data = parse_receipt(image_bytes)

        if not data or data.get("amount") is None:
            await wait_msg.edit_text(
                "❌ Je n'ai pas pu lire le montant sur cette image.\n"
                "_Essaie avec une photo plus nette, bien cadrée sur le total._",
                parse_mode="Markdown",
            )
            return

        result = google_sheets.add_expense(
            amount=float(data["amount"]),
            category=data.get("category", "Autre"),
            description=data.get("description", "Quittance"),
            date_iso=data.get("date_iso"),
        )

        warning = ""
        try:
            summary = google_sheets.get_summary("month")
            budget = summary.get("budget")
            if budget:
                pct = (summary["total"] / budget) * 100
                if pct >= 100:
                    warning = f"\n\n🔴 *Budget dépassé !* {summary['total']:.2f}/{budget:.0f} CHF"
                elif pct >= 80:
                    warning = f"\n\n⚠️ Budget à *{pct:.0f}%* — {summary['total']:.2f}/{budget:.0f} CHF"
        except Exception:
            pass

        await wait_msg.edit_text(
            f"💸 *Dépense extraite automatiquement*\n"
            f"─────────────────\n"
            f"{_cat_emoji(result['category'])} {result['category']}\n"
            f"💰 *{result['amount']:.2f} CHF*  ·  {result['date']}\n"
            f"📝 _{data.get('description', '')}_"
            f"{warning}\n"
            f"─────────────────\n"
            f"[📊 Google Sheet]({result['sheet_url']})",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Erreur photo quittance : {e}", exc_info=True)
        await wait_msg.edit_text(f"❌ Erreur lors de l'analyse : {e}")


async def _transcribe_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> tuple[str, int]:
    """Transcrit un message vocal. Retourne (texte, durée_secondes)."""
    import tempfile
    import speech_recognition as sr
    from pydub import AudioSegment

    voice = update.message.voice or update.message.audio
    if not voice:
        return "", 0

    duration = getattr(voice, "duration", 0) or 0
    tg_file = await context.bot.get_file(voice.file_id)

    with tempfile.TemporaryDirectory() as tmp:
        ogg_path = os.path.join(tmp, "voice.ogg")
        await tg_file.download_to_drive(ogg_path)

        audio = AudioSegment.from_ogg(ogg_path)
        recognizer = sr.Recognizer()

        CHUNK_MS = 50_000  # 50 secondes par chunk
        chunks = [audio[i:i + CHUNK_MS] for i in range(0, len(audio), CHUNK_MS)]
        texts = []

        for i, chunk in enumerate(chunks):
            wav_path = os.path.join(tmp, f"chunk_{i}.wav")
            chunk.export(wav_path, format="wav")
            with sr.AudioFile(wav_path) as source:
                audio_data = recognizer.record(source)
            try:
                t = recognizer.recognize_google(audio_data, language="fr-FR")
                if t:
                    texts.append(t)
            except sr.UnknownValueError:
                pass
            except sr.RequestError as e:
                raise RuntimeError(f"Service de transcription indisponible : {e}")

        return " ".join(texts), duration


# ── Routes web ─────────────────────────────────────────────────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère les boutons inline (briefing, erreurs calendrier)."""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id

    action_map = {
        "agenda": "calendar_read_today",
        "taches": "task_list",
        "notes": "note_list",
    }

    if query.data in action_map:
        from bot.handlers.dispatcher import dispatch as _dispatch
        from services import tasks_db, google_calendar, weather as weather_svc

        action_name = action_map[query.data]
        try:
            if action_name == "calendar_read_today":
                events = google_calendar.get_events_today(os.getenv("TIMEZONE", "Europe/Zurich"))
                text = google_calendar.format_events_text(events, os.getenv("TIMEZONE", "Europe/Zurich"))
                await context.bot.send_message(chat_id, f"📅 *Agenda d'aujourd'hui*\n{text}", parse_mode="Markdown")
            elif action_name == "task_list":
                tasks = await tasks_db.list_tasks()
                if not tasks:
                    await context.bot.send_message(chat_id, "🎉 Aucune tâche en cours !")
                else:
                    lines = "\n".join(f"• #{t['id']} {t['title']}" for t in tasks)
                    await context.bot.send_message(chat_id, f"📋 *Tâches en cours :*\n{lines}", parse_mode="Markdown")
            elif action_name == "note_list":
                notes = await tasks_db.list_notes()
                if not notes:
                    await context.bot.send_message(chat_id, "📝 Aucune note.")
                else:
                    lines = "\n".join(f"• #{n['id']} {n['content']}" for n in notes)
                    await context.bot.send_message(chat_id, f"📝 *Tes notes :*\n{lines}", parse_mode="Markdown")
        except Exception as e:
            if "pas encore connecté" in str(e):
                from bot.handlers.dispatcher import _CALENDAR_ERROR_KEYBOARD
                await context.bot.send_message(
                    chat_id,
                    "📅 Google Calendar n'est pas connecté.",
                    reply_markup=_CALENDAR_ERROR_KEYBOARD,
                )
            else:
                await context.bot.send_message(chat_id, f"❌ Erreur : {e}")

    elif query.data.startswith("exp_"):
        period = query.data[4:]  # today / week / month / year
        from services import google_sheets
        from bot.handlers.dispatcher import format_expense_text, get_expense_keyboard
        try:
            summary = google_sheets.get_summary(period)
            await query.message.edit_text(
                format_expense_text(summary),
                parse_mode="Markdown",
                reply_markup=get_expense_keyboard(period),
            )
        except Exception as e:
            await query.message.edit_text(f"❌ Erreur : {e}")

    elif query.data == "set_budget":
        await _set_waiting(context, "budget", chat_id,
            "💰 *Quel est ton budget mensuel en CHF ?*\n_Envoie juste le montant (ex: 2000)_")

    elif query.data == "outils_journal":
        await _set_waiting(context, "journal", chat_id,
            "📓 _Raconte-moi ta journée ou ce que tu veux noter..._\n_(tu peux aussi envoyer un vocal)_")

    elif query.data == "outils_ideas":
        try:
            from services import google_tasks
            ideas = google_tasks.list_ideas()
            if not ideas:
                await context.bot.send_message(
                    chat_id,
                    "💡 *Idées*\n─────────────────\n_Aucune idée pour l'instant._\n\nDis-moi une idée à sauvegarder !",
                    parse_mode="Markdown",
                )
            else:
                lines = [f"  `#{i['id']}`  {i['content']}" for i in ideas]
                await context.bot.send_message(
                    chat_id,
                    f"💡 *Tes idées* ({len(ideas)})\n─────────────────\n" + "\n".join(lines),
                    parse_mode="Markdown",
                )
        except Exception as e:
            await context.bot.send_message(chat_id, f"❌ Erreur : {e}")

    elif query.data == "outils_write":
        await _set_waiting(context, "write_assist", chat_id,
            "✍️ _Qu'est-ce que tu veux rédiger ?_\n_Décris-moi le contexte (ex: un email à mon patron pour demander des vacances)_")

    elif query.data == "connecter_calendar":
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        base_url = _get_base_url()
        redirect_uri = f"{base_url}/oauth/callback"
        from urllib.parse import urlencode
        auth_url = "https://accounts.google.com/o/oauth2/auth?" + urlencode({
            "response_type": "code", "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": "https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/tasks https://www.googleapis.com/auth/spreadsheets https://www.googleapis.com/auth/drive.file",
            "access_type": "offline", "prompt": "consent",
        })
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        await context.bot.send_message(
            chat_id,
            "Clique pour connecter Google Calendar :",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Connecter", url=auth_url)]]),
        )


async def handle_telegram_webhook(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        update = Update.de_json(data, _telegram_app.bot)
        await _telegram_app.process_update(update)
    except Exception as e:
        logger.error(f"Erreur webhook : {e}")
    return web.Response(text="OK")


async def oauth_callback(request: web.Request) -> web.Response:
    code = request.rel_url.query.get("code")
    error = request.rel_url.query.get("error")
    if error or not code:
        return web.Response(text=f"❌ Erreur : {error or 'code manquant'}", content_type="text/html")
    try:
        from google_auth_oauthlib.flow import Flow
        base_url = _get_base_url()
        redirect_uri = f"{base_url}/oauth/callback"
        flow = Flow.from_client_config(
            {"web": {
                "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }},
            scopes=[
                "https://www.googleapis.com/auth/calendar",
                "https://www.googleapis.com/auth/tasks",
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive.file",
            ],
            redirect_uri=redirect_uri,
        )
        flow.fetch_token(code=code)
        creds = flow.credentials
        token_data = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": list(creds.scopes) if creds.scopes else [
                "https://www.googleapis.com/auth/calendar",
                "https://www.googleapis.com/auth/tasks",
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive.file",
            ],
        }
        with open("google_token.json", "w") as f:
            json.dump(token_data, f)
        if _telegram_app and ALLOWED_USER_ID:
            token_json_str = json.dumps(token_data)
            await _telegram_app.bot.send_message(
                chat_id=ALLOWED_USER_ID,
                text="✅ *Google Calendar connecté !*\n\n"
                     "⚠️ *Action requise pour que ça reste connecté après redémarrage :*\n"
                     "1. Va sur Render → ton service → *Environment*\n"
                     "2. Ajoute une variable :\n"
                     "   Nom : `GOOGLE_TOKEN_JSON`\n"
                     "   Valeur : le JSON ci-dessous\n"
                     "3. Clique *Save Changes*\n\n"
                     f"`{token_json_str}`",
                parse_mode="Markdown",
            )
        return web.Response(
            text='<!DOCTYPE html><html><head><meta charset="utf-8"></head>'
                 '<body style="font-family:sans-serif;text-align:center;padding:60px;background:#0f0f23;color:white;">'
                 '<h1>✅ Google Calendar connecté !</h1><p>Ferme cette page et reviens sur Telegram.</p>'
                 '</body></html>',
            content_type="text/html",
        )
    except Exception as e:
        logger.error(f"Erreur OAuth : {e}", exc_info=True)
        return web.Response(text=f"❌ Erreur : {e}", content_type="text/html")


async def trigger_briefing(request: web.Request) -> web.Response:
    secret = request.rel_url.query.get("secret")
    if secret != os.getenv("CRON_SECRET", ""):
        return web.Response(status=403, text="Forbidden")
    try:
        from bot.handlers.dispatcher import send_briefing
        await send_briefing(ALLOWED_USER_ID, _telegram_app)
        return web.Response(text="OK")
    except Exception as e:
        return web.Response(status=500, text=str(e))


async def health(request: web.Request) -> web.Response:
    return web.Response(text="OK")


# ── Point d'entrée ─────────────────────────────────────────────────────────────

async def _run():
    global _telegram_app

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN manquant")

    base_url = _get_base_url()
    use_webhook = not base_url.startswith("http://localhost")

    builder = ApplicationBuilder().token(token)
    if use_webhook:
        builder = builder.updater(None)
    telegram_app = builder.build()
    _telegram_app = telegram_app

    telegram_app.add_handler(CommandHandler("start", cmd_start))
    telegram_app.add_handler(CommandHandler("debug_calendar", cmd_debug_calendar))
    telegram_app.add_handler(CommandHandler("connecter_calendar", cmd_connecter_calendar))
    telegram_app.add_handler(CommandHandler("agenda", cmd_agenda))
    telegram_app.add_handler(CommandHandler("taches", cmd_taches))
    telegram_app.add_handler(CommandHandler("notes", cmd_notes))
    telegram_app.add_handler(CommandHandler("briefing", cmd_briefing))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    telegram_app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    telegram_app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    telegram_app.add_handler(CallbackQueryHandler(handle_callback))

    # Démarrer le serveur web
    web_app = web.Application()
    web_app.router.add_get("/", health)
    web_app.router.add_get("/health", health)
    web_app.router.add_get("/oauth/callback", oauth_callback)
    web_app.router.add_post(f"/webhook/{token}", handle_telegram_webhook)
    web_app.router.add_get("/cron/briefing", trigger_briefing)

    runner = web.AppRunner(web_app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    logger.info(f"Serveur web démarré sur le port {PORT}")

    async with telegram_app:
        await telegram_app.start()

        if use_webhook:
            webhook_url = f"{base_url}/webhook/{token}"
            await telegram_app.bot.set_webhook(webhook_url)
            logger.info(f"✅ Webhook : {webhook_url}")
        else:
            await telegram_app.updater.start_polling()
            logger.info("🔄 Mode polling (local)")

        logger.info("🤖 Bastien Agent opérationnel !")

        # Envoie le clavier permanent dès le démarrage
        if ALLOWED_USER_ID:
            try:
                await telegram_app.bot.send_message(
                    chat_id=ALLOWED_USER_ID,
                    text="🤖 _Prêt !_",
                    parse_mode="Markdown",
                    reply_markup=MAIN_KEYBOARD,
                )
            except Exception:
                pass

        await asyncio.Event().wait()  # tourne indéfiniment


def main():
    asyncio.run(_run())


if __name__ == "__main__":
    main()
