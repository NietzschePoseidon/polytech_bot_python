# PolytechBot (Python 3.11)

Полный перенос Java-бота (`PolytechBot.java` + `Database.java` + `Scheduler.java`,
Maven/`pom.xml`) на Python 3.11. Функциональность и тексты сообщений
сохранены один в один. Docker-файлы намеренно не переносились — по заданию
они не нужны, бот запускается напрямую через `python bot.py` (или через
systemd/screen/tmux на сервере).

## Что изменилось технически (не в поведении, а "под капотом")

| Было (Java) | Стало (Python) |
|---|---|
| Maven, `pom.xml`, сборка в jar | `pip`, `requirements.txt` |
| `org.telegram:telegrambots` (long polling) | `python-telegram-bot` 21.x (тоже long polling) |
| `sqlite-jdbc` + ручной JDBC | встроенный модуль `sqlite3` |
| `OkHttp` + `Gson` для запроса к РУЗ API | `requests`, ответ парсится как обычный dict/JSON |
| `com.github.fleshka4:RuzSpbStuJavaApi` (в коде не вызывалась ни разу) | не переносилась — она не использовалась, бот и в Java-версии ходил напрямую в REST API `https://ruz.spbstu.ru/api/v1/ruz/...` |
| `ScheduledExecutorService` с ручным расчётом задержки до 18:00 | `JobQueue.run_daily(...)` из python-telegram-bot |
| Токен бота захардкожен в исходнике | Токен читается из переменной окружения / `.env` |

БД (`bot.db`) использует ту же самую схему таблиц, поэтому существующий
файл базы (со всеми группами, ДЗ, объявлениями и админами) можно
использовать без каких-либо миграций — он уже скопирован в этот проект.

## ⚠️ Важно: токен бота

В исходном `PolytechBot.java` токен бота был записан прямо в код открытым
текстом. Раз он попал в файлы, которые вы куда-то заливали/пересылали —
считайте его скомпрометированным. **Зайдите к @BotFather и получите новый
токен** (`/mybots` → выбрать бота → `API Token` → `Revoke current token`),
затем впишите новый токен в `.env` (см. ниже). Старый токен оставлен в
`config.py` только как запасной вариант, чтобы бот сразу завёлся после
переноса — обязательно замените/удалите его.

## Установка

```bash
python3.11 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Настройка

```bash
cp .env.example .env
# отредактируйте .env — впишите новый BOT_TOKEN
```

## Запуск

```bash
python bot.py
```

При старте бот:
1. Создаёт/проверяет таблицы в `bot.db` (или в пути из `DB_PATH`).
2. Запускает Telegram-поллинг.
3. Регистрирует ежедневную рассылку на 18:00 (настраивается через
   `DIGEST_HOUR` / `DIGEST_MINUTE` в `.env`).

## Структура проекта

```
polytech_bot_python/
├── bot.py           # точка входа, обработка всех команд (порт onUpdateReceived)
├── database.py       # работа с sqlite3 (порт Database.java)
├── ruz_client.py      # HTTP-запросы к API РУЗ СПбПУ (порт OkHttp-вызовов)
├── formatting.py      # построение текста расписания (порт handleSchedule/handleScheduleWeek)
├── scheduler.py       # ежедневная рассылка (порт Scheduler.java)
├── config.py          # токен, пути, время рассылки
├── requirements.txt
├── .env.example
└── bot.db             # существующая база (перенесена как есть)
```

## Команды бота (без изменений)

Все команды и тексты ответов идентичны исходной Java-версии:
`/start`, `/schedule [ДД-ММ | week [ДД-ММ]]`, `/setgroup`, `/subscribe`,
`/unsubscribe`, `/hw`, `/am`, `/suggest hw|am ДД-ММ "..."`, `/pending`,
`/approve`, `/reject`, `/delete`, `/admin_help`, `/admins`,
`/add_admin_by_id`, `/remove_admin_by_id`, `/test_send`, `/debug_hw`.

## Известные особенности, перенесённые как есть

- В `/admin_help` упоминаются команды `/list_hw` и `/list_am` — в
  оригинальной Java-версии обработчиков для них не было (сообщение
  "Неизвестная команда"), это поведение сохранено при переносе.
- В `/suggest hw|am ДД-ММ "Предмет: Описание"` кавычки не парсятся особым
  образом — они остаются частью текста (как и в Java-версии), поэтому
  первое "слово" после даты (включая ведущую кавычку) становится
  предметом/заголовком, а остальное — описанием.
