from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import (get_all_creators, get_videos_by_creator, get_all_videos,
                      verify_instagram, get_current_period, get_all_periods,
                      set_period_rate, close_period_and_create_next,
                      get_all_payouts, get_period_by_id, get_pending_instagram_videos,
                      approve_pending_views, get_creator_by_id)

ADMINS = {"mldznst", "kirvitkovski"}

def is_admin(update: Update):
    user = update.effective_user
    return user.username and user.username.lower() in ADMINS

def is_admin_user(user):
    return user.username and user.username.lower() in ADMINS

def calc_payout(views_gained, video_count, period):
    if not period:
        return 0
    if period["rate_type"] == "per_1000":
        return round(views_gained / 1000 * period["rate_value"], 2)
    return round(video_count * period["rate_fix"] + views_gained / 1000 * period["rate_value"], 2)

async def admin_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("❌ У тебя нет доступа к этой команде.")
        return

    ctx.bot_data["admin_id"] = update.effective_user.id

    creators = get_all_creators()
    all_videos = get_all_videos()
    period = get_current_period()
    pending = get_pending_instagram_videos()

    total_gained = sum(max(0, v["views"] - v["views_at_period_start"]) for v in all_videos)
    total_payout = calc_payout(total_gained, len(all_videos), period) if period else 0

    if period:
        rate_str = (f"{period['rate_value']:.0f} ₽/1000 просм." if period["rate_type"] == "per_1000"
                    else f"{period['rate_fix']:.0f}₽ фикс + {period['rate_value']:.0f}₽/1000")
    else:
        rate_str = "—"

    lines = [
        "👑 Админ-панель D-Creator",
        "",
        f"📅 Период: {period['start_date']} — {period['end_date']}" if period else "Нет периода",
        f"💲 Тариф: {rate_str}",
        "",
        f"👥 Креаторов: {len(creators)}",
        f"🎬 Роликов: {len(all_videos)}",
        f"📈 Прирост за период: +{total_gained:,} просм.",
        f"💰 Прогноз выплат: {total_payout:,.2f} ₽",
        f"⏳ Instagram на проверке: {len(pending)} шт.",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    for c in creators:
        videos = get_videos_by_creator(c["id"])
        c_gained = sum(max(0, v["views"] - v["views_at_period_start"]) for v in videos)
        c_payout = calc_payout(c_gained, len(videos), period) if period else 0
        lines.append(
            f"👤 {c['name']} (@{c['username'] or c['tg_id']})\n"
            f"   🎬 {len(videos)} роликов | 📈 +{c_gained:,} | 💰 {c_payout:.2f} ₽\n"
        )

    await update.message.reply_text("\n".join(lines))

    keyboard = [
        [InlineKeyboardButton("📊 Все ролики", callback_data="admin_all_videos"),
         InlineKeyboardButton(f"⏳ Instagram ({len(pending)})", callback_data="admin_check_instagram")],
        [InlineKeyboardButton("💲 Изменить тариф", callback_data="admin_change_rate")],
        [InlineKeyboardButton("📅 История периодов", callback_data="admin_periods"),
         InlineKeyboardButton("💸 Выплаты", callback_data="admin_payouts")],
        [InlineKeyboardButton("🔒 Закрыть период", callback_data="admin_close_period")],
    ]
    await update.message.reply_text("Выбери действие:", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin_user(query.from_user):
        await query.edit_message_text("❌ Нет доступа.")
        return

    data = query.data
    period = get_current_period()

    if data == "admin_all_videos":
        all_videos = get_all_videos()
        if not all_videos:
            await query.edit_message_text("Нет роликов.")
            return
        lines = ["🎬 Все ролики:\n"]
        for v in all_videos[:30]:
            icon = {"youtube": "📺", "tiktok": "🎵", "instagram": "📸"}.get(v["platform"], "🎬")
            gained = max(0, v["views"] - v["views_at_period_start"])
            payout = calc_payout(gained, 1, period)
            pending_str = f" ⏳{v['pending_views']:,}" if v["pending_views"] else ""
            title = (v["title"] or "—")[:25]
            lines.append(f"{icon} {v['creator_name']} — {title}\n   👁 {v['views']:,}{pending_str} | 📈 +{gained:,} | 💰 {payout:.2f}₽")
        await query.edit_message_text("\n".join(lines))

    elif data == "admin_check_instagram":
        pending = get_pending_instagram_videos()
        if not pending:
            await query.edit_message_text("✅ Нет Instagram роликов на проверке.")
            return
        lines = ["📸 Instagram на проверке:\n"]
        keyboard = []
        for v in pending:
            lines.append(
                f"👤 {v['creator_name']}\n"
                f"🔗 {v['url']}\n"
                f"👁 Сейчас: {v['views']:,} | Заявлено: {v['pending_views']:,}\n"
            )
            keyboard.append([InlineKeyboardButton(
                f"✅ Одобрить {v['creator_name']} — {v['pending_views']:,}",
                callback_data=f"admin_approve_ig_{v['id']}_{v['creator_tg_id']}"
            )])
        await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("admin_approve_ig_"):
        parts = data.split("_")
        video_id = int(parts[3])
        creator_tg_id = int(parts[4])
        approve_pending_views(video_id)
        # Уведомить креатора
        try:
            await ctx.bot.send_message(
                creator_tg_id,
                "✅ Просмотры Instagram одобрены!\n\n"
                "Твои просмотры учтены и включены в прогноз выплаты. "
                "Смотри /stats для актуальной статистики."
            )
        except Exception:
            pass
        await query.edit_message_text("✅ Просмотры одобрены, креатор уведомлён!")

    elif data == "admin_change_rate":
        p_str = f"{period['start_date']} — {period['end_date']}" if period else "—"
        keyboard = [
            [InlineKeyboardButton("✏️ Своя цена за 1000 просм.", callback_data="admin_rate_custom")],
            [InlineKeyboardButton("💰 Фикс 1200₽ + 30₽/1000", callback_data="admin_rate_fix_preset")],
        ]
        await query.edit_message_text(
            f"💲 Изменить тариф для периода {p_str}\n\nВыбери тип:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data == "admin_rate_custom":
        ctx.user_data["waiting_rate_input"] = True
        ctx.user_data["rate_mode"] = "per_1000"
        await query.edit_message_text("✏️ Введи цену за 1 000 просмотров (например: 60):")

    elif data == "admin_rate_fix_preset":
        if period:
            set_period_rate(period["id"], "fix_plus_per_1000", 30, 1200)
        await query.edit_message_text("✅ Тариф: 1 200 ₽ за ролик + 30 ₽ / 1 000 просм.")

    elif data == "admin_periods":
        periods = get_all_periods()
        lines = ["📅 Отчётные периоды:\n"]
        for p in periods:
            status = "🟢 Текущий" if not p["closed"] else "🔒 Закрыт"
            rate_str = (f"{p['rate_value']:.0f}₽/1000" if p["rate_type"] == "per_1000"
                        else f"{p['rate_fix']:.0f}₽ + {p['rate_value']:.0f}₽/1000")
            lines.append(f"{status} {p['start_date']} — {p['end_date']}\n   💲 {rate_str}\n")
        await query.edit_message_text("\n".join(lines))

    elif data == "admin_payouts":
        payouts = get_all_payouts()
        if not payouts:
            await query.edit_message_text("💸 Выплат ещё не было.")
            return
        lines = ["💸 История выплат:\n"]
        for p in payouts[:20]:
            lines.append(
                f"👤 {p['creator_name']}\n"
                f"   📅 {p['start_date']} — {p['end_date']}\n"
                f"   📈 +{p['views_gained']:,} | 💰 {p['amount']:.2f} ₽\n"
            )
        await query.edit_message_text("\n".join(lines))

    elif data == "admin_close_period":
        if not period:
            await query.edit_message_text("Нет активного периода.")
            return
        keyboard = [[
            InlineKeyboardButton("✅ Да, закрыть", callback_data=f"admin_confirm_close_{period['id']}"),
            InlineKeyboardButton("❌ Отмена", callback_data="admin_cancel"),
        ]]
        await query.edit_message_text(
            f"⚠️ Закрыть период {period['start_date']} — {period['end_date']}?\n\n"
            "Зафиксируются все просмотры и рассчитаются выплаты. Нельзя отменить.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("admin_confirm_close_"):
        period_id = int(data.split("_")[-1])
        new_id = close_period_and_create_next(period_id)
        new_period = get_period_by_id(new_id)
        await query.edit_message_text(
            f"✅ Период закрыт! Выплаты зафиксированы.\n\n"
            f"📅 Новый период: {new_period['start_date']} — {new_period['end_date']}"
        )

    elif data == "admin_cancel":
        await query.edit_message_text("Отменено.")

async def handle_rate_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.user_data.get("waiting_rate_input"):
        return
    if not is_admin_user(update.effective_user):
        return
    try:
        value = float(update.message.text.strip().replace(",", "."))
    except ValueError:
        await update.message.reply_text("❌ Введи число, например: 60")
        return
    period = get_current_period()
    if period:
        set_period_rate(period["id"], "per_1000", value, 0)
    await update.message.reply_text(f"✅ Тариф установлен: {value:.0f} ₽ / 1 000 просмотров\nДействует на все ролики этого периода.")
    ctx.user_data["waiting_rate_input"] = False
