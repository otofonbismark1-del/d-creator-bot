from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from database import get_creator, create_creator

WAITING_NAME, WAITING_TIKTOK, WAITING_YOUTUBE, WAITING_INSTAGRAM = range(4)

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    creator = get_creator(tg_id)
    if creator:
        await update.message.reply_text(
            f"👋 Привет, {creator['name']}!\n\n"
            "Команды:\n"
            "➕ /add — добавить ролик\n"
            "📊 /stats — моя статистика\n"
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "👋 Добро пожаловать в D-Creator!\n\n"
        "Давай зарегистрируемся. Как тебя зовут? (Имя и фамилия)"
    )
    return WAITING_NAME

async def get_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["name"] = update.message.text.strip()
    await update.message.reply_text(
        "📱 Введи ссылку на свой TikTok-канал\n"
        "(например: https://tiktok.com/@username)\n\n"
        "Если нет — напиши: нет"
    )
    return WAITING_TIKTOK

async def get_tiktok(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    val = update.message.text.strip()
    ctx.user_data["tiktok"] = None if val.lower() == "нет" else val
    await update.message.reply_text(
        "📺 Введи ссылку на свой YouTube-канал\n"
        "(например: https://youtube.com/@username)\n\n"
        "Если нет — напиши: нет"
    )
    return WAITING_YOUTUBE

async def get_youtube(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    val = update.message.text.strip()
    ctx.user_data["youtube"] = None if val.lower() == "нет" else val
    await update.message.reply_text(
        "📸 Введи ссылку на свой Instagram-профиль\n"
        "(например: https://instagram.com/username)\n\n"
        "Если нет — напиши: нет"
    )
    return WAITING_INSTAGRAM

async def get_instagram(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    val = update.message.text.strip()
    ctx.user_data["instagram"] = None if val.lower() == "нет" else val

    user = update.effective_user
    create_creator(
        tg_id=user.id,
        username=user.username,
        name=ctx.user_data["name"],
        tiktok=ctx.user_data["tiktok"],
        youtube=ctx.user_data["youtube"],
        instagram=ctx.user_data["instagram"],
    )

    # Уведомить админа
    admin_username = "mldznst"
    try:
        from telegram import Bot
        import os
        # Уведомление идёт через handle admin_notify в bot.py
        pass
    except Exception:
        pass

    # Отправить уведомление админу
    admin_id = ctx.bot_data.get("admin_id")
    if admin_id:
        await ctx.bot.send_message(
            chat_id=admin_id,
            text=f"🆕 Новый креатор зарегистрировался!\n\n"
                 f"👤 {ctx.user_data['name']}\n"
                 f"🆔 @{user.username or user.id}\n"
                 f"📱 TikTok: {ctx.user_data['tiktok'] or '—'}\n"
                 f"📺 YouTube: {ctx.user_data['youtube'] or '—'}\n"
                 f"📸 Instagram: {ctx.user_data['instagram'] or '—'}"
        )

    await update.message.reply_text(
        f"✅ Отлично, {ctx.user_data['name']}! Ты зарегистрирован.\n\n"
        "Команды:\n"
        "➕ /add — добавить ролик по ссылке\n"
        "📊 /stats — моя статистика и прогноз выплат\n"
    )
    return ConversationHandler.END
