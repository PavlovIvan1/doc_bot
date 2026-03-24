from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from datetime import datetime
import os

from handlers.states import Registration
from database import Database
import keyboard as kb
from config import LAWYER_ID, FINANCE_DIRECTOR_ID, ACCOUNTANT_ID, MANAGERS, CONSENT_LINK

router = Router()
db = Database()


def convert_date_to_db_format(date_str):
    """Конвертирует дату из формата DD.MM.YYYY в YYYY-MM-DD для MySQL"""
    if not date_str or date_str == '':
        return None
    try:
        dt = datetime.strptime(date_str, "%d.%m.%Y")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return None


@router.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    
    # Проверяем, если user_id соответствует одной из ролей (из .env)
    if user_id == LAWYER_ID:
        await message.answer("👨‍💼 Меню юриста:", reply_markup=kb.lawyer_main_keyboard())
        return
    elif user_id == FINANCE_DIRECTOR_ID:
        await message.answer("💰 Меню финансового директора:", reply_markup=kb.finance_main_keyboard())
        return
    elif user_id == ACCOUNTANT_ID:
        await message.answer("📊 Меню бухгалтера:", reply_markup=kb.finance_main_keyboard())
        return
    elif user_id in MANAGERS:
        dept = MANAGERS[user_id]
        await message.answer(f"👔 Меню руководителя отдела {dept}:", reply_markup=kb.manager_main_keyboard())
        return
    
    user = db.get_user(user_id)
    
    if user:
        if user['registration_status'] == 'active':
            await message.answer(
                "Выбери действие:",
                reply_markup=kb.simple_main_menu_keyboard()
            )
        elif user['registration_status'] == 'pending':
            await message.answer("⏳ Ваша регистрация на проверке. Ожидайте ответа юриста.")
        elif user['registration_status'] == 'nda_pending':
            await message.answer("📄 Ожидайте НДА на подписание от юриста.")
        elif user['registration_status'] == 'fired':
            await message.answer("❌ Доступ заблокирован. Обратитесь к руководителю.")
    else:
        text = "Привет, коллега!\nЯ бот-помощник по документообороту.\n\nСейчас тебе важно заполнить карточку контрагента. Ошибка в одном поле = задержка нда/договора/оплаты.\n\nЖми ниже"
        await message.answer(text, reply_markup=kb.registration_start_keyboard())


# Обработчик кнопки "Начать регистрацию"
@router.message(F.text == "📝 Начать регистрацию")
@router.callback_query(F.data == "start_registration")
async def start_registration(event, state: FSMContext):
    await state.clear()
    await state.set_state(Registration.waiting_for_full_name)
    
    text = f"Перед стартом: ты даешь согласие на обработку персональных данных ([ссылка]({CONSENT_LINK})) с целью оформления документов (нда, договор, акт выполненных работ), а также выплат согласно акту внутри компании.\n\nВведите ваше ФИО (Полностью):"
    
    if isinstance(event, Message):
        await event.answer(text, reply_markup=kb.cancel_keyboard())
    else:
        await event.message.edit_text(text, reply_markup=kb.cancel_keyboard())


@router.message(Registration.waiting_for_full_name)
async def get_full_name(message: Message, state: FSMContext):
    full_name = message.text.strip()
    if len(full_name.split()) < 2:
        await message.answer("❌ Введите полное ФИО (минимум 2 слова)")
        return
    await state.update_data(full_name=full_name)
    await state.set_state(Registration.waiting_for_inn)
    await message.answer("Введите ИНН:")


@router.message(Registration.waiting_for_inn)
async def get_inn(message: Message, state: FSMContext):
    inn = message.text.strip()
    if not inn.isdigit() or len(inn) not in [10, 12]:
        await message.answer("❌ ИНН должен быть 10 или 12 цифр")
        return
    await state.update_data(inn=inn)
    await state.set_state(Registration.waiting_for_phone)
    await message.answer("Введите номер телефона:")


@router.message(Registration.waiting_for_phone)
async def get_phone(message: Message, state: FSMContext):
    phone = message.text.strip()
    await state.update_data(phone=phone)
    await state.set_state(Registration.waiting_for_email)
    await message.answer("Введите Email:")


@router.message(Registration.waiting_for_email)
async def get_email(message: Message, state: FSMContext):
    email = message.text.strip()
    if '@' not in email:
        await message.answer("❌ Введите корректный Email")
        return
    await state.update_data(email=email)
    await state.set_state(Registration.waiting_for_start_date)
    await message.answer("Введите дату начала работы (ДД.ММ.ГГГГ):")


