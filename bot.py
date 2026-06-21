import logging
import os
from telegram import Update
from telegram.ext import (Application, CommandHandler, MessageHandler,
                           filters, ConversationHandler, CallbackQueryHandler)
from dotenv import load_dotenv

from database import init_db
from updater import start_scheduler
from handlers.start import (start, get_name, get_tiktok, get_youtube, get_instagram,
                             main_menu, WAITING_NAME, WAITING_TIKTOK, WAITING_YOUTUBE, WAITING_INSTAGRAM)
from handlers.videos import (add_video, handle_video_link, handle_ig_views_input,
                              my_videos_command, video_callback, refresh_views_command,
                              WAITING_LINK, WAITING_IG_VIEWS)
from handlers.stats import stats_command, periods_command
from handlers.admin import admin_panel, admin_callback, handle_admin_text

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ── Кнопки нижнего меню → команды ──
BUTTON_MAP = {
    "➕ Добавить ролик": "add",
    "📊 Статистика": "stats",
    "🎬 Мои ролики": "myvideos",
    "📅 Периоды и выплаты": "periods",
    "🔄 Обновить просмотры": "refresh",
}

async def menu_button_handler(update: Update, ctx):
    """Роутер кнопок нижнего меню"""
    text = update.message.text

    # Сначала отдать в очередь Instagram edit
    if ctx.user_data.get("waiting_ig_edit"):
        await handle_ig_edit(update, ctx)
        return

    # Отдать в очередь пароля/тарифа
    if await handle_admin_text(update, ctx):
        return

    if text == "➕ Добавить ролик":
        result = await add_video(update, ctx)
        if result is not None:
            ctx.user_data["_video_conv_state"] = result
        return
    elif text == "📊 Статистика":
        await stats_command(update, ctx)
    elif text == "🎬 Мои ролики":
        await my_videos_command(update, ctx)
    elif text == "📅 Периоды и выплаты":
        await periods_command(update, ctx)
    elif text == "🔄 Обновить просмотры":
        await refresh_views_command(update, ctx)

async def handle_ig_edit(update: Update, ctx):
    """Обработка ввода новых просмотров Instagram"""
    from database import get_creator, set_pending_views, get_video_by_id
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    try:
        views = int(update.message.text.strip().replace(" ", "").replace(",", ""))
    except ValueError:
        await update.message.reply_text("❌ Введи число, например: 25000")
        return
    video_id = ctx.user_data.get("edit_ig_video_id")
    creator = get_creator(update.effective_user.id)
    video = get_video_by_id(video_id)
    if not video or video["creator_id"] != creator["id"]:
        await update.message.reply_text("❌ Ролик не найден.")
        ctx.user_data["waiting_ig_edit"] = False
        return
    set_pending_views(video_id, views)
    admin_id = ctx.bot_data.get("admin_id")
    if admin_id:
        kb = [[InlineKeyboardButton(
            f"✅ Одобрить {views:,}",
            callback_data=f"adm_approve_ig_{video_id}_{update.effective_user.id}"
        )]]
        await ctx.bot.send_message(
            admin_id,
            f"✏️ {creator['name']} обновил просмотры Instagram!\n🔗 {video['url']}\n"
            f"👁 Старые: {video['views']:,} → Новые: {views:,}",
            reply_markup=InlineKeyboardMarkup(kb)
        )
    await update.message.reply_text(
        f"✅ Новые просмотры ({views:,}) отправлены на проверку!",
        reply_markup=main_menu()
    )
    ctx.user_data["waiting_ig_edit"] = False

def main():
    init_db()
    app = Application.builder().token(os.getenv("BOT_TOKEN")).build()

    # Регистрация
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

    # Добавление ролика по команде /add
    video_conv = ConversationHandler(
        entry_points=[CommandHandler("add", add_video)],
        states={
            WAITING_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_video_link)],
            WAITING_IG_VIEWS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ig_views_input)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    app.add_handler(reg_conv)
    app.add_handler(video_conv)
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^adm_"))
    app.add_handler(CallbackQueryHandler(video_callback, pattern="^(del_video_|edit_ig_)"))
    # Все кнопки меню и текстовые вводы
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.Regex(
            r"^(➕ Добавить ролик|📊 Статистика|🎬 Мои ролики|📅 Периоды и выплаты|🔄 Обновить просмотры)$"
        ),
        menu_button_handler
    ))
    # Все остальные текстовые сообщения (пароль, тариф, instagram edit, ссылки)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_button_handler))

    start_scheduler()
    logging.info("D-Creator бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
