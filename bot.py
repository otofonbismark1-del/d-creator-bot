import logging
import os
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler
from telegram import Update
from dotenv import load_dotenv

from database import init_db
from updater import start_scheduler
from handlers.start import start, get_name, get_tiktok, get_youtube, get_instagram, WAITING_NAME, WAITING_TIKTOK, WAITING_YOUTUBE, WAITING_INSTAGRAM
from handlers.videos import add_video, handle_video_link, WAITING_LINK
from handlers.stats import stats_command
from handlers.admin import admin_panel, admin_callback

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def main():
    init_db()
    app = Application.builder().token(os.getenv("BOT_TOKEN")).build()

    # Регистрация пользователя
    reg_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAITING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            WAITING_TIKTOK: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_tiktok)],
            WAITING_YOUTUBE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_youtube)],
            WAITING_INSTAGRAM: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_instagram)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    # Добавление ролика
    video_conv = ConversationHandler(
        entry_points=[CommandHandler("add", add_video)],
        states={
            WAITING_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_video_link)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    app.add_handler(reg_conv)
    app.add_handler(video_conv)
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))

    start_scheduler()
    logging.info("Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
