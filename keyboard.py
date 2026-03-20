from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import DEPARTMENTS, TAX_TYPES

# ----- ОСНОВНЫЕ КЛАВИАТУРЫ -----
def main_menu_keyboard():
    """Главное меню для активных пользователей"""
    buttons = [
        [KeyboardButton(text="📋 Сдать факт выполненных работ")],
        [KeyboardButton(text="📄 Новые документы на подпись")],
        [KeyboardButton(text="📤 Загрузить подписанные документы и счет")],
        [KeyboardButton(text="🧾 Загрузить чек")],
        [KeyboardButton(text="💳 Банковские реквизиты")],
        [KeyboardButton(text="📁 Мои документы")],
        [KeyboardButton(text="✏️ Уведомить об изменениях")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def registration_start_keyboard():
    """Клавиатура для начала регистрации"""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📝 Заполнить карточку")]],
        resize_keyboard=True
    )

# ----- INLINE КЛАВИАТУРЫ ДЛЯ РЕГИСТРАЦИИ -----
def consent_keyboard():
    """Согласие на обработку данных"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Подтверждаю", callback_data="consent_confirm"))
    builder.add(InlineKeyboardButton(text="❓ Задать вопрос", callback_data="ask_lawyer_question"))
    return builder.as_markup()

def tax_type_keyboard():
    """Выбор типа налогообложения"""
    builder = InlineKeyboardBuilder()
    for tax_key, tax_name in TAX_TYPES.items():
        builder.add(InlineKeyboardButton(text=tax_name, callback_data=f"tax_{tax_key}"))
    builder.adjust(1)
    return builder.as_markup()

def departments_keyboard():
    """Выбор отдела"""
    builder = InlineKeyboardBuilder()
    for dept in DEPARTMENTS:
        builder.add(InlineKeyboardButton(text=dept, callback_data=f"dept_{dept}"))
    builder.adjust(1)
    return builder.as_markup()

def confirm_data_keyboard():
    """Подтверждение данных после регистрации"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_all"))
    builder.add(InlineKeyboardButton(text="✏️ Исправить ФИО", callback_data="edit_full_name"))
    builder.add(InlineKeyboardButton(text="✏️ Исправить паспорт", callback_data="edit_passport"))
    builder.add(InlineKeyboardButton(text="✏️ Исправить адрес", callback_data="edit_address"))
    builder.add(InlineKeyboardButton(text="✏️ Исправить ИНН", callback_data="edit_inn"))
    builder.add(InlineKeyboardButton(text="✏️ Исправить телефон", callback_data="edit_phone"))
    builder.add(InlineKeyboardButton(text="✏️ Исправить email", callback_data="edit_email"))
    builder.add(InlineKeyboardButton(text="✏️ Исправить дату начала", callback_data="edit_start_date"))
    builder.add(InlineKeyboardButton(text="✏️ Исправить налог", callback_data="edit_tax"))
    builder.add(InlineKeyboardButton(text="✏️ Исправить отдел", callback_data="edit_department"))
    builder.adjust(1)
    return builder.as_markup()

# ----- КЛАВИАТУРЫ ДЛЯ НДА -----
def nda_keyboard():
    """Клавиатура для работы с НДА"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Загрузить подписанный НДА", callback_data="upload_signed_nda"))
    builder.add(InlineKeyboardButton(text="⏳ Запросить продление", callback_data="ask_nda_extension"))
    builder.adjust(1)
    return builder.as_markup()

def nda_review_keyboard(user_id):
    """Клавиатура для юриста при проверке НДА"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Принять НДА", callback_data=f"approve_nda_{user_id}"))
    builder.add(InlineKeyboardButton(text="❌ Вернуть на доработку", callback_data=f"reject_nda_{user_id}"))
    return builder.as_markup()

