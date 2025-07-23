from datetime import datetime
import logging
import os
import sqlite3
from typing import List, Optional, Tuple

from .config import config

try:
    import psycopg2
except ImportError:
    psycopg2 = None

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path: str = None):
        if config.DB_TYPE == 'sqlite':
            self.db_type = 'sqlite'
            self.db_path = db_path if db_path else config.SQLITE_PATH
        elif config.DB_TYPE == 'postgres':
            self.db_type = 'postgres'
            self.db_host = config.DB_HOST
            self.db_port = config.DB_PORT
            self.db_user = config.DB_USER
            self.db_password = config.DB_PASSWORD
            self.db_name = config.DB_NAME
            if psycopg2 is None:
                raise ImportError('psycopg2 is required for PostgreSQL support')
        else:
            raise ValueError(f"Unknown DB_TYPE: {config.DB_TYPE}")
        self.init_db()

    def get_conn(self):
        if self.db_type == 'sqlite':
            return sqlite3.connect(self.db_path)
        elif self.db_type == 'postgres':
            return psycopg2.connect(  # type: ignore
                dbname=self.db_name,
                user=self.db_user,
                password=self.db_password,
                host=self.db_host,
                port=self.db_port
            )
        else:
            raise ValueError(f"Unknown db_type: {self.db_type}")

    def init_db(self):
        """
        Инициализация базы данных (создание таблиц, если их нет)
        """
        with self.get_conn() as conn:
            cur = conn.cursor()
            if self.db_type == 'sqlite':
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        description TEXT,
                        creator_id INTEGER NOT NULL,
                        event_date TEXT NOT NULL,
                        event_limit INTEGER,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        is_active INTEGER DEFAULT 1,
                        chat_id BIGINT NOT NULL
                    )
                ''')
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS votes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        username TEXT,
                        vote INTEGER NOT NULL,
                        plus_count INTEGER DEFAULT 0,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        voted_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS subscribers (
                        user_id INTEGER PRIMARY KEY
                    )
                ''')
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS user_settings (
                        user_id INTEGER PRIMARY KEY,
                        display_name TEXT,
                        default_limit INTEGER
                    )
                ''')
            elif self.db_type == 'postgres':
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS events (
                        id SERIAL PRIMARY KEY,
                        title TEXT NOT NULL,
                        description TEXT,
                        creator_id BIGINT NOT NULL,
                        event_date TEXT NOT NULL,
                        event_limit INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        is_active INTEGER DEFAULT 1,
                        chat_id BIGINT NOT NULL
                    )
                ''')
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS votes (
                        id SERIAL PRIMARY KEY,
                        event_id INTEGER NOT NULL REFERENCES events(id),
                        user_id BIGINT NOT NULL,
                        vote INTEGER NOT NULL,
                        plus_count INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS subscribers (
                        user_id BIGINT PRIMARY KEY
                    )
                ''')
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS user_settings (
                        user_id BIGINT PRIMARY KEY,
                        display_name TEXT,
                        default_limit INTEGER
                    )
                ''')
            conn.commit()
    
    def create_event(self, title: str, description: str, creator_id: int, event_date: str, event_limit: Optional[int], chat_id: int) -> int:
        logger.info(f"[create_event] title={title!r}, description={description!r}, creator_id={creator_id}, event_date={event_date}, event_limit={event_limit}, chat_id={chat_id}")
        try:
            with self.get_conn() as conn:
                cursor = conn.execute(
                    'INSERT INTO events (title, description, creator_id, event_date, event_limit, chat_id) VALUES (?, ?, ?, ?, ?, ?)',
                    (title, description, creator_id, event_date, event_limit, chat_id)
                )
                event_id = cursor.lastrowid
                logger.info(f"[create_event] Inserted event_id={event_id}")
                conn.commit()
                logger.info(f"[create_event] Commit successful for event_id={event_id}")
                return event_id
        except Exception as e:
            logger.error(f"[create_event] Ошибка при создании мероприятия: {e}", exc_info=True)
            raise
    
    def get_active_events(self, chat_id: int) -> List[Tuple]:
        """Получение всех активных мероприятий"""
        with self.get_conn() as conn:
            return conn.execute(
                "SELECT id, title, description, creator_id, event_date, event_limit, created_at FROM events WHERE is_active = 1 AND chat_id = ?",
                (chat_id,)
            ).fetchall()
    
    def get_event(self, event_id: int, chat_id: int) -> Optional[Tuple]:
        """Получение мероприятия по ID"""
        with self.get_conn() as conn:
            return conn.execute(
                "SELECT id, title, description, creator_id, event_date, event_limit, created_at FROM events WHERE id = ? AND chat_id = ? AND is_active = 1",
                (event_id, chat_id)
            ).fetchone()
    
    def vote_for_event(self, event_id: int, user_id: int, username: str, vote: int) -> bool:
        """Голосование за мероприятие (0=нет, 1=да, 2=думаю), сохраняет plus_count"""
        try:
            with self.get_conn() as conn:
                row = conn.execute(
                    "SELECT plus_count FROM votes WHERE event_id = ? AND user_id = ?",
                    (event_id, user_id)
                ).fetchone()
                plus_count = row[0] if row else 0
                conn.execute(
                    "INSERT OR REPLACE INTO votes (event_id, user_id, username, vote, plus_count) VALUES (?, ?, ?, ?, ?)",
                    (event_id, user_id, username, vote, plus_count)
                )
                return True
        except Exception:
            return False
    
    def get_vote_stats(self, event_id: int) -> tuple[int, int, int]:
        """Получение статистики голосов (да, нет, думаю)"""
        with self.get_conn() as conn:
            yes_votes = conn.execute(
                "SELECT COUNT(*) FROM votes WHERE event_id = ? AND vote = 1",
                (event_id,)
            ).fetchone()[0]
            no_votes = conn.execute(
                "SELECT COUNT(*) FROM votes WHERE event_id = ? AND vote = 0",
                (event_id,)
            ).fetchone()[0]
            maybe_votes = conn.execute(
                "SELECT COUNT(*) FROM votes WHERE event_id = ? AND vote = 2",
                (event_id,)
            ).fetchone()[0]
            return yes_votes, no_votes, maybe_votes
    
    def set_plus(self, event_id: int, user_id: int, delta: int) -> int:
        """Увеличить/уменьшить plus_count для пользователя (максимум 5, минимум 0). Возвращает новое значение."""
        with self.get_conn() as conn:
            row = conn.execute("SELECT plus_count FROM votes WHERE event_id = ? AND user_id = ?", (event_id, user_id)).fetchone()
            if not row:
                return 0
            current = row[0] or 0
            new_val = max(0, min(5, current + delta))
            conn.execute("UPDATE votes SET plus_count = ? WHERE event_id = ? AND user_id = ?", (new_val, event_id, user_id))
            return new_val
    def reset_all_plus(self, event_id: int):
        with self.get_conn() as conn:
            conn.execute("UPDATE votes SET plus_count = 0 WHERE event_id = ?", (event_id,))
    def get_voters_list(self, event_id: int, vote: int) -> list[str]:
        """Получение списка проголосовавших с учётом plus_count"""
        with self.get_conn() as conn:
            voters = conn.execute(
                "SELECT username, plus_count FROM votes WHERE event_id = ? AND vote = ? ORDER BY voted_at",
                (event_id, vote)
            ).fetchall()
            result = []
            for username, plus in voters:
                if username:
                    if plus and plus > 0:
                        result.append(f"{username} (+{plus})")
                    else:
                        result.append(username)
            return result
    
    def delete_event(self, event_id: int, creator_id: int, chat_id: int) -> bool:
        """Удаление мероприятия (только создателем)"""
        try:
            with self.get_conn() as conn:
                result = conn.execute(
                    "UPDATE events SET is_active = 0 WHERE id = ? AND creator_id = ? AND chat_id = ?",
                    (event_id, creator_id, chat_id)
                )
                return result.rowcount > 0
        except Exception:
            return False 

    def deactivate_past_events(self, today: str):
        """Деактивирует мероприятия, дата которых раньше today"""
        with self.get_conn() as conn:
            conn.execute(
                "UPDATE events SET is_active = 0 WHERE event_date < ? AND is_active = 1",
                (today,)
            ) 

    def add_subscriber(self, user_id: int, username: str, first_name: str, last_name: str):
        with self.get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO subscribers (user_id, username, first_name, last_name) VALUES (?, ?, ?, ?)",
                (user_id, username, first_name, last_name)
            )
    def remove_subscriber(self, user_id: int):
        with self.get_conn() as conn:
            conn.execute("DELETE FROM subscribers WHERE user_id = ?", (user_id,))
    def get_all_subscribers(self) -> list:
        with self.get_conn() as conn:
            return [row[0] for row in conn.execute("SELECT user_id FROM subscribers").fetchall()] 

    def set_display_name(self, user_id: int, display_name: str):
        with self.get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO user_settings (user_id, display_name) VALUES (?, ?)",
                (user_id, display_name)
            )
    def get_display_name(self, user_id: int, fallback: str) -> str:
        with self.get_conn() as conn:
            row = conn.execute("SELECT display_name FROM user_settings WHERE user_id = ?", (user_id,)).fetchone()
            return row[0] if row and row[0] else fallback 

    def set_default_limit(self, user_id: int, limit: int):
        with self.get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO user_settings (user_id, default_limit) VALUES (?, ?)",
                (user_id, limit)
            )
    def get_default_limit(self, user_id: int) -> int:
        with self.get_conn() as conn:
            row = conn.execute("SELECT default_limit FROM user_settings WHERE user_id = ?", (user_id,)).fetchone()
            return row[0] if row and row[0] else 10
    def set_event_limit(self, event_id: int, limit: int):
        with self.get_conn() as conn:
            conn.execute('UPDATE events SET event_limit = ? WHERE id = ?', (limit, event_id))
    def get_event_limit(self, event_id: int, creator_id: int) -> int:
        with self.get_conn() as conn:
            row = conn.execute('SELECT event_limit FROM events WHERE id = ?', (event_id,)).fetchone()
            if row and row[0]:
                return row[0]
            # если лимит не задан, берём из user_settings
            return self.get_default_limit(creator_id)
    def get_main_and_reserve(self, event_id: int, limit: int) -> tuple[list, list]:
        with self.get_conn() as conn:
            voters = conn.execute(
                "SELECT user_id, username, plus_count, voted_at FROM votes WHERE event_id = ? AND vote = 1 ORDER BY voted_at",
                (event_id,)
            ).fetchall()
            main, reserve = [], []
            count = 0
            for user_id, username, plus, voted_at in voters:
                display = self.get_display_name(user_id, username)
                n = (plus or 0) + 1
                for i in range(n):
                    if count < limit:
                        main.append(display if i == 0 else f"{display} (+{i})")
                        count += 1
                    else:
                        reserve.append(display if i == 0 else f"{display} (+{i})")
            return main, reserve 

    def set_event_description(self, event_id: int, description: str):
        with self.get_conn() as conn:
            conn.execute('UPDATE events SET description = ? WHERE id = ?', (description, event_id))
            conn.commit() 

    def get_voters_with_ids(self, event_id: int, vote: int) -> list[tuple[int, str, int]]:
        """Получение списка (user_id, username, plus_count) для заданного голоса"""
        with self.get_conn() as conn:
            return conn.execute(
                "SELECT user_id, username, plus_count FROM votes WHERE event_id = ? AND vote = ? ORDER BY voted_at",
                (event_id, vote)
            ).fetchall() 

    def get_yes_votes_with_plus(self, event_id: int) -> int:
        """Считает общее количество "иду" с учётом плюсов."""
        with self.get_conn() as conn:
            cur = conn.cursor()
            if self.db_type == 'sqlite':
                cur.execute(
                    "SELECT SUM(plus_count + 1) FROM votes WHERE event_id = ? AND vote = 1",
                    (event_id,)
                )
            else:
                cur.execute(
                    "SELECT SUM(plus_count + 1) FROM votes WHERE event_id = %s AND vote = 1",
                    (event_id,)
                )
            result = cur.fetchone()[0]
            return int(result) if result is not None else 0 

    def run_sqlite_migration(self):
        """
        Выполняет SQL-миграцию для добавления chat_id в таблицу events и заполнения его значением 0 для всех существующих записей.
        """
        with self.get_conn() as conn:
            cursor = conn.execute("PRAGMA table_info(events)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'chat_id' not in columns:
                conn.execute("ALTER TABLE events ADD COLUMN chat_id BIGINT")
                conn.execute("UPDATE events SET chat_id = 0 WHERE chat_id IS NULL")
                conn.commit()

    def migrate_add_chat_id(self, default_chat_id: int = 0):
        """
        Добавляет поле chat_id в таблицу events, если оно отсутствует, и заполняет его для существующих записей.
        """
        if self.db_type == 'sqlite':
            self.run_sqlite_migration()
        else:
            with self.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='events'")
                    columns = [row[0] for row in cur.fetchall()]
                    if 'chat_id' not in columns:
                        cur.execute("ALTER TABLE events ADD COLUMN chat_id BIGINT")
                        cur.execute("UPDATE events SET chat_id = %s WHERE chat_id IS NULL", (default_chat_id,))
                        conn.commit() 

    def get_events_for_group(self, group_id: int, user_id: int):
        with self.get_conn() as conn:
            return conn.execute(
                'SELECT id, title, description, creator_id, event_date, event_limit, created_at FROM events WHERE is_active = 1 AND chat_id = ?',
                (group_id,)
            ).fetchall()

    def get_events_for_user(self, user_id: int):
        with self.get_conn() as conn:
            return conn.execute(
                'SELECT id, title, description, creator_id, event_date, event_limit, created_at FROM events WHERE is_active = 1 AND (creator_id = ? OR chat_id = ?)',
                (user_id, user_id)
            ).fetchall() 