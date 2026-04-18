from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, FSInputFile
from aiogram.fsm.context import FSMContext
from datetime import datetime
from aiogram.utils.keyboard import InlineKeyboardButton
import os

from handlers.states import MonthlyReport, BankDetails, DocumentUpload, PaymentRequest, PaymentRequestUpload, NDAProcess
from database import Database
import keyboard as kb
from config import MANAGERS
from config import is_whitelisted

router = Router()
db = Database()

REQUIRED_CLOSING_DOCS = ("act", "contract", "check")
DOC_LABELS = {
    "act": "Подписанный акт",
    "contract": "Подписанный договор",
    "check": "Чек",
}
UPLOAD_ALLOWED_STATUSES = {
    "act": {"pending_manager", "pending_finance", "approved", "awaiting_payment", "paid", "documents_uploaded"},
    "contract": {"pending_manager", "pending_finance", "approved", "awaiting_payment", "paid", "documents_uploaded"},
    "check": {"paid", "documents_uploaded"},
}

# Создаём директории для загрузок если не существуют
os.makedirs("downloads/payment_requests", exist_ok=True)
os.makedirs("downloads/nda", exist_ok=True)

# Проверка доступа
async def check_active_user(message: Message):
    if not is_whitelisted(message.from_user.id):
        await message.answer("⛔ Доступ к боту ограничен. Обратитесь к администратору.")
        return False

    user = db.get_user(message.from_user.id)
    if not user or user['registration_status'] != 'active':
        await message.answer("❌ Доступ запрещен. Пройдите регистрацию.")
        return False
    return True


def get_missing_closing_docs(doc_types):
    return [doc for doc in REQUIRED_CLOSING_DOCS if doc not in doc_types]


def format_missing_docs(missing_docs):
    return "\n".join(f"- {DOC_LABELS.get(doc, doc)}" for doc in missing_docs)


def evaluate_closing_docs_status(request_id):
    request = db.get_payment_request(request_id)
    if not request:
        return None, [], False

    docs = db.get_payment_request_documents(request_id)
    doc_types = {d['doc_type'] for d in docs}
    missing_docs = get_missing_closing_docs(doc_types)
    status_changed = False

    if request['status'] in ('paid', 'documents_uploaded') and not missing_docs and request['status'] != 'documents_uploaded':
        db.update_payment_request_status(request_id, 'documents_uploaded')
        status_changed = True
        request['status'] = 'documents_uploaded'

    return request, missing_docs, status_changed


def build_upload_result_message(doc_type, request, missing_docs, status_changed):
    success_text = {
        'act': '✅ Акт прикреплён!',
        'contract': '✅ Договор прикреплён!',
        'check': '✅ Чек прикреплён!',
    }[doc_type]

    if not request:
        return success_text

    if request['status'] in ('paid', 'documents_uploaded'):
        if not missing_docs:
            if status_changed:
                return success_text + "\n\n📎 Статус изменён: Документы загружены"
            return success_text + "\n\n📎 Все закрывающие документы уже загружены"
        return success_text + "\n\nОсталось загрузить:\n" + format_missing_docs(missing_docs)

    return success_text


async def show_upload_requests_menu(message: Message, doc_type: str):
    if not await check_active_user(message):
        return

    requests = db.get_user_payment_requests(message.from_user.id)
    allowed_statuses = UPLOAD_ALLOWED_STATUSES[doc_type]
    filtered_requests = [req for req in requests if req['status'] in allowed_statuses]

    if not filtered_requests:
        if doc_type == 'check':
            await message.answer("❌ Нет заявок для загрузки чека. Чек доступен после статуса 'Оплачено'.")
        else:
            await message.answer("❌ Нет заявок, куда сейчас можно загрузить этот документ.")
        return

    title = {
        'act': '📎 Выберите заявку для загрузки акта:',
        'contract': '📑 Выберите заявку для загрузки договора:',
        'check': '🧾 Выберите заявку для загрузки чека:',
    }[doc_type]
    await message.answer(
        title,
        reply_markup=kb.payment_request_list_keyboard(filtered_requests, prefix=f"upload_{doc_type}")
    )

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
    print(f"DEBUG: user department = {user['department']}")
    print(f"DEBUG: MANAGERS = {MANAGERS}")
    
    manager_id = None
    # Проверяем, есть ли менеджер для этого отдела
    for uid, depts in MANAGERS.items():
        if user['department'] in depts:
            manager_id = uid
            break
    
    if not manager_id:
        # Используем MY_ID как запасной вариант
        from config import MY_ID
        manager_id = MY_ID
        print(f"DEBUG: Using MY_ID as fallback: {manager_id}")
    
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
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пропустить", callback_data="skip_contract")]
    ])
    await message.answer("📋 Введите номер договора подряда (если есть, или пропустите):", reply_markup=keyboard)
    await state.set_state(PaymentRequest.contract_number)

