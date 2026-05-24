# Обработчики Telegram-бота — что отвечать на сообщения и нажатия кнопок
#
# Библиотека pyTelegramBotAPI (telebot):
#   @bot.message_handler(commands=["start"])  — команда /start
#   @bot.message_handler(func=lambda m: True) — любой текст
#   @bot.callback_query_handler              — inline-кнопки (call.data)
#   bot.send_message, bot.answer_callback_query
#   types.Message, types.CallbackQuery, ReplyKeyboardRemove
#
# Состояние диалога храним в памяти (словари), не в БД — после перезапуска бота нужен /start

import telebot
from telebot import types

import core
from core import InvalidMasterPasswordError, UserLockedError
import logger
import keyboards

# В каком шаге диалога сейчас пользователь (строковые константы)
AWAIT_MASTER_CREATE = "AWAIT_MASTER_CREATE"
AWAIT_MASTER_CONFIRM = "AWAIT_MASTER_CONFIRM"
AWAIT_MASTER_LOGIN = "AWAIT_MASTER_LOGIN"
LOGGED_IN = "LOGGED_IN"
AWAIT_SERVICE = "AWAIT_SERVICE"
AWAIT_LOGIN = "AWAIT_LOGIN"
AWAIT_PASSWORD = "AWAIT_PASSWORD"

# user_states[user_id] = {"state": ..., "temp": {...}, "prev_state": ...}
user_states = {}
# Ключ Fernet после входа — только в RAM, пока бот работает
user_keys = {}
# Первый ввод мастер-пароля, пока ждём повтор для подтверждения
temp_passwords = {}

HELP_TEXT = (
    "Бот-менеджер паролей. Доступные кнопки:\n"
    "➕ Добавить пароль — вручную добавить сервис/логин/пароль\n"
    "📋 Мои сервисы — список сохранённых сервисов (панели для просмотра/действий)\n"
    "🎲 Сгенерировать пароль — быстро сгенерировать и сохранить\n"
    "🗑 Удалить пароль — удалить сервис\n"
)

MAIN_BUTTONS = {
    "➕ Добавить пароль",
    "📋 Мои сервисы",
    "🎲 Сгенерировать пароль",
    "🗑 Удалить пароль",
    "❓ Помощь",
}


def get_user_state(user_id: int) -> dict:
    """Создаём запись состояния, если пользователь пишет впервые."""
    if user_id not in user_states:
        user_states[user_id] = {"state": None, "temp": {}, "prev_state": None}
    return user_states[user_id]


def callback_to_int(data: str, prefix: str) -> int | None:
    """Из callback 'view:5' или 'gen_len:12' достаём число после двоеточия."""
    if not data.startswith(prefix):
        return None
    parts = data.split(":", 1)
    if len(parts) != 2:
        return None
    try:
        return int(parts[1])
    except (TypeError, ValueError):
        return None


def show_main_menu(bot: telebot.TeleBot, chat_id: int, text: str = "Главное меню.") -> None:
    bot.send_message(chat_id, text, reply_markup=keyboards.get_main_menu())


def send_add_back_hint(bot: telebot.TeleBot, chat_id: int, text: str) -> None:
    bot.send_message(chat_id, text, reply_markup=keyboards.get_back_step_keyboard())


def send_password_method_menu(bot: telebot.TeleBot, chat_id: int) -> None:
    bot.send_message(chat_id, "Выберите способ:", reply_markup=keyboards.get_password_method_keyboard())


def send_services_for_view(bot: telebot.TeleBot, user_id: int) -> None:
    services = core.get_services(user_id)
    if not services:
        bot.send_message(user_id, "Список сервисов пуст.")
        return
    bot.send_message(
        user_id,
        "Выберите сервис:",
        reply_markup=keyboards.get_services_list(services, "view"),
    )


def send_services_for_delete(bot: telebot.TeleBot, user_id: int) -> None:
    services = core.get_services(user_id)
    if not services:
        bot.send_message(user_id, "Список сервисов пуст.")
        return
    bot.send_message(
        user_id,
        "Выберите сервис для удаления:",
        reply_markup=keyboards.get_services_list(services, "del"),
    )


