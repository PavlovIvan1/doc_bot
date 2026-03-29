from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from datetime import datetime
import os
import re
from datetime import timedelta

from handlers.states import Registration
from database import Database
import keyboard as kb
from config import LAWYER_ID, FINANCE_DIRECTOR_ID, ACCOUNTANT_ID, MANAGERS, CONSENT_LINK, LAWYER_SKIP_REGISTRATION, is_whitelisted

router = Router()
db = Database()

VALIDATION_BYPASS_USER_ID = 5201430878


def is_validation_bypassed(user_id: int) -> bool:
    return user_id == VALIDATION_BYPASS_USER_ID


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

    if not is_whitelisted(user_id):
        await message.answer("⛔ Доступ к боту ограничен. Обратитесь к администратору для добавления в whitelist.")
        return
    
    # Проверяем, если user_id соответствует одной из ролей
    # Если LAWYER_SKIP_REGISTRATION=true, то юрист сразу получает меню без регистрации
    if LAWYER_SKIP_REGISTRATION and user_id == LAWYER_ID:
        await message.answer("👨‍💼 Меню юриста:", reply_markup=kb.lawyer_main_keyboard())
        return
    elif user_id == LAWYER_ID:
        # Проверяем, есть ли пользователь в БД
        user = db.get_user(user_id)
        if user and user.get('registration_status') == 'active':
            await message.answer("👨‍💼 Меню юриста:", reply_markup=kb.lawyer_main_keyboard())
            return
        # Иначе начинаем регистрацию
        text = """
Привет, коллега 👋
Я бот-помощник по документообороту

Сейчас тебе важно заполнить карточку контрагента. Ошибка в одном поле = задержка нда/договора/оплаты.

Жми ниже👇
        """
        await message.answer(text, reply_markup=kb.registration_start_keyboard())
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
            nda_signed = user.get('nda_status') == 'signed'
            if nda_signed:
                start_text = (
                    "Выбери действие:\n"
                    "1) Подписать договор\n"
                    "2) Сдать факт выполненных работ\n"
                    "3) Дальше открой полное меню"
                )
            else:
                start_text = "Выбери действие: сначала нужно подписать NDA"

            await message.answer(
                start_text,
                reply_markup=kb.simple_main_menu_keyboard(nda_signed=nda_signed)
            )

            # Напоминания по незагруженным закрывающим документам
            cursor = db.connection.cursor(dictionary=True)
            cursor.execute(
                "SELECT id, created_at FROM payment_requests WHERE user_id = %s AND status = 'paid'",
                (user_id,)
            )
            paid_requests = cursor.fetchall()

            for req in paid_requests:
                docs = db.get_payment_request_documents(req['id'])
                doc_types = [d['doc_type'] for d in docs]

                if 'act' not in doc_types or 'contract' not in doc_types or 'check' not in doc_types:
                    await message.answer(
                        f"⚠️ По заявке #{req['id']} не загружены закрывающие документы.\n"
                        f"Загрузите: акт, договор и чек."
                    )

                created_at = req.get('created_at')
                if created_at and datetime.now() - created_at > timedelta(days=5) and 'act' not in doc_types:
                    await message.answer(
                        f"⏰ Просрочка по акту в заявке #{req['id']}.\n"
                        f"Пожалуйста, срочно загрузите подписанный акт."
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


@router.message(F.text == "📑 Подписать договор")
async def sign_contract_shortcut(message: Message):
    user = db.get_user(message.from_user.id)
    if not user or user['registration_status'] != 'active':
        await message.answer("❌ Доступ запрещён. Пройдите регистрацию.")
        return

    if user.get('nda_status') != 'signed':
        await message.answer("📄 Сначала нужно подписать и согласовать NDA.")
        return

    await message.answer(
        "📑 Этап договора активен.\n"
        "Откройте полное меню (кнопка «📋 Меню») и загрузите договор в своей заявке.\n"
        "После договора сдайте факт выполненных работ."
    )

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
    if not is_whitelisted(message.from_user.id):
        await message.answer("⛔ Доступ к боту ограничен. Обратитесь к администратору.")
        return

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
    await callback.message.edit_text("1/13 Введи фамилию как в паспорте")
    await state.set_state(Registration.last_name)

@router.callback_query(F.data == "ask_lawyer_question")
async def ask_lawyer(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("📝 Напишите ваш вопрос, и юрист ответит в ближайшее время:")
    await state.set_state("waiting_lawyer_question")

@router.message(Registration.last_name)
async def reg_last_name(message: Message, state: FSMContext):
    last_name = (message.text or "").strip()
    if not is_validation_bypassed(message.from_user.id) and len(last_name) < 2:
        await message.answer("❌ Фамилия слишком короткая")
        return

    await state.update_data(last_name=last_name)
    await message.answer("2/13 Введи имя как в паспорте")
    await state.set_state(Registration.first_name)


@router.message(Registration.first_name)
async def reg_first_name(message: Message, state: FSMContext):
    first_name = (message.text or "").strip()
    if not is_validation_bypassed(message.from_user.id) and len(first_name) < 2:
        await message.answer("❌ Имя слишком короткое")
        return

    await state.update_data(first_name=first_name)
    await message.answer("3/13 Введи отчество как в паспорте")
    await state.set_state(Registration.middle_name)


@router.message(Registration.middle_name)
async def reg_middle_name(message: Message, state: FSMContext):
    middle_name = (message.text or "").strip()
    if not is_validation_bypassed(message.from_user.id) and len(middle_name) < 2:
        await message.answer("❌ Отчество слишком короткое")
        return

    data = await state.get_data()
    last_name = data.get('last_name', '').strip()
    first_name = data.get('first_name', '').strip()
    full_name = f"{last_name} {first_name} {middle_name}".strip()

    await state.update_data(middle_name=middle_name, full_name=full_name)
    await message.answer("4/13 Паспорт — введи серию и номер в одну строку без пробелов (пример: 1234567890)")
    await state.set_state(Registration.passport_series)

@router.message(Registration.passport_series)
async def reg_passport_series(message: Message, state: FSMContext):
    passport_data = (message.text or "").strip()
    bypass_validation = is_validation_bypassed(message.from_user.id)

    if not bypass_validation:
        if " " in passport_data:
            await message.answer("❌ Паспортные данные нужно вводить в одну строку без пробелов")
            return

        if not passport_data.isdigit() or len(passport_data) < 10:
            await message.answer("❌ Паспортные данные должны содержать только цифры и минимум 10 символов")
            return

    await state.update_data(passport_data=passport_data)
    await message.answer("4/13 Паспорт - введи дату выдачи (ДД.ММ.ГГГГ)")
    await state.set_state(Registration.passport_date)

@router.message(Registration.passport_date)
async def reg_passport_date(message: Message, state: FSMContext):
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        await state.update_data(passport_date=message.text)
        await message.answer("4/13 Паспорт - введи кем выдан (как в паспорте)")
        await state.set_state(Registration.passport_issued)
    except ValueError:
        await message.answer("❌ Неверный формат даты. Используй ДД.ММ.ГГГГ")

@router.message(Registration.passport_issued)
async def reg_passport_issued(message: Message, state: FSMContext):
    await state.update_data(passport_issued=message.text)
    await message.answer("4/13 Паспорт - введи код подразделения (пример: 770-001)")
    await state.set_state(Registration.passport_code)

@router.message(Registration.passport_code)
async def reg_passport_code(message: Message, state: FSMContext):
    await state.update_data(passport_code=message.text)
    await message.answer("5/13 Паспорт - введи дату рождения (ДД.ММ.ГГГГ)")
    await state.set_state(Registration.birth_date)

@router.message(Registration.birth_date)
async def reg_birth_date(message: Message, state: FSMContext):
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        await state.update_data(birth_date=message.text)
        await message.answer("6/13 Введи индекс адреса (только цифры)")
        await state.set_state(Registration.address_index)
    except ValueError:
        await message.answer("❌ Неверный формат даты. Используй ДД.ММ.ГГГГ")

@router.message(Registration.address_index)
async def reg_address_index(message: Message, state: FSMContext):
    address_index = (message.text or "").strip()
    if not is_validation_bypassed(message.from_user.id):
        if not address_index.isdigit() or len(address_index) != 6:
            await message.answer("❌ Индекс должен содержать ровно 6 цифр")
            return

    await state.update_data(address_index=address_index)
    await message.answer("7/13 Введи город")
    await state.set_state(Registration.address_city)


@router.message(Registration.address_city)
async def reg_address_city(message: Message, state: FSMContext):
    city = (message.text or "").strip()
    if not is_validation_bypassed(message.from_user.id) and len(city) < 2:
        await message.answer("❌ Город указан некорректно")
        return

    await state.update_data(address_city=city)
    await message.answer("8/13 Введи улицу, дом и квартиру/офис")
    await state.set_state(Registration.address_street)


@router.message(Registration.address_street)
async def reg_address_street(message: Message, state: FSMContext):
    street = (message.text or "").strip()
    if not is_validation_bypassed(message.from_user.id) and len(street) < 3:
        await message.answer("❌ Улица/дом указаны некорректно")
        return

    data = await state.get_data()
    address = f"{data.get('address_index', '').strip()}, {data.get('address_city', '').strip()}, {street}".strip(', ')

    await state.update_data(address_street=street, address=address)
    await message.answer("9/13 Введи ИНН (только цифры, 12 символов)")
    await state.set_state(Registration.inn)

@router.message(Registration.inn)
async def reg_inn(message: Message, state: FSMContext):
    inn = (message.text or "").strip()
    if not is_validation_bypassed(message.from_user.id):
        if not inn.isdigit() or len(inn) != 12:
            await message.answer("❌ ИНН физического лица должен состоять из 12 цифр")
            return

    await state.update_data(inn=inn)
    await message.answer("10/13 Введи номер телефона (минимум 9 цифр, для РФ — 11)")
    await state.set_state(Registration.phone)

@router.message(Registration.phone)
async def reg_phone(message: Message, state: FSMContext):
    phone = (message.text or "").strip()
    if not is_validation_bypassed(message.from_user.id):
        digits = re.sub(r"\D", "", phone)
        min_len = 11 if phone.startswith('+7') or phone.startswith('8') or digits.startswith('7') else 9
        if len(digits) < min_len:
            await message.answer(f"❌ Номер телефона слишком короткий. Минимум {min_len} цифр")
            return

    await state.update_data(phone=phone)
    await message.answer("11/13 Введи адрес электронной почты")
    await state.set_state(Registration.email)

@router.message(Registration.email)
async def reg_email(message: Message, state: FSMContext):
    email = (message.text or "").strip()
    if not is_validation_bypassed(message.from_user.id):
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            await message.answer("❌ Неверный формат email. Нужен полный адрес вида name@domain.ru")
            return

    await state.update_data(email=email)
    await message.answer("12/13 Дата начала сотрудничества с ИП Трофимова А.А — ДД.ММ.ГГГГ")
    await state.set_state(Registration.start_date)

@router.message(Registration.start_date)
async def reg_start_date(message: Message, state: FSMContext):
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        await state.update_data(start_date=message.text)
        await message.answer(
            "13/13 Укажи свою форму налогообложения:",
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

@router.message(Registration.tax_document)
async def reg_tax_document(message: Message, state: FSMContext, bot):
    # Проверяем, что есть документ
    if not message.document:
        await message.answer("❌ Пожалуйста, прикрепите файл документа")
        return
    
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
        passport_data=data.get('passport_data', ''),
        passport_date=convert_date_to_db_format(data.get('passport_date', '')),
        passport_issued=data.get('passport_issued', ''),
        passport_code=data.get('passport_code', ''),
        birth_date=convert_date_to_db_format(data['birth_date']),
        registration_address=data['address'],
        inn=data['inn'],
        phone=data['phone'],
        email=data['email'],
        start_date=convert_date_to_db_format(data['start_date']),
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
