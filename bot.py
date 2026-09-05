"""
Telegram-бот расписания СПбПУ. Полный перенос PolytechBot.java на Python 3.11
+ python-telegram-bot.

Диспетчеризация команд сделана одним обработчиком текстовых сообщений
(как и в оригинале — один onUpdateReceived с цепочкой if/elif), чтобы
поведение совпадало 1:1, включая нестандартные форматы команд
(/schedule week 13-09, /suggest hw dd-MM "текст" и т.д.).
"""

import logging
import re
from datetime import date

from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

import config
import formatting
import ruz_client
import scheduler as digest_scheduler
from database import Database

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)

db = Database()

_NUMBER_RE = re.compile(r"^\d+$")


def _search_results(context: ContextTypes.DEFAULT_TYPE) -> dict:
    return context.bot_data.setdefault("search_results", {})


async def send_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str) -> None:
    """Порт PolytechBot.sendMessage(...)."""
    try:
        await context.bot.send_message(chat_id=chat_id, text=text)
    except Exception as e:
        print(e)


async def get_schedule_for_date(group_id: int, on_date: date) -> str:
    """Порт PolytechBot.getScheduleForDate(...) — используется планировщиком."""
    try:
        schedule_json = ruz_client.get_schedule(group_id, on_date)
        return formatting.get_schedule_for_date(schedule_json, on_date)
    except Exception as e:
        return f"❌ Ошибка получения расписания: {e}"


# ===================== Обработчики (порт private-методов PolytechBot.java) =====================


