import os
import json
import logging
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
_telegram_app = None


def _is_authorized(update: Update) -> bool:
    return ALLOWED_USER_ID == 0 or update.effective_user.id == ALLOWED_USER_ID


def _get_base_url() -> str:
    for env_var in ("RENDER_EXTERNAL_URL", "RAILWAY_PUBLIC_DOMAIN"):
        val = os.getenv(env_var)
        if val:
            return val if val.startswith("http") else f"https://{val}"
    return os.getenv("BASE_URL", f"http://localhost:{PORT}")


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
        "• _\"Ajoute acheter du pain à ma liste\"_\n"
        "• _\"Note : code wifi = abc123\"_\n"
        "• _\"Météo ?\"_\n\n"
        f"📅 Google Calendar : {cal}\n\n"
        "Commandes :\n"
        "/agenda — agenda du jour\n"
        "/taches — tâches en cours\n"
        "/notes — tes notes\n"
        "/briefing — briefing maintenant\n"
        "/connecter\\_calendar — connecter Google Calendar",
        parse_mode="Markdown",
    )


def _calendar_connected() -> bool:
    return bool(os.getenv("GOOGLE_TOKEN_JSON")) or os.path.exists("google_token.json")


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
        "scope": "https://www.googleapis.com/auth/calendar",
        "access_type": "offline",
        "prompt": "consent",
    })

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Connecter Google Calendar", url=auth_url)]])
    await update.message.reply_text(
        "Clique sur le bouton ci-dessous :\n"
        "→ Connecte-toi avec Google\n"
        "→ Reviens ici automatiquement ✅",
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


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
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


# ── Routes web ─────────────────────────────────────────────────────────────────

async def handle_telegram_webhook(request: web.Request) -> web.Response:
    """Reçoit les mises à jour Telegram via webhook."""
    try:
        data = await request.json()
        update = Update.de_json(data, _telegram_app.bot)
        await _telegram_app.process_update(update)
    except Exception as e:
        logger.error(f"Erreur webhook Telegram : {e}")
    return web.Response(text="OK")


async def oauth_callback(request: web.Request) -> web.Response:
    """Reçoit le code OAuth Google et échange contre un token."""
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

        if _telegram_app and ALLOWED_USER_ID:
            await _telegram_app.bot.send_message(
                chat_id=ALLOWED_USER_ID,
                text="✅ Google Calendar connecté ! Essaie /agenda",
            )

        return web.Response(
            text="""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="font-family:sans-serif;text-align:center;padding:60px;background:#0f0f23;color:white;">
<h1>✅ Google Calendar connecté !</h1><p>Tu peux fermer cette page et revenir sur Telegram.</p>
</body></html>""",
            content_type="text/html",
        )
    except Exception as e:
        logger.error(f"Erreur OAuth : {e}", exc_info=True)
        return web.Response(text=f"❌ Erreur : {e}", content_type="text/html")


async def trigger_briefing(request: web.Request) -> web.Response:
    """Endpoint appelé par cron-job.org pour le briefing quotidien."""
    secret = request.rel_url.query.get("secret")
    if secret != os.getenv("CRON_SECRET", ""):
        return web.Response(status=403, text="Forbidden")
    try:
        from bot.handlers.dispatcher import send_briefing
        await send_briefing(ALLOWED_USER_ID, _telegram_app)
        return web.Response(text="Briefing envoyé !")
    except Exception as e:
        logger.error(f"Erreur briefing cron : {e}")
        return web.Response(status=500, text=str(e))


async def health(request: web.Request) -> web.Response:
    return web.Response(text="OK")


# ── Démarrage ──────────────────────────────────────────────────────────────────

def main():
    import asyncio
    from services.tasks_db import init_db

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN manquant")

    base_url = _get_base_url()
    use_webhook = not base_url.startswith("http://localhost")

    app_builder = ApplicationBuilder().token(token)
    if use_webhook:
        app_builder = app_builder.updater(None)  # Désactive le polling
    telegram_app = app_builder.build()

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

        web_app = web.Application()
        web_app.router.add_get("/", health)
        web_app.router.add_get("/health", health)
        web_app.router.add_get("/oauth/callback", oauth_callback)
        web_app.router.add_post(f"/webhook/{token}", handle_telegram_webhook)
        web_app.router.add_get("/cron/briefing", trigger_briefing)

        runner = web.AppRunner(web_app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", PORT)
        await site.start()

        if use_webhook:
            webhook_url = f"{base_url}/webhook/{token}"
            await application.bot.set_webhook(webhook_url)
            logger.info(f"✅ Webhook Telegram configuré : {webhook_url}")
        else:
            logger.info("🔄 Mode polling (local)")

        logger.info(f"🤖 Bastien Agent démarré sur port {PORT}")

    telegram_app.post_init = post_init

    if use_webhook:
        asyncio.get_event_loop().run_until_complete(telegram_app.initialize())
        asyncio.get_event_loop().run_until_complete(telegram_app.start())
        asyncio.get_event_loop().run_until_complete(telegram_app.post_init(telegram_app))

        async def run_forever():
            while True:
                await asyncio.sleep(3600)

        asyncio.get_event_loop().run_until_complete(run_forever())
    else:
        telegram_app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
