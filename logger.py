# Простые логи в консоль (стандартный print)
#
# Библиотеки:
#   datetime — время для строки лога

from datetime import datetime

import config


def _print(level: str, msg: str) -> None:
    ts = datetime.now().strftime(config.TIME_FORMAT)
    print(f"[{ts}] {level}: {msg}")


def log_info(msg: str) -> None:
    """Обычные события: старт, вход, сохранение."""
    _print("INFO", msg)


def log_error(msg: str) -> None:
    """Ошибки."""
    _print("ERROR", msg)


def log_debug(msg: str) -> None:
    """Отладка; для паролей в handlers пишем ***."""
    _print("DEBUG", msg)
