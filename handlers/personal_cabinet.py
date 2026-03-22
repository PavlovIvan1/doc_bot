from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from datetime import datetime
from aiogram.utils.keyboard import InlineKeyboardButton
import os

from handlers.states import MonthlyReport, BankDetails, DocumentUpload, PaymentRequest, PaymentRequestUpload
from database import Database
import keyboard as kb
from config import MANAGERS

router = Router()
db = Database()

# Проверка доступа
async def check_active_user(message: Message):
    user = db.get_user(message.from_user.id)
    if not user or user['registration_status'] != 'active':
        await message.answer("❌ Доступ запрещен. Пройдите регистрацию.")
        return False
    return True

@router.message(F.text == "📋 Сдать факт выполненных работ")
async def start_monthly_report(message: Message, state: FSMContext):
    if not await check_active_user(message):
        return
    
    # Определяем предыдущий месяц
    last_month = datetime.now().replace(day=1)
    month_name = last_month.strftime("%B %Y")
    
    await message.answer(
        f"📝 Отчет за {month_name}\n\n"
        "Пропиши подробно что сделано за прошлый период и в каком кол-ве, например:\n"
        "1. Написано 53 сценария для сторителлингов\n"
        "2. Оформлено и опубликовано 53 сторителлинга\n"
        "3. Написано 40 сценариев для постов-каруселей"
    )
    await state.set_state(MonthlyReport.description)
    await state.update_data(report_month=last_month.strftime("%Y-%m-%d"))

@router.message(MonthlyReport.description)
async def report_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("💰 Укажи сумму к оплате (только цифры):")
    await state.set_state(MonthlyReport.amount)

@router.message(MonthlyReport.amount)
async def report_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text)
        await state.update_data(amount=amount)
        
        # Проверяем есть ли банковские реквизиты
        user = db.get_user(message.from_user.id)
        if user and user['bank_details']:
            await message.answer(
                f"💳 Текущие банковские реквизиты:\n{user['bank_details']}\n\n"
                "Использовать их?",
                reply_markup=kb.InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Да", callback_data="use_existing_bank")],
                    [InlineKeyboardButton(text="✏️ Ввести новые", callback_data="enter_new_bank")]
                ])
            )
        else:
            await message.answer("💳 Введите банковские реквизиты для зачисления:")
            await state.set_state(MonthlyReport.bank_details)
    except ValueError:
        await message.answer("❌ Введите число")

@router.callback_query(F.data == "use_existing_bank")
async def use_existing_bank(callback: CallbackQuery, state: FSMContext):
    user = db.get_user(callback.from_user.id)
    await state.update_data(bank_details=user['bank_details'])
    await show_report_confirm(callback.message, state)

@router.callback_query(F.data == "enter_new_bank")
async def enter_new_bank(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("💳 Введите банковские реквизиты:")
    await state.set_state(MonthlyReport.bank_details)

@router.message(MonthlyReport.bank_details)
async def report_bank_details(message: Message, state: FSMContext):
    await state.update_data(bank_details=message.text)
    await show_report_confirm(message, state)

async def show_report_confirm(message: Message, state: FSMContext):
    data = await state.get_data()
    text = f"""
📋 Проверьте отчет:

📝 Описание работ:
{data['description']}

💰 Сумма: {data['amount']} руб.

💳 Реквизиты:
{data['bank_details']}

Всё верно?
    """
    await message.answer(
        text,
        reply_markup=kb.InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Отправить", callback_data="send_report")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
        ])
    )
    await state.set_state(MonthlyReport.confirm)

