"""
Конфигурация бота.

Токен и имя бота теперь читаются из переменных окружения (или файла .env),
а не хранятся в коде в открытом виде, как это было в Java-версии.

ВАЖНО: старый токен был "зашит" прямо в исходники (PolytechBot.java) и
теперь виден в истории чата/репозитория. Настоятельно рекомендуется
получить новый токен через @BotFather (команда /revoke или /token) и
прописать его в .env, а старый токен считать скомпрометированным.
"""

import os

try:
    # Если установлен python-dotenv — подхватываем .env автоматически.
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# Оставляем старое значение как fallback ТОЛЬКО для того, чтобы бот
# завёлся сразу после переноса без дополнительной настройки.
# Замените/удалите его после того как заведёте .env с новым токеном.
_LEGACY_TOKEN_FALLBACK = "8641011901:AAEcET1tVnsAUPLOA1E_6GZ3uV5qgX5rV6U"

BOT_TOKEN = os.environ.get("BOT_TOKEN", _LEGACY_TOKEN_FALLBACK)
BOT_USERNAME = os.environ.get("BOT_USERNAME", "Polytech_Bio_Shedule_bot")

API_BASE = "https://ruz.spbstu.ru/api/v1/ruz"

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "bot.db"))

# Время ежедневной рассылки (локальное время сервера, как и в Java-версии).
DIGEST_HOUR = int(os.environ.get("DIGEST_HOUR", "18"))
DIGEST_MINUTE = int(os.environ.get("DIGEST_MINUTE", "0"))
