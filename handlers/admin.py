from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import (get_all_creators, get_videos_by_creator, get_all_videos,
                      get_current_period, get_all_periods, close_period_and_create_next,
                      get_all_payouts, get_period_by_id, get_pending_instagram_videos,
                      approve_pending_views, get_creator_by_id, set_creator_rate,
                      get_creator_rate, calc_payout)

ADMIN_PASSWORD = "123321"

def is_authed_admin(ctx):
    return ctx.user_data.get("admin_authed", False)

async def admin_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if is_authed_admin(ctx):
        await send_admin_menu(update, ctx)
        return
    ctx.user_data["waiting_admin_password"] = True
    await update.message.reply_text("🔐 Введи пароль для доступа к админ-панели:")

async def check_admin_password(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.user_data.get("waiting_admin_password"):
        return False
    text = update.message.text.strip()
    if text == ADMIN_PASSWORD:
        ctx.user_data["admin_authed"] = True
        ctx.user_data["waiting_admin_password"] = False
        ctx.bot_data["admin_id"] = update.effective_user.id
        await send_admin_menu(update, ctx)
    else:
        ctx.user_data["waiting_admin_password"] = False
        await update.message.reply_text("❌ Неверный пароль.")
    return True

async def send_admin_menu(update, ctx):
    creators = get_all_creators()
    all_videos = get_all_videos()
    period = get_current_period()
    pending = get_pending_instagram_videos()

    total_gained = sum(max(0, v["views"] - v["views_at_period_start"]) for v in all_videos)

    # Считаем общий прогноз с учётом индивидуальных тарифов
    total_payout = 0
    if period:
        for v in all_videos:
            rate = get_creator_rate(v["creator_id"], period["id"])
            gained = max(0, v["views"] - v["views_at_period_start"])
            total_payout += calc_payout(gained, 1, rate)

    lines = [
        "👑 Админ-панель D-Creator", "",
        f"📅 Период: {period['start_date']} — {period['end_date']}" if period else "Нет периода",
        f"💲 Базовый тариф: 60 ₽/1000 просм.",
        "",
        f"👥 Креаторов: {len(creators)}",
        f"🎬 Роликов: {len(all_videos)}",
        f"📈 Прирост за период: +{total_gained:,} просм.",
        f"💰 Прогноз выплат: {total_payout:,.2f} ₽",
        f"⏳ Instagram на проверке: {len(pending)} шт.",
    ]

    kb = [
        [InlineKeyboardButton("👥 Все креаторы", callback_data="adm_creators"),
         InlineKeyboardButton("🎬 Все ролики", callback_data="adm_videos")],
        [InlineKeyboardButton(f"⏳ Instagram ({len(pending)})", callback_data="adm_instagram"),
         InlineKeyboardButton("💲 Изменить тариф", callback_data="adm_rates")],
        [InlineKeyboardButton("📅 Периоды", callback_data="adm_periods"),
         InlineKeyboardButton("💸 Выплаты", callback_data="adm_payouts")],
        [InlineKeyboardButton("🔒 Закрыть период и выплатить", callback_data="adm_close_period")],
    ]
    await update.message.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))

