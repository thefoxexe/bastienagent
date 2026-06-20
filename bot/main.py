import os
import json
import logging
import threading
from aiohttp import web
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

ALLOWED_USER_ID = int(os.getenv("TELEGRAM_USER_ID", "0"))
PORT = int(os.getenv("PORT", "8080"))

# Référence globale à l'app Telegram pour le callback OAuth
_telegram_app = None


def _is_authorized(update: Update) -> bool:
    return ALLOWED_USER_ID == 0 or update.effective_user.id == ALLOWED_USER_ID


def _get_base_url() -> str:
    railway_url = os.getenv("RAILWAY_PUBLIC_DOMAIN")
    if railway_url:
        return f"https://{railway_url}"
    render_url = os.getenv("RENDER_EXTERNAL_URL")
    if render_url:
        return render_url
    return os.getenv("BASE_URL", f"http://localhost:{PORT}")


# ── Handlers Telegram ──────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    calendar_status = "✅ Connecté" if os.path.exists("google_token.json") or os.getenv("GOOGLE_TOKEN_JSON") else "❌ Non connecté — /connecter_calendar"
    await update.message.reply_text(
        "👋 Salut Bastien ! Je suis ton assistant personnel.\n\n"
        "Tu peux me parler naturellement :\n"
        "• _\"Qu'est-ce que j'ai aujourd'hui ?\"_\n"
        "• _\"Rdv dentiste mardi à 10h\"_\n"
        "• _\"Ajoute acheter du pain à ma liste\"_\n"
        "• _\"Note : code wifi = abc123\"_\n"
        "• _\"Météo ?\"_\n\n"
        "📅 Google Calendar : " + calendar_status + "\n\n"
        "Commandes :\n"
        "/agenda — agenda du jour\n"
        "/taches — tâches en cours\n"
        "/notes — tes notes\n"
        "/briefing — briefing complet\n"
        "/connecter\\_calendar — connecter Google Calendar",
        parse_mode="Markdown",
    )


async def cmd_connecter_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return

    base_url = _get_base_url()
    redirect_uri = f"{base_url}/oauth/callback"

    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id:
        await update.message.reply_text("❌ GOOGLE_CLIENT_ID manquant dans les variables d'environnement.")
        return

    from urllib.parse import urlencode
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": "https://www.googleapis.com/auth/calendar",
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_url = "https://accounts.google.com/o/oauth2/auth?" + urlencode(params)

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Connecter Google Calendar", url=auth_url)]])
    await update.message.reply_text(
        "Clique sur le bouton pour connecter ton Google Calendar.\n"
        "Tu seras redirigé vers Google, puis automatiquement revenu ici.",
        reply_markup=keyboard,
    )
    logger.info(f"OAuth URL générée avec redirect_uri={redirect_uri}")


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


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        logger.warning(f"Message non autorisé de {update.effective_user.id}")
        return

    user_text = update.message.text
    await update.message.chat.send_action("typing")

    try:
        from services.claude_ai import parse_message
        from bot.handlers.dispatcher import dispatch

        history = context.user_data.get("history", [])
        action = parse_message(user_text, history)

        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": action.get("reply", "")})
        context.user_data["history"] = history[-12:]

        await dispatch(action, update, context)
    except Exception as e:
        logger.error(f"Erreur message : {e}", exc_info=True)
        await update.message.reply_text(f"⚠️ Erreur : {e}")


# ── Serveur web OAuth callback ─────────────────────────────────────────────────

async def oauth_callback(request: web.Request) -> web.Response:
    code = request.rel_url.query.get("code")
    error = request.rel_url.query.get("error")

    if error:
        logger.error(f"OAuth erreur : {error}")
        return web.Response(text="❌ Autorisation refusée.", content_type="text/html")

    if not code:
        return web.Response(text="❌ Code manquant.", content_type="text/html")

    try:
        from google_auth_oauthlib.flow import Flow

        base_url = _get_base_url()
        redirect_uri = f"{base_url}/oauth/callback"

        creds_data = {
            "web": {
                "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        }

        flow = Flow.from_client_config(
            creds_data,
            scopes=["https://www.googleapis.com/auth/calendar"],
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
            "scopes": list(creds.scopes) if creds.scopes else ["https://www.googleapis.com/auth/calendar"],
        }

        with open("google_token.json", "w") as f:
            json.dump(token_data, f)

        logger.info("Token Google Calendar sauvé !")

        # Notifier Bastien via Telegram
        if _telegram_app and ALLOWED_USER_ID:
            try:
                await _telegram_app.bot.send_message(
                    chat_id=ALLOWED_USER_ID,
                    text="✅ Google Calendar connecté ! Tu peux maintenant utiliser /agenda et créer des événements.",
                )
            except Exception as e:
                logger.error(f"Erreur notification Telegram : {e}")

        html = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Bastien Agent</title></head>
<body style="font-family:sans-serif;text-align:center;padding:50px;background:#1a1a2e;color:white;">
<h1>✅ Google Calendar connecté !</h1>
<p>Tu peux fermer cette page et revenir sur Telegram.</p>
</body></html>"""
        return web.Response(text=html, content_type="text/html")

    except Exception as e:
        logger.error(f"Erreur OAuth callback : {e}", exc_info=True)
        return web.Response(text=f"❌ Erreur : {e}", content_type="text/html")


async def health(request: web.Request) -> web.Response:
    return web.Response(text="OK")


def create_web_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/oauth/callback", oauth_callback)
    app.router.add_get("/health", health)
    app.router.add_get("/", health)
    return app


# ── Point d'entrée ─────────────────────────────────────────────────────────────

def main():
    import asyncio
    from services.tasks_db import init_db
    from bot.scheduler import setup_scheduler

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN manquant dans .env")

    telegram_app = ApplicationBuilder().token(token).build()

    global _telegram_app
    _telegram_app = telegram_app

    telegram_app.add_handler(CommandHandler("start", cmd_start))
    telegram_app.add_handler(CommandHandler("connecter_calendar", cmd_connecter_calendar))
    telegram_app.add_handler(CommandHandler("agenda", cmd_agenda))
    telegram_app.add_handler(CommandHandler("taches", cmd_taches))
    telegram_app.add_handler(CommandHandler("notes", cmd_notes))
    telegram_app.add_handler(CommandHandler("briefing", cmd_briefing))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    async def post_init(application):
        await init_db()
        scheduler = setup_scheduler(application)
        scheduler.start()

        # Démarrer le serveur web OAuth en parallèle
        web_app = create_web_app()
        runner = web.AppRunner(web_app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", PORT)
        await site.start()
        logger.info(f"🤖 Bastien Agent démarré ! Web server sur port {PORT}")

    telegram_app.post_init = post_init
    telegram_app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
