# -*- coding: utf-8 -*-
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from event_voting_bot.database import Database
from event_voting_bot.config.config import BOT_TOKEN, ADMIN_ID
from datetime import datetime, timedelta
import re
import sqlite3
from event_voting_bot.tests.test_events_data import test_events
from telegram.ext import filters as tg_filters
import telegram
import os
from telegram.constants import ChatType

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Состояния для создания мероприятия
WAITING_TITLE, WAITING_DESCRIPTION, WAITING_DATE = range(3)

# Инициализация базы данных
db = Database()

# Глобальный словарь ожидания описания
editdesc_waits = {}

async def set_commands(application):
    commands = [
        BotCommand("start", "Начать работу с ботом"),
        BotCommand("help", "Справка"),
        BotCommand("create", "Создать мероприятие"),
        BotCommand("events", "Список мероприятий"),
        BotCommand("settings", "Персональные настройки"),
    ]
    await application.bot.set_my_commands(commands)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /start"""
    user = update.effective_user
    welcome_text = f"""
Привет, {user.first_name}! 👋

Я — бот для организации и голосования за мероприятия.

Что я умею:
• Создавать мероприятия с датой (только ближайшие 30 дней)
• Голосовать: "Иду ✅", "Не иду ❌", "Думаю 🤔"
• Показывать списки участников и статистику

<b>Основные команды:</b>
/create — создать мероприятие
/events — список активных мероприятий
/settings — персональные настройки (имя, лимит)
/help — подробная справка

<b>Внимание:</b>
• В личных сообщениях события видны только вам.
• Для групповых событий добавьте бота в группу и создайте мероприятие там.

Приятного использования! 🎉
"""
    await update.message.reply_text(welcome_text, parse_mode="HTML")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /help"""
    help_text = """
<b>Справка по использованию бота</b>

<b>Команды:</b>
/start — приветствие и краткая инструкция
/create — создать новое мероприятие
/events — список активных мероприятий
/settings — персональные настройки (имя, лимит)
/help — показать эту справку

<b>Как создать мероприятие:</b>
1. Введите /create и название события (например: /create Встреча друзей)
2. Введите дату в формате ГГГГ-ММ-ДД (только ближайшие 30 дней)
3. Событие будет создано и доступно для голосования

<b>Группы и приватность:</b>
• В личке события видны только вам.
• Для публичных событий добавьте бота в группу и создайте мероприятие там.

<b>Как голосовать:</b>
1. Введите /events
2. Нажмите на кнопку с нужным мероприятием
3. Выберите: "Иду ✅", "Не иду ❌" или "Думаю 🤔"

<b>Лимиты:</b>
• Для каждого события можно задать лимит участников (по умолчанию 10, можно изменить в настройках)

<b>Удаление и управление:</b>
• Создатель или админ может удалить мероприятие
• Создатель или админ может сбросить резервные места (плюсы)

Удачи! 🎉
"""
    await update.message.reply_text(help_text, parse_mode="HTML")

async def create_event_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args if hasattr(context, 'args') else []
    if not args:
        await update.message.reply_text(
            "Чтобы создать мероприятие, используйте команду так:\n"
            "/create Название мероприятия\n\n"
            "Например: /create Встреча друзей\n\n"
            "После этого бот попросит ввести дату мероприятия."
        )
        return
    context.user_data['event_title'] = ' '.join(args)
    context.user_data['wait_date'] = True
    # Проверяем, где создаётся событие
    chat_type = getattr(update.effective_chat, 'type', None)
    user_id = update.effective_user.id
    if chat_type == "private":
        await update.message.reply_text(
            "Это событие видно только вам. Чтобы оно было доступно другим, добавьте бота в группу и создайте событие там."
        )
    await update.message.reply_text("\U0001F4C5 Введите дату мероприятия в формате ГГГГ-ММ-ДД:")

