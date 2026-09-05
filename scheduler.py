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
    """Ежедневная рассылка в 18:00."""
    print("📨 Запуск ежедневной рассылки...")
    try:
        subscribers = db.get_all_subscribers()
        if not subscribers:
            print("   Нет подписчиков.")
            return

        tomorrow = date.today() + timedelta(days=1)
        date_str = tomorrow.strftime("%d.%m.%Y")

        sent_count = 0
        for chat_id in subscribers:
            try:
                group_id = db.get_group_id(chat_id)
                if group_id is None:
                    continue

                # 1. Расписание
                schedule_data = ruz_client.get_schedule(group_id, tomorrow)
                schedule_text = formatting.format_single_day_schedule(schedule_data, tomorrow)

                # 2. Домашние задания
                homework_items = db.get_homework_for_group(group_id)
                print(f"📚 Найдено ДЗ для группы {group_id}: {len(homework_items)}")

                # 3. Объявления
                announcements = db.get_announcements_for_group(group_id)

                # ФОРМИРУЕМ СООБЩЕНИЕ
                lines = [
                    "🔔 **Ежедневная рассылка**",
                    f"📅 Расписание на **{date_str}**",
                    "",
                    schedule_text,
                ]

                # Домашние задания
                if homework_items:
                    lines.append("")
                    lines.append("📚 **Домашние задания:**")
                    today = date.today()
                    three_days_later = today + timedelta(days=3)
                    
                    for hw in homework_items:
                        try:
                            day_str, month_str = hw.deadline.split("-")[:2]
                            day, month = int(day_str), int(month_str)
                            deadline_date = date(today.year, month, day)
                            if deadline_date < today:
                                deadline_date = deadline_date.replace(year=deadline_date.year + 1)
                            if deadline_date <= today:
                                continue
                            
                            emoji = "📌"
                            if deadline_date <= three_days_later:
                                emoji = "🔴"
                            days_left = (deadline_date - today).days
                            
                            lines.append(f"{emoji} **{hw.subject}**")
                            lines.append(f"   📝 {hw.description}")
                            lines.append(f"   📅 Дедлайн: {hw.deadline} (осталось {days_left} дн.)")
                            lines.append("")
                        except Exception as e:
                            print(f"   Ошибка парсинга ДЗ: {hw.deadline} | {e}")
                else:
                    lines.append("")
                    lines.append("📭 На ближайшее время ДЗ нет.")

                # Объявления
                if announcements:
                    lines.append("")
                    lines.append("📢 **Объявления:**")
                    for ann in announcements:
                        title = ann.get('title', '')
                        content = ann.get('content', '')
                        deadline = ann.get('deadline', '')
                        
                        lines.append(f"📢 {title}")
                        if content:
                            lines.append(f"   {content}")
                        lines.append(f"   📅 {deadline}")
                        lines.append("")
                else:
                    lines.append("")
                    lines.append("📭 Объявлений нет.")

                lines.append("---")
                lines.append("✅ Следите за обновлениями!")

                # Отправляем
                full_message = "\n".join(lines)
                await context.bot.send_message(chat_id=chat_id, text=full_message)
                sent_count += 1

            except Exception as e:
                print(f"   Ошибка при отправке пользователю {chat_id}: {e}")

        print(f"✅ Рассылка завершена. Отправлено {sent_count} пользователям.")

    except Exception as e:
        print(f"❌ Ошибка в рассылке: {e}")


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
