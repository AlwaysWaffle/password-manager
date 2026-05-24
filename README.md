# Password Manager Telegram Bot

Менеджер паролей с Telegram-ботом.

## Запуск

```bash
cd password_manager
pip install -r requirements.txt
# укажите BOT_TOKEN в config.py
python main.py
```

## Структура

- `main.py` — запуск бота
- `config.py` — токен, путь к БД
- `database.py` — SQLite
- `encryption.py` — хеш мастер-пароля и Fernet
- `core.py` — регистрация, вход, CRUD паролей
- `bot_handlers.py` — обработчики telebot
- `keyboards.py` — клавиатуры
- `logger.py` — логи в консоль

## Шифрование

Мастер-пароль не хранится в открытом виде — только sha256(пароль + соль).
Ключ Fernet каждый раз получается из мастер-пароля при входе и держится в памяти сессии.
