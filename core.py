# Бизнес-логика между ботом и базой
#
# Библиотеки:
#   string, secrets     - генератор случайного пароля
#   sqlite3             - ловим IntegrityError при дубликате сервиса
#   datetime, timedelta - блокировка после неверных попыток

import string
import secrets
import sqlite3
from datetime import datetime, timedelta

import config
import database
import encryption


class InvalidMasterPasswordError(Exception):
    """Неверный мастер-пароль при входе."""


class UserLockedError(Exception):
    """Слишком много попыток - аккаунт временно заблокирован."""

    def __init__(self, locked_until: datetime):
        self.locked_until = locked_until
        super().__init__(f"Аккаунт заблокирован до {locked_until.strftime('%H:%M:%S')}")


class ServiceAlreadyExistsError(Exception):
    pass


class ServiceNotFoundError(Exception):
    pass


def get_user(user_id: int):
    return database.get_user(user_id)


def register_user(user_id: int, master_password: str) -> bytes:
    """
    Регистрация: соль + хеш в БД, ключ Fernet возвращаем в память бота.
    """
    if database.user_exists(user_id):
        raise ValueError("Пользователь уже есть")

    salt = encryption.generate_salt()
    master_hash = encryption.hash_password(master_password, salt)
    database.register_user(user_id, master_hash, salt)
    return encryption.make_key_from_password(master_password)


def login_user(user_id: int, master_password: str) -> bytes:
    """
    Вход: сверяем хеш, сбрасываем счётчик попыток, отдаём ключ для расшифровки.
    """
    user = database.get_user(user_id)
    if not user:
        raise ValueError("Пользователь не найден")

    # Проверяем, не заблокирован ли
    locked_until = user.get("locked_until")
    if locked_until:
        try:
            until = datetime.fromisoformat(locked_until)
            if datetime.now() < until:
                raise UserLockedError(until)
        except ValueError:
            pass  # битая дата в БД — игнорируем

    attempt_hash = encryption.hash_password(master_password, user["salt"])
    if attempt_hash != user["master_password_hash"]:
        attempts = user.get("failed_attempts", 0) + 1
        database.update_failed_attempts(user_id, attempts)
        if attempts >= config.MAX_FAILED_ATTEMPTS:
            until = datetime.now() + timedelta(minutes=config.LOCKOUT_MINUTES)
            database.lock_user(user_id, until.isoformat())
            raise UserLockedError(until)
        raise InvalidMasterPasswordError(
            f"Неверный пароль. Попытка {attempts}/{config.MAX_FAILED_ATTEMPTS}."
        )

    database.update_failed_attempts(user_id, 0)
    database.lock_user(user_id, None)
    return encryption.make_key_from_password(master_password)


def get_services(user_id: int) -> list[tuple[int, str]]:
    return database.get_all_services(user_id)


def service_exists(user_id: int, service_name: str) -> bool:
    return database.get_password(user_id, service_name) is not None


def save_password(user_id: int, service_name: str, login: str, password: str, key: bytes) -> int:
    """Шифруем пароль сервиса и пишем в таблицу passwords."""
    if database.get_password(user_id, service_name):
        raise ServiceAlreadyExistsError(f"Сервис '{service_name}' уже существует")
    encrypted = encryption.encrypt_data(password, key)
    try:
        return database.add_password(user_id, service_name, login, encrypted)
    except sqlite3.IntegrityError as exc:
        # UNIQUE(user_id, service) — дубликат на уровне БД
        raise ServiceAlreadyExistsError(f"Сервис '{service_name}' уже существует") from exc


def get_password_by_id(user_id: int, entry_id: int, key: bytes) -> dict:
    entry = database.get_entry_by_id(user_id, entry_id)
    if not entry:
        raise ServiceNotFoundError("Сервис не найден")
    plain = encryption.decrypt_data(entry["password"], key)
    if plain is None:
        raise ServiceNotFoundError("Не удалось расшифровать пароль")
    return {"service": entry["service"], "login": entry["login"], "password": plain}


def delete_password(user_id: int, entry_id: int) -> None:
    if not database.delete_entry(user_id, entry_id):
        raise ServiceNotFoundError("Сервис не найден")


def get_entry_meta(user_id: int, entry_id: int) -> dict:
    """Только имя сервиса и логин — для экрана подтверждения удаления."""
    entry = database.get_entry_by_id(user_id, entry_id)
    if not entry:
        raise ServiceNotFoundError("Сервис не найден")
    return {"service": entry["service"], "login": entry["login"]}


def generate_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%&*?+-=_"
    return "".join(secrets.choice(alphabet) for _ in range(length))
