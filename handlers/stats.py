from telegram import Update
from telegram.ext import ContextTypes
from database import get_creator, get_videos_by_creator, get_current_period, get_payouts_by_creator, get_all_periods
from datetime import date

def calc_payout(views_gained, video_count, period):
    if not period:
        return 0
    if period["rate_type"] == "per_1000":
        return round(views_gained / 1000 * period["rate_value"], 2)
    return round(video_count * period["rate_fix"] + views_gained / 1000 * period["rate_value"], 2)

async def stats_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    creator = get_creator(tg_id)
    if not creator:
        await update.message.reply_text("❗ Сначала зарегистрируйся — напиши /start")
        return

    videos = get_videos_by_creator(creator["id"])
    period = get_current_period()

    # Тариф
    if period:
        if period["rate_type"] == "per_1000":
            rate_str = f"{period['rate_value']:.0f} ₽ / 1 000 просм."
        else:
            rate_str = f"{period['rate_fix']:.0f} ₽ за ролик + {period['rate_value']:.0f} ₽ / 1 000 просм."
    else:
        rate_str = "—"

    if not videos:
        await update.message.reply_text(
            f"📭 У тебя пока нет роликов.\n\n"
            f"💲 Текущий тариф: {rate_str}\n\n"
            f"➕ Добавить ролик: /add"
        )
        return

    total_views = sum(v["views"] for v in videos)
    total_gained = sum(max(0, v["views"] - v["views_at_period_start"]) for v in videos)

    yt_views = yt_gained = yt_count = 0
    tt_views = tt_gained = tt_count = 0
    ig_views = ig_gained = ig_count = 0

    for v in videos:
        gained = max(0, v["views"] - v["views_at_period_start"])
        if v["platform"] == "youtube":
            yt_views += v["views"]; yt_gained += gained; yt_count += 1
        elif v["platform"] == "tiktok":
            tt_views += v["views"]; tt_gained += gained; tt_count += 1
        elif v["platform"] == "instagram":
            ig_views += v["views"]; ig_gained += gained; ig_count += 1

    total_payout = calc_payout(total_gained, len(videos), period)
    today = date.today()

    lines = [
        f"📊 Статистика — {creator['name']}",
        "",
        f"📅 Период: {period['start_date']} — {period['end_date']}" if period else "",
        f"💲 Тариф: {rate_str}",
        "",
        "━━━━━ Просмотры за период ━━━━━",
    ]
    if yt_count:
        lines.append(f"📺 YouTube ({yt_count} р.): +{yt_gained:,} просм.")
    if tt_count:
        lines.append(f"🎵 TikTok ({tt_count} р.): +{tt_gained:,} просм.")
    if ig_count:
        lines.append(f"📸 Instagram ({ig_count} р.): +{ig_gained:,} просм.")

    lines += [
        "",
        f"📈 Итого прирост: +{total_gained:,} просм.",
        f"👁 Всего просмотров: {total_views:,}",
        f"💰 Прогноз выплаты: {total_payout:,.2f} ₽",
        "",
        "📋 Команды:",
        "➕ /add — добавить ролик",
        "🎬 /myvideos — мои ролики",
        "🔄 /refresh — обновить просмотры",
        "📅 /periods — отчётные периоды",
    ]

    await update.message.reply_text("\n".join(lines))

async def periods_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    creator = get_creator(tg_id)
    if not creator:
        await update.message.reply_text("❗ Сначала зарегистрируйся — /start")
        return

    period = get_current_period()
    payouts = get_payouts_by_creator(creator["id"])
    videos = get_videos_by_creator(creator["id"])
    total_gained = sum(max(0, v["views"] - v["views_at_period_start"]) for v in videos)
    current_payout = calc_payout(total_gained, len(videos), period)

    lines = [
        "📅 Отчётные периоды",
        "",
    ]

    # Текущий период
    if period:
        if period["rate_type"] == "per_1000":
            rate_str = f"{period['rate_value']:.0f} ₽/1000 просм."
        else:
            rate_str = f"{period['rate_fix']:.0f}₽ за ролик + {period['rate_value']:.0f}₽/1000"
        lines += [
            f"🟢 Текущий период",
            f"   📅 {period['start_date']} — {period['end_date']}",
            f"   💲 Тариф: {rate_str}",
            f"   📈 Прирост: +{total_gained:,} просм.",
            f"   💰 Текущая оценка: {current_payout:,.2f} ₽",
            "",
        ]

    # История выплат
    if payouts:
        lines.append("💸 История выплат:")
        for p in payouts:
            lines.append(
                f"   🔒 {p['start_date']} — {p['end_date']}\n"
                f"      📈 +{p['views_gained']:,} просм. | 💰 {p['amount']:.2f} ₽"
            )
    else:
        lines.append("💸 История выплат: пока пусто")

    await update.message.reply_text("\n".join(lines))
