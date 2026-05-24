# Клавиатуры Telegram — Reply (внизу чата) и Inline (кнопки под сообщением)
#
# Библиотека: pyTelegramBotAPI → telebot.types

from telebot import types


def get_main_menu() -> types.ReplyKeyboardMarkup:
    """Главное меню после входа."""
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)  # кнопки по ширине экрана
    kb.row("➕ Добавить пароль", "📋 Мои сервисы")
    kb.row("🎲 Сгенерировать пароль", "🗑 Удалить пароль")
    kb.row("❓ Помощь")
    return kb


def get_back_step_keyboard() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    # callback_data уходит в handle_callback как call.data
    kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_step"))
    return kb


def get_password_method_keyboard() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📝 Ввести вручную", callback_data="pw_manual"))
    kb.add(types.InlineKeyboardButton("🎲 Сгенерировать", callback_data="pw_gen"))
    kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_step"))
    return kb


def get_gen_length_keyboard(with_back: bool = False) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    for length in (8, 12, 16, 20):
        kb.add(types.InlineKeyboardButton(str(length), callback_data=f"gen_len:{length}"))
    if with_back:
        kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_step"))
    return kb


def get_services_list(services: list[tuple[int, str]], mode: str) -> types.InlineKeyboardMarkup:
    """mode: view — просмотр, del — удаление."""
    kb = types.InlineKeyboardMarkup()
    prefix = "view" if mode == "view" else "del"
    for entry_id, name in services:
        kb.add(types.InlineKeyboardButton(name, callback_data=f"{prefix}:{entry_id}"))
    kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu"))
    return kb


def get_confirm_delete_keyboard(entry_id: int) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✅ Да", callback_data=f"del_confirm:{entry_id}:yes"))
    kb.add(types.InlineKeyboardButton("❌ Нет", callback_data=f"del_confirm:{entry_id}:no"))
    kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_del_list"))
    return kb


def get_save_generated_keyboard() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Сохранить", callback_data="save_generated"))
    return kb


def get_back_to_list_keyboard() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_list"))
    return kb