async def handle_admin_help(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    if not db.is_admin(chat_id):
        await send_message(context, chat_id, "⛔ У вас нет прав администратора.")
        return

    response = (
        "👑 **Панель администратора**\n\n"
        "📋 **Модерация предложений:**\n"
        "/pending — посмотреть все предложения\n"
        "/approve hw ID — принять ДЗ\n"
        "/reject hw ID — отклонить ДЗ\n"
        "/approve am ID — принять объявление\n"
        "/reject am ID — отклонить объявление\n\n"
        "🗑️ **Удаление:**\n"
        "/delete hw ID — удалить ДЗ\n"
        "/delete am ID — удалить объявление\n"
        "/list_hw — показать все ДЗ с ID (для админов)\n"
        "/list_am — показать все объявления (для админов)\n"
        "/debug_hw — отладка таблиц\n\n"
        "📢 **Рассылка:**\n"
        "/test_send — отправить тестовую рассылку\n\n"
        "👥 **Управление админами:**\n"
        "/admins — список администраторов\n"
        "/add_admin_by_id ID — добавить администратора\n"
        "/remove_admin_by_id ID — удалить администратора\n\n"
        "📌 **Примеры:**\n"
        "/approve hw 5 — принять ДЗ с ID 5\n"
        "/delete hw 2 — удалить ДЗ с ID 2\n\n"
        "💡 **Пользовательские команды:** /start — полный список"
    )
    await send_message(context, chat_id, response)


async def handle_homework_list(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    try:
        group_id = db.get_group_id(chat_id)
        if group_id is None:
            await send_message(
                context, chat_id, "⚠️ Сначала укажите группу: /setgroup Название_группы"
            )
            return

        homework = db.get_all_homework(group_id)
        if not homework:
            await send_message(context, chat_id, "📭 Домашних заданий пока нет.")
            return

        today = date.today()
        sb = ["📚 **Список всех будущих ДЗ:**\n\n"]
        has_future = False

        for hw in homework:
            try:
                day_str, month_str = hw.deadline.split("-")[:2]
                day, month = int(day_str), int(month_str)
                deadline_date = date(today.year, month, day)

                if deadline_date < today:
                    deadline_date = deadline_date.replace(year=deadline_date.year + 1)

                if deadline_date <= today:
                    continue

                has_future = True

                three_days_later_ord = (today.toordinal() + 3)
                emoji = "📌"
                if deadline_date.toordinal() <= three_days_later_ord:
                    emoji = "🔴"

                days_left = (deadline_date - today).days

                # ДОБАВЛЕНО: ID в начале строки
                sb.append(f"ID: {hw.id}\n")
                sb.append(f"{emoji} **{hw.subject}**\n")
                sb.append(f"   📝 {hw.description}\n")
                sb.append(f"   📅 Дедлайн: {hw.deadline}")
                sb.append(f" (осталось {days_left} дн.)\n")
                sb.append("-------------------\n")

            except Exception as e:
                print(f"Ошибка парсинга ДЗ: {hw.deadline} | {e}")

        if not has_future:
            sb.append("📭 На ближайшее время ДЗ нет.\n")
        else:
            sb.append("\n💡 Для удаления ДЗ используйте: /delete hw ID")

        await send_message(context, chat_id, "".join(sb))

    except Exception as e:
        await send_message(context, chat_id, f"❌ Ошибка: {e}")


async def handle_announcement_list(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    try:
        group_id = db.get_group_id(chat_id)
        if group_id is None:
            await send_message(
                context, chat_id, "⚠️ Сначала укажите группу: /setgroup Название_группы"
            )
            return

        announcements = db.get_announcements_for_group(group_id)
        if not announcements:
            await send_message(context, chat_id, "📭 Объявлений пока нет.")
            return

        sb = ["📢 **Все объявления:**\n\n"]
        for ann in announcements:
            sb.append(f"**ID: {ann['id']}**\n")
            sb.append(f"📢 {ann['title']}\n")
            sb.append(f"📅 {ann['deadline']}\n\n")

        sb.append("💡 Для удаления объявления используйте: /delete am ID")
        await send_message(context, chat_id, "".join(sb))

    except Exception as e:
        await send_message(context, chat_id, f"❌ Ошибка: {e}")


# ===== Предложения =====


async def handle_suggest_homework(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, deadline: str, text: str
) -> None:
    group_id = db.get_group_id(chat_id)
    if group_id is None:
        await send_message(context, chat_id, "⚠️ Сначала укажите группу: /setgroup Название_группы")
        return

    parts = text.split(" ", 1)
    if len(parts) < 2:
        await send_message(context, chat_id, '⚠️ Формат: /suggest hw dd-MM "Предмет: Описание"')
        return

    subject, description = parts[0], parts[1]

    pending_id = db.add_pending_homework(group_id, subject, description, deadline, chat_id)
    if pending_id != -1:
        await send_message(context, chat_id, f"✅ ДЗ отправлено на модерацию! ID: {pending_id}")
        await notify_admins(
            context,
            "📚 Новое предложение ДЗ\n"
            f"ID: {pending_id}\n"
            f"📖 {subject}\n"
            f"📅 Дедлайн: {deadline}\n"
            f"📝 {description}\n"
            f"👤 от: {chat_id}\n\n"
            "Для модерации:\n"
            f"/approve hw {pending_id}\n"
            f"/reject hw {pending_id}",
        )
    else:
        await send_message(context, chat_id, "❌ Ошибка сохранения. Попробуйте позже.")


async def handle_suggest_announcement(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, deadline: str, full_text: str
) -> None:
    group_id = db.get_group_id(chat_id)
    if group_id is None:
        await send_message(context, chat_id, "⚠️ Сначала укажите группу: /setgroup Название_группы")
        return

    if ":" in full_text:
        title, content = full_text.split(":", 1)
        title = title.strip()
        content = content.strip()
    else:
        title = full_text
        content = ""

    pending_id = db.add_pending_announcement(group_id, title, content, deadline, chat_id)
    if pending_id != -1:
        await send_message(context, chat_id, f"✅ Объявление отправлено на модерацию! ID: {pending_id}")
        await notify_admins(
            context,
            "📢 Новое предложение объявления\n"
            f"ID: {pending_id}\n"
            f"📌 {title}\n"
            f"📝 {content}\n"
            f"📅 Дедлайн: {deadline}\n"
            f"👤 от: {chat_id}\n\n"
            "Для модерации:\n"
            f"/approve am {pending_id}\n"
            f"/reject am {pending_id}",
        )
    else:
        await send_message(context, chat_id, "❌ Ошибка сохранения. Попробуйте позже.")

async def notify_admins(context: ContextTypes.DEFAULT_TYPE, message: str) -> None:
    admins = db.get_all_admins()
    for admin_info in admins:
        try:
            admin_id = int(admin_info.split(" ")[0])
            await send_message(context, admin_id, f"🔔 {message}")
        except Exception as e:
            print(e)

# ===== Модерация =====


async def handle_pending(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    if not db.is_admin(chat_id):
        await send_message(context, chat_id, "⛔ У вас нет прав.")
        return

    group_id = db.get_group_id(chat_id)
    if group_id is None:
        await send_message(context, chat_id, "⚠️ Сначала укажите группу: /setgroup Название_группы")
        return

    pending_hw = db.get_pending_homework(group_id)
    pending_am = db.get_pending_announcements(group_id)

    sb = ["📋 **Ожидают модерации:**\n\n"]

    if pending_hw:
        sb.append("📚 **ДЗ:**\n")
        for hw in pending_hw:
            sb.append(f"• {hw}\n")
        sb.append("\n")

    if pending_am:
        sb.append("📢 **Объявления:**\n")
        for am in pending_am:
            sb.append(f"• {am}\n")
        sb.append("\n")

    if not pending_hw and not pending_am:
        sb.append("📭 Нет предложений на модерации.\n\n")

    sb.append("💡 **Команды:**\n")
    sb.append("/approve hw ID — принять ДЗ\n")
    sb.append("/reject hw ID — отклонить ДЗ\n")
    sb.append("/approve am ID — принять объявление\n")
    sb.append("/reject am ID — отклонить объявление\n")
    sb.append("/delete hw ID — удалить ДЗ\n")
    sb.append("/delete am ID — удалить объявление\n\n")
    sb.append("📌 **Пример:** /approve hw 5")

    await send_message(context, chat_id, "".join(sb))


async def handle_approve(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, suggest_type: str, item_id: int
) -> None:
    if not db.is_admin(chat_id):
        await send_message(context, chat_id, "⛔ У вас нет прав.")
        return

    if suggest_type == "hw":
        ok = db.approve_pending_homework(item_id)
        if ok:
            await send_message(context, chat_id, f"✅ ДЗ ID {item_id} принято!")
        else:
            await send_message(context, chat_id, f"⚠️ Заявка на ДЗ с ID {item_id} не найдена (проверьте /pending).")
    elif suggest_type == "am":
        ok = db.approve_pending_announcement(item_id)
        if ok:
            await send_message(context, chat_id, f"✅ Объявление ID {item_id} принято!")
        else:
            await send_message(context, chat_id, f"⚠️ Заявка на объявление с ID {item_id} не найдена (проверьте /pending).")
    else:
        await send_message(context, chat_id, "⚠️ Используйте: approve hw ID или approve am ID")


async def handle_reject(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, suggest_type: str, item_id: int
) -> None:
    if not db.is_admin(chat_id):
        await send_message(context, chat_id, "⛔ У вас нет прав.")
        return

    if suggest_type == "hw":
        ok = db.reject_pending_homework(item_id)
        if ok:
            await send_message(context, chat_id, f"❌ ДЗ ID {item_id} отклонено.")
        else:
            await send_message(context, chat_id, f"⚠️ Заявка на ДЗ с ID {item_id} не найдена (проверьте /pending).")
    elif suggest_type == "am":
        ok = db.reject_pending_announcement(item_id)
        if ok:
            await send_message(context, chat_id, f"❌ Объявление ID {item_id} отклонено.")
        else:
            await send_message(context, chat_id, f"⚠️ Заявка на объявление с ID {item_id} не найдена (проверьте /pending).")
    else:
        await send_message(context, chat_id, "⚠️ Используйте: reject hw ID или reject am ID")


async def handle_delete(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, suggest_type: str, item_id: int
) -> None:
    if not db.is_admin(chat_id):
        await send_message(context, chat_id, "⛔ У вас нет прав.")
        return

    if suggest_type == "hw":
        deleted = db.delete_homework(item_id)
        if deleted:
            await send_message(context, chat_id, f"🗑️ ДЗ ID {item_id} удалено.")
        else:
            await send_message(
                context,
                chat_id,
                f"⚠️ ДЗ с ID {item_id} не найдено в списке ДЗ (/hw). "
                "Если это была ещё не одобренная заявка — используйте /reject hw ID.",
            )
    elif suggest_type == "am":
        deleted = db.delete_announcement(item_id)
        if deleted:
            await send_message(context, chat_id, f"🗑️ Объявление ID {item_id} удалено.")
        else:
            await send_message(
                context,
                chat_id,
                f"⚠️ Объявление с ID {item_id} не найдено в списке объявлений (/am). "
                "Если это была ещё не одобренная заявка — используйте /reject am ID.",
            )
    else:
        await send_message(context, chat_id, "⚠️ Используйте: delete hw ID или delete am ID")


async def notify_admins(context: ContextTypes.DEFAULT_TYPE, message: str) -> None:
    admins = db.get_all_admins()
    for admin_info in admins:
        try:
            admin_id = int(admin_info.split(" ")[0])
            await send_message(context, admin_id, f"🔔 {message}")
        except Exception as e:
            print(e)


# ===== Управление админами (только по ID) =====


async def handle_add_admin(context: ContextTypes.DEFAULT_TYPE, chat_id: int, input_str: str) -> None:
    master_id = db.get_master_admin()

    if master_id == -1:
        db.add_admin(chat_id, "MASTER", chat_id)
        await send_message(
            context,
            chat_id,
            "✅ Вы назначены главным администратором!\n"
            "Теперь вы можете добавлять других админов командой:\n"
            "/add_admin_by_id ID_пользователя",
        )
        return

    if chat_id != master_id:
        await send_message(context, chat_id, "⛔ Только главный администратор может добавлять админов.")
        return

    if not input_str.isdigit():
        await send_message(
            context,
            chat_id,
            "👤 Чтобы добавить администратора:\n"
            "1. Попросите пользователя написать боту любое сообщение\n"
            "2. Узнайте его ID через @userinfobot\n"
            "3. Введите: /add_admin_by_id ЕГО_ID\n\n"
            "Например: /add_admin_by_id 123456789",
        )
        return

    try:
        new_admin_id = int(input_str)
        await handle_add_admin_direct(context, chat_id, new_admin_id)
    except ValueError:
        await send_message(context, chat_id, "❌ Неверный ID. Введите число.")


async def handle_add_admin_direct(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, admin_id: int
) -> None:
    master_id = db.get_master_admin()
    if chat_id != master_id:
        await send_message(context, chat_id, "⛔ Только главный администратор может добавлять админов.")
        return

    if db.is_admin(admin_id):
        await send_message(context, chat_id, f"⚠️ Пользователь с ID {admin_id} уже является администратором.")
        return

    db.add_admin(admin_id, f"user_{admin_id}", chat_id)
    await send_message(context, chat_id, f"✅ Пользователь с ID {admin_id} назначен администратором!")
    await send_message(
        context,
        admin_id,
        "🔔 Вы назначены администратором бота!\n"
        "Теперь вы можете использовать команды:\n"
        "/test_send — тестовая рассылка\n"
        "/admins — список администраторов",
    )


async def handle_remove_admin(context: ContextTypes.DEFAULT_TYPE, chat_id: int, input_str: str) -> None:
    master_id = db.get_master_admin()
    if chat_id != master_id:
        await send_message(context, chat_id, "⛔ Только главный администратор может удалять админов.")
        return

    if not input_str.isdigit():
        await send_message(
            context,
            chat_id,
            "⚠️ Используйте: /remove_admin_by_id ID_пользователя\n"
            "Например: /remove_admin_by_id 123456789",
        )
        return

    try:
        admin_id = int(input_str)

        if admin_id == master_id:
            await send_message(context, chat_id, "⛔ Нельзя удалить главного администратора.")
            return

        if not db.is_admin(admin_id):
            await send_message(context, chat_id, f"⚠️ Пользователь с ID {admin_id} не является администратором.")
            return

        db.remove_admin(admin_id)
        await send_message(context, chat_id, f"✅ Пользователь с ID {admin_id} больше не администратор.")
        await send_message(context, admin_id, "🔔 Вы больше не администратор бота.")

    except ValueError:
        await send_message(context, chat_id, "❌ Неверный ID. Введите число.")


async def handle_list_admins(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    if not db.is_admin(chat_id):
        await send_message(context, chat_id, "⛔ У вас нет прав.")
        return

    admins = db.get_all_admins()
    if not admins:
        await send_message(context, chat_id, "📭 Администраторов пока нет.")
        return

    master_id = db.get_master_admin()
    sb = ["👑 Администраторы:\n\n"]
    for admin in admins:
        prefix = "👑 " if str(master_id) in admin else "• "
        sb.append(f"{prefix}{admin}\n")

    sb.append("\n💡 Чтобы добавить админа: /add_admin_by_id ID\n")
    sb.append("💡 Чтобы удалить админа: /remove_admin_by_id ID")
    await send_message(context, chat_id, "".join(sb))


# ===== Группы =====


async def handle_set_group(context: ContextTypes.DEFAULT_TYPE, chat_id: int, group_name: str) -> None:
    search_results = _search_results(context)
    try:
        data = ruz_client.search_groups(group_name)
        groups = data.get("groups") or []

        if not groups:
            await send_message(context, chat_id, "❌ Группа не найдена. Проверьте название.")
            search_results.pop(chat_id, None)
            return

        if len(groups) == 1:
            group = groups[0]
            group_id = int(group["id"])
            name = group.get("name", "")
            db.save_group(chat_id, group_id)
            await send_message(context, chat_id, f'✅ Группа "{name}" (ID: {group_id}) сохранена!')
            search_results.pop(chat_id, None)
        else:
            search_results[chat_id] = groups
            sb = ["🔍 Найдено несколько групп:\n\n"]
            for i, g in enumerate(groups, start=1):
                line = f"{i}. {g.get('name', '')}"
                faculty = g.get("faculty")
                if faculty:
                    line += f" ({faculty.get('abbr', '')})"
                sb.append(line + "\n")
            sb.append(f"\nВведите номер группы (1-{len(groups)}):")
            await send_message(context, chat_id, "".join(sb))

    except Exception as e:
        await send_message(context, chat_id, f"Ошибка поиска группы: {e}")


async def handle_group_selection(context: ContextTypes.DEFAULT_TYPE, chat_id: int, choice: int) -> None:
    search_results = _search_results(context)
    groups = search_results.get(chat_id)
    if not groups or choice < 1 or choice > len(groups):
        await send_message(context, chat_id, "❌ Неверный номер. Попробуйте снова /setgroup")
        search_results.pop(chat_id, None)
        return

    try:
        group = groups[choice - 1]
        group_id = int(group["id"])
        name = group.get("name", "")

        db.save_group(chat_id, group_id)
        await send_message(context, chat_id, f'✅ Группа "{name}" (ID: {group_id}) сохранена!')
        search_results.pop(chat_id, None)
    except Exception as e:
        await send_message(context, chat_id, f"Ошибка: {e}")


# ===== Расписание =====


async def handle_schedule_week(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, week_date: date | None
) -> None:
    try:
        group_id = db.get_group_id(chat_id)
        if group_id is None:
            await send_message(context, chat_id, "⚠️ Сначала укажите группу: /setgroup Название_группы")
            return

        if week_date is None:
            week_date = date.today()

        data = ruz_client.get_schedule(group_id, week_date)
        text = formatting.format_week_schedule(data)
        await send_message(context, chat_id, text)

    except Exception as e:
        await send_message(context, chat_id, f"Ошибка получения расписания на неделю: {e}")


async def handle_schedule(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, requested_date: date | None
) -> None:
    try:
        group_id = db.get_group_id(chat_id)
        if group_id is None:
            await send_message(context, chat_id, "⚠️ Сначала укажите группу: /setgroup Название_группы")
            return

        if requested_date is None:
            requested_date = date.today()

        data = ruz_client.get_schedule(group_id, requested_date)
        text = formatting.format_single_day_schedule(data, requested_date)
        await send_message(context, chat_id, text)

    except Exception as e:
        await send_message(context, chat_id, f"Ошибка получения расписания: {e}")

# ===================== Обработчик всех текстовых сообщений =====================


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    message_text = update.message.text
    chat_id = update.effective_chat.id

    if message_text == "/start":
        response = (
            "🤖 **Привет! Я бот для расписания СПбПУ.**\n\n"
            "📌 **Основные команды:**\n"
            "/schedule — расписание на сегодня\n"
            "/schedule ДД-ММ — расписание на конкретный день\n"
            "/schedule week — расписание на текущую неделю\n"
            "/schedule week ДД-ММ — расписание на неделю с датой\n"
            "/setgroup Название_группы — выбрать группу\n"
            "/subscribe — подписаться на рассылку\n"
            "/unsubscribe — отписаться от рассылки\n\n"
            "📚 **Просмотр ДЗ и объявлений:**\n"
            "/hw — список всех будущих ДЗ\n"
            "/am — список всех объявлений\n\n"
            "📝 **Предложить ДЗ или объявление:**\n"
            '/suggest hw ДД-ММ "Предмет: Описание"\n'
            '/suggest am ДД-ММ "Заголовок: Текст"\n\n'
            "📌 **Примеры:**\n"
            '/suggest hw 10-09 "Математика: Решить задачи 1-10"\n'
            '/suggest am 11-09 "Собрание: Встреча в 14:00"\n\n'
            "👑 **Если вы администратор, напишите /admin_help**\n\n"
            "💡 **Стать администратором:** попросите главного админа добавить вас командой /add_admin_by_id ID"
        )
        await send_message(context, chat_id, response)

    elif message_text == "/admin_help":
        await handle_admin_help(context, chat_id)

    elif message_text == "/hw":
        await handle_homework_list(context, chat_id)

    elif message_text == "/am":
        await handle_announcement_list(context, chat_id)

    elif message_text.startswith("/setgroup "):
        group_name = message_text[len("/setgroup "):].strip()
        await handle_set_group(context, chat_id, group_name)

    elif _NUMBER_RE.match(message_text) and chat_id in _search_results(context):
        await handle_group_selection(context, chat_id, int(message_text))

    elif message_text.startswith("/schedule"):
        parts = message_text.split(" ")

        if len(parts) == 1:
            # /schedule — сегодня
            await handle_schedule(context, chat_id, None)
        elif parts[1].lower() == "week":
            if len(parts) == 2:
                # /schedule week — текущая неделя
                await handle_schedule_week(context, chat_id, None)
            else:
                # /schedule week 13-09 — неделя, в которую входит дата
                try:
                    day_str, month_str = parts[2].split("-")
                    parsed = date.today().replace(month=int(month_str), day=int(day_str))
                    await handle_schedule_week(context, chat_id, parsed)
                except Exception:
                    await send_message(
                        context, chat_id, "⚠️ Неверный формат даты. Используйте: /schedule week 13-09"
                    )
        else:
            # /schedule 13-09 — конкретный день
            try:
                day_str, month_str = parts[1].split("-")
                parsed = date.today().replace(month=int(month_str), day=int(day_str))
                await handle_schedule(context, chat_id, parsed)
            except Exception:
                await send_message(
                    context, chat_id, "⚠️ Неверный формат даты. Используйте: /schedule 04-09"
                )

    elif message_text == "/subscribe":
        group_id = db.get_group_id(chat_id)
        if group_id is not None:
            db.save_user(chat_id, group_id, "")
            await send_message(context, chat_id, "✅ Вы подписаны на рассылку!")
        else:
            await send_message(
                context, chat_id, "⚠️ Сначала укажите группу: /setgroup Название_группы"
            )

    elif message_text == "/unsubscribe":
        db.delete_user(chat_id)
        await send_message(context, chat_id, "❌ Вы отписаны от рассылки.")

    elif message_text == "/test_send":
        if db.is_admin(chat_id):
            await digest_scheduler.send_daily_digest(context)
            await send_message(context, chat_id, "✅ Тестовая рассылка запущена!")
        else:
            await send_message(context, chat_id, "⛔ У вас нет прав на эту команду.")

    elif message_text.startswith("/add_admin_by_id "):
        id_str = message_text[len("/add_admin_by_id "):].strip()
        await handle_add_admin(context, chat_id, id_str)

    elif message_text.startswith("/add_admin "):
        input_str = message_text[len("/add_admin "):].strip()
        await handle_add_admin(context, chat_id, input_str)

    elif message_text.startswith("/remove_admin_by_id "):
        id_str = message_text[len("/remove_admin_by_id "):].strip()
        await handle_remove_admin(context, chat_id, id_str)

    elif message_text.startswith("/remove_admin "):
        input_str = message_text[len("/remove_admin "):].strip()
        await handle_remove_admin(context, chat_id, input_str)

    elif message_text == "/admins":
        await handle_list_admins(context, chat_id)

    # ===== Предложения =====
    elif message_text.startswith("/suggest "):
        # Убираем "/suggest " и разбиваем остальное
        rest = message_text[len("/suggest "):].strip()
        
        # Разделяем на тип, дату и текст
        parts = rest.split(" ", 2)  # Разбиваем только по первым ДВУМ пробелам
        if len(parts) < 3:
            await send_message(
                context,
                chat_id,
                "⚠️ Используйте:\n"
                '/suggest hw dd-MM "Текст ДЗ"\n'
                '/suggest am dd-MM "Текст объявления"',
            )
            return
    
        suggest_type = parts[0].lower()  # hw или am
        deadline = parts[1]              # dd-MM
        text = parts[2].strip()          # ВСЁ, что после даты — полный текст
    
        if suggest_type == "hw":
            await handle_suggest_homework(context, chat_id, deadline, text)
        elif suggest_type == "am":
            await handle_suggest_announcement(context, chat_id, deadline, text)
        else:
            await send_message(
                context,
                chat_id,
                "⚠️ Неверный формат.\n"
                'ДЗ: /suggest hw dd-MM "Текст ДЗ"\n'
                'Объявление: /suggest am dd-MM "Текст объявления"',
            )

    # ===== Модерация (только для админов) =====
    elif message_text.startswith("/pending"):
        await handle_pending(context, chat_id)

    elif message_text.startswith("/approve "):
        parts = message_text.split(" ")
        if len(parts) == 3:
            suggest_type = parts[1].lower()
            try:
                item_id = int(parts[2])
                await handle_approve(context, chat_id, suggest_type, item_id)
            except ValueError:
                pass

    elif message_text.startswith("/reject "):
        parts = message_text.split(" ")
        if len(parts) == 3:
            suggest_type = parts[1].lower()
            try:
                item_id = int(parts[2])
                await handle_reject(context, chat_id, suggest_type, item_id)
            except ValueError:
                pass

    elif message_text.startswith("/delete "):
        parts = message_text.split(" ")
        if len(parts) == 3:
            suggest_type = parts[1].lower()
            try:
                item_id = int(parts[2])
                await handle_delete(context, chat_id, suggest_type, item_id)
            except ValueError:
                await send_message(context, chat_id, "⚠️ Неверный ID. Введите число.")
        else:
            await send_message(context, chat_id, "⚠️ Используйте: /delete hw ID или /delete am ID")

    elif message_text == "/debug_hw":
        if db.is_admin(chat_id):
            db.debug_homework()
            await send_message(context, chat_id, "✅ Проверьте консоль.")
        else:
            await send_message(context, chat_id, "⛔ У вас нет прав.")

    else:
        await send_message(context, chat_id, "Неизвестная команда. Используйте /start.")

# ===================== Точка входа =====================


def main() -> None:
    application = Application.builder().token(config.BOT_TOKEN).build()
    application.bot_data["db"] = db

    application.add_handler(MessageHandler(filters.TEXT, on_message))

    digest_scheduler.register(application)

    print("✅ Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
