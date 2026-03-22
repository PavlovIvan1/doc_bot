from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from datetime import datetime
import os

from handlers.states import Registration
from database import Database
import keyboard as kb
from config import LAWYER_ID, CONSENT_LINK

router = Router()
db = Database()

@router.message(Command("start"))
async def cmd_start(message: Message):
    user = db.get_user(message.from_user.id)
    
    if user:
        if user['registration_status'] == 'active':
            # По ТЗ - 2 кнопки: Подписать NDA и Создать счёт
            await message.answer(
                "Выбери действие:",
                reply_markup=kb.simple_main_menu_keyboard()
            )
        elif user['registration_status'] == 'pending':
            await message.answer(
                "⏳ Ваша регистрация на проверке. Ожидайте ответа юриста."
            )
        elif user['registration_status'] == 'nda_pending':
            await message.answer(
                "📄 Ожидайте НДА на подписание от юриста."
            )
        elif user['registration_status'] == 'fired':
            await message.answer(
                "❌ Доступ заблокирован. Обратитесь к руководителю."
            )
    else:
        text = """
Привет, коллега 👋
Я бот-помощник по документообороту

Сейчас тебе важно заполнить карточку контрагента. Ошибка в одном поле = задержка нда/договора/оплаты.

Жми ниже👇
        """
        await message.answer(text, reply_markup=kb.registration_start_keyboard())

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

# Обработчик кнопки "Создать счёт" - перенаправляет на создание заявки
@router.message(F.text == "💰 Создать счёт")
async def create_invoice_shortcut(message: Message, state: FSMContext):
    from handlers.states import PaymentRequest
    user = db.get_user(message.from_user.id)
    if not user or user['registration_status'] != 'active':
        await message.answer("❌ Доступ запрещён. Пройдите регистрацию.")
        return
    
    # Перенаправляем на создание заявки
    await message.answer("💰 Создание заявки на оплату\n\nВведите сумму (только число, например: 15000):")
    await state.set_state(PaymentRequest.amount)

# Обработчик кнопки "Меню" - показывает полное меню
@router.message(F.text == "📋 Меню")
async def show_full_menu(message: Message):
    user = db.get_user(message.from_user.id)
    if not user or user['registration_status'] != 'active':
        await message.answer("❌ Доступ запрещён. Пройдите регистрацию.")
        return
    
    await message.answer(
        "📋 Полное меню:",
        reply_markup=kb.main_menu_keyboard()
    )

@router.message(F.text == "📝 Заполнить карточку")
async def start_registration(message: Message, state: FSMContext):
    text = f"""
Перед стартом: ты даешь согласие на обработку персональных данных ([ссылка]({CONSENT_LINK})) с целью оформления документов (нда, договор, акт выполненных работ), а также выплат согласно акту внутри компании
    """
    await message.answer(
        text,
        parse_mode="Markdown",
        reply_markup=kb.consent_keyboard()
    )

