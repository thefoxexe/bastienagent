import os
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

ALLOWED_USER_ID = int(os.getenv("TELEGRAM_USER_ID", "0"))


def _is_authorized(update: Update) -> bool:
    return ALLOWED_USER_ID == 0 or update.effective_user.id == ALLOWED_USER_ID


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    await update.message.reply_text(
        "👋 Salut Bastien ! Je suis ton assistant personnel.\n\n"
        "Tu peux me parler naturellement, par exemple :\n"
        "• _\"Qu'est-ce que j'ai aujourd'hui ?\"_\n"
        "• _\"Crée un rdv chez le dentiste mardi à 10h\"_\n"
        "• _\"Ajoute à ma liste : appeler Tom\"_\n"
        "• _\"Note : mot de passe wifi = abc123\"_\n"
        "• _\"Donne-moi la météo\"_\n\n"
        "Commandes rapides :\n"
        "/agenda — agenda d'aujourd'hui\n"
        "/taches — tes tâches en cours\n"
        "/notes — tes notes\n"
        "/briefing — briefing complet maintenant",
        parse_mode="Markdown",
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
        logger.warning(f"Message non autorisé de {update.effective_user.id}")
        return

    user_text = update.message.text
    logger.info(f"Message reçu : {user_text}")

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
        logger.error(f"Erreur traitement message : {e}", exc_info=True)
        await update.message.reply_text(
            f"⚠️ Une erreur est survenue : {e}\nRéessaie ou contacte-moi si ça persiste."
        )


def main():
    from services.tasks_db import init_db
    from bot.scheduler import setup_scheduler
    import asyncio

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN manquant dans .env")

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("agenda", cmd_agenda))
    app.add_handler(CommandHandler("taches", cmd_taches))
    app.add_handler(CommandHandler("notes", cmd_notes))
    app.add_handler(CommandHandler("briefing", cmd_briefing))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    async def post_init(application):
        await init_db()
        scheduler = setup_scheduler(application)
        scheduler.start()
        logger.info("🤖 Bastien Agent démarré !")

    app.post_init = post_init
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
