import re
import os
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import (get_creator, add_video_db, get_videos_by_creator, delete_video,
                      update_video_views, get_current_period, set_pending_views,
                      get_video_by_id, get_creator_rate, calc_payout)

WAITING_LINK = 10
WAITING_IG_VIEWS = 11

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

def detect_platform(url):
    u = url.lower()
    if "youtube.com" in u or "youtu.be" in u: return "youtube"
    if "tiktok.com" in u: return "tiktok"
    if "instagram.com" in u: return "instagram"
    return None

def get_youtube_video_id(url):
    for p in [r"youtu\.be/([a-zA-Z0-9_-]{11})", r"v=([a-zA-Z0-9_-]{11})", r"shorts/([a-zA-Z0-9_-]{11})"]:
        m = re.search(p, url)
        if m: return m.group(1)
    return None

def fetch_youtube_views(video_id):
    try:
        r = requests.get(
            f"https://www.googleapis.com/youtube/v3/videos?part=statistics,snippet&id={video_id}&key={YOUTUBE_API_KEY}",
            timeout=10
        )
        item = r.json()["items"][0]
        return item["snippet"]["title"], int(item["statistics"]["viewCount"])
    except Exception:
        return None, None

def fetch_tiktok_views(url):
    try:
        r = requests.get(f"https://www.tiktok.com/oembed?url={url}", timeout=10,
                         headers={"User-Agent": "Mozilla/5.0"})
        title = r.json().get("title", "TikTok видео")
    except Exception:
        title = "TikTok видео"
    try:
        headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15"}
        r2 = requests.get(url, headers=headers, timeout=15)
        for pat in [r'"playCount":(\d+)', r'"play_count":(\d+)']:
            m = re.search(pat, r2.text)
            if m: return title, int(m.group(1))
    except Exception:
        pass
    return title, 0

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
    period = get_current_period()

    platform = detect_platform(url)
    if not platform:
        await update.message.reply_text("❌ Не могу определить платформу. Отправь ссылку YouTube, TikTok или Instagram.")
        return WAITING_LINK

    await update.message.reply_text(f"⏳ Получаю данные с {platform.capitalize()}...")

    rate = get_creator_rate(creator["id"], period["id"]) if period else {"rate_type":"per_1000","rate_value":60,"rate_fix":0}
    rate_str = (f"{rate['rate_value']:.0f} ₽/1000 просм." if rate["rate_type"] == "per_1000"
                else f"{rate['rate_fix']:.0f}₽ за ролик + {rate['rate_value']:.0f}₽/1000")

    if platform == "youtube":
        vid_id = get_youtube_video_id(url)
        if not vid_id:
            await update.message.reply_text("❌ Не могу найти ID видео. Проверь ссылку.")
            return WAITING_LINK
        title, views = fetch_youtube_views(vid_id)
        if views is None:
            await update.message.reply_text("❌ Ошибка YouTube API. Проверь ссылку или ключ.")
            return WAITING_LINK
        add_video_db(creator["id"], "youtube", url, title, views)
        from handlers.start import main_menu
        await update.message.reply_text(
            f"✅ YouTube ролик добавлен!\n\n🎬 {title}\n📊 {views:,} просм.\n💲 Тариф: {rate_str}",
            reply_markup=main_menu()
        )
        return ConversationHandler.END

    elif platform == "tiktok":
        title, views = fetch_tiktok_views(url)
        add_video_db(creator["id"], "tiktok", url, title, views or 0)
        from handlers.start import main_menu
        await update.message.reply_text(
            f"✅ TikTok ролик добавлен!\n\n🎬 {title}\n📊 {views or 0:,} просм.\n💲 Тариф: {rate_str}",
            reply_markup=main_menu()
        )
        return ConversationHandler.END

    elif platform == "instagram":
        ctx.user_data["ig_url"] = url
        ctx.user_data["ig_creator_id"] = creator["id"]
        await update.message.reply_text("📸 Instagram ролик.\n\nСколько просмотров на нём прямо сейчас?")
        return WAITING_IG_VIEWS