def register_handlers(bot: telebot.TeleBot) -> None:
    """Регистрируем все хендлеры на переданном экземпляре бота."""

    @bot.message_handler(commands=["start"])
    def handle_start(message: types.Message):
        user_id = message.from_user.id  # Telegram id — ключ в БД
        chat_id = message.chat.id       # куда слать ответ (личка = обычно тот же id)
        state = get_user_state(user_id)

        try:
            user = core.get_user(user_id)
            if not user:
                # Новый юзер — просим придумать мастер-пароль
                state["state"] = AWAIT_MASTER_CREATE
                state["temp"] = {}
                state["prev_state"] = None
                logger.log_info(f"новый пользователь {user_id}")
                bot.send_message(chat_id, "Придумайте мастер-пароль (8-32 символа):")
                bot.send_message(chat_id, "Важно! Пароль нужно запомнить. Восстановить нельзя.")
                return

            # Уже регистрировался — просим ввести пароль
            state["state"] = AWAIT_MASTER_LOGIN
            state["temp"] = {}
            state["prev_state"] = None
            logger.log_info(f"вход {user_id}")
            bot.send_message(chat_id, "Пожалуйста, введите мастер-пароль для входа:")
        except Exception as exc:
            logger.log_error(f"/start user {user_id}: {exc}")
            bot.send_message(chat_id, "Ошибка при запуске. Повторите /start.")

    @bot.message_handler(func=lambda m: True)
    def handle_text(message: types.Message):
        """Все текстовые сообщения (не команды) — ветвимся по state."""
        user_id = message.from_user.id
        chat_id = message.chat.id
        text = (message.text or "").strip()
        state = get_user_state(user_id)
        current = state.get("state")

        if current is None:
            bot.send_message(chat_id, "Отправьте /start для начала.")
            return

        sensitive = current in {
            AWAIT_MASTER_CREATE,
            AWAIT_MASTER_CONFIRM,
            AWAIT_MASTER_LOGIN,
            AWAIT_PASSWORD,
        }
        if sensitive:
            logger.log_debug(f"сообщение от {user_id}: ***")
        else:
            logger.log_debug(f"сообщение от {user_id}: {text[:50]}")

        try:
            # Регистрация мастер пароля (1-й ввод)
            if current == AWAIT_MASTER_CREATE:
                if len(text) < 8 or len(text) > 32:
                    bot.send_message(chat_id, "Пароль должен быть 8-32 символа. Попробуйте ещё раз:")
                    return
                temp_passwords[user_id] = text
                state["state"] = AWAIT_MASTER_CONFIRM
                bot.send_message(chat_id, "Повторите мастер-пароль для подтверждения:")
                return

            if current == AWAIT_MASTER_CONFIRM:
                initial = temp_passwords.get(user_id)
                if not initial:
                    state["state"] = AWAIT_MASTER_CREATE
                    bot.send_message(chat_id, "Ошибка. Начните заново: введите мастер-пароль:")
                    return
                if text != initial:
                    state["state"] = AWAIT_MASTER_CREATE
                    temp_passwords.pop(user_id, None)
                    bot.send_message(chat_id, "Пароли не совпали. Введите мастер-пароль заново:")
                    return

                try:
                    key = core.register_user(user_id, text)  # хеш в SQLite, key в память
                    user_keys[user_id] = key
                    temp_passwords.pop(user_id, None)
                    state["state"] = LOGGED_IN
                    state["temp"] = {}
                    logger.log_info(f"регистрация {user_id}")
                    bot.send_message(
                        chat_id,
                        "Мастер-пароль создан. Доступ разрешён.",
                        reply_markup=keyboards.get_main_menu(),
                    )
                except ValueError:
                    bot.send_message(chat_id, "Пользователь уже существует. /start")
                except Exception as exc:
                    logger.log_error(f"регистрация {user_id}: {exc}")
                    bot.send_message(chat_id, "Ошибка при создании пользователя.")
                return

            # Вход (2-й ввод)
            if current == AWAIT_MASTER_LOGIN:
                try:
                    key = core.login_user(user_id, text)
                    user_keys[user_id] = key
                    state["state"] = LOGGED_IN
                    logger.log_info(f"вход ok {user_id}")
                    bot.send_message(chat_id, "Вход успешен.", reply_markup=keyboards.get_main_menu())
                except UserLockedError as exc:
                    bot.send_message(chat_id, f"Ваш аккаунт заблокирован до {exc.locked_until.strftime('%H:%M:%S')}")
                except InvalidMasterPasswordError as exc:
                    bot.send_message(chat_id, str(exc))
                except ValueError:
                    bot.send_message(chat_id, "Пользователь не найден. Отправьте /start.")
                except Exception as exc:
                    logger.log_error(f"вход {user_id}: {exc}")
                    bot.send_message(chat_id, "Ошибка входа.")
                return

            # Главное меню
            if current == LOGGED_IN:
                if text == "❓ Помощь":
                    bot.send_message(chat_id, HELP_TEXT)
                    return
                if text == "📋 Мои сервисы":
                    send_services_for_view(bot, user_id)
                    return
                if text == "➕ Добавить пароль":
                    state["prev_state"] = LOGGED_IN  # для кнопки "Назад"
                    state["state"] = AWAIT_SERVICE
                    state["temp"] = {}  # сюда пойдут service, login, generated_password
                    # Убираем Reply-клавиатуру, дальше только текст + inline
                    bot.send_message(chat_id, "Введите название сервиса:", reply_markup=types.ReplyKeyboardRemove())
                    send_add_back_hint(bot, chat_id, "Чтобы вернуться в главное меню, нажмите кнопку ниже.")
                    return
                if text == "🎲 Сгенерировать пароль":
                    bot.send_message(chat_id, "Выберите длину пароля:", reply_markup=keyboards.get_gen_length_keyboard())
                    return
                if text == "🗑 Удалить пароль":
                    send_services_for_delete(bot, user_id)
                    return
                bot.send_message(chat_id, "Неизвестная команда. Используйте главное меню.")
                return

            # Добавление пароля (шаг 1)
            if current == AWAIT_SERVICE:
                if text in MAIN_BUTTONS:
                    bot.send_message(chat_id, "Сейчас нужно ввести название сервиса или нажать Назад.")
                    return
                if core.service_exists(user_id, text):
                    bot.send_message(chat_id, f"Сервис '{text}' уже существует. Введите другое имя.")
                    return
                state["temp"]["service"] = text
                state["prev_state"] = AWAIT_SERVICE
                state["state"] = AWAIT_LOGIN
                send_add_back_hint(bot, chat_id, "Введите логин для сервиса:")
                return

            if current == AWAIT_LOGIN:
                if text in MAIN_BUTTONS:
                    bot.send_message(chat_id, "Сейчас нужно ввести логин или нажать Назад.")
                    return
                state["temp"]["login"] = text

                # Пароль уже сгенерили заранее - сохраняем сразу
                gen_pwd = state["temp"].pop("generated_password", None)
                if gen_pwd:
                    key = user_keys.get(user_id)
                    if not key:
                        state["state"] = AWAIT_MASTER_LOGIN
                        bot.send_message(chat_id, "Сессия устарела. Войдите снова.")
                        return
                    try:
                        core.save_password(user_id, state["temp"]["service"], text, gen_pwd, key)
                        state["state"] = LOGGED_IN
                        state["temp"] = {}
                        bot.send_message(chat_id, "Сгенерированный пароль сохранён.", reply_markup=keyboards.get_main_menu())
                        logger.log_info(f"сохранён пароль {user_id}")
                    except core.ServiceAlreadyExistsError as exc:
                        bot.send_message(chat_id, str(exc))
                    except Exception as exc:
                        logger.log_error(f"сохранение {user_id}: {exc}")
                        bot.send_message(chat_id, "Ошибка при сохранении.")
                    return

                state["prev_state"] = AWAIT_LOGIN
                state["state"] = AWAIT_PASSWORD
                send_password_method_menu(bot, chat_id)
                return

            if current == AWAIT_PASSWORD:
                key = user_keys.get(user_id)
                if not key:
                    state["state"] = AWAIT_MASTER_LOGIN
                    bot.send_message(chat_id, "Сессия устарела. Войдите снова.")
                    return
                service_name = state["temp"].get("service")
                login = state["temp"].get("login")
                if not service_name or not login:
                    state["state"] = LOGGED_IN
                    state["temp"] = {}
                    bot.send_message(chat_id, "Ошибка сессии. Начните добавление заново.")
                    return
                try:
                    core.save_password(user_id, service_name, login, text, key)
                    state["state"] = LOGGED_IN
                    state["temp"] = {}
                    bot.send_message(chat_id, "Пароль сохранён.", reply_markup=keyboards.get_main_menu())
                    logger.log_info(f"сохранён {service_name} для {user_id}")
                except core.ServiceAlreadyExistsError as exc:
                    bot.send_message(chat_id, str(exc))
                except Exception as exc:
                    logger.log_error(f"сохранение {user_id}: {exc}")
                    bot.send_message(chat_id, "Ошибка при сохранении.")
                return

        except Exception as exc:
            logger.log_error(f"handle_text {user_id}: {exc}")
            bot.send_message(chat_id, "Произошла ошибка. Попробуйте снова.")

    @bot.callback_query_handler(func=lambda call: True)
    def handle_callback(call: types.CallbackQuery):
        """Нажатия inline-кнопок: call.data = строка из callback_data."""
        user_id = call.from_user.id
        data = call.data or ""
        state = get_user_state(user_id)

        try:
            if data.startswith("gen_len:"):
                length = callback_to_int(data, "gen_len:")
                if length is None:
                    bot.answer_callback_query(call.id, "Неверный формат")
                    return

                password = core.generate_password(length=length)
                current = state.get("state")

                if current == AWAIT_PASSWORD:
                    key = user_keys.get(user_id)
                    if not key:
                        state["state"] = AWAIT_MASTER_LOGIN
                        bot.send_message(user_id, "Сессия устарела. Войдите снова.")
                        bot.answer_callback_query(call.id)
                        return
                    service_name = state["temp"].get("service")
                    login = state["temp"].get("login")
                    if not service_name or not login:
                        state["state"] = LOGGED_IN
                        state["temp"] = {}
                        bot.send_message(user_id, "Ошибка сессии. Начните заново.")
                        bot.answer_callback_query(call.id)
                        return
                    bot.send_message(user_id, f"Сгенерированный пароль:\n{password}")
                    try:
                        core.save_password(user_id, service_name, login, password, key)
                        state["state"] = LOGGED_IN
                        state["temp"] = {}
                        bot.send_message(user_id, "Сгенерированный пароль сохранён.", reply_markup=keyboards.get_main_menu())
                    except core.ServiceAlreadyExistsError as exc:
                        bot.send_message(user_id, str(exc))
                    except Exception as exc:
                        logger.log_error(f"сохранение gen {user_id}: {exc}")
                        bot.send_message(user_id, "Ошибка при сохранении.")
                    bot.answer_callback_query(call.id)
                    return

                state["temp"]["generated_password"] = password
                bot.send_message(
                    user_id,
                    f"Сгенерированный пароль:\n{password}",
                    reply_markup=keyboards.get_save_generated_keyboard(),
                )
                bot.answer_callback_query(call.id)
                return

            if data == "save_generated":
                state["prev_state"] = LOGGED_IN
                state["state"] = AWAIT_SERVICE
                bot.send_message(
                    user_id,
                    "Введите название сервиса для сохранения сгенерированного пароля:",
                    reply_markup=types.ReplyKeyboardRemove(),
                )
                send_add_back_hint(bot, user_id, "Чтобы вернуться в главное меню, нажмите кнопку ниже.")
                bot.answer_callback_query(call.id)
                return

            if data == "back_step":
                # Шаг назад в мастере "добавить пароль"
                prev = state.get("prev_state")
                if not prev:
                    state["state"] = LOGGED_IN
                    state["temp"] = {}
                    show_main_menu(bot, user_id, "Возврат в главное меню.")
                    bot.answer_callback_query(call.id)
                    return
                state["state"] = prev
                state["prev_state"] = None
                if prev == AWAIT_SERVICE:
                    bot.send_message(user_id, "Введите название сервиса:")
                    send_add_back_hint(bot, user_id, "Чтобы вернуться в главное меню, нажмите кнопку ниже.")
                elif prev == AWAIT_LOGIN:
                    send_add_back_hint(bot, user_id, "Введите логин для сервиса:")
                elif prev == AWAIT_PASSWORD:
                    send_password_method_menu(bot, user_id)
                bot.answer_callback_query(call.id)
                return

            if data == "pw_manual":
                state["prev_state"] = AWAIT_LOGIN
                state["state"] = AWAIT_PASSWORD
                send_add_back_hint(bot, user_id, "Введите пароль для сохранения:")
                bot.answer_callback_query(call.id)
                return

            if data == "pw_gen":
                bot.send_message(
                    user_id,
                    "Выберите длину пароля:",
                    reply_markup=keyboards.get_gen_length_keyboard(with_back=True),
                )
                bot.answer_callback_query(call.id)
                return

            if data.startswith("view:"):
                entry_id = callback_to_int(data, "view:")
                if entry_id is None:
                    bot.send_message(user_id, "Некорректный запрос.")
                    return
                key = user_keys.get(user_id)
                if not key:
                    state["state"] = AWAIT_MASTER_LOGIN
                    bot.send_message(user_id, "Сессия устарела. Войдите снова.")
                    return
                try:
                    item = core.get_password_by_id(user_id, entry_id, key)
                    bot.send_message(
                        user_id,
                        f"Сервис: {item['service']}\nЛогин: {item['login']}\nПароль: {item['password']}",
                        reply_markup=keyboards.get_back_to_list_keyboard(),
                    )
                    logger.log_info(f"просмотр {item['service']} user {user_id}")
                except core.ServiceNotFoundError:
                    bot.send_message(user_id, "Сервис не найден.")
                bot.answer_callback_query(call.id)
                return

            if data == "back_to_list":
                send_services_for_view(bot, user_id)
                bot.answer_callback_query(call.id)
                return

            if data == "back_to_menu":
                state["state"] = LOGGED_IN
                state["prev_state"] = None
                state["temp"] = {}
                show_main_menu(bot, user_id, "Возврат в главное меню.")
                bot.answer_callback_query(call.id)
                return

            if data.startswith("del:"):
                entry_id = callback_to_int(data, "del:")
                if entry_id is None:
                    bot.answer_callback_query(call.id, "Неверный запрос")
                    return
                try:
                    entry = core.get_entry_meta(user_id, entry_id)
                except core.ServiceNotFoundError:
                    bot.send_message(user_id, "Запись не найдена.")
                    bot.answer_callback_query(call.id)
                    return
                bot.send_message(
                    user_id,
                    f"Подтвердите удаление {entry['service']}:",
                    reply_markup=keyboards.get_confirm_delete_keyboard(entry_id),
                )
                bot.answer_callback_query(call.id)
                return

            if data == "back_del_list":
                send_services_for_delete(bot, user_id)
                bot.answer_callback_query(call.id)
                return

            if data.startswith("del_confirm:"):
                parts = data.split(":")
                if len(parts) != 3:
                    bot.answer_callback_query(call.id, "Неверный формат")
                    return
                try:
                    entry_id = int(parts[1])
                except (TypeError, ValueError):
                    bot.answer_callback_query(call.id, "Неверный id")
                    return
                if parts[2] == "yes":
                    try:
                        core.delete_password(user_id, entry_id)
                        bot.send_message(user_id, "Запись удалена.")
                        logger.log_info(f"удаление id={entry_id} user {user_id}")
                    except core.ServiceNotFoundError:
                        bot.send_message(user_id, "Сервис не найден.")
                else:
                    send_services_for_delete(bot, user_id)
                state["state"] = LOGGED_IN
                bot.answer_callback_query(call.id)
                return

            bot.answer_callback_query(call.id, "Неизвестное действие")

        except Exception as exc:
            logger.log_error(f"callback {user_id}: {exc}")
            bot.send_message(user_id, "Произошла ошибка при обработке действия.")
