from telegram import Update
from telegram.ext import ContextTypes
from database import (get_creator, get_videos_by_creator, get_current_period,
                      get_payouts_by_creator, get_creator_rate, calc_payout)
from handlers.start import main_menu

async def stats_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    creator = get_creator(tg_id)
    if not creator:
        await update.message.reply_text("❗ Сначала зарегистрируйся — /start")
        return

    videos = get_videos_by_creator(creator["id"])
    period = get_current_period()
    rate = get_creator_rate(creator["id"], period["id"]) if period else {"rate_type":"per_1000","rate_value":60,"rate_fix":0}

    rate_str = (f"{rate['rate_value']:.0f} ₽/1000 просм." if rate["rate_type"] == "per_1000"
                else f"{rate['rate_fix']:.0f}₽ за ролик + {rate['rate_value']:.0f}₽/1000")

    if not videos:
        await update.message.reply_text(
            f"📭 Роликов нет.\n\n💲 Тариф: {rate_str}", reply_markup=main_menu()
        )
        return

    total_gained = yt_gained = tt_gained = ig_gained = 0
    total_views = yt_views = tt_views = ig_views = 0
    yt_c = tt_c = ig_c = 0

    for v in videos:
        g = max(0, v["views"] - v["views_at_period_start"])
        total_gained += g
        total_views += v["views"]
        if v["platform"] == "youtube":
            yt_gained += g; yt_views += v["views"]; yt_c += 1
        elif v["platform"] == "tiktok":
            tt_gained += g; tt_views += v["views"]; tt_c += 1
        elif v["platform"] == "instagram":
            ig_gained += g; ig_views += v["views"]; ig_c += 1

    # Если прирост за период = 0 (все ролики добавлены в этом периоде),
    # считаем прогноз по текущим просмотрам
    views_for_payout = total_gained if total_gained > 0 else total_views
    total_payout = calc_payout(views_for_payout, len(videos), rate)

    payout_note = "" if total_gained > 0 else "\n   ⚠️ Ролики только добавлены — считается по текущим просмотрам"

    lines = [
        f"📊 Статистика — {creator['name']}",
        f"📅 {period['start_date']} — {period['end_date']}" if period else "",
        f"💲 Тариф: {rate_str}", "",
        "━━━ Просмотры за период ━━━",
    ]
    if yt_c: lines.append(f"📺 YouTube ({yt_c} р.): {yt_views:,} просм. / +{yt_gained:,} прирост")
    if tt_c: lines.append(f"🎵 TikTok ({tt_c} р.): {tt_views:,} просм. / +{tt_gained:,} прирост")
    if ig_c: lines.append(f"📸 Instagram ({ig_c} р.): {ig_views:,} просм. / +{ig_gained:,} прирост")
    lines += [
        "",
        f"📈 Прирост за период: +{total_gained:,} просм.",
        f"💰 Прогноз выплаты: {total_payout:,.2f} ₽{payout_note}",
    ]

    await update.message.reply_text("\n".join(lines), reply_markup=main_menu())

async def periods_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    creator = get_creator(tg_id)
    if not creator:
        await update.message.reply_text("❗ Сначала зарегистрируйся — /start")
        return

    period = get_current_period()
    videos = get_videos_by_creator(creator["id"])
    payouts = get_payouts_by_creator(creator["id"])

    rate = get_creator_rate(creator["id"], period["id"]) if period else {"rate_type":"per_1000","rate_value":60,"rate_fix":0}
    total_gained = sum(max(0, v["views"] - v["views_at_period_start"]) for v in videos)
    current_payout = calc_payout(total_gained, len(videos), rate)
    rate_str = (f"{rate['rate_value']:.0f}₽/1000" if rate["rate_type"] == "per_1000"
                else f"{rate['rate_fix']:.0f}₽ + {rate['rate_value']:.0f}₽/1000")

    lines = ["📅 Отчётные периоды\n"]
    if period:
        lines += [
            f"🟢 Текущий: {period['start_date']} — {period['end_date']}",
            f"   💲 Тариф: {rate_str}",
            f"   📈 Прирост: +{total_gained:,} просм.",
            f"   💰 Оценка: {current_payout:,.2f} ₽", ""
        ]

    if payouts:
        lines.append("💸 История выплат:")
        for p in payouts:
            lines.append(f"   🔒 {p['start_date']} — {p['end_date']}: {p['amount']:.2f} ₽ (+{p['views_gained']:,} просм.)")
    else:
        lines.append("💸 Выплат пока не было.")

    await update.message.reply_text("\n".join(lines), reply_markup=main_menu())
