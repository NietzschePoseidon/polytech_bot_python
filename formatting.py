"""
Форматирование текстовых сообщений с расписанием.

Логика 1:1 повторяет getScheduleForDate / handleSchedule / handleScheduleWeek
из PolytechBot.java, включая структуру строк и эмодзи.
"""

from datetime import date
from typing import Any, Dict, List, Optional

_RU_WEEKDAYS_SHORT = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def _weekday_short_ru(d: date) -> str:
    return _RU_WEEKDAYS_SHORT[d.weekday()]


def _find_day(days: List[Dict[str, Any]], target_date_str: str) -> Optional[Dict[str, Any]]:
    for day in days:
        if day.get("date") == target_date_str:
            return day
    return None


def _teacher_line(lesson: Dict[str, Any], indent: str) -> Optional[str]:
    teachers = lesson.get("teachers")
    if teachers:
        full_name = teachers[0].get("full_name", "")
        return f"{indent}👨‍🏫 {full_name}"
    return None


def _auditory_line(lesson: Dict[str, Any], indent: str) -> Optional[str]:
    auditories = lesson.get("auditories")
    if not auditories:
        return None
    auditory = auditories[0]
    room = auditory.get("name", "")

    building_name = ""
    building = auditory.get("building")
    if building:
        building_name = building.get("abbr") or building.get("name") or ""

    if building_name:
        return f"{indent}🏛️ {building_name}, 🏫 ауд. {room}"
    return f"{indent}🏫 ауд. {room}"


def format_day_lessons_block(lessons: List[Dict[str, Any]]) -> str:
    """
    Формат "дневного" вида (используется и в /schedule на конкретный день,
    и в ежедневной рассылке): каждая пара + разделитель "-------------------".
    """
    parts: List[str] = []
    for lesson in lessons:
        time_start = lesson.get("time_start", "")
        time_end = lesson.get("time_end", "")
        subject = lesson.get("subject", "")

        type_name = ""
        type_obj = lesson.get("typeObj")
        if type_obj:
            type_name = type_obj.get("name", "")

        line = f"📖 {subject}"
        if type_name:
            line += f" ({type_name})"

        parts.append(f"🕐 {time_start} - {time_end}")
        parts.append(line)

        teacher_line = _teacher_line(lesson, "")
        if teacher_line:
            parts.append(teacher_line)

        auditory_line = _auditory_line(lesson, "")
        if auditory_line:
            parts.append(auditory_line)

        parts.append("-------------------")

    return "\n".join(parts) + ("\n" if parts else "")


def get_schedule_for_date(days_json: Dict[str, Any], on_date: date) -> str:
    """
    Порт getScheduleForDate(int groupId, LocalDate date) — используется
    планировщиком (scheduler.py) для ежедневной рассылки. На вход уже
    принимает распарсенный JSON-ответ ruz_client.get_schedule(...).
    """
    date_short = on_date.strftime("%d.%m")
    days = days_json.get("days") or []
    if not days:
        return f"📭 На {date_short} пар нет."

    target = on_date.strftime("%Y-%m-%d")
    day = _find_day(days, target)
    if day is None:
        return f"📭 На {date_short} пар нет."

    lessons = day.get("lessons") or []
    if not lessons:
        return f"📭 На {date_short} пар нет."

    return format_day_lessons_block(lessons)


def format_single_day_schedule(days_json: Dict[str, Any], requested_date: date) -> str:
    """Порт handleSchedule(...) — сообщение для команды /schedule [дата]."""
    days = days_json.get("days") or []
    if not days:
        return "📭 Расписание не найдено."

    target = requested_date.strftime("%Y-%m-%d")
    day = _find_day(days, target)
    if day is None:
        return f"📭 На {requested_date.strftime('%d.%m')} пар нет."

    lessons = day.get("lessons") or []
    if not lessons:
        return f"📭 На {requested_date.strftime('%d.%m')} пар нет."

    header = f"📚 Расписание на {requested_date.strftime('%d.%m.%Y')}:\n\n"
    return header + format_day_lessons_block(lessons)


def format_week_schedule(days_json: Dict[str, Any]) -> str:
    """Порт handleScheduleWeek(...) — сообщение для команды /schedule week [дата]."""
    days = days_json.get("days") or []
    if not days:
        return "📭 Расписание на неделю не найдено."

    week = days_json.get("week") or {}
    week_start = week.get("date_start", "")
    week_end = week.get("date_end", "")
    is_odd = bool(week.get("is_odd", False))

    sb: List[str] = []
    sb.append(f"📅 Расписание на неделю {week_start} — {week_end}")
    sb.append(f" ({'нечётная' if is_odd else 'чётная'})\n\n")

    for day in days:
        day_date_str = day.get("date", "")
        lessons = day.get("lessons") or []

        d = date.fromisoformat(day_date_str)
        day_of_week = _weekday_short_ru(d)

        sb.append(f"📆 {d.strftime('%d.%m')}")
        sb.append(f" ({day_of_week}):\n")

        if not lessons:
            sb.append("   ➜ Пар нет\n\n")
            continue

        for lesson in lessons:
            time_start = lesson.get("time_start", "")
            time_end = lesson.get("time_end", "")
            subject = lesson.get("subject", "")

            type_name = ""
            type_obj = lesson.get("typeObj")
            if type_obj:
                type_name = type_obj.get("name", "")

            sb.append(f"   🕐 {time_start} - {time_end}\n")
            line = f"      📖 {subject}"
            if type_name:
                line += f" ({type_name})"
            sb.append(line + "\n")

            teacher_line = _teacher_line(lesson, "      ")
            if teacher_line:
                sb.append(teacher_line + "\n")

            auditories = lesson.get("auditories")
            if auditories:
                auditory_line = _auditory_line(lesson, "      ")
                if auditory_line:
                    sb.append(auditory_line + "\n")
                sb.append("\n")

        sb.append("\n")

    return "".join(sb)