async def handle_ig_views_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        views = int(update.message.text.strip().replace(" ", "").replace(",", ""))
    except ValueError:
        await update.message.reply_text("❌ Введи число, например: 15000")
        return WAITING_IG_VIEWS

    url = ctx.user_data.get("ig_url")
    creator_id = ctx.user_data.get("ig_creator_id")
    creator = get_creator(update.effective_user.id)

    add_video_db(creator_id, "instagram", url, "Instagram Reels", 0)

    from database import get_conn
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
                callback_data=f"admin_approve_ig_{video['id']}_{update.effective_user.id}"
            )]]
            await ctx.bot.send_message(
                admin_id,
                f"📸 Instagram от {creator['name']}!\n🔗 {url}\n👁 Заявлено: {views:,}",
                reply_markup=InlineKeyboardMarkup(kb)
            )

    from handlers.start import main_menu
    await update.message.reply_text(
        f"✅ Отправлено на проверку!\n👁 Заявлено: {views:,} просм.\n⏳ Ждём одобрения админа.",
        reply_markup=main_menu()
    )
    ctx.user_data.pop("ig_url", None)
    ctx.user_data.pop("ig_creator_id", None)
    return ConversationHandler.END

async def my_videos_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    creator = get_creator(tg_id)
    if not creator:
        await update.message.reply_text("❗ Сначала зарегистрируйся — /start")
        return

    videos = get_videos_by_creator(creator["id"])
    if not videos:
        from handlers.start import main_menu
        await update.message.reply_text("📭 Роликов нет. Добавь первый!", reply_markup=main_menu())
        return

    period = get_current_period()
    await update.message.reply_text(f"🎬 Твои ролики ({len(videos)} шт.):")

    for v in videos:
        icon = {"youtube":"📺","tiktok":"🎵","instagram":"📸"}.get(v["platform"],"🎬")
        gained = max(0, v["views"] - v["views_at_period_start"])
        rate = get_creator_rate(creator["id"], period["id"]) if period else {"rate_type":"per_1000","rate_value":60,"rate_fix":0}
        payout = calc_payout(gained, 1, rate)
        title = (v["title"] or "Без названия")[:35]
        pending_str = f"\n   ⏳ На проверке: {v['pending_views']:,} просм." if v["pending_views"] else ""

        kb = [[InlineKeyboardButton("🗑 Удалить", callback_data=f"del_video_{v['id']}")]]
        if v["platform"] == "instagram":
            kb[0].append(InlineKeyboardButton("✏️ Изменить просмотры", callback_data=f"edit_ig_{v['id']}"))

        await update.message.reply_text(
            f"{icon} {title}\n"
            f"   👁 {v['views']:,} | 📈 +{gained:,} за период | 💰 {payout:.2f} ₽{pending_str}\n"
            f"   🔗 {v['url'][:55]}",
            reply_markup=InlineKeyboardMarkup(kb)
        )

async def video_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    creator = get_creator(query.from_user.id)
    if not creator:
        return

    if data.startswith("del_video_"):
        video_id = int(data.split("_")[-1])
        delete_video(video_id, creator["id"])
        await query.edit_message_text("🗑 Ролик удалён.")

    elif data.startswith("edit_ig_"):
        video_id = int(data.split("_")[-1])
        ctx.user_data["edit_ig_video_id"] = video_id
        ctx.user_data["waiting_ig_edit"] = True
        await query.edit_message_text("✏️ Введи новое количество просмотров для этого Instagram ролика:")

async def refresh_views_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    creator = get_creator(tg_id)
    if not creator:
        await update.message.reply_text("❗ Сначала зарегистрируйся — /start")
        return

    videos = [v for v in get_videos_by_creator(creator["id"]) if v["platform"] in ("youtube","tiktok")]
    if not videos:
        await update.message.reply_text("Нет YouTube/TikTok роликов для обновления.")
        return

    await update.message.reply_text(f"⏳ Обновляю {len(videos)} роликов...")
    updated = 0
    for v in videos:
        try:
            if v["platform"] == "youtube":
                vid_id = get_youtube_video_id(v["url"])
                if vid_id:
                    _, views = fetch_youtube_views(vid_id)
                    if views: update_video_views(v["id"], views); updated += 1
            elif v["platform"] == "tiktok":
                _, views = fetch_tiktok_views(v["url"])
                if views: update_video_views(v["id"], views); updated += 1
        except Exception:
            pass

    from handlers.start import main_menu
    await update.message.reply_text(
        f"✅ Обновлено {updated} из {len(videos)} роликов!",
        reply_markup=main_menu()
    )