async def handle_create_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[handle_create_date] Вход в функцию. update.effective_chat={getattr(update, 'effective_chat', None)}, update.effective_user={getattr(update, 'effective_user', None)}, context.user_data={context.user_data}")
    chat_type = getattr(update.effective_chat, 'type', None)
    user_id = update.effective_user.id
    if chat_type == "private":
        chat_id = user_id
    else:
        chat_id = get_chat_id(update)
    logger.info(f"[handle_create_date] chat_id={chat_id}, chat_type={chat_type}")
    # Удаляем проверку на группу и сообщение
    # if update.effective_chat.type not in ["group", "supergroup"]:
    #     logger.info(f"[handle_create_date] Не группа: chat_type={getattr(update.effective_chat, 'type', None)}")
    #     await update.message.reply_text("Пожалуйста, добавьте бота в группу, чтобы создавать мероприятия.")
    #     return
    logger.info(f"[handle_create_date] context.user_data={context.user_data}")
    if context.user_data.get('wait_date'):
        logger.info(f"[handle_create_date] Ожидание даты. update.message.text={getattr(update.message, 'text', None)}")
        if not update.message or not update.message.text:
            logger.info("handle_create_date: no message or text, return")
            return  # Игнорируем пустые сообщения или не текстовые
        event_date = update.message.text.strip()
        logger.info(f"handle_create_date: event_date={event_date}")
        # Валидация формата даты
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", event_date):
            logger.info("handle_create_date: invalid date format, return")
            await update.message.reply_text("❌ Дата должна быть в формате ГГГГ-ММ-ДД.")
            await update.message.reply_text("Пожалуйста, введите дату мероприятия в формате ГГГГ-ММ-ДД:")
            return  # Не писать ошибку, просто игнорировать
        try:
            date_obj = datetime.strptime(event_date, "%Y-%m-%d")
            today = datetime.now().date()
            max_date = today + timedelta(days=30)
            if not (today < date_obj.date() <= max_date):
                logger.info(f"handle_create_date: date not in range, today={today}, max_date={max_date}, return")
                await update.message.reply_text(
                    f"❌ Дата должна быть не ранее завтрашнего дня и не позднее {max_date.strftime('%Y-%m-%d')}."
                )
                await update.message.reply_text("Пожалуйста, введите дату мероприятия в формате ГГГГ-ММ-ДД:")
                return
        except Exception as e:
            logger.exception(f"handle_create_date: exception in date parsing: {e}")
            await update.message.reply_text("❌ Ошибка при разборе даты. Попробуйте снова.")
            await update.message.reply_text("Пожалуйста, введите дату мероприятия в формате ГГГГ-ММ-ДД:")
            return
        user_id = update.effective_user.id
        title = context.user_data.get('event_title')
        logger.info(f"handle_create_date: creating event, user_id={user_id}, title={title}, event_date={event_date}")
        default_limit = db.get_default_limit(user_id)
        chat_id = get_chat_id(update)
        logger.info(f"handle_create_date: chat_id={chat_id}, chat_type={getattr(update.effective_chat, 'type', None)}")
        logger.info(f"DEBUG: update.effective_chat={update.effective_chat}, update.effective_user={update.effective_user}")
        try:
            event_id = db.create_event(title, '', user_id, event_date, default_limit, chat_id)
            logger.info(f"handle_create_date: event created, event_id={event_id}")
        except Exception as e:
            logger.error(f"handle_create_date: exception in db.create_event: {e}", exc_info=True)
            await update.message.reply_text("Ошибка при создании мероприятия. Попробуйте позже.")
            return
        await update.message.reply_text(
            f"✅ Мероприятие создано успешно!\n\n"
            f"🎯 {title}\n"
            f"📅 Дата: {event_date}\n\n"
            f"ID мероприятия: {event_id}\n"
            f"Теперь пользователи могут голосовать за это мероприятие!"
        )
        context.user_data['wait_date'] = False
        context.user_data['event_title'] = None
        # Рассылка уведомлений подписчикам
        subscribers = db.get_all_subscribers()
        logger.info(f"handle_create_date: notifying {len(subscribers)} subscribers")
        for uid in subscribers:
            try:
                await context.bot.send_message(
                    chat_id=uid,
                    text=f"\U0001F195 Новое мероприятие!\n\n\U0001F3AF {title}\n\U0001F4C5 Дата: {event_date}"
                )
            except Exception as e:
                logger.warning(f"handle_create_date: failed to notify subscriber {uid}: {e}")
        chat_type = getattr(update.effective_chat, 'type', None)
        is_private = chat_type == "private"
        event_text, reply_markup = render_event_card(event_id, update.effective_user.id, chat_id, is_private)
        logger.info(f"handle_create_date: event card sent for event_id={event_id}")
        await update.message.reply_text(event_text, reply_markup=reply_markup)
    elif 'setlimit_event' in context.user_data:
        logger.info("handle_create_date: in setlimit_event branch")
        event_id = context.user_data.pop('setlimit_event')
        try:
            new_limit = int(update.message.text.strip())
            if not (1 <= new_limit <= 100):
                await update.message.reply_text("Лимит должен быть от 1 до 100")
                return
            db.set_event_limit(event_id, new_limit)
            await update.message.reply_text(f"Лимит для мероприятия {event_id} установлен: {new_limit}")
            chat_type = getattr(update.effective_chat, 'type', None)
            is_private = chat_type == "private"
            event_text, reply_markup = render_event_card(event_id, update.effective_user.id, get_chat_id(update), is_private)
            await update.message.reply_text(event_text, reply_markup=reply_markup)
        except Exception as e:
            logger.exception(f"handle_create_date: exception in setlimit_event: {e}")
            await update.message.reply_text("Введите корректное число для лимита")
        return

async def cancel_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена создания мероприятия"""
    await update.message.reply_text("❌ Создание мероприятия отменено.")
    return ConversationHandler.END

async def show_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать все активные мероприятия"""
    today = datetime.now().strftime('%Y-%m-%d')
    db.deactivate_past_events(today)
    chat_type = getattr(update.effective_chat, 'type', None)
    is_private = chat_type == "private"
    if chat_type in ["group", "supergroup"]:
        group_id = get_chat_id(update)
        # Получаем user_id всех участников группы (Telegram API не даёт напрямую, поэтому фильтруем по chat_id=group_id или chat_id=user_id создателя)
        # Показываем все события, где chat_id == group_id или chat_id == user_id участника
        # Для MVP: показываем все события, где chat_id == group_id или chat_id == user_id любого участника (user_id только текущего пользователя)
        user_id = update.effective_user.id
        events = db.get_events_for_group(group_id, user_id)
    else:
        # В личке показываем только свои события
        user_id = update.effective_user.id
        events = db.get_events_for_user(user_id)
    if not events:
        await update.message.reply_text("📭 Пока нет активных мероприятий. Создайте первое с помощью /create!")
        return
    keyboard = []
    for event in events:
        event_id, title, description, creator_id, event_date, event_limit, created_at = event
        yes_votes = db.get_yes_votes_with_plus(event_id)
        _, no_votes, maybe_votes = db.get_vote_stats(event_id)
        button_text = f"🎯 {title} (✅{yes_votes} ❌{no_votes} 🤔{maybe_votes})"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"event_{event_id}")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📋 **Активные мероприятия:**", reply_markup=reply_markup)