async def admin_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_authed_admin(ctx):
        await query.edit_message_text("❌ Сессия истекла. Напиши /admin снова.")
        return

    data = query.data
    period = get_current_period()

    # ── Все креаторы ──
    if data == "adm_creators":
        creators = get_all_creators()
        lines = [f"👥 Креаторов: {len(creators)}\n"]
        kb = []
        for c in creators:
            videos = get_videos_by_creator(c["id"])
            rate = get_creator_rate(c["id"], period["id"]) if period else {"rate_type":"per_1000","rate_value":60,"rate_fix":0}
            gained = sum(max(0, v["views"] - v["views_at_period_start"]) for v in videos)
            payout = calc_payout(gained, len(videos), rate)
            rate_str = (f"{rate['rate_value']:.0f}₽/1000" if rate["rate_type"] == "per_1000"
                        else f"{rate['rate_fix']:.0f}₽+{rate['rate_value']:.0f}₽/1000")
            lines.append(f"👤 {c['name']} (@{c['username'] or c['tg_id']})\n"
                         f"   🎬 {len(videos)} р. | +{gained:,} просм. | {payout:.2f}₽ | 💲{rate_str}")
            kb.append([InlineKeyboardButton(f"👤 {c['name']}", callback_data=f"adm_creator_{c['id']}")])
        kb.append([InlineKeyboardButton("◀️ Назад", callback_data="adm_back")])
        await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("adm_creator_"):
        cid = int(data.split("_")[-1])
        c = get_creator_by_id(cid)
        videos = get_videos_by_creator(cid)
        rate = get_creator_rate(cid, period["id"]) if period else {"rate_type":"per_1000","rate_value":60,"rate_fix":0}
        gained = sum(max(0, v["views"] - v["views_at_period_start"]) for v in videos)
        payout = calc_payout(gained, len(videos), rate)
        rate_str = (f"{rate['rate_value']:.0f}₽/1000" if rate["rate_type"] == "per_1000"
                    else f"{rate['rate_fix']:.0f}₽ за ролик + {rate['rate_value']:.0f}₽/1000")
        lines = [
            f"👤 {c['name']} (@{c['username'] or c['tg_id']})",
            f"📺 YouTube: {c['youtube'] or '—'}",
            f"🎵 TikTok: {c['tiktok'] or '—'}",
            f"📸 Instagram: {c['instagram'] or '—'}",
            "",
            f"🎬 Роликов: {len(videos)}",
            f"📈 Прирост: +{gained:,} просм.",
            f"💲 Тариф: {rate_str}",
            f"💰 Прогноз: {payout:.2f} ₽",
        ]
        kb = [
            [InlineKeyboardButton("💲 Изменить тариф", callback_data=f"adm_rate_creator_{cid}")],
            [InlineKeyboardButton("◀️ Назад", callback_data="adm_creators")],
        ]
        await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))

    # ── Все ролики ──
    elif data == "adm_videos":
        all_videos = get_all_videos()
        if not all_videos:
            await query.edit_message_text("Нет роликов.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="adm_back")]]))
            return
        lines = [f"🎬 Все ролики ({len(all_videos)} шт.):\n"]
        for v in all_videos[:40]:
            icon = {"youtube":"📺","tiktok":"🎵","instagram":"📸"}.get(v["platform"],"🎬")
            gained = max(0, v["views"] - v["views_at_period_start"])
            rate = get_creator_rate(v["creator_id"], period["id"]) if period else {"rate_type":"per_1000","rate_value":60,"rate_fix":0}
            payout = calc_payout(gained, 1, rate)
            pending_s = f" ⏳{v['pending_views']:,}" if v["pending_views"] else ""
            title = (v["title"] or "—")[:25]
            lines.append(f"{icon} {v['creator_name']} — {title}\n   👁{v['views']:,}{pending_s} | +{gained:,} | {payout:.2f}₽")
        kb = [[InlineKeyboardButton("◀️ Назад", callback_data="adm_back")]]
        await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))

    # ── Instagram на проверке ──
    elif data == "adm_instagram":
        pending = get_pending_instagram_videos()
        if not pending:
            await query.edit_message_text("✅ Нет Instagram роликов на проверке.",
                                          reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="adm_back")]]))
            return
        lines = [f"📸 Instagram на проверке ({len(pending)} шт.):\n"]
        kb = []
        for v in pending:
            lines.append(f"👤 {v['creator_name']}\n🔗 {v['url']}\n👁 Сейчас: {v['views']:,} | Заявлено: {v['pending_views']:,}\n")
            kb.append([InlineKeyboardButton(
                f"✅ Одобрить {v['creator_name']} — {v['pending_views']:,}",
                callback_data=f"adm_approve_ig_{v['id']}_{v['creator_tg_id']}"
            )])
        kb.append([InlineKeyboardButton("◀️ Назад", callback_data="adm_back")])
        await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("adm_approve_ig_"):
        parts = data.split("_")
        video_id = int(parts[3])
        creator_tg_id = int(parts[4])
        approve_pending_views(video_id)
        try:
            await ctx.bot.send_message(
                creator_tg_id,
                "✅ Просмотры Instagram одобрены!\nТвои просмотры учтены в статистике. Смотри кнопку 📊 Статистика."
            )
        except Exception:
            pass
        await query.edit_message_text("✅ Просмотры одобрены, креатор уведомлён!",
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="adm_instagram")]]))

    # ── Тарифы ──
    elif data == "adm_rates":
        creators = get_all_creators()
        lines = ["💲 Выбери креатора для изменения тарифа:"]
        kb = [[InlineKeyboardButton(f"👤 {c['name']}", callback_data=f"adm_rate_creator_{c['id']}")] for c in creators]
        kb.append([InlineKeyboardButton("◀️ Назад", callback_data="adm_back")])
        await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("adm_rate_creator_"):
        cid = int(data.split("_")[-1])
        c = get_creator_by_id(cid)
        rate = get_creator_rate(cid, period["id"]) if period else {"rate_type":"per_1000","rate_value":60,"rate_fix":0}
        rate_str = (f"{rate['rate_value']:.0f}₽/1000" if rate["rate_type"] == "per_1000"
                    else f"{rate['rate_fix']:.0f}₽ + {rate['rate_value']:.0f}₽/1000")
        kb = [
            [InlineKeyboardButton("💰 Фикс 1200₽ + 30₽/1000", callback_data=f"adm_setrate_fix_{cid}")],
            [InlineKeyboardButton("✏️ Своя цена за 1000 просм.", callback_data=f"adm_setrate_custom_{cid}")],
            [InlineKeyboardButton("◀️ Назад", callback_data="adm_rates")],
        ]
        await query.edit_message_text(
            f"💲 Тариф для {c['name']}\nСейчас: {rate_str}\n\nВыбери новый:",
            reply_markup=InlineKeyboardMarkup(kb)
        )

    elif data.startswith("adm_setrate_fix_"):
        cid = int(data.split("_")[-1])
        c = get_creator_by_id(cid)
        if period:
            set_creator_rate(cid, period["id"], "fix_plus_per_1000", 30, 1200)
        try:
            await ctx.bot.send_message(
                c["tg_id"],
                "💲 Твой тариф изменён!\n\nНовый тариф: 1 200 ₽ за ролик + 30 ₽/1000 просмотров\nДействует с этого периода."
            )
        except Exception:
            pass
        await query.edit_message_text(
            f"✅ Тариф для {c['name']} установлен: 1200₽ + 30₽/1000\nКреатор уведомлён.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="adm_rates")]])
        )

    elif data.startswith("adm_setrate_custom_"):
        cid = int(data.split("_")[-1])
        ctx.user_data["waiting_custom_rate_cid"] = cid
        ctx.user_data["waiting_custom_rate"] = True
        await query.edit_message_text(
            f"✏️ Введи цену за 1 000 просмотров для этого креатора (например: 45):"
        )

    # ── Периоды ──
    elif data == "adm_periods":
        periods = get_all_periods()
        lines = ["📅 Отчётные периоды:\n"]
        for p in periods:
            status = "🟢 Текущий" if not p["closed"] else "🔒 Закрыт"
            lines.append(f"{status} {p['start_date']} — {p['end_date']}")
        kb = [[InlineKeyboardButton("◀️ Назад", callback_data="adm_back")]]
        await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))

    # ── Выплаты ──
    elif data == "adm_payouts":
        payouts = get_all_payouts()
        if not payouts:
            await query.edit_message_text("💸 Выплат ещё не было.",
                                          reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="adm_back")]]))
            return
        lines = ["💸 История выплат:\n"]
        for p in payouts[:20]:
            lines.append(f"👤 {p['creator_name']}\n   📅 {p['start_date']}—{p['end_date']} | +{p['views_gained']:,} | 💰{p['amount']:.2f}₽")
        kb = [[InlineKeyboardButton("◀️ Назад", callback_data="adm_back")]]
        await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))

    # ── Закрыть период ──
    elif data == "adm_close_period":
        if not period:
            await query.edit_message_text("Нет активного периода.")
            return
        kb = [
            [InlineKeyboardButton("✅ Да, закрыть и выплатить", callback_data=f"adm_confirm_close_{period['id']}")],
            [InlineKeyboardButton("❌ Отмена", callback_data="adm_back")],
        ]
        await query.edit_message_text(
            f"⚠️ Закрыть период {period['start_date']} — {period['end_date']}?\n\nБудут зафиксированы все просмотры и рассчитаны выплаты.",
            reply_markup=InlineKeyboardMarkup(kb)
        )

    elif data.startswith("adm_confirm_close_"):
        period_id = int(data.split("_")[-1])
        new_id, payout_summary = close_period_and_create_next(period_id)
        new_period = get_period_by_id(new_id)

        # Отправляем полный список роликов и выплат
        old_period = get_period_by_id(period_id)
        header = f"✅ Период {old_period['start_date']} — {old_period['end_date']} закрыт!\n\n💸 ИТОГОВЫЙ ОТЧЁТ:\n"
        await query.edit_message_text(header + f"📅 Новый период: {new_period['start_date']} — {new_period['end_date']}")

        for summary in payout_summary:
            lines = [
                f"👤 {summary['name']}",
                f"💰 К выплате: {summary['amount']:.2f} ₽",
                f"📈 Прирост: +{summary['views']:,} просм.",
                f"🎬 Роликов: {summary['video_count']}",
                "",
                "🔗 Ролики:",
            ]
            for v in summary["videos"]:
                icon = {"youtube":"📺","tiktok":"🎵","instagram":"📸"}.get(v["platform"],"🎬")
                gained = max(0, v["views"] - v["views_at_period_start"])
                title = (v["title"] or "—")[:30]
                lines.append(f"{icon} {title}\n   👁 {v['views']:,} | +{gained:,} | {v['url']}")
            await ctx.bot.send_message(query.from_user.id, "\n".join(lines))

    elif data == "adm_back":
        # Перерисовать главное меню
        creators = get_all_creators()
        all_videos = get_all_videos()
        pending = get_pending_instagram_videos()
        total_gained = sum(max(0, v["views"] - v["views_at_period_start"]) for v in all_videos)
        total_payout = 0
        if period:
            for v in all_videos:
                rate = get_creator_rate(v["creator_id"], period["id"])
                total_payout += calc_payout(max(0, v["views"] - v["views_at_period_start"]), 1, rate)
        lines = [
            "👑 Админ-панель D-Creator", "",
            f"📅 {period['start_date']} — {period['end_date']}" if period else "",
            f"👥 {len(creators)} | 🎬 {len(all_videos)} | 📈 +{total_gained:,} | 💰 {total_payout:.2f}₽",
            f"⏳ Instagram: {len(pending)}"
        ]
        kb = [
            [InlineKeyboardButton("👥 Все креаторы", callback_data="adm_creators"),
             InlineKeyboardButton("🎬 Все ролики", callback_data="adm_videos")],
            [InlineKeyboardButton(f"⏳ Instagram ({len(pending)})", callback_data="adm_instagram"),
             InlineKeyboardButton("💲 Изменить тариф", callback_data="adm_rates")],
            [InlineKeyboardButton("📅 Периоды", callback_data="adm_periods"),
             InlineKeyboardButton("💸 Выплаты", callback_data="adm_payouts")],
            [InlineKeyboardButton("🔒 Закрыть период и выплатить", callback_data="adm_close_period")],
        ]
        await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))

async def handle_admin_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых вводов в режиме админа"""
    # Пароль
    if ctx.user_data.get("waiting_admin_password"):
        await check_admin_password(update, ctx)
        return True

    # Кастомный тариф
    if ctx.user_data.get("waiting_custom_rate") and is_authed_admin(ctx):
        try:
            value = float(update.message.text.strip().replace(",", "."))
        except ValueError:
            await update.message.reply_text("❌ Введи число, например: 45")
            return True
        cid = ctx.user_data.get("waiting_custom_rate_cid")
        c = get_creator_by_id(cid)
        period = get_current_period()
        if period and c:
            set_creator_rate(cid, period["id"], "per_1000", value, 0)
            try:
                await ctx.bot.send_message(
                    c["tg_id"],
                    f"💲 Твой тариф изменён!\n\nНовый тариф: {value:.0f} ₽/1000 просмотров\nДействует с этого периода."
                )
            except Exception:
                pass
            await update.message.reply_text(
                f"✅ Тариф для {c['name']}: {value:.0f}₽/1000. Креатор уведомлён."
            )
        ctx.user_data["waiting_custom_rate"] = False
        return True

    return False