@router.message(Registration.waiting_for_start_date)
async def get_start_date(message: Message, state: FSMContext):
    start_date = message.text.strip()
    try:
        datetime.strptime(start_date, "%d.%m.%Y")
    except ValueError:
        await message.answer("❌ Введите дату в формате ДД.ММ.ГГГГ")
        return
    await state.update_data(start_date=start_date)
    await state.set_state(Registration.waiting_for_department)
    await message.answer("Выберите отдел:", reply_markup=kb.department_selection_keyboard())


@router.message(Registration.waiting_for_department)
async def get_department(message: Message, state: FSMContext):
    department = message.text
    if department not in ["Отдел контента", "Отдел маркетинга", "Отдел продаж", 
                          "Департамент продукта", "Отдел контроля качества", 
                          "Финансово-юридический отдел"]:
        await message.answer("❌ Выберите отдел из списка")
        return
    await state.update_data(department=department)
    await state.set_state(Registration.waiting_for_tax_type)
    await message.answer("Выберите систему налогообложения:", reply_markup=kb.tax_type_keyboard())


@router.message(Registration.waiting_for_tax_type)
async def get_tax_type(message: Message, state: FSMContext):
    tax_type = message.text
    await state.update_data(tax_type=tax_type)
    await state.set_state(Registration.waiting_for_address)
    await message.answer("Введите адрес (фактический):")


@router.message(Registration.waiting_for_address)
async def get_address(message: Message, state: FSMContext):
    address = message.text.strip()
    if len(address) < 5:
        await message.answer("❌ Введите корректный адрес")
        return
    await state.update_data(address=address)
    
    # Получаем все данные
    data = await state.get_data()
    
    # Формируем сообщение для подтверждения
    text = f"Проверьте введенные данные:\n\nФИО: {data['full_name']}\nИНН: {data['inn']}\nТелефон: {data['phone']}\nEmail: {data['email']}\nДата начала: {data['start_date']}\nНалогообложение: {data['tax_type']}\nОтдел: {data['department']}\nАдрес: {data['address']}\n\nЕсли всё верно - нажмите Подтвердить"
    
    await message.answer(text, reply_markup=kb.confirm_data_keyboard())
    await state.set_state(Registration.confirm)


@router.message(Registration.confirm)
async def confirm_registration(message: Message, state: FSMContext):
    if message.text != "✅ Подтвердить":
        await message.answer("Нажмите кнопку Подтвердить")
        return
    
    data = await state.get_data()
    
    # Конвертируем дату в формат для БД
    passport_date = convert_date_to_db_format(data.get('start_date', ''))
    
    # Добавляем пользователя
    db.add_user(
        user_id=message.from_user.id,
        full_name=data['full_name'],
        inn=data['inn'],
        phone=data['phone'],
        email=data['email'],
        start_date=passport_date,
        tax_type=data['tax_type'],
        department=data['department'],
        address=data['address']
    )
    
    await message.answer("✅ Регистрация отправлена на проверку! Ожидайте подтверждения от юриста.")
    await state.clear()


# Обработчик кнопки "Подписать NDA"
@router.message(F.text == "📄 Подписать NDA")
async def sign_nda_menu(message: Message):
    user = db.get_user(message.from_user.id)
    if not user or user['registration_status'] != 'active':
        await message.answer("❌ Доступ запрещён. Пройдите регистрацию.")
        return
    
    await message.answer(
        "📄 Загрузите подписанный NDA:",
        reply_markup=kb.nda_keyboard()
    )


# Обработчик кнопки "Создать счёт"
@router.message(F.text == "💰 Создать счёт")
async def create_invoice_menu(message: Message):
    user = db.get_user(message.from_user.id)
    if not user or user['registration_status'] != 'active':
        await message.answer("❌ Доступ запрещён. Пройдите регистрацию.")
        return
    
    await message.answer("💰 Создание счёта:")
    # Здесь можно добавить перенаправление на manager router


# Обработчик кнопки "Отмена"
@router.message(F.text == "❌ Отмена")
async def cancel_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Действие отменено. Используйте /start для начала.")


# Обработчик callback "Отмена"  
@router.callback_query(F.data == "cancel")
async def cancel_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Действие отменено.")
    await callback.answer()