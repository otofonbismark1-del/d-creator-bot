from telegram import Update
from telegram.ext import ContextTypes
from database import get_creator, get_videos_by_creator

RATE_PER_1000 = 60  # рублей

async def stats_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    creator = get_creator(tg_id)
    if not creator:
        await update.message.reply_text("❗ Сначала зарегистрируйся — напиши /start")
        return

    videos = get_videos_by_creator(creator["id"])
    if not videos:
        await update.message.reply_text(
            "📭 У тебя пока нет роликов.\n\n"
            "Добавь первый: /add"
        )
        return

    total_views = 0
    yt_views = 0
    tt_views = 0
    ig_views = 0
    yt_count = tt_count = ig_count = 0

    for v in videos:
        total_views += v["views"]
        if v["platform"] == "youtube":
            yt_views += v["views"]
            yt_count += 1
        elif v["platform"] == "tiktok":
            tt_views += v["views"]
            tt_count += 1
        elif v["platform"] == "instagram":
            ig_views += v["views"]
            ig_count += 1

    total_payout = round(total_views / 1000 * RATE_PER_1000, 2)

    lines = [
        f"📊 Статистика — {creator['name']}",
        "",
    ]

    if yt_count:
        lines.append(f"📺 YouTube ({yt_count} роликов): {yt_views:,} просмотров")
    if tt_count:
        lines.append(f"🎵 TikTok ({tt_count} роликов): {tt_views:,} просмотров")
    if ig_count:
        lines.append(f"📸 Instagram ({ig_count} роликов): {ig_views:,} просмотров")

    lines += [
        "",
        f"👁 Всего просмотров: {total_views:,}",
        f"💰 Прогноз выплаты: {total_payout:,.2f} ₽",
        f"   (60 ₽ за 1 000 просмотров)",
        "",
        "➕ Добавить ролик: /add",
    ]

    # Список роликов
    if videos:
        lines.append("")
        lines.append("🎬 Мои ролики:")
        for v in videos[:10]:  # последние 10
            payout_v = round(v["views"] / 1000 * RATE_PER_1000, 2)
            platform_icon = {"youtube": "📺", "tiktok": "🎵", "instagram": "📸"}.get(v["platform"], "🎬")
            title = (v["title"] or "Без названия")[:35]
            lines.append(f"{platform_icon} {title} — {v['views']:,} просм. / {payout_v:.0f} ₽")

    await update.message.reply_text("\n".join(lines))
