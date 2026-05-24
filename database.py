# Работа с SQLite — файл passwords.db, две таблицы: users и passwords
#
# Библиотеки:
#   sqlite3           — встроенная БД в одном файле
#   contextmanager    — декоратор @contextmanager для «открыл — сделал — закрыл»

import sqlite3
from contextlib import contextmanager

# Путь к файлу БД задаётся один раз в init_db()
_db_path = None


def init_db(db_path: str) -> None:
    """Вызываем из main.py при старте: запоминаем путь и создаём таблицы."""
    global _db_path
    _db_path = db_path
    _create_tables()


@contextmanager
def _connect():
    """
    Подключение к SQLite на одну операцию.
    yield conn — внутри with работаем с conn, в finally соединение закрывается.
    """
    conn = sqlite3.connect(_db_path)
    conn.row_factory = sqlite3.Row  # строки как словарь: row["user_id"]
    conn.execute("PRAGMA foreign_keys = ON")  # нельзя удалить юзера, если есть его пароли
    try:
        yield conn
    finally:
        conn.close()


def _create_tables():
    """Создаём таблицы, если их ещё нет."""
    with _connect() as conn:
        cur = conn.cursor()

        # Миграция со старой версии бота (там был лишний столбец encrypted_fernet_key)
        cur.execute("PRAGMA table_info(users)")
        cols = {row[1] for row in cur.fetchall()}
        if "encrypted_fernet_key" in cols:
            cur.execute("DROP TABLE IF EXISTS passwords")
            cur.execute("DROP TABLE IF EXISTS users")

        # users — один Telegram-пользователь = одна строка
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                master_password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                locked_until TEXT,
                failed_attempts INTEGER DEFAULT 0
            )
            """
        )
        # passwords — записи паролей (поле password уже зашифровано Fernet)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS passwords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                service TEXT NOT NULL,
                login TEXT NOT NULL,
                password TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                UNIQUE(user_id, service)
            )
            """
        )
        conn.commit()  # сохраняем изменения на диск


def register_user(user_id: int, master_hash: str, salt: str) -> None:
    """Новый пользователь после регистрации мастер-пароля."""
    with _connect() as conn:
        # ? — плейсхолдеры, защита от SQL-инъекций
        conn.execute(
            "INSERT INTO users (user_id, master_password_hash, salt) VALUES (?, ?, ?)",
            (user_id, master_hash, salt),
        )
        conn.commit()


def get_user(user_id: int) -> dict | None:
    """Прочитать пользователя по Telegram user_id."""
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            return None
        return {
            "user_id": row["user_id"],
            "master_password_hash": row["master_password_hash"],
            "salt": row["salt"],
            "created_at": row["created_at"],
            "locked_until": row["locked_until"],
            "failed_attempts": int(row["failed_attempts"] or 0),
        }


def user_exists(user_id: int) -> bool:
    return get_user(user_id) is not None


def update_failed_attempts(user_id: int, count: int) -> None:
    """Счётчик неверных попыток входа."""
    with _connect() as conn:
        conn.execute("UPDATE users SET failed_attempts = ? WHERE user_id = ?", (count, user_id))
        conn.commit()


def lock_user(user_id: int, until_time: str | None) -> None:
    """until_time — ISO-строка до которой блок, или None чтобы снять блок."""
    with _connect() as conn:
        conn.execute("UPDATE users SET locked_until = ? WHERE user_id = ?", (until_time, user_id))
        conn.commit()


def add_password(user_id: int, service: str, login: str, encrypted_password: str) -> int:
    """Добавить запись. encrypted_password уже строка от Fernet."""
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO passwords (user_id, service, login, password) VALUES (?, ?, ?, ?)",
            (user_id, service, login, encrypted_password),
        )
        conn.commit()
        return cur.lastrowid  # id новой строки


def get_password(user_id: int, service: str) -> dict | None:
    """Найти запись по имени сервиса (vk, gmail...)."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, user_id, service, login, password, created_at "
            "FROM passwords WHERE user_id = ? AND service = ?",
            (user_id, service),
        ).fetchone()
        if not row:
            return None
        return dict(row)


def get_entry_by_id(user_id: int, entry_id: int) -> dict | None:
    """Запись по числовому id (кнопки inline передают этот id)."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, user_id, service, login, password, created_at "
            "FROM passwords WHERE user_id = ? AND id = ?",
            (user_id, entry_id),
        ).fetchone()
        if not row:
            return None
        return dict(row)


def get_all_services(user_id: int) -> list[tuple[int, str]]:
    """Список (id, название) для клавиатуры «Мои сервисы»."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, service FROM passwords WHERE user_id = ? ORDER BY service COLLATE NOCASE",
            (user_id,),
        ).fetchall()
        return [(int(r[0]), r[1]) for r in rows]


def delete_entry(user_id: int, entry_id: int) -> bool:
    """True если строка реально удалилась."""
    with _connect() as conn:
        cur = conn.execute("DELETE FROM passwords WHERE user_id = ? AND id = ?", (user_id, entry_id))
        conn.commit()
        return cur.rowcount > 0