@router.message(PaymentRequest.contract_number)
async def payment_request_contract(message: Message, state: FSMContext):
    contract_num = message.text.strip() if message.text and message.text.strip() else None
    await state.update_data(contract_number=contract_num)
    await message.answer("📎 Прикрепите файл счёта (PDF, фото или doc):")
    await state.set_state(PaymentRequest.invoice_file)

@router.callback_query(F.data == "skip_contract")
async def skip_contract(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(contract_number=None)
    await callback.message.answer("📎 Прикрепите файл счёта (PDF, фото или doc):")
    await state.set_state(PaymentRequest.invoice_file)

@router.message(PaymentRequest.invoice_file)
async def payment_request_invoice(message: Message, state: FSMContext, bot):
    if not message.document and not message.photo:
        await message.answer("❌ Пожалуйста, прикрепите счёт (файл или фото)")
        return

    # Скачиваем файл/фото
    if message.document:
        file_id = message.document.file_id
        original_name = message.document.file_name
    else:
        file_id = message.photo[-1].file_id
        original_name = f"invoice_{message.from_user.id}.jpg"

    file = await bot.get_file(file_id)
    file_path = f"downloads/payment_requests/{message.from_user.id}_{original_name}"
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
 📎 Счёт: {original_name}
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
    from config import MANAGERS, MY_ID
    print(f"DEBUG: user department = {user['department']}")
    print(f"DEBUG: MANAGERS = {MANAGERS}")
    print(f"DEBUG: MY_ID = {MY_ID}")
    
    manager_id = None
    # Проверяем, есть ли менеджер для этого отдела
    for uid, depts in MANAGERS.items():
        print(f"DEBUG: Checking manager {uid} with depts {depts}")
        if user['department'] in depts:
            manager_id = uid
            print(f"DEBUG: Found manager {manager_id} for department {user['department']}")
            break
    
    # Если менеджер не найден, используем MY_ID как запасной вариант
    if not manager_id:
        manager_id = MY_ID
        print(f"DEBUG: Using MY_ID as fallback: {manager_id}")
    
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
        manager_id,
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


@router.message(F.text == "📎 Прикрепить акт")
async def upload_act_from_menu(message: Message):
    await show_upload_requests_menu(message, 'act')


@router.message(F.text == "📑 Прикрепить договор")
async def upload_contract_from_menu(message: Message):
    await show_upload_requests_menu(message, 'contract')


@router.message(F.text == "🧾 Загрузить чек")
async def upload_check_from_menu(message: Message):
    await show_upload_requests_menu(message, 'check')

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

    history = db.get_payment_request_history(request_id)
    history_text = "\n".join([
        f"  - {h['changed_at'].strftime('%d.%m.%Y %H:%M') if h.get('changed_at') else ''}: {status_names.get(h['new_status'], h['new_status'])}"
        + (f" ({h['comment']})" if h.get('comment') else "")
        for h in history
    ]) or "  История пока пуста"
    
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

🕘 История статусов:
{history_text}
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

    request = db.get_payment_request(request_id)
    if not request or request['user_id'] != callback.from_user.id:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    if request['status'] not in UPLOAD_ALLOWED_STATUSES['act']:
        await callback.answer("Сейчас нельзя загрузить акт для этой заявки", show_alert=True)
        return

    await state.update_data(upload_request_id=request_id, upload_type='act')
    await callback.message.answer("📎 Прикрепите подписанный акт:")
    await state.set_state(PaymentRequestUpload.act)
    await callback.answer()

# Прикрепление договора
@router.callback_query(F.data.startswith("upload_contract_"))
async def upload_contract(callback: CallbackQuery, state: FSMContext):
    request_id = int(callback.data.replace("upload_contract_", ""))

    request = db.get_payment_request(request_id)
    if not request or request['user_id'] != callback.from_user.id:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    if request['status'] not in UPLOAD_ALLOWED_STATUSES['contract']:
        await callback.answer("Сейчас нельзя загрузить договор для этой заявки", show_alert=True)
        return

    await state.update_data(upload_request_id=request_id, upload_type='contract')
    await callback.message.answer("📑 Прикрепите подписанный договор:")
    await state.set_state(PaymentRequestUpload.contract)
    await callback.answer()

# Прикрепление чека
@router.callback_query(F.data.startswith("upload_check_"))
async def upload_check(callback: CallbackQuery, state: FSMContext):
    request_id = int(callback.data.replace("upload_check_", ""))

    request = db.get_payment_request(request_id)
    if not request or request['user_id'] != callback.from_user.id:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    if request['status'] not in UPLOAD_ALLOWED_STATUSES['check']:
        await callback.answer("Чек можно загрузить только после оплаты", show_alert=True)
        return

    await state.update_data(upload_request_id=request_id, upload_type='check')
    await callback.message.answer("🧾 Прикрепите чек:")
    await state.set_state(PaymentRequestUpload.check)
    await callback.answer()

@router.message(PaymentRequestUpload.act)
async def save_act(message: Message, state: FSMContext, bot):
    if not message.document:
        await message.answer("❌ Пожалуйста, прикрепите файл акта")
        return
    
    data = await state.get_data()
    request_id = data.get('upload_request_id')
    if not request_id:
        await message.answer("❌ Сессия загрузки не найдена. Нажмите кнопку 'Прикрепить акт' еще раз.")
        await state.clear()
        return
    
    file = await bot.get_file(message.document.file_id)
    file_path = f"downloads/payment_requests/{message.from_user.id}_act_{message.document.file_name}"
    await bot.download_file(file.file_path, file_path)
    
    db.add_payment_request_document(request_id, 'act', file_path)

    request, missing_docs, status_changed = evaluate_closing_docs_status(request_id)
    await message.answer(build_upload_result_message('act', request, missing_docs, status_changed))
    await state.clear()

@router.message(PaymentRequestUpload.contract)
async def save_contract(message: Message, state: FSMContext, bot):
    if not message.document:
        await message.answer("❌ Пожалуйста, прикрепите файл договора")
        return
    
    data = await state.get_data()
    request_id = data.get('upload_request_id')
    if not request_id:
        await message.answer("❌ Сессия загрузки не найдена. Нажмите кнопку 'Прикрепить договор' еще раз.")
        await state.clear()
        return
    
    file = await bot.get_file(message.document.file_id)
    file_path = f"downloads/payment_requests/{message.from_user.id}_contract_{message.document.file_name}"
    await bot.download_file(file.file_path, file_path)
    
    db.add_payment_request_document(request_id, 'contract', file_path)

    request, missing_docs, status_changed = evaluate_closing_docs_status(request_id)
    await message.answer(build_upload_result_message('contract', request, missing_docs, status_changed))
    await state.clear()

@router.message(PaymentRequestUpload.check)
async def save_check(message: Message, state: FSMContext, bot):
    if not message.document:
        await message.answer("❌ Пожалуйста, прикрепите чек")
        return
    
    data = await state.get_data()
    request_id = data.get('upload_request_id')
    if not request_id:
        await message.answer("❌ Сессия загрузки не найдена. Нажмите кнопку 'Загрузить чек' еще раз.")
        await state.clear()
        return
    
    file = await bot.get_file(message.document.file_id)
    file_path = f"downloads/payment_requests/{message.from_user.id}_check_{message.document.file_name}"
    await bot.download_file(file.file_path, file_path)
    
    db.add_payment_request_document(request_id, 'check', file_path)

    request, missing_docs, status_changed = evaluate_closing_docs_status(request_id)
    await message.answer(build_upload_result_message('check', request, missing_docs, status_changed))
    
    await state.clear()

# Кнопка для закрытия заявки (когда всё готово)
@router.callback_query(F.data.startswith("close_request_"))
async def close_request(callback: CallbackQuery):
    request_id = int(callback.data.replace("close_request_", ""))
    request = db.get_payment_request(request_id)
    
    if request['user_id'] != callback.from_user.id:
        await callback.answer("Это не ваша заявка", show_alert=True)
        return
    
    # Проверяем что все документы на месте
    docs = db.get_payment_request_documents(request_id)
    doc_types = [d['doc_type'] for d in docs]
    
    if 'act' not in doc_types or 'contract' not in doc_types or 'check' not in doc_types:
        await callback.message.answer(
            "❌ Нельзя закрыть заявку. Загрузите:\n"
            "- Подписанный акт\n"
            "- Подписанный договор\n"
            "- Чек"
        )
        return
    
    db.update_payment_request_status(request_id, 'closed', callback.from_user.id, 'Заявка закрыта сотрудником')
    
    await callback.message.edit_text(
        callback.message.text + "\n\n✅ Заявка закрыта!"
    )


# ----- ОБРАБОТЧИКИ НДА -----

@router.callback_query(F.data == "upload_signed_nda")
async def upload_signed_nda(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Загрузить подписанный НДА'"""
    user = db.get_user(callback.from_user.id)
    if not user or user['nda_status'] not in ['sent', 'not_sent']:
        await callback.message.answer("❌ Нет активного NDA для подписания")
        await callback.answer()
        return
    
    await callback.message.answer("📎 Отправьте подписанный НДА:")
    await state.set_state(NDAProcess.signed_nda_upload)
    await callback.answer()


@router.message(NDAProcess.signed_nda_upload)
async def receive_signed_nda(message: Message, state: FSMContext, bot):
    """Получение подписанного NDA от пользователя"""
    if not message.document:
        await message.answer("❌ Пожалуйста, прикрепите файл NDA")
        return
    
    user_id = message.from_user.id
    
    # Скачиваем файл
    file = await bot.get_file(message.document.file_id)
    file_path = f"downloads/nda/signed_{user_id}_{message.document.file_name}"
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    await bot.download_file(file.file_path, file_path)
    
    # Сохраняем в БД
    db.add_document(user_id, 'nda', file_path, status='signed_by_user')
    
    # Обновляем статус
    db.update_user(user_id, nda_status='signed')
    
    await message.answer("✅ НДА загружен! Юрист проверит документ и подтвердит.")
    
    # Уведомляем юриста
    user = db.get_user(user_id)
    from config import LAWYER_ID
    await bot.send_document(
        LAWYER_ID,
        message.document.file_id,
        caption=(
            f"📄 Пользователь {user['full_name']} (ID: {user_id}) загрузил подписанный НДА.\n"
            f"Проверьте и подтвердите."
        ),
        reply_markup=kb.nda_review_keyboard(user_id)
    )
    
    await state.clear()


@router.callback_query(F.data == "ask_nda_extension")
async def ask_nda_extension(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Запросить продление'"""
    user = db.get_user(callback.from_user.id)
    if not user or user['nda_status'] not in ['sent', 'not_sent']:
        await callback.message.answer("❌ Нет активного запроса NDA")
        await callback.answer()
        return
    
    await callback.message.answer("📝 Напишите причину продления и желаемую дату:")
    await state.set_state(NDAProcess.nda_extension_request)
    await callback.answer()


@router.message(NDAProcess.nda_extension_request)
async def receive_nda_extension_request(message: Message, state: FSMContext, bot):
    """Получение запроса на продление NDA"""
    user = db.get_user(message.from_user.id)
    
    # Отправляем запрос юристу
    from config import LAWYER_ID
    await bot.send_message(
        LAWYER_ID,
        f"⏰ Запрос на продление NDA от {user['full_name']}:\n\n"
        f"Причина и желаемая дата: {message.text}"
    )
    
    await message.answer("✅ Запрос на продление отправлен юристу.")
    await state.clear()