def get_chat_links_keyboard(department):
    """Клавиатура со ссылками на чаты после подписания НДА"""
    from config import DEPARTMENT_CHATS, CHANNEL_NEWS, COMMUNITY_CHAT
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="📢 Новостной канал", url=CHANNEL_NEWS))
    builder.add(InlineKeyboardButton(text="💬 Чат комьюнити", url=COMMUNITY_CHAT))
    if department in DEPARTMENT_CHATS:
        builder.add(InlineKeyboardButton(text=f"👥 Чат {department}", url=DEPARTMENT_CHATS[department]))
    builder.adjust(1)
    return builder.as_markup()

# ----- КЛАВИАТУРЫ ДЛЯ РУКОВОДИТЕЛЕЙ -----
def manager_main_keyboard():
    """Главное меню руководителя"""
    buttons = [
        [KeyboardButton(text="👥 Выбрать отдел")],
        [KeyboardButton(text="📊 Отчеты на проверку")],
        [KeyboardButton(text="🔄 Изменить должность")],
        [KeyboardButton(text="🚫 Уволить сотрудника")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def departments_select_keyboard():
    """Выбор отдела из списка"""
    builder = InlineKeyboardBuilder()
    for dept in DEPARTMENTS:
        builder.add(InlineKeyboardButton(text=dept, callback_data=f"select_dept_{dept}"))
    builder.adjust(1)
    return builder.as_markup()

def report_review_keyboard(report_id):
    """Клавиатура для проверки отчета"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"approve_report_{report_id}"))
    builder.add(InlineKeyboardButton(text="✏️ Внести корректировки", callback_data=f"edit_report_{report_id}"))
    return builder.as_markup()

def employee_list_keyboard(users, action_type):
    """Список сотрудников для действий (увольнение/изменение)"""
    builder = InlineKeyboardBuilder()
    for user in users:
        builder.add(InlineKeyboardButton(
            text=user['full_name'],
            callback_data=f"{action_type}_{user['user_id']}"
        ))
    builder.adjust(1)
    return builder.as_markup()

# ----- КЛАВИАТУРЫ ДЛЯ ЮРИСТА -----
def lawyer_main_keyboard():
    """Главное меню юриста"""
    buttons = [
        [KeyboardButton(text="📝 Новые запросы на НДА")],
        [KeyboardButton(text="💰 Запросы на оплату")],
        [KeyboardButton(text="📎 Подписанные документы")],
        [KeyboardButton(text="🧾 Чеки")],
        [KeyboardButton(text="👥 Выбрать отдел")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def payment_request_keyboard(report_id):
    """Клавиатура для обработки запроса на оплату"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Передать на оплату", callback_data=f"pay_{report_id}"))
    builder.add(InlineKeyboardButton(text="✏️ На корректировку", callback_data=f"correction_{report_id}"))
    return builder.as_markup()

# ----- КЛАВИАТУРЫ ДЛЯ ФИНАНСОВОГО ОТДЕЛА -----
def finance_main_keyboard():
    """Главное меню фин отдела"""
    buttons = [
        [KeyboardButton(text="💳 Платежные поручения")],
        [KeyboardButton(text="✅ Подтвердить оплату")],
        [KeyboardButton(text="📊 Статусы платежей")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# ----- КЛАВИАТУРЫ ДЛЯ ЛИЧНОГО КАБИНЕТА -----
def bank_details_keyboard():
    """Клавиатура для банковских реквизитов"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="💳 Заполнить реквизиты", callback_data="fill_bank_details"))
    builder.add(InlineKeyboardButton(text="✏️ Исправить реквизиты", callback_data="edit_bank_details"))
    return builder.as_markup()

def change_type_keyboard():
    """Типы изменений личных данных"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="📄 Смена формы налогообложения", callback_data="change_tax_type"))
    builder.add(InlineKeyboardButton(text="👤 Смена фамилии", callback_data="change_last_name"))
    return builder.as_markup()

def save_cancel_keyboard():
    """Кнопки Сохранить/Отмена"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="💾 Сохранить", callback_data="save_data"))
    builder.add(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()