async def event_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /event [описание] только в группах"""
    chat = update.effective_chat
    user = update.effective_user
    if chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        await update.message.reply_text("Создавать мероприятия можно только в группе.")
        return
    # Получаем описание события
    args = context.args
    if not args:
        await update.message.reply_text("Пожалуйста, укажите описание события после команды.\nПример: /event Встреча в пятницу")
        return
    description = " ".join(args)
    chat_id = chat.id
    creator_id = user.id
    # Генерируем уникальный event_id (например, через create_event)
    event_id = db.create_event(
        title=description[:30],  # Можно использовать часть описания как заголовок
        description=description,
        creator_id=creator_id,
        event_date=None,  # Дата не указана в команде
        event_limit=None,  # Лимит не указан
        chat_id=chat_id
    )
    await update.message.reply_text(f"Мероприятие создано!\nID: {event_id}\nОписание: {description}")

def build_event_keyboard(event_id, user_id, creator_id, is_closed=False, show_admin_buttons=True):
    # Получаем текущий голос пользователя
    user_vote = None
    with db.get_conn() as conn:
        row = conn.execute("SELECT vote FROM votes WHERE event_id = ? AND user_id = ?", (event_id, user_id)).fetchone()
        if row:
            user_vote = row[0]
    # Определяем, показывать ли плюсовые кнопки как активные
    plus_active = not (user_vote in [0, 2])
    if is_closed:
        row1 = [
            InlineKeyboardButton("Иду недоступно", callback_data="noop"),
            InlineKeyboardButton("Не иду ❌", callback_data=f"vote_no_{event_id}"),
            InlineKeyboardButton("Думаю 🤔", callback_data=f"vote_maybe_{event_id}")
        ]
        row2 = [
            InlineKeyboardButton("+1 недоступно", callback_data="noop"),
            InlineKeyboardButton("-1", callback_data="noop" if not plus_active else f"minus_{event_id}")
        ]
    else:
        row1 = [
            InlineKeyboardButton("Иду ✅", callback_data=f"vote_yes_{event_id}"),
            InlineKeyboardButton("Не иду ❌", callback_data=f"vote_no_{event_id}"),
            InlineKeyboardButton("Думаю 🤔", callback_data=f"vote_maybe_{event_id}")
        ]
        row2 = [
            InlineKeyboardButton("+1", callback_data="noop" if not plus_active else f"plus_{event_id}"),
            InlineKeyboardButton("-1", callback_data="noop" if not plus_active else f"minus_{event_id}")
        ]
    # Кнопки управления только если show_admin_buttons и пользователь админ/создатель
    keyboard = [row1, row2, [InlineKeyboardButton("🔙 Назад к списку", callback_data="back_to_events")]]
    if show_admin_buttons and (user_id == creator_id or user_id == ADMIN_ID):
        keyboard.append([InlineKeyboardButton("📝 Создать/Изменить описание", callback_data=f"editdesc_{event_id}")])
        keyboard.append([InlineKeyboardButton("🛠️ Изменить лимит", callback_data=f"setlimit_{event_id}")])
        # Кнопка закрытия/открытия набора
        if is_closed:
            keyboard.append([InlineKeyboardButton("🔓 Открыть набор", callback_data=f"open_event_{event_id}")])
        else:
            keyboard.append([InlineKeyboardButton("🔒 Закрыть набор", callback_data=f"close_event_{event_id}")])
        # Кнопка удаления всегда в самом низу
        keyboard.append([InlineKeyboardButton("🗑 Удалить мероприятие", callback_data=f"delete_event_{event_id}")])
        # Кнопка "Минус всех" всегда отображается, но неактивна если плюсы неактивны
        keyboard[1].append(InlineKeyboardButton("Минус всех 🧹", callback_data="noop" if not plus_active else f"resetplus_{event_id}"))
    return InlineKeyboardMarkup(keyboard)

async def handle_event_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # --- PATCH: ensure context.user_data is always a dict ---
    if context.user_data is None:
        context.user_data = {}
    query = update.callback_query
    logger.info(f"handle_event_selection: callback_data={getattr(query, 'data', None)} user_id={getattr(query.from_user, 'id', None)} context.user_data={context.user_data}")
    await query.answer()
    user_id = query.from_user.id
    username = query.from_user.username or query.from_user.first_name
    chat_type = getattr(update.effective_chat, 'type', None) if hasattr(update, 'effective_chat') else None
    is_private = chat_type == "private"
    # Сначала обрабатываем кнопки изменения лимита
    if query.data == "plus_limit":
        if 'limit_value' in context.user_data:
            context.user_data['limit_value'] = min(100, context.user_data['limit_value'] + 1)
            await query.edit_message_text(f"Текущий лимит: {context.user_data['limit_value']}", reply_markup=build_limit_keyboard(context.user_data['limit_value']))
        return
    elif query.data == "minus_limit":
        if 'limit_value' in context.user_data:
            context.user_data['limit_value'] = max(1, context.user_data['limit_value'] - 1)
            await query.edit_message_text(f"Текущий лимит: {context.user_data['limit_value']}", reply_markup=build_limit_keyboard(context.user_data['limit_value']))
        return
    elif query.data == "plus5_limit":
        if 'limit_value' in context.user_data:
            context.user_data['limit_value'] = min(100, context.user_data['limit_value'] + 5)
            await query.edit_message_text(f"Текущий лимит: {context.user_data['limit_value']}", reply_markup=build_limit_keyboard(context.user_data['limit_value']))
        return
    elif query.data == "minus5_limit":
        if 'limit_value' in context.user_data:
            context.user_data['limit_value'] = max(1, context.user_data['limit_value'] - 5)
            await query.edit_message_text(f"Текущий лимит: {context.user_data['limit_value']}", reply_markup=build_limit_keyboard(context.user_data['limit_value']))
        return
    elif query.data == "cancel_limit":
        # Просто возвращаемся к карточке мероприятия
        if 'setlimit_event' in context.user_data:
            event_id = context.user_data.pop('setlimit_event')
            context.user_data.pop('limit_value', None)
            event_text, reply_markup = render_event_card(event_id, user_id, get_chat_id(update))
            await query.edit_message_text(event_text, reply_markup=reply_markup)
        return
    elif query.data == "confirm_limit":
        if 'setlimit_event' in context.user_data and 'limit_value' in context.user_data:
            event_id = context.user_data.pop('setlimit_event')
            new_limit = context.user_data.pop('limit_value')
            db.set_event_limit(event_id, new_limit)
            event_text, reply_markup = render_event_card(event_id, user_id, get_chat_id(update))
            await query.edit_message_text(event_text, reply_markup=reply_markup)
            await query.answer(f"Лимит установлен: {new_limit}", show_alert=False)
        return
    # --- обработка лимита по умолчанию ---
    elif query.data.startswith("plus_default_limit") or query.data.startswith("minus_default_limit") or query.data.startswith("plus5_default_limit") or query.data.startswith("minus5_default_limit") or query.data.startswith("cancel_default_limit") or query.data.startswith("confirm_default_limit"):
        # Эти callback'и обрабатываются отдельным handler'ом handle_limit_buttons, здесь просто return
        return
    if query.data.startswith("event_"):
        event_id = int(query.data.split("_")[1])
        event_text, reply_markup = render_event_card(event_id, user_id, get_chat_id(update), is_private)
        try:
            await query.edit_message_text(event_text, reply_markup=reply_markup)
        except telegram.error.BadRequest as e:
            if "Message is not modified" not in str(e):
                raise
    elif query.data.startswith("vote_yes_"):
        event_id = int(query.data.split("_")[2])
        # Универсальный поиск события
        chat_id = get_chat_id(update)
        event = get_event_for_user_or_admin(event_id, user_id, chat_id)
        if not event:
            await query.answer("Мероприятие не найдено.", show_alert=True)
            return
        event_id_db, title, description, creator_id, event_date, event_limit, created_at = event[:7]
        main, reserve = db.get_main_and_reserve(event_id, event_limit)
        display_name = db.get_display_name(user_id, username)
        in_reserve = any(display_name in label for label in reserve)
        if in_reserve:
            await query.answer("Основной список заполнен. Вы в резерве и не можете голосовать 'Иду' или плюсовать.", show_alert=True)
            return
        db.vote_for_event(event_id, user_id, username, 1)
        event_text, reply_markup = render_event_card(event_id, user_id, chat_id, is_private)
        try:
            await query.edit_message_text(event_text, reply_markup=reply_markup)
        except telegram.error.BadRequest as e:
            if "Message is not modified" not in str(e):
                raise
    elif query.data.startswith("vote_no_"):
        event_id = int(query.data.split("_")[2])
        chat_id = get_chat_id(update)
        db.vote_for_event(event_id, user_id, username, 0)
        with db.get_conn() as conn:
            conn.execute("UPDATE votes SET plus_count = 0 WHERE event_id = ? AND user_id = ?", (event_id, user_id))
            conn.commit()
        event_text, reply_markup = render_event_card(event_id, user_id, chat_id, is_private)
        try:
            await query.edit_message_text(event_text, reply_markup=reply_markup)
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e):
                pass
            else:
                raise
    elif query.data.startswith("vote_maybe_"):
        event_id = int(query.data.split("_")[2])
        chat_id = get_chat_id(update)
        db.vote_for_event(event_id, user_id, username, 2)
        # Плюсы недоступны для 'Думаю', поэтому сбрасываем plus_count
        with db.get_conn() as conn:
            conn.execute("UPDATE votes SET plus_count = 0 WHERE event_id = ? AND user_id = ?", (event_id, user_id))
            conn.commit()
        event_text, reply_markup = render_event_card(event_id, user_id, chat_id, is_private)
        try:
            await query.edit_message_text(event_text, reply_markup=reply_markup)
        except telegram.error.BadRequest as e:
            if "Message is not modified" not in str(e):
                raise
    elif query.data.startswith("plus_"):
        event_id = int(query.data.split("_")[1])
        chat_id = get_chat_id(update)
        event = get_event_for_user_or_admin(event_id, user_id, chat_id)
        if not event:
            await query.answer("Мероприятие не найдено.", show_alert=True)
            return
        event_id, title, description, creator_id, event_date, event_limit, created_at = event[:7]
        with db.get_conn() as conn:
            voters = conn.execute(
                "SELECT user_id, username, plus_count, voted_at FROM votes WHERE event_id = ? AND vote = 1 ORDER BY voted_at",
                (event_id,)
            ).fetchall()
        # Считаем текущее количество мест (основной + плюсы)
        total_yes = sum((plus or 0) + 1 for _, _, plus, _ in voters)
        if total_yes >= event_limit:
            await query.answer("Достигнут лимит участников!", show_alert=True)
            return
        db.set_plus(event_id, user_id, 1)
        event_text, reply_markup = render_event_card(event_id, user_id, chat_id, is_private)
        try:
            await query.edit_message_text(event_text, reply_markup=reply_markup)
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e):
                pass
            else:
                raise
        return
    elif query.data.startswith("minus_"):
        event_id = int(query.data.split("_")[1])
        chat_id = get_chat_id(update)
        event = get_event_for_user_or_admin(event_id, user_id, chat_id)
        if not event:
            await query.answer("Мероприятие не найдено.", show_alert=True)
            return
        with db.get_conn() as conn:
            row = conn.execute("SELECT vote FROM votes WHERE event_id = ? AND user_id = ?", (event_id, user_id)).fetchone()
            if not row or row[0] != 1:
                await query.answer("Минусовать можно только если вы выбрали 'Иду ✅'!", show_alert=True)
                return
        db.set_plus(event_id, user_id, -1)
        event_text, reply_markup = render_event_card(event_id, user_id, chat_id, is_private)
        try:
            await query.edit_message_text(event_text, reply_markup=reply_markup)
        except telegram.error.BadRequest as e:
            if "Message is not modified" not in str(e):
                raise
    elif query.data.startswith("resetplus_"):
        event_id = int(query.data.split("_")[1])
        chat_id = get_chat_id(update)
        event = get_event_for_user_or_admin(event_id, user_id, chat_id)
        if not event:
            await query.answer("Мероприятие не найдено.", show_alert=True)
            return
        _, _, _, creator_id, _, event_limit, _ = event[:7]
        if user_id == creator_id or user_id == ADMIN_ID:
            db.reset_all_plus(event_id)
            await query.answer("Плюсы сброшены.")
            event_text, reply_markup = render_event_card(event_id, user_id, chat_id, is_private)
            try:
                await query.edit_message_text(event_text, reply_markup=reply_markup)
            except telegram.error.BadRequest as e:
                if "Message is not modified" not in str(e):
                    raise
        else:
            await query.answer("Только создатель или админ может сбросить плюсы.", show_alert=True)
    elif query.data == "back_to_events":
        events = db.get_active_events(get_chat_id(update))
        if not events:
            await query.delete_message()
            await query.message.reply_text("📭 Пока нет активных мероприятий. Создайте первое с помощью /create!")
            return
        keyboard = []
        for event in events:
            event_id, title, description, creator_id, event_date, event_limit, created_at = event
            yes_votes = db.get_yes_votes_with_plus(event_id)
            _, no_votes, maybe_votes = db.get_vote_stats(event_id)
            button_text = f"🎯 {title} (✅{yes_votes} ❌{no_votes} 🤔{maybe_votes})"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"event_{event_id}")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.delete_message()
        await query.message.reply_text("📋 **Активные мероприятия:**", reply_markup=reply_markup)
        return
    elif query.data.startswith("editdesc_"):
        event_id = int(query.data.split("_")[1])
        event = get_event_for_user_or_admin(event_id, user_id)
        if not event:
            await query.answer("Мероприятие не найдено", show_alert=True)
            return
        event_id, title, description, creator_id, event_date, event_limit, created_at = event
        if user_id != creator_id and user_id != ADMIN_ID:
            await query.answer("Только создатель или админ может менять описание", show_alert=True)
            return
        editdesc_waits[user_id] = (event_id, query.message.chat_id, query.message.message_id)
        await query.delete_message()
        await query.message.reply_text("✏️ Введите новое описание мероприятия:")
        logger.info(f"Пользователь {user_id} начал редактирование описания для event_id={event_id}")
        return
    elif query.data.startswith("setlimit_"):
        event_id = int(query.data.split("_")[1])
        event = get_event_for_user_or_admin(event_id, user_id)
        if not event:
            await query.delete_message()
            await query.message.reply_text("Мероприятие не найдено или уже удалено.")
            return
        event_id, title, description, creator_id, event_date, event_limit, created_at = event
        if user_id == creator_id or user_id == ADMIN_ID:
            context.user_data['setlimit_event'] = event_id
            context.user_data['limit_value'] = event_limit
            await query.delete_message()
            await query.message.reply_text(f"Изменить лимит для '{title}': {event_limit}", reply_markup=build_limit_keyboard(event_limit))
        else:
            await query.answer("Только создатель мероприятия или админ может менять лимит!", show_alert=True)
        return
    elif query.data.startswith("delete_event_"):
        event_id = int(query.data.split("_")[2])
        event = get_event_for_user_or_admin(event_id, user_id)
        if not event:
            await query.delete_message()
            await query.message.reply_text("Мероприятие не найдено или уже удалено.")
            return
        event_id, title, description, creator_id, event_date, event_limit, created_at = event
        if user_id == creator_id or user_id == ADMIN_ID:
            db.delete_event(event_id, creator_id, get_chat_id(update))
            await query.delete_message()
            await query.message.reply_text(f"🗑 Мероприятие '{title}' удалено.")
        else:
            await query.delete_message()
            await query.message.reply_text("Только создатель или админ может удалить мероприятие.")
        return
    elif query.data.startswith("close_event_"):
        event_id = int(query.data.split("_")[2])
        event = get_event_for_user_or_admin(event_id, user_id)
        if not event:
            await query.answer("Мероприятие не найдено.", show_alert=True)
            return
        event_id, title, description, creator_id, event_date, event_limit, created_at = event
        # Считаем текущее количество идущих с учётом плюсов
        with db.get_conn() as conn:
            voters = conn.execute(
                "SELECT user_id, username, plus_count, voted_at FROM votes WHERE event_id = ? AND vote = 1 ORDER BY voted_at",
                (event_id,)
            ).fetchall()
        total_yes = sum((plus or 0) + 1 for _, _, plus, _ in voters)
        db.set_event_limit(event_id, total_yes)
        event_text, reply_markup = render_event_card(event_id, user_id, get_chat_id(update), is_private)
        await query.edit_message_text(event_text, reply_markup=reply_markup)
        return
    elif query.data.startswith("open_event_"):
        event_id = int(query.data.split("_")[2])
        logger.info(f"[open_event] Попытка открыть набор для event_id={event_id}, user_id={user_id}")
        event = get_event_for_user_or_admin(event_id, user_id)
        logger.info(f"[open_event] get_event_for_user_or_admin вернул: {event}")
        if not event:
            await query.answer("Мероприятие не найдено.", show_alert=True)
            logger.info(f"[open_event] Мероприятие не найдено для event_id={event_id}, user_id={user_id}")
            return
        # Открываем набор — увеличиваем лимит на 1
        old_limit = event[5] or 0
        new_limit = old_limit + 1
        logger.info(f"Открыть набор: event_id={event_id}, старый лимит={old_limit}, новый лимит={new_limit}")
        db.set_event_limit(event_id, new_limit)
        event_text, reply_markup = render_event_card(event_id, user_id, get_chat_id(update), is_private)
        try:
            await query.edit_message_text(event_text, reply_markup=reply_markup)
            await query.message.reply_text(f"🔓 Лимит увеличен: {old_limit} → {new_limit}")
        except telegram.error.BadRequest as e:
            if "Message is not modified" not in str(e):
                raise
        return

async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_subscriber(user.id, user.username or '', user.first_name or '', user.last_name or '')
    await update.message.reply_text("✅ Вы подписались на уведомления о новых мероприятиях!")

async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.remove_subscriber(user.id)
    await update.message.reply_text("❌ Вы отписались от уведомлений о новых мероприятиях.")

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    current = db.get_display_name(user.id, user.username or user.first_name or "Без имени")
    keyboard = [
        [InlineKeyboardButton("\U0001F464 Установить имя", callback_data="settings_setname")],
        [InlineKeyboardButton("\U0001F465 Установить лимит", callback_data="settings_setlimit")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"\U0001F464 Ваше текущее отображаемое имя: {current}\n\nВыберите действие:",
        reply_markup=reply_markup
    )

# Новый обработчик для кнопок меню настроек
async def handle_settings_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import logging
    logger = logging.getLogger(__name__)
    query = update.callback_query
    logger.info(f"[handle_settings_buttons] callback received: data={query.data}, user_id={query.from_user.id}")
    await query.answer()
    user = query.from_user
    if query.data == "settings_setname":
        context.user_data['wait_display_name'] = True
        await query.edit_message_text("Пожалуйста, введите новое имя для отображения:")
    elif query.data == "settings_setlimit":
        current = db.get_default_limit(user.id)
        context.user_data['default_limit_value'] = current
        await query.edit_message_text(
            f"Ваш лимит по умолчанию: {current}",
            reply_markup=build_limit_keyboard(current, confirm_cb="confirm_default_limit", plus_cb="plus_default_limit", minus_cb="minus_default_limit")
        )

async def setname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("Укажите имя после команды, например: /setname Вася")
        return
    name = " ".join(context.args).strip()
    if len(name) > 32:
        await update.message.reply_text("Имя слишком длинное (максимум 32 символа)")
        return
    db.set_display_name(user.id, name)
    await update.message.reply_text(f"Имя для отображения установлено: {name}")

# Добавляю функцию для генерации клавиатуры изменения лимита

def build_limit_keyboard(current, min_val=1, max_val=100, confirm_cb="confirm_limit", plus_cb="plus_limit", minus_cb="minus_limit"):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("-5", callback_data="minus5_limit" if plus_cb == "plus_limit" else "minus5_default_limit"),
            InlineKeyboardButton("-", callback_data=f"{minus_cb}"),
            InlineKeyboardButton("+", callback_data=f"{plus_cb}"),
            InlineKeyboardButton("+5", callback_data="plus5_limit" if plus_cb == "plus_limit" else "plus5_default_limit")
        ],
        [
            InlineKeyboardButton("Назад", callback_data="cancel_limit" if plus_cb == "plus_limit" else "cancel_default_limit"),
            InlineKeyboardButton("OK", callback_data=f"{confirm_cb}")
        ]
    ])

# Для setlimit команды (лимит по умолчанию)
async def setlimit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    current = db.get_default_limit(user.id)
    context.user_data['default_limit_value'] = current
    msg = await update.message.reply_text(
        f"Ваш лимит по умолчанию: {current}",
        reply_markup=build_limit_keyboard(current, confirm_cb="confirm_default_limit", plus_cb="plus_default_limit", minus_cb="minus_default_limit")
    )
    context.user_data['default_limit_message_id'] = msg.message_id
    context.user_data['default_limit_chat_id'] = msg.chat_id

async def handle_limit_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    val = context.user_data.get('default_limit_value', 10)
    if query.data == "plus_default_limit":
        val = min(100, val + 1)
        context.user_data['default_limit_value'] = val
        await query.edit_message_text(
            f"Ваш лимит по умолчанию: {val}",
            reply_markup=build_limit_keyboard(val, confirm_cb="confirm_default_limit", plus_cb="plus_default_limit", minus_cb="minus_default_limit")
        )
        return
    elif query.data == "minus_default_limit":
        val = max(1, val - 1)
        context.user_data['default_limit_value'] = val
        await query.edit_message_text(
            f"Ваш лимит по умолчанию: {val}",
            reply_markup=build_limit_keyboard(val, confirm_cb="confirm_default_limit", plus_cb="plus_default_limit", minus_cb="minus_default_limit")
        )
        return
    elif query.data == "plus5_default_limit":
        val = min(100, val + 5)
        context.user_data['default_limit_value'] = val
        await query.edit_message_text(
            f"Ваш лимит по умолчанию: {val}",
            reply_markup=build_limit_keyboard(val, confirm_cb="confirm_default_limit", plus_cb="plus_default_limit", minus_cb="minus_default_limit")
        )
        return
    elif query.data == "minus5_default_limit":
        val = max(1, val - 5)
        context.user_data['default_limit_value'] = val
        await query.edit_message_text(
            f"Ваш лимит по умолчанию: {val}",
            reply_markup=build_limit_keyboard(val, confirm_cb="confirm_default_limit", plus_cb="plus_default_limit", minus_cb="minus_default_limit")
        )
        return
    elif query.data == "cancel_default_limit":
        await query.edit_message_text("Изменение лимита по умолчанию отменено.")
        return
    elif query.data == "confirm_default_limit":
        val = context.user_data.pop('default_limit_value', 10)
        db.set_default_limit(user_id, val)
        await query.edit_message_text(f"Лимит по умолчанию установлен: {val}")
        return

async def seteventlimit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if len(context.args) < 2 or not context.args[0].isdigit() or not context.args[1].isdigit():
        await update.message.reply_text("Используйте: /seteventlimit <id> <лимит>")
        return
    event_id = int(context.args[0])
    limit = int(context.args[1])
    event = get_event_for_user_or_admin(event_id, user.id)
    if not event:
        await update.message.reply_text("Мероприятие не найдено.")
        return
    _, _, _, creator_id, _, event_limit, _ = event
    if user.id != creator_id and user.id != ADMIN_ID:
        await update.message.reply_text("Только создатель или админ может менять лимит.")
        return
    db.set_event_limit(event_id, limit)
    await update.message.reply_text(f"Лимит для мероприятия {event_id} установлен: {limit}")

async def migrate_chat_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID', '0'))
    if user_id != admin_id:
        await update.message.reply_text('Только администратор может запускать миграцию.')
        return
    db.migrate_add_chat_id()
    await update.message.reply_text('Миграция chat_id завершена.')

def get_display(user_id, username, first_name):
    return db.get_display_name(user_id, username or first_name or "Без имени")

async def handle_editdesc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # --- PATCH: ensure context.user_data is always a dict ---
    if context.user_data is None:
        context.user_data = {}
    user_id = update.effective_user.id
    logger.info(f"handle_editdesc: user_id={user_id}, editdesc_waits={editdesc_waits}")
    if user_id not in editdesc_waits:
        return
    event_id, chat_id, message_id = editdesc_waits.pop(user_id)
    new_desc = update.message.text
    db.set_event_description(event_id, new_desc)
    await update.message.reply_text("Описание мероприятия обновлено!")
    logger.info(f"Описание для event_id={event_id} изменено пользователем {user_id}")
    # Отправляем карточку мероприятия пользователю
    event_text, reply_markup = render_event_card(event_id, user_id, chat_id)
    await update.message.reply_text(event_text, reply_markup=reply_markup)

def render_event_card(event_id, user_id, chat_id=None, is_private=False):
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[render_event_card] event_id={event_id}, user_id={user_id}, chat_id={chat_id}, is_private={is_private}")
    # Если chat_id не задан, ищем событие среди всех, где пользователь — создатель или админ
    event = None
    if chat_id is not None:
        event = db.get_event(event_id, chat_id)
    if not event:
        # Попытка найти по event_id среди всех событий, где пользователь — создатель или админ
        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT id, title, description, creator_id, event_date, event_limit, created_at, chat_id FROM events WHERE id = ? AND is_active = 1",
                (event_id,)
            ).fetchone()
            if row and (row[3] == user_id or user_id == ADMIN_ID):
                event = row[:7]  # без chat_id
                chat_id = row[7]
    if not event:
        logger.info(f"[render_event_card] event not found or deactivated: event_id={event_id}")
        return "❌ Мероприятие не найдено или деактивировано.", None
    event_id, title, description, creator_id, event_date, event_limit, created_at = event
    logger.info(f"[render_event_card] creator_id={creator_id}, ADMIN_ID={ADMIN_ID}")
    yes_votes, no_votes, maybe_votes = db.get_vote_stats(event_id)
    # Получаем список голосовавших с плюсами
    with db.get_conn() as conn:
        voters = conn.execute(
            "SELECT user_id, username, plus_count, voted_at FROM votes WHERE event_id = ? AND vote = 1 ORDER BY voted_at",
            (event_id,)
        ).fetchall()
    # Формируем основной и резервный списки с учётом плюсов
    main, reserve = [], []
    count = 0
    for user_id_v, username, plus, voted_at in voters:
        display = db.get_display_name(user_id_v, username)
        n = (plus or 0) + 1
        label = display if not plus or plus == 0 else f"{display} +{plus}"
        if count < event_limit:
            main.append(label)
            count += n
        else:
            reserve.append(label)
    # Считаем общее количество "Идут" с учётом плюсов
    total_yes = sum((plus or 0) + 1 for _, _, plus, _ in voters)
    # Формируем список 'не идут'
    no_voters = []
    for user_id_v, username, plus in db.get_voters_with_ids(event_id, 0):
        display = db.get_display_name(user_id_v, username)
        no_voters.append(display)
    # Формируем список 'думают'
    maybe_voters = []
    for user_id_v, username, plus in db.get_voters_with_ids(event_id, 2):
        display = db.get_display_name(user_id_v, username)
        maybe_voters.append(display)
    # Получаем display_name или username создателя
    creator_display = db.get_display_name(creator_id, None)
    if not creator_display or creator_display == str(creator_id):
        # display_name не задан, пробуем найти username среди участников событий
        with db.get_conn() as conn:
            row = conn.execute("SELECT username FROM votes WHERE user_id = ? AND username IS NOT NULL ORDER BY id DESC LIMIT 1", (creator_id,)).fetchone()
            if row and row[0]:
                creator_display = f"@{row[0]}"
            else:
                creator_display = f"id={creator_id}"
    event_text = f"{title}\n\n📋 {description}\n\n"
    event_text += f"🗓 Дата: {event_date}\n"
    event_text += f"👤 Создатель: {creator_display}\n"
    event_text += f"👥 Лимит: {event_limit}\n\n"
    # Добавляем сообщение о приватности, если событие создано в личке
    if chat_id == creator_id:
        event_text += "⚠️ Это событие видно только вам. Чтобы оно было доступно другим, добавьте бота в группу и создайте событие там.\n\n"
    event_text += f"📊 Статистика голосов:\n"
    event_text += f"✅ Идут: {total_yes}\n"
    event_text += f"❌ Не идут: {no_votes}\n"
    event_text += f"🤔 Думают: {maybe_votes}\n\n"
    if main:
        event_text += f"Основной список: {', '.join(main)}\n"
    if reserve:
        event_text += f"Резерв: {', '.join(reserve)}\n"
    if no_voters:
        event_text += f"Не идут: {', '.join(no_voters)}\n"
    if maybe_voters:
        event_text += f"Думают: {', '.join(maybe_voters)}\n"
    is_closed = False
    # Проверяем, равен ли лимит количеству идущих (закрыт ли набор)
    if event_limit is not None and event_limit == total_yes:
        is_closed = True
    # Показываем админ-кнопки только для создателя/админа (убираем ограничение is_private)
    show_admin_buttons = (user_id == creator_id or user_id == ADMIN_ID)
    logger.info(f"[render_event_card] show_admin_buttons={show_admin_buttons} (user_id={user_id}, creator_id={creator_id}, ADMIN_ID={ADMIN_ID}, is_private={is_private})")
    reply_markup = build_event_keyboard(event_id, user_id, creator_id, is_closed, show_admin_buttons)
    return event_text, reply_markup

def get_chat_id(update):
    return update.effective_chat.id if update.effective_chat else None

# Универсальный поиск события по event_id для создателя/админа

def get_event_for_user_or_admin(event_id, user_id, chat_id=None):
    # 1. Сначала ищем по chat_id=user_id (личка)
    event = db.get_event(event_id, user_id)
    if event:
        return event
    # 2. Пробуем найти по event_id среди всех событий, где пользователь — создатель или админ
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT id, title, description, creator_id, event_date, event_limit, created_at, chat_id FROM events WHERE id = ? AND is_active = 1",
            (event_id,)
        ).fetchone()
        if row and (row[3] == user_id or user_id == ADMIN_ID):
            return row
    # 3. В группах ищем по chat_id из update
    if chat_id is not None:
        event = db.get_event(event_id, chat_id)
        if event:
            return event
    return None

async def universal_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # Если пользователь редактирует описание
    if user_id in editdesc_waits:
        await handle_editdesc(update, context)
    # Если пользователь вводит дату для создания мероприятия
    elif context.user_data.get('wait_date') or context.user_data.get('setlimit_event'):
        await handle_create_date(update, context)
    # Если пользователь вводит новое имя для отображения
    elif context.user_data.get('wait_display_name'):
        name = update.message.text.strip()
        if len(name) > 32:
            await update.message.reply_text("Имя слишком длинное (максимум 32 символа)")
            return
        db.set_display_name(user_id, name)
        context.user_data['wait_display_name'] = False
        await update.message.reply_text(f"Имя для отображения установлено: {name}")
    # Можно добавить другие режимы по необходимости

def main():
    """Запуск бота"""
    global db
    db = Database()
    # Создание приложения
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Устанавливаем меню команд Telegram
    import asyncio
    asyncio.get_event_loop().run_until_complete(set_commands(application))

    # Универсальный обработчик текстовых сообщений
    application.add_handler(MessageHandler(tg_filters.TEXT & ~tg_filters.COMMAND, universal_text_handler))
    
    # СНАЧАЛА: CallbackQueryHandler для settings (чтобы pattern имел приоритет)
    application.add_handler(CallbackQueryHandler(handle_settings_buttons, pattern="^settings_(setname|setlimit)$"))
    # Остальные обработчики
    application.add_handler(CallbackQueryHandler(handle_limit_buttons, pattern="^(plus_default_limit|minus_default_limit|plus5_default_limit|minus5_default_limit|cancel_default_limit|confirm_default_limit)$"))
    application.add_handler(CallbackQueryHandler(handle_event_selection))
    application.add_handler(CommandHandler("subscribe", subscribe))
    application.add_handler(CommandHandler("unsubscribe", unsubscribe))
    application.add_handler(CommandHandler("settings", settings))
    application.add_handler(CommandHandler("setname", setname))
    application.add_handler(CommandHandler("setlimit", setlimit))
    application.add_handler(CommandHandler("seteventlimit", seteventlimit))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("create", create_event_start))
    application.add_handler(CommandHandler("events", show_events))
    application.add_handler(CommandHandler('migrate_chat_id', migrate_chat_id_command))
    application.add_handler(CommandHandler("event", event_command))
    
    # Запуск бота
    print("🤖 Бот запущен!")
    application.run_polling()

if __name__ == '__main__':
    import os
    import signal
    import subprocess
    # Завершаем все процессы python, связанные с event_voting_bot/bot.py (кроме текущего)
    try:
        current_pid = os.getpid()
        # Получаем список процессов
        ps = subprocess.Popen(['ps', 'aux'], stdout=subprocess.PIPE)
        output = ps.communicate()[0].decode()
        for line in output.splitlines():
            if 'event_voting_bot/bot.py' in line and str(current_pid) not in line:
                pid = int(line.split()[1])
                os.kill(pid, signal.SIGKILL)
    except Exception as e:
        print(f"[WARN] Не удалось завершить другие процессы бота: {e}")
    # import subprocess
    # print('⏳ Запуск автотестов...')
    # result = subprocess.run(['python3', '-m', 'unittest', 'tests.test_database'], capture_output=True, text=True)
    # print(result.stdout)
    # if result.returncode != 0:
    #     print('❌ Автотесты не пройдены! Бот не будет запущен.')
    #     exit(1)
    # print('✅ Автотесты пройдены. Запуск бота...')
    main() 