@router.callback_query(MonthlyReport.confirm, F.data == "send_report")
async def send_report(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    
    # Сохраняем отчет
    report_id = db.add_report(
        user_id=callback.from_user.id,
        month=data['report_month'],
        description=data['description'],
        amount=data['amount'],
        bank_details=data['bank_details']
    )
    
    # Уведомляем руководителя
    user = db.get_user(callback.from_user.id)
    if user['department'] in MANAGERS:
        manager_id = [uid for uid, dept in MANAGERS.items() if dept == user['department']][0]
        await callback.bot.send_message(
            manager_id,
            f"📊 Новый отчет от {user['full_name']}\n"
            f"Сумма: {data['amount']} руб.\n"
            f"Описание: {data['description'][:100]}..."
        )
    
    await callback.message.edit_text("✅ Отчет отправлен руководителю на проверку!")
    await state.clear()

# Банковские реквизиты
@router.message(F.text == "💳 Банковские реквизиты")
async def bank_details_menu(message: Message):
    if not await check_active_user(message):
        return
    
    user = db.get_user(message.from_user.id)
    if user and user['bank_details']:
        text = f"💳 Ваши реквизиты:\n{user['bank_details']}"
    else:
        text = "💳 У вас еще нет сохраненных реквизитов"
    
    await message.answer(text, reply_markup=kb.bank_details_keyboard())

@router.callback_query(F.data == "fill_bank_details")
async def fill_bank_details(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите банковские реквизиты:")
    await state.set_state(BankDetails.details)

@router.message(BankDetails.details)
async def save_bank_details(message: Message, state: FSMContext):
    db.update_user(message.from_user.id, bank_details=message.text)
    await message.answer("✅ Реквизиты сохранены!")
    await state.clear()

# Уведомление об изменениях
@router.message(F.text == "✏️ Уведомить об изменениях")
async def change_notification(message: Message):
    if not await check_active_user(message):
        return
    
    await message.answer(
        "Выберите тип изменений:",
        reply_markup=kb.change_type_keyboard()
    )

@router.callback_query(F.data == "change_tax_type")
async def change_tax_type(callback: CallbackQuery):
    await callback.message.answer(
        "Выберите новый тип налогообложения:",
        reply_markup=kb.tax_type_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data == "change_last_name")
async def change_last_name(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите новую фамилию:")
    await state.set_state("waiting_new_lastname")

# Мои документы
@router.message(F.text == "📁 Мои документы")
async def my_documents(message: Message):
    if not await check_active_user(message):
        return
    
    documents = db.get_user_documents(message.from_user.id)
    if not documents:
        await message.answer("📁 У вас пока нет подписанных документов")
        return
    
    text = "📁 Ваши документы:\n\n"
    for doc in documents:
        month = doc['month'].strftime("%B %Y") if doc['month'] else "НДА"
        text += f"📄 {month} - {doc['doc_type']} - {doc['status']}\n"
    
    await message.answer(text)

# ----- ЗАЯВКИ НА ОПЛАТУ -----

# Создание счёта на оплату
@router.message(F.text == "💰 Создать счёт на оплату")
async def create_payment_request_start(message: Message, state: FSMContext):
    if not await check_active_user(message):
        return
    
    await message.answer("💰 Создание заявки на оплату\n\n"
                        "Введите сумму (только число, например: 15000):")
    await state.set_state(PaymentRequest.amount)

@router.message(PaymentRequest.amount)
async def payment_request_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(',', '.'))
        if amount <= 0:
            await message.answer("❌ Сумма должна быть больше 0")
            return
        await state.update_data(amount=amount)
        await message.answer("📝 Введите назначение платежа:")
        await state.set_state(PaymentRequest.payment_purpose)
    except ValueError:
        await message.answer("❌ Введите число без пробелов и запятых")

@router.message(PaymentRequest.payment_purpose)
async def payment_request_purpose(message: Message, state: FSMContext):
    await state.update_data(payment_purpose=message.text)
    await message.answer("🏢 Введите контрагента (название компании или ФИО):")
    await state.set_state(PaymentRequest.counterparty)

@router.message(PaymentRequest.counterparty)
async def payment_request_counterparty(message: Message, state: FSMContext):
    await state.update_data(counterparty=message.text)
    await message.answer("📁 Введите название проекта:")
    await state.set_state(PaymentRequest.project)

@router.message(PaymentRequest.project)
async def payment_request_project(message: Message, state: FSMContext):
    await state.update_data(project=message.text)
    await message.answer("📋 Введите номер договора подряда (если есть, или пропустите):")
    await state.set_state(PaymentRequest.contract_number)

@router.message(PaymentRequest.contract_number)
async def payment_request_contract(message: Message, state: FSMContext):
    contract_num = message.text if message.text.strip() else None
    await state.update_data(contract_number=contract_num)
    await message.answer("📎 Прикрепите файл счёта (PDF, фото или doc):")
    await state.set_state(PaymentRequest.invoice_file)

@router.message(PaymentRequest.invoice_file)
async def payment_request_invoice(message: Message, state: FSMContext, bot):
    if not message.document:
        await message.answer("❌ Пожалуйста, прикрепите файл")
        return
    
    # Скачиваем файл
    file = await bot.get_file(message.document.file_id)
    file_ext = message.document.file_name.split('.')[-1] if '.' in message.document.file_name else 'pdf'
    file_path = f"downloads/payment_requests/{message.from_user.id}_{message.document.file_name}"
    os.makedirs("downloads/payment_requests", exist_ok=True)
    await bot.download_file(file.file_path, file_path)
    
    await state.update_data(invoice_file_path=file_path)
    
    # Показываем подтверждение
    data = await state.get_data()
    text = f"""
💰 Проверьте заявку на оплату:

💵 Сумма: {data['amount']} руб.
📝 Назначение: {data['payment_purpose']}
🏢 Контрагент: {data['counterparty']}
📁 Проект: {data['project']}
📋 Договор: {data['contract_number'] or 'Не указан'}
📎 Счёт: {message.document.file_name}
    """
    
    await message.answer(text)
    
    # Создаём заявку
    request_id = db.add_payment_request(
        user_id=message.from_user.id,
        amount=data['amount'],
        payment_purpose=data['payment_purpose'],
        counterparty=data['counterparty'],
        project=data['project'],
        contract_number=data['contract_number']
    )
    
    # Сохраняем файл счёта
    db.add_payment_request_document(request_id, 'invoice', file_path)
    
    await message.answer(
        "✅ Заявка создана!\n\nОтправить на согласование?",
        reply_markup=kb.payment_request_confirm_keyboard(request_id)
    )
    await state.set_state(PaymentRequest.confirm)

@router.callback_query(PaymentRequest.confirm, F.data.startswith("send_payment_request_"))
async def send_payment_request(callback: CallbackQuery, state: FSMContext):
    request_id = int(callback.data.replace("send_payment_request_", ""))
    
    # Получаем данные заявки
    request = db.get_payment_request(request_id)
    user = db.get_user(callback.from_user.id)
    
    # Уведомляем руководителя
    from config import MANAGERS
    if user['department'] in MANAGERS:
        manager_id = [uid for uid, dept in MANAGERS.items() if dept == user['department']]
        if manager_id:
            text = f"""
📋 Новая заявка на оплату #{request_id}

👤 Сотрудник: {user['full_name']}
🏢 Отдел: {user['department']}
💵 Сумма: {request['amount']} руб.
📝 Назначение: {request['payment_purpose']}
🏢 Контрагент: {request['counterparty']}
📁 Проект: {request['project']}
            """
            await callback.bot.send_message(
                manager_id[0],
                text,
                reply_markup=kb.manager_payment_review_keyboard(request_id)
            )
    
    await callback.message.edit_text(
        f"✅ Заявка #{request_id} отправлена на согласование!\n\n"
        "Статус: Ожидает проверки руководителем"
    )
    await state.clear()

# Мои заявки
@router.message(F.text == "📁 Мои заявки")
async def my_payment_requests(message: Message):
    if not await check_active_user(message):
        return
    
    requests = db.get_user_payment_requests(message.from_user.id)
    
    if not requests:
        await message.answer("📁 У вас пока нет заявок на оплату")
        return
    
    await message.answer("📁 Ваши заявки на оплату:",
                         reply_markup=kb.my_requests_keyboard(requests))

@router.callback_query(F.data.startswith("my_request_"))
async def view_my_request(callback: CallbackQuery):
    request_id = int(callback.data.replace("my_request_", ""))
    request = db.get_payment_request(request_id)
    
    if not request or request['user_id'] != callback.from_user.id:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    
    status_names = {
        'pending_manager': '⏳ Ожидает проверки',
        'pending_finance': '👀 На проверке у финансов',
        'approved': '✅ Одобрено',
        'rejected': '❌ Отклонено',
        'awaiting_payment': '💳 Ожидает оплаты',
        'paid': '💰 Оплачено',
        'documents_uploaded': '📎 Документы загружены',
        'closed': '🔒 Закрыто'
    }
    
    docs = db.get_payment_request_documents(request_id)
    docs_text = "\n".join([f"  - {d['doc_type']}" for d in docs]) or "  Нет документов"
    
    comment = request.get('manager_comment') or request.get('finance_comment')
    comment_text = f"\n📝 Комментарий: {comment}" if comment else ""
    
    text = f"""
💰 Заявка #{request_id}

Статус: {status_names.get(request['status'], request['status'])}
💵 Сумма: {request['amount']} руб.
📝 Назначение: {request['payment_purpose']}
🏢 Контрагент: {request['counterparty']}
📁 Проект: {request['project']}
📋 Договор: {request['contract_number'] or 'Не указан'}

📎 Документы:
{docs_text}
{comment_text}
    """
    
    await callback.message.edit_text(
        text,
        reply_markup=kb.request_documents_keyboard(request_id, request['status'])
    )

# Прикрепление акта
@router.callback_query(F.data.startswith("upload_act_"))
async def upload_act(callback: CallbackQuery, state: FSMContext):
    request_id = int(callback.data.replace("upload_act_", ""))
    await state.update_data(upload_request_id=request_id, upload_type='act')
    await callback.message.answer("📎 Прикрепите подписанный акт:")
    await state.set_state(PaymentRequestUpload.act)

# Прикрепление договора
@router.callback_query(F.data.startswith("upload_contract_"))
async def upload_contract(callback: CallbackQuery, state: FSMContext):
    request_id = int(callback.data.replace("upload_contract_", ""))
    await state.update_data(upload_request_id=request_id, upload_type='contract')
    await callback.message.answer("📑 Прикрепите подписанный договор:")
    await state.set_state(PaymentRequestUpload.contract)

# Прикрепление чека
@router.callback_query(F.data.startswith("upload_check_"))
async def upload_check(callback: CallbackQuery, state: FSMContext):
    request_id = int(callback.data.replace("upload_check_", ""))
    await state.update_data(upload_request_id=request_id, upload_type='check')
    await callback.message.answer("🧾 Прикрепите чек:")
    await state.set_state(PaymentRequestUpload.check)

@router.message(PaymentRequestUpload.act)
async def save_act(message: Message, state: FSMContext, bot):
    if not message.document:
        await message.answer("❌ Пожалуйста, прикрепите файл акта")
        return
    
    data = await state.get_data()
    request_id = data['upload_request_id']
    
    file = await bot.get_file(message.document.file_id)
    file_path = f"downloads/payment_requests/{message.from_user.id}_act_{message.document.file_name}"
    await bot.download_file(file.file_path, file_path)
    
    db.add_payment_request_document(request_id, 'act', file_path)
    
    await message.answer("✅ Акт прикреплён!")
    await state.clear()

@router.message(PaymentRequestUpload.contract)
async def save_contract(message: Message, state: FSMContext, bot):
    if not message.document:
        await message.answer("❌ Пожалуйста, прикрепите файл договора")
        return
    
    data = await state.get_data()
    request_id = data['upload_request_id']
    
    file = await bot.get_file(message.document.file_id)
    file_path = f"downloads/payment_requests/{message.from_user.id}_contract_{message.document.file_name}"
    await bot.download_file(file.file_path, file_path)
    
    db.add_payment_request_document(request_id, 'contract', file_path)
    
    await message.answer("✅ Договор прикреплён!")
    await state.clear()

@router.message(PaymentRequestUpload.check)
async def save_check(message: Message, state: FSMContext, bot):
    if not message.document:
        await message.answer("❌ Пожалуйста, прикрепите чек")
        return
    
    data = await state.get_data()
    request_id = data['upload_request_id']
    
    file = await bot.get_file(message.document.file_id)
    file_path = f"downloads/payment_requests/{message.from_user.id}_check_{message.document.file_name}"
    await bot.download_file(file.file_path, file_path)
    
    db.add_payment_request_document(request_id, 'check', file_path)
    
    # Проверяем какие документы загружены и обновляем статус
    request = db.get_payment_request(request_id)
    docs = db.get_payment_request_documents(request_id)
    doc_types = [d['doc_type'] for d in docs]
    
    # Если все нужные документы загружены - меняем статус на "Документы загружены"
    if request['status'] == 'paid':
        # Проверяем есть ли акт и чек (основные документы)
        if 'act' in doc_types and 'check' in doc_types:
            db.update_payment_request_status(request_id, 'documents_uploaded')
            await message.answer(
                "✅ Чек прикреплён!\n\n"
                "📎 Статус изменён: Документы загружены"
            )
        else:
            await message.answer(
                "✅ Чек прикреплён!\n\n"
                "Пожалуйста, убедите что загружены:\n"
                "- Подписанный акт\n"
                "- Чек\n\n"
                "Когда все документы будут загружены, статус изменится на 'Документы загружены'"
            )
    else:
        await message.answer("✅ Чек прикреплён!")
    
    await state.clear()

# Кнопка для закрытия заявки (когда всё готово)
@router.callback_query(F.data == "close_request")
async def close_request(callback: CallbackQuery):
    request_id = int(callback.data.replace("close_request_", ""))
    request = db.get_payment_request(request_id)
    
    if request['user_id'] != callback.from_user.id:
        await callback.answer("Это не ваша заявка", show_alert=True)
        return
    
    # Проверяем что все документы на месте
    docs = db.get_payment_request_documents(request_id)
    doc_types = [d['doc_type'] for d in docs]
    
    if 'act' not in doc_types or 'check' not in doc_types:
        await callback.message.answer(
            "❌ Нельзя закрыть заявку. Загрузите:\n"
            "- Подписанный акт\n"
            "- Чек"
        )
        return
    
    db.update_payment_request_status(request_id, 'closed', callback.from_user.id, 'Заявка закрыта сотрудником')
    
    await callback.message.edit_text(
        callback.message.text + "\n\n✅ Заявка закрыта!"
    )