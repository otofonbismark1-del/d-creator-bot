import re
import os
import requests
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from database import get_creator, add_video_db

WAITING_LINK = 10

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

def detect_platform(url: str):
    url = url.lower()
    if "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    if "tiktok.com" in url:
        return "tiktok"
    if "instagram.com" in url:
        return "instagram"
    return None

def get_youtube_video_id(url: str):
    # youtu.be/ID или youtube.com/watch?v=ID или /shorts/ID
    patterns = [
        r"youtu\.be/([a-zA-Z0-9_-]{11})",
        r"v=([a-zA-Z0-9_-]{11})",
        r"shorts/([a-zA-Z0-9_-]{11})",
    ]
    for p in patterns:
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
        views = int(item["statistics"]["viewCount"])
        title = item["snippet"]["title"]
        return title, views
    except Exception as e:
        return None, None

def get_tiktok_video_id(url: str):
    # https://www.tiktok.com/@user/video/1234567890
    m = re.search(r"/video/(\d+)", url)
    if m:
        return m.group(1)
    return None

def fetch_tiktok_views(url: str):
    """
    TikTok не имеет официального API для просмотров по ссылке.
    Используем неофициальный способ через TikTok oEmbed endpoint.
    """
    try:
        oembed_url = f"https://www.tiktok.com/oembed?url={url}"
        r = requests.get(oembed_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        data = r.json()
        title = data.get("title", "TikTok видео")
        # oEmbed не даёт просмотры — используем scraping через нефильтрованный HTML
        # Получим просмотры через TikTok API неофициально
        views = fetch_tiktok_views_scrape(url)
        return title, views
    except Exception:
        return None, None

def fetch_tiktok_views_scrape(url: str):
    """Получает просмотры TikTok через scraping страницы"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15"
        }
        r = requests.get(url, headers=headers, timeout=15)
        # Ищем playCount в JSON данных страницы
        match = re.search(r'"playCount":(\d+)', r.text)
        if match:
            return int(match.group(1))
        # Запасной вариант
        match = re.search(r'"play_count":(\d+)', r.text)
        if match:
            return int(match.group(1))
        return 0
    except Exception:
        return 0

async def add_video(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    creator = get_creator(tg_id)
    if not creator:
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
        await update.message.reply_text("❌ Не могу определить платформу. Отправь ссылку с YouTube, TikTok или Instagram.")
        return WAITING_LINK

    await update.message.reply_text(f"⏳ Получаю данные с {platform.capitalize()}...")

    title = None
    views = None

    if platform == "youtube":
        video_id = get_youtube_video_id(url)
        if not video_id:
            await update.message.reply_text("❌ Не могу найти ID видео в ссылке. Проверь ссылку.")
            return WAITING_LINK
        title, views = fetch_youtube_views(video_id)
        if views is None:
            await update.message.reply_text("❌ Не удалось получить данные с YouTube. Проверь ссылку или API ключ.")
            return WAITING_LINK

    elif platform == "tiktok":
        title, views = fetch_tiktok_views(url)
        if views is None:
            title = "TikTok видео"
            views = 0
            await update.message.reply_text(
                "⚠️ Не удалось получить просмотры TikTok автоматически.\n"
                "Ролик добавлен с 0 просмотров. Данные обновятся при следующей проверке."
            )

    elif platform == "instagram":
        title = "Instagram Reels"
        views = 0
        await update.message.reply_text(
            "📸 Instagram добавлен вручную.\n"
            "⚠️ Просмотры нужно вписать вручную — напиши мне сколько просмотров на этом ролике."
        )
        ctx.user_data["pending_instagram_url"] = url
        ctx.user_data["pending_creator_id"] = creator["id"]
        ctx.user_data["pending_platform"] = "instagram"
        # Сохраняем с 0 и ждём ручного ввода — уведомим админа
        add_video_db(creator["id"], "instagram", url, title, 0)
        # Уведомить админа
        admin_id = ctx.bot_data.get("admin_id")
        if admin_id:
            await ctx.bot.send_message(
                admin_id,
                f"📸 Новый Instagram ролик от {creator['name']}:\n{url}\n\n"
                f"⚠️ Проверь что ролик реальный. Просмотры будут введены вручную."
            )
        return ConversationHandler.END

    add_video_db(creator["id"], platform, url, title or "Без названия", views or 0)

    payout = round((views or 0) / 1000 * 60, 2)
    await update.message.reply_text(
        f"✅ Ролик добавлен!\n\n"
        f"🎬 {title or 'Без названия'}\n"
        f"📊 Просмотры: {views:,}\n"
        f"💰 Прогноз выплаты: {payout:,.2f} ₽\n"
        f"🔗 Платформа: {platform.capitalize()}"
    )
    return ConversationHandler.END
