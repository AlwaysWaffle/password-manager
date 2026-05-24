# Точка входа: проверка config → база → бот → polling
#
# Библиотеки:
#   sys, pathlib.Path  — выход при ошибке, путь к файлу БД
#   telebot            — pyTelegramBotAPI, обёртка над Telegram Bot API

import sys
from pathlib import Path

import telebot

import config
import database
import logger
from bot_handlers import register_handlers


def validate_config():
    """Проверяем токен и что можем создать/открыть файл базы."""
    if not config.BOT_TOKEN or "REPLACE_" in config.BOT_TOKEN or len(config.BOT_TOKEN) < 20:
        print("Ошибка: укажите BOT_TOKEN в config.py")
        sys.exit(1)

    db_path = Path(config.DB_PATH)
    try:
        if not db_path.exists():
            if db_path.parent and not db_path.parent.exists():
                db_path.parent.mkdir(parents=True, exist_ok=True)
            open(db_path, "a").close()  # пустой файл — sqlite допишет структуру
    except Exception as e:
        print(f"Нет доступа к базе: {e}")
        sys.exit(1)


def main():
    validate_config()
    logger.log_info("Конфиг проверен")

    database.init_db(config.DB_PATH)
    logger.log_info("База данных готова")

    bot = telebot.TeleBot(config.BOT_TOKEN)
    
    try:
        bot.remove_webhook()  # иначе polling может не получать сообщения
        bot.get_me()  # проверка токена — запрос getMe к API
        logger.log_info("telegram api ок")
    except Exception as e:
        logger.log_error(f"telegram api: {e}")

    register_handlers(bot)  # вешаем @bot.message_handler и callback
    logger.log_info("бот запущен, polling...")

    try:
        # none_stop=True — после ошибки снова опрашивает сервер
        bot.polling(none_stop=True)
    except KeyboardInterrupt:
        logger.log_info("остановка ctrl-c")
    except Exception as e:
        logger.log_error(f"polling: {e}")


if __name__ == "__main__":
    main()
