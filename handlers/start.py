from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from database import get_creator, create_creator

WAITING_NAME, WAITING_TIKTOK, WAITING_YOUTUBE, WAITING_INSTAGRAM = range(4)

def main_menu():
    kb = [
        [KeyboardButton("➕ Добавить ролик"), KeyboardButton("📊 Статистика")],
        [KeyboardButton("🎬 Мои ролики"), KeyboardButton("📅 Периоды и выплаты")],
        [KeyboardButton("🔄 Обновить просмотры")],
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    creator = get_creator(tg_id)
    if creator:
        await update.message.reply_text(
            f"👋 Привет, {creator['name']}!\nВыбери действие:",
            reply_markup=main_menu()
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "👋 Добро пожаловать в D-Creator!\n\nКак тебя зовут? (Имя и фамилия)",
        reply_markup=ReplyKeyboardRemove()
    )
    return WAITING_NAME

async def get_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["name"] = update.message.text.strip()
    await update.message.reply_text(
        "📱 Ссылка на TikTok-канал\n(например: https://tiktok.com/@username)\n\nЕсли нет — напиши: нет"
    )
    return WAITING_TIKTOK

async def get_tiktok(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    val = update.message.text.strip()
    ctx.user_data["tiktok"] = None if val.lower() == "нет" else val
    await update.message.reply_text(
        "📺 Ссылка на YouTube-канал\n(например: https://youtube.com/@username)\n\nЕсли нет — напиши: нет"
    )
    return WAITING_YOUTUBE

async def get_youtube(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    val = update.message.text.strip()
    ctx.user_data["youtube"] = None if val.lower() == "нет" else val
    await update.message.reply_text(
        "📸 Ссылка на Instagram-профиль\n(например: https://instagram.com/username)\n\nЕсли нет — напиши: нет"
    )
    return WAITING_INSTAGRAM

async def get_instagram(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    val = update.message.text.strip()
    ctx.user_data["instagram"] = None if val.lower() == "нет" else val

    user = update.effective_user
    create_creator(
        tg_id=user.id, username=user.username, name=ctx.user_data["name"],
        tiktok=ctx.user_data["tiktok"], youtube=ctx.user_data["youtube"],
        instagram=ctx.user_data["instagram"],
    )

    admin_id = ctx.bot_data.get("admin_id")
    if admin_id:
        await ctx.bot.send_message(
            admin_id,
            f"🆕 Новый креатор!\n\n"
            f"👤 {ctx.user_data['name']} (@{user.username or user.id})\n"
            f"📱 TikTok: {ctx.user_data['tiktok'] or '—'}\n"
            f"📺 YouTube: {ctx.user_data['youtube'] or '—'}\n"
            f"📸 Instagram: {ctx.user_data['instagram'] or '—'}"
        )

    await update.message.reply_text(
        f"✅ Готово, {ctx.user_data['name']}!\nДобро пожаловать в D-Creator!",
        reply_markup=main_menu()
    )
    return ConversationHandler.END
