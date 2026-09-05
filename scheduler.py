"""
Ежедневная рассылка расписания + ДЗ + объявлений.

Порт Scheduler.java. Вместо ручного ScheduledExecutorService используется
JobQueue из python-telegram-bot (run_daily), который делает то же самое —
запуск каждый день в 18:00 (время задаётся в config.DIGEST_HOUR/MINUTE) —
но надёжнее и без ручного вычисления initialDelay.
"""

from datetime import date, timedelta

from telegram.ext import ContextTypes

import config
import formatting
import ruz_client
from database import Database


async def send_daily_digest(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Порт Scheduler.sendDailyDigest()."""
    db: Database = context.bot_data["db"]
    bot = context.bot

    print("📨 Запуск ежедневной рассылки...")

    subscribers = db.get_all_subscribers()
    if not subscribers:
        print("   Нет подписчиков.")
        return

    tomorrow = date.today() + timedelta(days=1)
    date_str = tomorrow.strftime("%d.%m.%Y")

    for chat_id in subscribers:
        try:
            group_id = db.get_group_id(chat_id)
            if group_id is None:
                continue  # у пользователя нет группы

            message_parts = []
            message_parts.append("🔔 **Ежедневная рассылка**\n")
            message_parts.append(f"📅 Расписание на **{date_str}**\n\n")

            # 1. Расписание
            try:
                schedule_json = ruz_client.get_schedule(group_id, tomorrow)
                schedule_text = formatting.get_schedule_for_date(schedule_json, tomorrow)
            except Exception as e:  # сеть/API может упасть — не роняем всю рассылку
                schedule_text = f"❌ Ошибка получения расписания: {e}"
            message_parts.append(schedule_text)

            homework_items = db.get_homework_for_group(group_id)
            print(f"📚 Найдено ДЗ для группы {group_id}: {len(homework_items)}")

            if homework_items:
                message_parts.append("\n📚 **Домашние задания:**\n")

                today = date.today()
                three_days_later = today + timedelta(days=3)
                has_homework = False

                for hw in homework_items:
                    try:
                        day_str, month_str = hw.deadline.split("-")[:2]
                        day, month = int(day_str), int(month_str)

                        deadline_date = date(today.year, month, day)

                        print(
                            f"   Проверка ДЗ: {hw.subject} | {hw.deadline} -> "
                            f"{deadline_date} (сегодня: {today})"
                        )

                        # Пропускаем ДЗ из прошлого (дедлайн строго раньше сегодня)
                        if deadline_date < today:
                            print(f"      ⏭️ Пропускаем (дедлайн в прошлом: {deadline_date} < {today})")
                            continue

                        has_homework = True

                        emoji = "📌"
                        if deadline_date <= three_days_later:
                            emoji = "🔴"

                        message_parts.append(f"{emoji} **{hw.subject}**{emoji}\n")
                        message_parts.append(f"   📝 {hw.description}\n")
                        message_parts.append(f"   📅 Дедлайн: {hw.deadline}")
                        if emoji == "🔴":
                            days_left = (deadline_date - today).days
                            message_parts.append(f" ⚠️ осталось {days_left} дн.")
                        message_parts.append("\n\n")

                    except Exception as e:
                        print(f"   ❌ Ошибка парсинга ДЗ: {hw.deadline} | {e}")

                if not has_homework:
                    message_parts.append("📭 На ближайшее время ДЗ нет.\n")
            else:
                message_parts.append("\n📭 На ближайшее время ДЗ нет.\n")

            # 3. Объявления
            announcements = db.get_announcements_for_group(group_id)
            if announcements:
                message.append("\n📢 **Объявления:**\n")
                for ann in announcements:
                    title = ann.get('title', '')
                    content = ann.get('content', '')
                    deadline = ann.get('deadline', '')
                    
                    message.append(f"📢 {title}\n")
                    if content:
                        message.append(f"   {content}\n")
                    message.append(f"   📅 {deadline}\n\n")

            message_parts.append("\n---\n")
            message_parts.append("✅ Следите за обновлениями!")

            await bot.send_message(chat_id=chat_id, text="".join(message_parts))

        except Exception as e:
            print(f"   Ошибка при отправке пользователю {chat_id}: {e}")

    print(f"✅ Рассылка завершена. Отправлено {len(subscribers)} пользователям.")


def register(application) -> None:
    """Регистрирует ежедневную задачу в JobQueue приложения."""
    from datetime import time as dtime

    application.job_queue.run_daily(
        send_daily_digest,
        time=dtime(hour=config.DIGEST_HOUR, minute=config.DIGEST_MINUTE),
        name="daily_digest",
    )
    print(
        f"⏰ Планировщик запущен. Ежедневная рассылка в "
        f"{config.DIGEST_HOUR:02d}:{config.DIGEST_MINUTE:02d}"
    )
