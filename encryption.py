# Шифрование: мастер-пароль в хеш, пароли сервисов через Fernet
#
# Библиотеки:
#   hashlib.sha256     — хеш мастер-пароля (в БД не храним сам пароль)
#   base64             — Fernet требует ключ в base64
#   secrets            — случайная соль
#   cryptography.fernet — симметричное шифрование паролей сервисов

from hashlib import sha256
import base64
import secrets

from cryptography.fernet import Fernet, InvalidToken


def hash_password(password: str, salt: str) -> str:
    """Хеш для проверки мастер-пароля при входе. В БД лежит только он + соль."""
    # Склеиваем пароль и соль, кодируем в байты, считаем sha256, отдаём hex-строку
    return sha256((password + salt).encode("utf-8")).hexdigest()


def make_key_from_password(password: str) -> bytes:
    """
    Ключ Fernet из мастер-пароля. Не сохраняем в БД —
    при каждом входе заново получаем из введённого пароля.
    """
    raw = sha256(password.encode("utf-8")).digest()  # 32 байта
    return base64.urlsafe_b64encode(raw)  # формат, который ждёт Fernet


def encrypt_data(plain_text: str, key: bytes) -> str:
    """Зашифровать пароль сервиса перед записью в SQLite."""
    f = Fernet(key)
    token = f.encrypt((plain_text or "").encode("utf-8"))
    return token.decode("utf-8")  # в БД храним как текст


def decrypt_data(encrypted_text: str, key: bytes) -> str | None:
    """Расшифровать. None — если ключ не подошёл или данные битые."""
    try:
        f = Fernet(key)
        data = f.decrypt(encrypted_text.encode("utf-8"))
        return data.decode("utf-8")
    except (InvalidToken, TypeError):
        return None


def generate_salt() -> str:
    """Случайная соль для нового пользователя (32 hex-символа)."""
    return secrets.token_hex(16)
