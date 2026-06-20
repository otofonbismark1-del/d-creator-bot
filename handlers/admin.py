import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import get_all_creators, get_videos_by_creator, get_all_videos, verify_instagram

ADMIN_USERNAME = "mldznst"
RATE_PER_1000 = 60

def is_admin(update: Update):
    user = update.effective_user
    return user.username and user.username.lower() == ADMIN_USERNAME.lower()

async def admin_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("❌ У тебя нет доступа к этой команде.")
        return

    # Сохранить admin_id для уведомлений
    ctx.bot_data["admin_id"] = update.effective_user.id

    creators = get_all_creators()
    all_videos = get_all_videos()

    total_views = sum(v["views"] for v in all_videos)
    total_payout = round(total_views / 1000 * RATE_PER_1000, 2)

    lines = [
        "👑 Админ-панель D-Creator",
        "",
        f"👥 Всего креаторов: {len(creators)}",
        f"🎬 Всего роликов: {len(all_videos)}",
        f"👁 Суммарные просмотры: {total_views:,}",
        f"💰 Общий прогноз выплат: {total_payout:,.2f} ₽",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "👤 Список креаторов:",
        "",
    ]

    for c in creators:
        videos = get_videos_by_creator(c["id"])
        c_views = sum(v["views"] for v in videos)
        c_payout = round(c_views / 1000 * RATE_PER_1000, 2)
        ig_status = "✅" if c["instagram_verified"] else ("⚠️" if c["instagram"] else "—")

        lines.append(
            f"👤 {c['name']} (@{c['username'] or c['tg_id']})\n"
            f"   📺 YT: {c['youtube'] or '—'}\n"
            f"   🎵 TT: {c['tiktok'] or '—'}\n"
            f"   📸 IG: {c['instagram'] or '—'} {ig_status}\n"
            f"   🎬 Роликов: {len(videos)} | 👁 {c_views:,} | 💰 {c_payout:.2f} ₽\n"
        )

    await update.message.reply_text("\n".join(lines))

    # Кнопки действий
    keyboard = [
        [InlineKeyboardButton("📊 Все ролики", callback_data="admin_all_videos")],
        [InlineKeyboardButton("⚠️ Instagram на проверку", callback_data="admin_check_instagram")],
    ]
    await update.message.reply_text(
        "Выбери действие:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def admin_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not (query.from_user.username and query.from_user.username.lower() == ADMIN_USERNAME.lower()):
        await query.edit_message_text("❌ Нет доступа.")
        return

    data = query.data

    if data == "admin_all_videos":
        all_videos = get_all_videos()
        if not all_videos:
            await query.edit_message_text("Нет роликов.")
            return

        lines = ["🎬 Все ролики:\n"]
        for v in all_videos[:30]:
            icon = {"youtube": "📺", "tiktok": "🎵", "instagram": "📸"}.get(v["platform"], "🎬")
            payout = round(v["views"] / 1000 * RATE_PER_1000, 2)
            title = (v["title"] or "—")[:30]
            lines.append(f"{icon} {v['creator_name']} — {title}\n   👁 {v['views']:,} | 💰 {payout:.2f} ₽")

        await query.edit_message_text("\n".join(lines))

    elif data == "admin_check_instagram":
        all_videos = get_all_videos()
        ig_videos = [v for v in all_videos if v["platform"] == "instagram"]

        if not ig_videos:
            await query.edit_message_text("✅ Нет роликов Instagram на проверку.")
            return

        lines = ["📸 Instagram ролики (проверь вручную):\n"]
        keyboard = []
        for v in ig_videos:
            lines.append(f"👤 {v['creator_name']}\n🔗 {v['url']}\n👁 {v['views']:,} просм.\n")
            keyboard.append([
                InlineKeyboardButton(
                    f"✅ Подтвердить {v['creator_name']}",
                    callback_data=f"admin_verify_ig_{v['id']}"
                )
            ])

        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
        )

    elif data.startswith("admin_verify_ig_"):
        video_id = int(data.split("_")[-1])
        verify_instagram(video_id)
        await query.edit_message_text(f"✅ Instagram ролик #{video_id} подтверждён!")
