"""
Слой работы с БД. Прямой перенос com.yourname.Database (Java) на sqlite3.

Схема таблиц полностью совпадает с оригиналом, поэтому существующий
bot.db (из Java-версии) можно использовать без миграций.
"""

import sqlite3
import threading
from dataclasses import dataclass
from typing import List, Optional

import config


@dataclass
class HomeworkItem:
    id: int
    subject: str
    description: str
    deadline: str


class Database:
    def __init__(self, db_path: str = config.DB_PATH):
        # check_same_thread=False — т.к. в python-telegram-bot колбэки
        # (в т.ч. джобы планировщика) могут выполняться не в том потоке,
        # где было создано соединение. Синхронизацию обеспечивает self._lock,
        # как и synchronized(lock) в оригинальном Java-коде.
        self._connection = sqlite3.connect(db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._create_tables()

    def _create_tables(self) -> None:
        with self._lock:
            cur = self._connection.cursor()
            cur.execute(
                """CREATE TABLE IF NOT EXISTS users (
                    chat_id INTEGER PRIMARY KEY,
                    group_id INTEGER,
                    group_name TEXT
                )"""
            )
            cur.execute(
                """CREATE TABLE IF NOT EXISTS homework (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER,
                    subject TEXT,
                    description TEXT,
                    deadline TEXT,
                    created_at TEXT
                )"""
            )
            cur.execute(
                """CREATE TABLE IF NOT EXISTS announcements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER,
                    title TEXT,
                    content TEXT,
                    created_at TEXT
                )"""
            )
            cur.execute(
                """CREATE TABLE IF NOT EXISTS pending_homework (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER,
                    subject TEXT,
                    description TEXT,
                    deadline TEXT,
                    suggested_by INTEGER,
                    suggested_at TEXT,
                    status TEXT DEFAULT 'pending'
                )"""
            )
            cur.execute(
                """CREATE TABLE IF NOT EXISTS pending_announcements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER,
                    title TEXT,
                    content TEXT,
                    deadline TEXT,  -- Добавлено
                    suggested_by INTEGER,
                    suggested_at TEXT,
                    status TEXT DEFAULT 'pending'
                )"""
            )
            cur.execute(
                """CREATE TABLE IF NOT EXISTS admins (
                    chat_id INTEGER PRIMARY KEY,
                    username TEXT,
                    added_by INTEGER,
                    added_at TEXT
                )"""
            )
            cur.execute(
                """CREATE TABLE IF NOT EXISTS announcements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER,
                    title TEXT,
                    content TEXT,
                    deadline TEXT,  -- Добавлено: дата в формате dd-MM
                    created_at TEXT
                )"""
            )
            self._connection.commit()
            print("✅ Таблицы БД созданы/проверены")

    # ===== Пользователи =====
    def save_group(self, chat_id: int, group_id: int) -> None:
        with self._lock:
            self._connection.execute(
                "INSERT OR REPLACE INTO users (chat_id, group_id) VALUES (?, ?)",
                (chat_id, group_id),
            )
            self._connection.commit()

    def save_user(self, chat_id: int, group_id: Optional[int], group_name: str) -> None:
        with self._lock:
            if group_id is None:
                self._connection.execute(
                    "INSERT OR REPLACE INTO users (chat_id, group_name) VALUES (?, ?)",
                    (chat_id, group_name),
                )
            else:
                self._connection.execute(
                    "INSERT OR REPLACE INTO users (chat_id, group_id, group_name) VALUES (?, ?, ?)",
                    (chat_id, group_id, group_name),
                )
            self._connection.commit()

    def get_group_id(self, chat_id: int) -> Optional[int]:
        with self._lock:
            row = self._connection.execute(
                "SELECT group_id FROM users WHERE chat_id = ?", (chat_id,)
            ).fetchone()
            if row is not None and row["group_id"] is not None:
                return int(row["group_id"])
            return None

    def delete_user(self, chat_id: int) -> None:
        with self._lock:
            self._connection.execute("DELETE FROM users WHERE chat_id = ?", (chat_id,))
            self._connection.commit()

    def get_all_subscribers(self) -> List[int]:
        with self._lock:
            rows = self._connection.execute("SELECT chat_id FROM users").fetchall()
            return [int(r["chat_id"]) for r in rows]

    # ===== Домашние задания =====
    def add_homework(self, group_id: int, subject: str, description: str, deadline: str) -> None:
        with self._lock:
            try:
                self._connection.execute(
                    "INSERT INTO homework (group_id, subject, description, deadline, created_at) "
                    "VALUES (?, ?, ?, ?, datetime('now'))",
                    (group_id, subject, description, deadline),
                )
                self._connection.commit()
                print(f"✅ ДЗ добавлено в БД: {subject} | {deadline}")
            except sqlite3.Error as e:
                print(f"❌ Ошибка добавления ДЗ: {e}")

    def get_homework_for_group(self, group_id: int) -> List[HomeworkItem]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT id, subject, description, deadline FROM homework "
                "WHERE group_id = ? ORDER BY deadline ASC",
                (group_id,),
            ).fetchall()
            return [
                HomeworkItem(r["id"], r["subject"], r["description"], r["deadline"])
                for r in rows
            ]

    # Идентична get_homework_for_group — в Java-версии тоже был дублирующий метод.
    def get_all_homework(self, group_id: int) -> List[HomeworkItem]:
        return self.get_homework_for_group(group_id)

    def delete_homework(self, homework_id: int) -> bool:
        """
        Удаляет ДЗ из основной таблицы homework по его id.

        ВАЖНО: раньше здесь также удалялась запись с тем же числовым id из
        pending_homework — но это две независимые последовательности
        AUTOINCREMENT, и id могли случайно совпасть с СОВЕРШЕННО ДРУГОЙ,
        ещё не рассмотренной заявкой на модерацию, которая от этого молча
        исчезала. Плюс одобренные заявки никогда не удалялись из
        pending_homework (только помечались статусом), поэтому их id не
        имели отношения к id в homework. Теперь approve/reject сами
        полностью удаляют строку из pending_homework (см. ниже), поэтому
        /delete должен трогать только основную таблицу.

        Возвращает True, если запись действительно была найдена и удалена.
        """
        with self._lock:
            print(f"🗑️ Удаление ДЗ ID: {homework_id}")
            cur = self._connection.execute("DELETE FROM homework WHERE id = ?", (homework_id,))
            self._connection.commit()
            if cur.rowcount > 0:
                print("   ✅ Удалено из homework")
                return True
            print("   ⚠️ Не найдено в homework")
            return False

    def debug_homework(self) -> None:
        with self._lock:
            print("===== ВСЕ ЗАПИСИ В homework =====")
            for r in self._connection.execute(
                "SELECT id, subject, description, deadline, group_id FROM homework"
            ):
                print(
                    f"   ID: {r['id']} | Предмет: {r['subject']} "
                    f"| Группа: {r['group_id']} | Дедлайн: {r['deadline']}"
                )
            print("=================================")

            print("===== ВСЕ ЗАПИСИ В pending_homework =====")
            for r in self._connection.execute(
                "SELECT id, subject, description, deadline, status FROM pending_homework"
            ):
                print(f"   ID: {r['id']} | Предмет: {r['subject']} | Статус: {r['status']}")
            print("===========================================")

    # ===== Предложения ДЗ =====
    def add_pending_homework(
        self, group_id: int, subject: str, description: str, deadline: str, suggested_by: int
    ) -> int:
        with self._lock:
            try:
                cur = self._connection.execute(
                    "INSERT INTO pending_homework "
                    "(group_id, subject, description, deadline, suggested_by, suggested_at, status) "
                    "VALUES (?, ?, ?, ?, ?, datetime('now'), 'pending')",
                    (group_id, subject, description, deadline, suggested_by),
                )
                self._connection.commit()
                return cur.lastrowid
            except sqlite3.Error as e:
                print(f"❌ Ошибка добавления pending homework: {e}")
                return -1

    def get_pending_homework(self, group_id: int) -> List[str]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT id, subject, description, deadline, suggested_by FROM pending_homework "
                "WHERE group_id = ? AND status = 'pending'",
                (group_id,),
            ).fetchall()
            return [
                f"ID: {r['id']} | 📚 {r['subject']} | 📅 {r['deadline']}\n"
                f"   {r['description']}\n"
                f"   👤 от: {r['suggested_by']}"
                for r in rows
            ]

    def approve_pending_homework(self, pending_id: int) -> bool:
        with self._lock:
            try:
                row = self._connection.execute(
                    "SELECT group_id, subject, description, deadline FROM pending_homework WHERE id = ?",
                    (pending_id,),
                ).fetchone()
                if row is None:
                    print(f"   ⚠️ ДЗ с ID {pending_id} не найдено в pending_homework")
                    return False

                print(f"✅ Принято ДЗ: {row['subject']} | Дедлайн: {row['deadline']}")

                self._connection.execute(
                    "INSERT INTO homework (group_id, subject, description, deadline, created_at) "
                    "VALUES (?, ?, ?, ?, datetime('now'))",
                    (row["group_id"], row["subject"], row["description"], row["deadline"]),
                )
                print("   ✅ Добавлено в homework")
                self._connection.execute(
                    "DELETE FROM pending_homework WHERE id = ?", (pending_id,)
                )
                self._connection.commit()
                return True
            except sqlite3.Error as e:
                self._connection.rollback()
                print(f"❌ Ошибка approve_pending_homework: {e}")
                return False

    def reject_pending_homework(self, pending_id: int) -> bool:
        """Полностью удаляет отклонённую заявку из pending_homework."""
        with self._lock:
            cur = self._connection.execute(
                "DELETE FROM pending_homework WHERE id = ?", (pending_id,)
            )
            self._connection.commit()
            return cur.rowcount > 0

    # ===== Объявления =====
    def add_announcement(self, group_id: int, title: str, content: str, deadline: str) -> None:
        with self._lock:
            self._connection.execute(
                "INSERT INTO announcements (group_id, title, content, deadline, created_at) "
                "VALUES (?, ?, ?, ?, datetime('now'))",
                (group_id, title, content, deadline),
            )
            self._connection.commit()

    def get_announcements_for_group(self, group_id: int) -> List[dict]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT id, title, content, deadline FROM announcements WHERE group_id = ?",
                (group_id,)
            ).fetchall()
            return [
                {"id": r["id"], "title": r["title"], "content": r["content"], "deadline": r["deadline"]}
                for r in rows
            ]

    def delete_announcement(self, announcement_id: int) -> bool:
        """
        Удаляет объявление из основной таблицы announcements по его id.
        См. комментарий в delete_homework — по той же причине здесь больше
        не трогается pending_announcements по совпадающему числовому id.
        """
        with self._lock:
            print(f"🗑️ Удаление объявления ID: {announcement_id}")
            cur = self._connection.execute(
                "DELETE FROM announcements WHERE id = ?", (announcement_id,)
            )
            self._connection.commit()
            if cur.rowcount > 0:
                print("   ✅ Удалено из announcements")
                return True
            print("   ⚠️ Не найдено в announcements")
            return False

    # ===== Предложения объявлений =====
    def add_pending_announcement(
        self, group_id: int, title: str, content: str, deadline: str, suggested_by: int
    ) -> int:
        with self._lock:
            try:
                cur = self._connection.execute(
                    "INSERT INTO pending_announcements "
                    "(group_id, title, content, deadline, suggested_by, suggested_at, status) "
                    "VALUES (?, ?, ?, ?, ?, datetime('now'), 'pending')",
                    (group_id, title, content, deadline, suggested_by),
                )
                self._connection.commit()
                return cur.lastrowid
            except sqlite3.Error as e:
                print(f"❌ Ошибка добавления pending announcement: {e}")
                return -1

    def get_pending_announcements(self, group_id: int) -> List[str]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT id, title, content, suggested_by FROM pending_announcements "
                "WHERE group_id = ? AND status = 'pending'",
                (group_id,),
            ).fetchall()
            return [
                f"ID: {r['id']} | 📢 {r['title']}\n"
                f"   {r['content']}\n"
                f"   👤 от: {r['suggested_by']}"
                for r in rows
            ]

    def approve_pending_announcement(self, pending_id: int) -> bool:
        with self._lock:
            try:
                row = self._connection.execute(
                    "SELECT group_id, title, content, deadline FROM pending_announcements WHERE id = ?",
                    (pending_id,),
                ).fetchone()
                if row is None:
                    return False
    
                self._connection.execute(
                    "INSERT INTO announcements (group_id, title, content, deadline, created_at) "
                    "VALUES (?, ?, ?, ?, datetime('now'))",
                    (row["group_id"], row["title"], row["content"], row["deadline"]),
                )
                self._connection.execute(
                    "DELETE FROM pending_announcements WHERE id = ?", (pending_id,)
                )
                self._connection.commit()
                return True
            except sqlite3.Error as e:
                self._connection.rollback()
                print(f"❌ Ошибка approve_pending_announcement: {e}")
                return False

    def reject_pending_announcement(self, pending_id: int) -> bool:
        """Полностью удаляет отклонённую заявку из pending_announcements."""
        with self._lock:
            cur = self._connection.execute(
                "DELETE FROM pending_announcements WHERE id = ?", (pending_id,)
            )
            self._connection.commit()
            return cur.rowcount > 0

    # ===== Администраторы =====
    def add_admin(self, chat_id: int, username: str, added_by: int) -> None:
        with self._lock:
            self._connection.execute(
                "INSERT OR REPLACE INTO admins (chat_id, username, added_by, added_at) "
                "VALUES (?, ?, ?, datetime('now'))",
                (chat_id, username, added_by),
            )
            self._connection.commit()

    def remove_admin(self, chat_id: int) -> None:
        with self._lock:
            self._connection.execute("DELETE FROM admins WHERE chat_id = ?", (chat_id,))
            self._connection.commit()

    def is_admin(self, chat_id: int) -> bool:
        with self._lock:
            row = self._connection.execute(
                "SELECT chat_id FROM admins WHERE chat_id = ?", (chat_id,)
            ).fetchone()
            return row is not None

    def get_all_admins(self) -> List[str]:
        with self._lock:
            rows = self._connection.execute("SELECT chat_id, username FROM admins").fetchall()
            return [f"{r['chat_id']} ({r['username']})" for r in rows]

    def get_master_admin(self) -> int:
        with self._lock:
            row = self._connection.execute(
                "SELECT chat_id FROM admins ORDER BY added_at LIMIT 1"
            ).fetchone()
            if row is not None:
                return int(row["chat_id"])
            return -1

    def close(self) -> None:
        with self._lock:
            self._connection.close()
