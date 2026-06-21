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

async def handle_ig_edit(update: Update, ctx):
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
    if not video or not creator or video["creator_id"] != creator["id"]:
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

async def universal_text_handler(update: Update, ctx):
    """Единый обработчик всех текстовых сообщений вне ConversationHandler"""
    text = update.message.text.strip()

    # 1. Instagram edit (ожидаем число просмотров)
    if ctx.user_data.get("waiting_ig_edit"):
        await handle_ig_edit(update, ctx)
        return

    # 2. Пароль / тариф от админа
    if await handle_admin_text(update, ctx):
        return

    # 3. Кнопки меню
    if text == "➕ Добавить ролик":
        await update.message.reply_text("🔗 Отправь ссылку на ролик (YouTube, TikTok или Instagram):")
        ctx.user_data["waiting_video_link"] = True
        return
    elif text == "📊 Статистика":
        await stats_command(update, ctx); return
    elif text == "🎬 Мои ролики":
        await my_videos_command(update, ctx); return
    elif text == "📅 Периоды и выплаты":
        await periods_command(update, ctx); return
    elif text == "🔄 Обновить просмотры":
        await refresh_views_command(update, ctx); return

    # 4. Ожидаем ссылку на ролик
    if ctx.user_data.get("waiting_video_link"):
        ctx.user_data["waiting_video_link"] = False
        await _process_video_link(update, ctx, text)
        return

    # 5. Ожидаем просмотры Instagram (после ссылки)
    if ctx.user_data.get("waiting_ig_views"):
        ctx.user_data["waiting_ig_views"] = False
        await _process_ig_views(update, ctx, text)
        return

async def _process_video_link(update: Update, ctx, url: str):
    from handlers.videos import detect_platform, get_youtube_video_id, fetch_youtube_views, fetch_tiktok_views
    from database import get_creator, add_video_db, get_current_period, get_creator_rate, calc_payout

    creator = get_creator(update.effective_user.id)
    if not creator:
        await update.message.reply_text("❗ Сначала зарегистрируйся — /start")
        return

    platform = detect_platform(url)
    if not platform:
        await update.message.reply_text(
            "❌ Не могу определить платформу. Отправь ссылку YouTube, TikTok или Instagram.\n\nПопробуй ещё раз — отправь ссылку:",
        )
        ctx.user_data["waiting_video_link"] = True
        return

    await update.message.reply_text(f"⏳ Получаю данные с {platform.capitalize()}...")

    period = get_current_period()
    rate = get_creator_rate(creator["id"], period["id"]) if period else {"rate_type":"per_1000","rate_value":60,"rate_fix":0}
    rate_str = (f"{rate['rate_value']:.0f} ₽/1000 просм." if rate["rate_type"] == "per_1000"
                else f"{rate['rate_fix']:.0f}₽ за ролик + {rate['rate_value']:.0f}₽/1000")

    # Проверка дубликата
    from database import get_videos_by_creator
    existing = get_videos_by_creator(creator["id"])
    if any(v["url"].rstrip("/") == url.rstrip("/") for v in existing):
        await update.message.reply_text(
            "⚠️ Этот ролик уже добавлен!\n\nОтправь другую ссылку или нажми 📊 Статистика.",
            reply_markup=main_menu()
        )
        return

    if platform == "youtube":
        vid_id = get_youtube_video_id(url)
        if not vid_id:
            await update.message.reply_text("❌ Не могу найти ID видео. Проверь ссылку и отправь ещё раз:")
            ctx.user_data["waiting_video_link"] = True
            return
        title, views = fetch_youtube_views(vid_id)
        if views is None:
            await update.message.reply_text("❌ Ошибка YouTube API. Проверь ключ в Railway.")
            return
        add_video_db(creator["id"], "youtube", url, title, views)
        payout_now = calc_payout(views, 1, rate)
        await update.message.reply_text(
            f"✅ YouTube ролик добавлен!\n\n"
            f"🎬 {title}\n"
            f"📊 Просмотров сейчас: {views:,}\n"
            f"💰 Прогноз выплаты: {payout_now:,.2f} ₽\n"
            f"💲 Тариф: {rate_str}",
            reply_markup=main_menu()
        )

    elif platform == "tiktok":
        title, views = fetch_tiktok_views(url)
        views = views or 0
        add_video_db(creator["id"], "tiktok", url, title, views)
        payout_now = calc_payout(views, 1, rate)
        await update.message.reply_text(
            f"✅ TikTok ролик добавлен!\n\n"
            f"🎬 {title}\n"
            f"📊 Просмотров сейчас: {views:,}\n"
            f"💰 Прогноз выплаты: {payout_now:,.2f} ₽\n"
            f"💲 Тариф: {rate_str}",
            reply_markup=main_menu()
        )

    elif platform == "instagram":
        ctx.user_data["ig_url"] = url
        ctx.user_data["ig_creator_id"] = creator["id"]
        ctx.user_data["waiting_ig_views"] = True
        await update.message.reply_text("📸 Instagram ролик.\n\nСколько просмотров на нём прямо сейчас? Введи число:")

async def _process_ig_views(update: Update, ctx, text: str):
    from database import get_creator, add_video_db, set_pending_views, get_conn
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    try:
        views = int(text.replace(" ", "").replace(",", ""))
    except ValueError:
        await update.message.reply_text("❌ Введи число, например: 15000")
        ctx.user_data["waiting_ig_views"] = True
        return

    url = ctx.user_data.get("ig_url")
    creator_id = ctx.user_data.get("ig_creator_id")
    creator = get_creator(update.effective_user.id)

    add_video_db(creator_id, "instagram", url, "Instagram Reels", 0)

    conn = get_conn()
    video = conn.execute(
        "SELECT id FROM videos WHERE creator_id=? AND url=? ORDER BY id DESC LIMIT 1",
        (creator_id, url)
    ).fetchone()
    conn.close()

    if video:
        set_pending_views(video["id"], views)
        admin_id = ctx.bot_data.get("admin_id")
        if admin_id:
            kb = [[InlineKeyboardButton(
                f"✅ Одобрить {views:,} просм.",
                callback_data=f"adm_approve_ig_{video['id']}_{update.effective_user.id}"
            )]]
            await ctx.bot.send_message(
                admin_id,
                f"📸 Instagram от {creator['name']}!\n🔗 {url}\n👁 Заявлено: {views:,}",
                reply_markup=InlineKeyboardMarkup(kb)
            )

    await update.message.reply_text(
        f"✅ Отправлено на проверку!\n👁 Заявлено: {views:,} просм.\n⏳ Ждём одобрения.",
        reply_markup=main_menu()
    )
    ctx.user_data.pop("ig_url", None)
    ctx.user_data.pop("ig_creator_id", None)

def main():
    init_db()
    app = Application.builder().token(os.getenv("BOT_TOKEN")).build()

    # Регистрация — ConversationHandler только для /start онбординга
    reg_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAITING_NAME:      [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            WAITING_TIKTOK:    [MessageHandler(filters.TEXT & ~filters.COMMAND, get_tiktok)],
            WAITING_YOUTUBE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, get_youtube)],
            WAITING_INSTAGRAM: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_instagram)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    app.add_handler(reg_conv)
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^adm_"))
    app.add_handler(CallbackQueryHandler(video_callback, pattern="^(del_video_|edit_ig_)"))

    # Единый обработчик всего остального текста
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, universal_text_handler))

    start_scheduler()
    logging.info("D-Creator бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