@router.callback_query(F.data == "consent_confirm")
async def consent_confirm(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("1/10 Введи полное ФИО как в паспорте (например: Иванов Иван Иванович)")
    await state.set_state(Registration.full_name)

@router.callback_query(F.data == "ask_lawyer_question")
async def ask_lawyer(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("📝 Напишите ваш вопрос, и юрист ответит в ближайшее время:")
    await state.set_state("waiting_lawyer_question")

@router.message(Registration.full_name)
async def reg_full_name(message: Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    await message.answer("2/10 Паспорт - введи серию и номер паспорта (пример: 1234 567890)")
    await state.set_state(Registration.passport_series)

@router.message(Registration.passport_series)
async def reg_passport_series(message: Message, state: FSMContext):
    await state.update_data(passport_data=message.text)
    await message.answer("2/10 Паспорт - введи дату выдачи (ДД.ММ.ГГГГ)")
    await state.set_state(Registration.passport_date)

@router.message(Registration.passport_date)
async def reg_passport_date(message: Message, state: FSMContext):
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        await state.update_data(passport_date=message.text)
        await message.answer("2/10 Паспорт - введи кем выдан (как в паспорте)")
        await state.set_state(Registration.passport_issued)
    except ValueError:
        await message.answer("❌ Неверный формат даты. Используй ДД.ММ.ГГГГ")

@router.message(Registration.passport_issued)
async def reg_passport_issued(message: Message, state: FSMContext):
    await state.update_data(passport_issued=message.text)
    await message.answer("2/10 Паспорт - введи код подразделения (пример: 770-001)")
    await state.set_state(Registration.passport_code)

@router.message(Registration.passport_code)
async def reg_passport_code(message: Message, state: FSMContext):
    await state.update_data(passport_code=message.text)
    await message.answer("2/10 Паспорт - введи дату рождения (ДД.ММ.ГГГГ)")
    await state.set_state(Registration.birth_date)

@router.message(Registration.birth_date)
async def reg_birth_date(message: Message, state: FSMContext):
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        await state.update_data(birth_date=message.text)
        await message.answer("3/10 Введи адрес регистрации (для самозанятых) или юр. адрес (для ИП). Формат: индекс, город, улица, дом, квартира/офис")
        await state.set_state(Registration.address)
    except ValueError:
        await message.answer("❌ Неверный формат даты. Используй ДД.ММ.ГГГГ")

@router.message(Registration.address)
async def reg_address(message: Message, state: FSMContext):
    await state.update_data(address=message.text)
    await message.answer("4/10 Введи ИНН (только цифры)")
    await state.set_state(Registration.inn)

@router.message(Registration.inn)
async def reg_inn(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ ИНН должен содержать только цифры")
        return
    await state.update_data(inn=message.text)
    await message.answer("5/10 Введи номер телефона (пример: +7XXXXXXXXXX)")
    await state.set_state(Registration.phone)

@router.message(Registration.phone)
async def reg_phone(message: Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await message.answer("6/10 Введи адрес электронной почты")
    await state.set_state(Registration.email)

@router.message(Registration.email)
async def reg_email(message: Message, state: FSMContext):
    if "@" not in message.text:
        await message.answer("❌ Неверный формат email")
        return
    await state.update_data(email=message.text)
    await message.answer("7/10 Дата начала сотрудничества с ИП Трофимова А.А — ДД.ММ.ГГГГ")
    await state.set_state(Registration.start_date)

@router.message(Registration.start_date)
async def reg_start_date(message: Message, state: FSMContext):
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        await state.update_data(start_date=message.text)
        await message.answer(
            "8/10 Укажи свою форму налогообложения:",
            reply_markup=kb.tax_type_keyboard()
        )
        await state.set_state(Registration.tax_type)
    except ValueError:
        await message.answer("❌ Неверный формат даты. Используй ДД.ММ.ГГГГ")

@router.callback_query(Registration.tax_type, F.data.startswith("tax_"))
async def reg_tax_type(callback: CallbackQuery, state: FSMContext):
    tax_type = callback.data.replace("tax_", "")
    await state.update_data(tax_type=tax_type)
    
    if tax_type in ['self_employed_npd', 'ip_npd']:
        await callback.message.edit_text(
            "Прикрепи подтверждающий документ 'Справка о постановке на учёт' из 'Мой налог'"
        )
        await state.set_state(Registration.tax_document)
    else:
        await callback.message.edit_text(
            "9/10 Выбери отдел компании:",
            reply_markup=kb.departments_keyboard()
        )
        await state.set_state(Registration.department)

@router.message(Registration.tax_document, F.content_type == 'document')
async def reg_tax_document(message: Message, state: FSMContext, bot):
    # Скачиваем документ
    file = await bot.get_file(message.document.file_id)
    file_path = f"downloads/tax_docs/{message.from_user.id}_{message.document.file_name}"
    await bot.download_file(file.file_path, file_path)
    
    await state.update_data(tax_document_path=file_path)
    await message.answer(
        "9/10 Выбери отдел компании:",
        reply_markup=kb.departments_keyboard()
    )
    await state.set_state(Registration.department)

@router.callback_query(Registration.department, F.data.startswith("dept_"))
async def reg_department(callback: CallbackQuery, state: FSMContext):
    department = callback.data.replace("dept_", "")
    await state.update_data(department=department)
    
    # Получаем все данные
    data = await state.get_data()
    
    # Формируем сообщение для подтверждения
    text = f"""
📋 Проверьте введенные данные:

👤 ФИО: {data['full_name']}
🆔 ИНН: {data['inn']}
📞 Телефон: {data['phone']}
📧 Email: {data['email']}
📅 Дата начала: {data['start_date']}
💰 Налогообложение: {data['tax_type']}
🏢 Отдел: {data['department']}
📍 Адрес: {data['address']}

Если всё верно - нажмите Подтвердить
    """
    
    await callback.message.edit_text(text, reply_markup=kb.confirm_data_keyboard())
    await state.set_state(Registration.confirm)

@router.callback_query(Registration.confirm, F.data == "confirm_all")
async def confirm_registration(callback: CallbackQuery, state: FSMContext, bot):
    data = await state.get_data()
    
    # Сохраняем пользователя в БД
    db.add_user(
        user_id=callback.from_user.id,
        telegram_login=callback.from_user.username,
        full_name=data['full_name'],
        passport_data=f"{data['passport_data']} {data['passport_date']} {data['passport_issued']} {data['passport_code']}",
        birth_date=data['birth_date'],
        registration_address=data['address'],
        inn=data['inn'],
        phone=data['phone'],
        email=data['email'],
        start_date=data['start_date'],
        tax_type=data['tax_type'],
        tax_document_path=data.get('tax_document_path'),
        department=data['department'],
        registration_status='pending'
    )
    
    await callback.message.edit_text(
        "✅ Принял! Твой профиль ушёл на проверку. Как только юрист подтвердит и подготовит НДА, я вышлю тебе его на подпись."
    )
    
    # Уведомление юристу
    await bot.send_message(
        LAWYER_ID,
        f"🆕 Новый сотрудник на регистрации:\n"
        f"ФИО: {data['full_name']}\n"
        f"Отдел: {data['department']}\n"
        f"ИНН: {data['inn']}\n"
        f"Телефон: {data['phone']}"
    )
    
    await state.clear()

# Обработчики для исправления данных (коротко)
@router.callback_query(F.data.startswith("edit_"))
async def edit_data(callback: CallbackQuery, state: FSMContext):
    field = callback.data.replace("edit_", "")
    
    field_questions = {
        "full_name": "Введите новое ФИО:",
        "passport": "Введите новые паспортные данные:",
        "address": "Введите новый адрес:",
        "inn": "Введите новый ИНН:",
        "phone": "Введите новый телефон:",
        "email": "Введите новый email:",
        "start_date": "Введите новую дату начала:",
        "tax": "Выберите новый тип налогообложения:",
        "department": "Выберите новый отдел:"
    }
    
    await callback.message.answer(field_questions[field])
    
    if field == "tax":
        await callback.message.answer("Выберите тип:", reply_markup=kb.tax_type_keyboard())
        await state.set_state(Registration.tax_type)
    elif field == "department":
        await callback.message.answer("Выберите отдел:", reply_markup=kb.departments_keyboard())
        await state.set_state(Registration.department)
    else:
        # Сохраняем что редактируем
        await state.update_data(editing_field=field)
        await state.set_state("editing_data")