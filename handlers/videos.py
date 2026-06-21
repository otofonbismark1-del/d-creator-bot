import re
import os
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import (get_creator, add_video_db, get_videos_by_creator,
                      delete_video, update_video_views, get_current_period,
                      set_pending_views, get_video_by_id)

WAITING_LINK = 10
WAITING_IG_VIEWS = 11
WAITING_IG_EDIT_VIEWS = 12

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

def detect_platform(url: str):
    u = url.lower()
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    if "tiktok.com" in u:
        return "tiktok"
    if "instagram.com" in u:
        return "instagram"
    return None

def get_youtube_video_id(url: str):
    for p in [r"youtu\.be/([a-zA-Z0-9_-]{11})", r"v=([a-zA-Z0-9_-]{11})", r"shorts/([a-zA-Z0-9_-]{11})"]:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

def fetch_youtube_views(video_id: str):
    url = f"https://www.googleapis.com/youtube/v3/videos?part=statistics,snippet&id={video_id}&key={YOUTUBE_API_KEY}"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        item = data["items"][0]
        return item["snippet"]["title"], int(item["statistics"]["viewCount"])
    except Exception:
        return None, None

def fetch_tiktok_views(url: str):
    try:
        oembed = f"https://www.tiktok.com/oembed?url={url}"
        r = requests.get(oembed, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        title = r.json().get("title", "TikTok видео")
        views = _scrape_tiktok(url)
        return title, views
    except Exception:
        return "TikTok видео", 0

def _scrape_tiktok(url: str):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15"}
        r = requests.get(url, headers=headers, timeout=15)
        for pattern in [r'"playCount":(\d+)', r'"play_count":(\d+)']: 
            m = re.search(pattern, r.text)
            if m:
                return int(m.group(1))
        return 0
    except Exception:
        return 0

def calc_payout(views_gained, video_count, period):
    if not period:
        return 0
    if period["rate_type"] == "per_1000":
        return round(views_gained / 1000 * period["rate_value"], 2)
    return round(video_count * period["rate_fix"] + views_gained / 1000 * period["rate_value"], 2)

async def add_video(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not get_creator(update.effective_user.id):
        await update.message.reply_text("❗ Сначала зарегистрируйся — напиши /start")
        return ConversationHandler.END
    await update.message.reply_text("🔗 Отправь ссылку на ролик (YouTube, TikTok или Instagram):")
    return WAITING_LINK

async def handle_video_link(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    tg_id = update.effective_user.id
    creator = get_creator(tg_id)

    platform = detect_platform(url)
    if not platform:
        await update.message.reply_text("❌ Не могу определить платформу. Отправь ссылку YouTube, TikTok или Instagram.")
        return WAITING_LINK

    await update.message.reply_text(f"⏳ Получаю данные с {platform.capitalize()}...")
    period = get_current_period()
    rate_str = f"{period['rate_value']:.0f} ₽/1000 просм." if period else "—"

    if platform == "youtube":
        video_id = get_youtube_video_id(url)
        if not video_id:
            await update.message.reply_text("❌ Не могу найти ID видео. Проверь ссылку.")
            return WAITING_LINK
        title, views = fetch_youtube_views(video_id)
        if views is None:
            await update.message.reply_text("❌ Не удалось получить данные с YouTube. Проверь ссылку или API ключ.")
            return WAITING_LINK
        add_video_db(creator["id"], "youtube", url, title, views)
        payout = calc_payout(0, 1, period)
        await update.message.reply_text(
            f"✅ Ролик добавлен!\n\n"
            f"🎬 {title}\n"
            f"📊 Просмотров сейчас: {views:,}\n"
            f"📈 Прирост за период будет считаться с этого момента\n"
            f"💲 Тариф: {rate_str}"
        )
        return ConversationHandler.END

    elif platform == "tiktok":
        title, views = fetch_tiktok_views(url)
        add_video_db(creator["id"], "tiktok", url, title or "TikTok видео", views or 0)
        await update.message.reply_text(
            f"✅ TikTok ролик добавлен!\n\n"
            f"🎬 {title or 'TikTok видео'}\n"
            f"📊 Просмотров сейчас: {(views or 0):,}\n"
            f"📈 Прирост за период будет считаться с этого момента\n"
            f"💲 Тариф: {rate_str}"
        )
        return ConversationHandler.END

    elif platform == "instagram":
        ctx.user_data["ig_url"] = url
        ctx.user_data["ig_creator_id"] = creator["id"]
        await update.message.reply_text(
            "📸 Instagram ролик добавляется вручную.\n\n"
            "Напиши сколько просмотров на этом ролике прямо сейчас:"
        )
        return WAITING_IG_VIEWS

async def handle_ig_views_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Получить просмотры Instagram от юзера, отправить на проверку админу"""
    try:
        views = int(update.message.text.strip().replace(" ", "").replace(",", ""))
    except ValueError:
        await update.message.reply_text("❌ Введи число, например: 15000")
        return WAITING_IG_VIEWS

    url = ctx.user_data.get("ig_url")
    creator_id = ctx.user_data.get("ig_creator_id")
    creator = get_creator(update.effective_user.id)
    period = get_current_period()
    rate_str = f"{period['rate_value']:.0f} ₽/1000 просм." if period else "—"

    # Добавляем ролик с 0, а pending_views = указанные просмотры
    add_video_db(creator_id, "instagram", url, "Instagram Reels", 0)

    # Получаем только что добавленный ролик
    from database import get_conn
    conn = get_conn()
    video = conn.execute(
        "SELECT id FROM videos WHERE creator_id=? AND url=? ORDER BY id DESC LIMIT 1",
        (creator_id, url)
    ).fetchone()
    conn.close()

    if video:
        set_pending_views(video["id"], views)

    # Уведомить админа
    admin_id = ctx.bot_data.get("admin_id")
    if admin_id:
        keyboard = [[InlineKeyboardButton(
            f"✅ Одобрить {views:,} просм.",
            callback_data=f"admin_approve_ig_{video['id']}_{update.effective_user.id}"
        )]]
        await ctx.bot.send_message(
            admin_id,
            f"📸 Новый Instagram ролик от {creator['name']}!\n\n"
            f"🔗 {url}\n"
            f"👁 Заявлено просмотров: {views:,}\n\n"
            f"Проверь ролик и одобри просмотры:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    await update.message.reply_text(
        f"✅ Instagram ролик отправлен на проверку!\n\n"
        f"👁 Заявлено просмотров: {views:,}\n"
        f"💲 Тариф: {rate_str}\n\n"
        f"⏳ Как только админ одобрит — просмотры засчитаются."
    )

    ctx.user_data.pop("ig_url", None)
    ctx.user_data.pop("ig_creator_id", None)
    return ConversationHandler.END

async def my_videos_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Список всех роликов с возможностью удалить"""
    tg_id = update.effective_user.id
    creator = get_creator(tg_id)
    if not creator:
        await update.message.reply_text("❗ Сначала зарегистрируйся — /start")
        return

    videos = get_videos_by_creator(creator["id"])
    if not videos:
        await update.message.reply_text("📭 У тебя пока нет роликов.\n\nДобавь первый: /add")
        return

    period = get_current_period()
    await update.message.reply_text(
        f"🎬 Твои ролики ({len(videos)} шт.):\nНажми на ролик чтобы удалить."
    )

    for v in videos:
        icon = {"youtube": "📺", "tiktok": "🎵", "instagram": "📸"}.get(v["platform"], "🎬")
        gained = max(0, v["views"] - v["views_at_period_start"])
        payout = calc_payout(gained, 1, period)
        title = (v["title"] or "Без названия")[:35]
        pending = f"\n   ⏳ На проверке: {v['pending_views']:,} просм." if v["pending_views"] else ""

        status = ""
        if v["platform"] == "instagram" and v["pending_views"]:
            status = " ⏳"

        keyboard = [[
            InlineKeyboardButton(f"🗑 Удалить", callback_data=f"del_video_{v['id']}"),
        ]]
        if v["platform"] == "instagram":
            keyboard[0].append(InlineKeyboardButton("✏️ Изменить просмотры", callback_data=f"edit_ig_{v['id']}"))

        await update.message.reply_text(
            f"{icon} {title}{status}\n"
            f"   👁 {v['views']:,} просм. | 📈 +{gained:,} за период\n"
            f"   💰 {payout:.2f} ₽{pending}\n"
            f"   🔗 {v['url'][:50]}...",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def video_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    tg_id = query.from_user.id
    creator = get_creator(tg_id)
    if not creator:
        return

    if data.startswith("del_video_"):
        video_id = int(data.split("_")[-1])
        delete_video(video_id, creator["id"])
        await query.edit_message_text("🗑 Ролик удалён.")

    elif data.startswith("edit_ig_"):
        video_id = int(data.split("_")[-1])
        ctx.user_data["edit_ig_video_id"] = video_id
        await query.edit_message_text(
            "✏️ Введи новое количество просмотров для этого Instagram ролика:"
        )
        ctx.user_data["waiting_ig_edit"] = True

async def handle_ig_edit_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.user_data.get("waiting_ig_edit"):
        return
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
        keyboard = [[InlineKeyboardButton(
            f"✅ Одобрить {views:,} просм.",
            callback_data=f"admin_approve_ig_{video_id}_{update.effective_user.id}"
        )]]
        await ctx.bot.send_message(
            admin_id,
            f"✏️ {creator['name']} обновил просмотры Instagram!\n\n"
            f"🔗 {video['url']}\n"
            f"👁 Старые: {video['views']:,}\n"
            f"👁 Новые: {views:,}\n\n"
            f"Одобрить обновление?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    await update.message.reply_text(
        f"✅ Новые просмотры ({views:,}) отправлены на проверку админу.\n"
        f"Как только одобрят — засчитаются."
    )
    ctx.user_data["waiting_ig_edit"] = False

async def refresh_views_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Обновить просмотры у всех роликов пользователя прямо сейчас"""
    tg_id = update.effective_user.id
    creator = get_creator(tg_id)
    if not creator:
        await update.message.reply_text("❗ Сначала зарегистрируйся — /start")
        return

    videos = get_videos_by_creator(creator["id"])
    auto_videos = [v for v in videos if v["platform"] in ("youtube", "tiktok")]
    if not auto_videos:
        await update.message.reply_text("Нет роликов YouTube/TikTok для обновления.")
        return

    await update.message.reply_text(f"⏳ Обновляю просмотры ({len(auto_videos)} роликов)...")

    updated = 0
    for v in auto_videos:
        try:
            if v["platform"] == "youtube":
                vid_id = get_youtube_video_id(v["url"])
                if vid_id:
                    _, views = fetch_youtube_views(vid_id)
                    if views is not None:
                        update_video_views(v["id"], views)
                        updated += 1
            elif v["platform"] == "tiktok":
                _, views = fetch_tiktok_views(v["url"])
                if views:
                    update_video_views(v["id"], views)
                    updated += 1
        except Exception:
            pass

    await update.message.reply_text(
        f"✅ Обновлено {updated} из {len(auto_videos)} роликов!\n\n"
        f"📊 Смотри статистику: /stats"
    )
