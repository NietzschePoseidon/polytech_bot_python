"""
Клиент к REST API расписания РУЗ СПбПУ.

В Java-версии для этого использовался OkHttp + Gson напрямую к
https://ruz.spbstu.ru/api/v1/ruz/... — библиотека RuzSpbStuJavaApi.jar
фактически не вызывалась (в коде PolytechBot.java и Scheduler.java нет ни
одного обращения к её классам), поэтому в Python-версии используется тот
же самый REST API через requests, без сторонних зависимостей.
"""

from datetime import date
from typing import Any, Dict

import requests

import config

_HEADERS = {"User-Agent": "Mozilla/5.0"}
_TIMEOUT = 15


def search_groups(query: str) -> Dict[str, Any]:
    """Поиск групп по названию. Возвращает разобранный JSON-ответ API."""
    url = f"{config.API_BASE}/search/groups"
    resp = requests.get(url, params={"q": query}, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def get_schedule(group_id: int, on_date: date) -> Dict[str, Any]:
    """Расписание группы (ответ содержит 'days' и 'week')."""
    url = f"{config.API_BASE}/scheduler/{group_id}"
    resp = requests.get(
        url,
        params={"date": on_date.strftime("%Y-%m-%d")},
        headers=_HEADERS,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()
