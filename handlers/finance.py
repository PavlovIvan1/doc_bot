from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.types import InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from database import Database
import keyboard as kb
from handlers.states import FinanceActions
from config import FINANCE_DIRECTOR_ID, ACCOUNTANT_ID, LAWYER_ID
from config import is_whitelisted
import os

router = Router()
db = Database()

async def check_finance(message: Message):
    """Проверка доступа к фин отделу"""
    if not is_whitelisted(message.from_user.id):
        await message.answer("⛔ Доступ к боту ограничен. Обратитесь к администратору.")
        return False

    if message.from_user.id not in [FINANCE_DIRECTOR_ID, ACCOUNTANT_ID]:
        await message.answer("❌ У вас нет доступа к этому разделу")
        return False
    return True

@router.message(F.text == "💳 Платежные поручения")
async def payment_orders(message: Message):
    if not await check_finance(message):
        return
    
    # Для бухгалтера (Аня)
    if message.from_user.id == ACCOUNTANT_ID:
        cursor = db.connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT wr.*, u.full_name, u.bank_details 
            FROM work_reports wr
            JOIN users u ON wr.user_id = u.user_id
            WHERE wr.status = 'sent_to_lawyer'
        """)
        reports = cursor.fetchall()
        
        if not reports:
            await message.answer("✅ Нет новых запросов на формирование платежек")
            return
        
        for report in reports:
            text = f"""
💳 Сформируйте платежное поручение:

Получатель: {report['full_name']}
Сумма: {report['amount']} руб.
Назначение: Оплата услуг по договору
Реквизиты: {report['bank_details']}
            """
            await message.answer(
                text,
                reply_markup=kb.InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Платежка сформирована", 
                                        callback_data=f"payment_done_{report['id']}")]
                ])
            )

@router.callback_query(F.data.startswith("payment_done_"))
async def payment_done(callback: CallbackQuery):
    report_id = int(callback.data.replace("payment_done_", ""))
    
    # Обновляем статус
    cursor = db.connection.cursor()
    cursor.execute(
        "UPDATE work_reports SET status = 'payment_order_created' WHERE id = %s",
        (report_id,)
    )
    db.connection.commit()
    
    # Уведомляем финдиректора
    await callback.bot.send_message(
        FINANCE_DIRECTOR_ID,
        f"✅ Платежное поручение по отчету #{report_id} готово к подписи"
    )
    
    await callback.message.edit_text(callback.message.text + "\n\n✅ Передано финдиректору")

@router.message(F.text == "✅ Подтвердить оплату")
async def confirm_payment(message: Message):
    if not await check_finance(message):
        return
    
    # Для финдиректора (Елена)
    if message.from_user.id == FINANCE_DIRECTOR_ID:
        cursor = db.connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT wr.*, u.full_name 
            FROM work_reports wr
            JOIN users u ON wr.user_id = u.user_id
            WHERE wr.status = 'payment_order_created'
        """)
        reports = cursor.fetchall()
        
        if not reports:
            await message.answer("✅ Нет платежей на подпись")
            return
        
        for report in reports:
            text = f"""
✅ Подтвердите оплату:

Получатель: {report['full_name']}
Сумма: {report['amount']} руб.
            """
            await message.answer(
                text,
                reply_markup=kb.InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="💰 Оплачено", 
                                        callback_data=f"paid_{report['id']}")]
                ])
            )

@router.callback_query(F.data.startswith("paid_"))
async def mark_paid(callback: CallbackQuery):
    report_id = int(callback.data.replace("paid_", ""))
    
    # Получаем данные отчета
    cursor = db.connection.cursor(dictionary=True)
    cursor.execute("SELECT * FROM work_reports WHERE id = %s", (report_id,))
    report = cursor.fetchone()
    
    # Обновляем статус
    cursor.execute(
        "UPDATE work_reports SET status = 'paid' WHERE id = %s",
        (report_id,)
    )
    db.connection.commit()
    
    # Уведомления
    # Сотруднику
    await callback.bot.send_message(
        report['user_id'],
        f"✅ Счёт за период оплачен!\n\n"
        f"Сумма: {report['amount']} руб."
    )
    
    # Проверяем тип налогообложения
    user = db.get_user(report['user_id'])
    if user['tax_type'] in ['self_employed_npd', 'ip_npd']:
        await callback.bot.send_message(
            report['user_id'],
            "🧾 Ожидаю от тебя чек из «Мой налог». Пришли чек в течение 5 дней.\n"
            "ВАЖНО: дата чека = дате поступления денежных средств на счет"
        )
    
    # Юристу
    from config import LAWYER_ID
    await callback.bot.send_message(
        LAWYER_ID,
        f"💰 Счет #{report_id} оплачен"
    )
    
    await callback.message.edit_text(callback.message.text + "\n\n✅ Оплата проведена")

# ----- НОВЫЕ ЗАЯВКИ НА ОПЛАТУ -----

@router.message(F.text == "💰 Заявки на оплату")
async def finance_payment_requests(message: Message):
    if not await check_finance(message):
        return
    
    requests = db.get_pending_payment_requests_for_finance()
    
    if not requests:
        await message.answer("✅ Нет заявок на оплату")
        return
    
    for req in requests:
        text = f"""
💰 Заявка #{req['id']}

👤 Сотрудник: {req['full_name']}
🏢 Отдел: {req['department']}
💵 Сумма: {req['amount']} руб.
📝 Назначение: {req['payment_purpose']}
🏢 Контрагент: {req['counterparty']}
📁 Проект: {req['project']}
📋 Статус: {req['status']}
        """
        await message.answer(
            text,
            reply_markup=kb.finance_review_keyboard(req['id'])
        )

@router.callback_query(F.data.startswith("finance_approve_"))
async def finance_approve_payment(callback: CallbackQuery):
    request_id = int(callback.data.replace("finance_approve_", ""))
    
    # Обновляем статус
    db.update_payment_request_status(request_id, 'awaiting_payment', callback.from_user.id)
    
    # Уведомляем сотрудника
    request = db.get_payment_request(request_id)
    await callback.bot.send_message(
        request['user_id'],
        f"✅ Ваша заявка #{request_id} одобрена финансовым отделом!\n\n"
        "Статус: Ожидает оплату."
    )
    
    # Уведомляем бухгалтера
    await callback.bot.send_message(
        ACCOUNTANT_ID,
        f"💰 Заявка #{request_id} готова к оплате\n\n"
        f"Сумма: {request['amount']} руб.\n"
        f"Контрагент: {request['counterparty']}\n"
        f"Проект: {request['project']}",
        reply_markup=kb.accountant_payment_keyboard(request_id)
    )
    
    await callback.message.edit_text(callback.message.text + "\n\n✅ Заявка передана на оплату!")

@router.callback_query(F.data.startswith("finance_reject_"))
async def finance_reject_payment(callback: CallbackQuery, state: FSMContext):
    request_id = int(callback.data.replace("finance_reject_", ""))
    await state.update_data(finance_reject_id=request_id)
    
    await callback.message.answer("❌ Напишите причину возврата:")
    await state.set_state(FinanceActions.reject_reason)

@router.message(FinanceActions.reject_reason)
async def finance_reject_reason(message: Message, state: FSMContext):
    data = await state.get_data()
    request_id = data['finance_reject_id']
    
    # Обновляем статус
    db.update_payment_request_status(
        request_id, 'rejected', message.from_user.id, message.text
    )
    
    # Уведомляем сотрудника
    request = db.get_payment_request(request_id)
    await message.bot.send_message(
        request['user_id'],
        f"❌ Ваша заявка #{request_id} возвращена на доработку\n\n"
        f"Причина: {message.text}"
    )
    
    await message.answer("✅ Заявка возвращена, сотрудник уведомлён")
    await state.clear()

# Заявки в ожидании оплаты (для бухгалтера)
@router.message(F.text == "💳 Заявки в ожидании оплаты")
async def awaiting_payment_requests(message: Message):
    if not await check_finance(message):
        return
    
    requests = db.get_payment_requests_for_accountant()
    
    if not requests:
        await message.answer("✅ Нет заявок в ожидании оплаты")
        return
    
    for req in requests:
        text = f"""
💳 Заявка #{req['id']}

👤 Получатель: {req['full_name']}
💵 Сумма: {req['amount']} руб.
📁 Проект: {req['project']}
💳 Реквизиты: {req.get('bank_details', 'Нет реквизитов')}
        """
        await message.answer(
            text,
            reply_markup=kb.accountant_payment_keyboard(req['id'])
        )

@router.callback_query(F.data.startswith("accountant_paid_"))
async def accountant_mark_paid(callback: CallbackQuery):
    request_id = int(callback.data.replace("accountant_paid_", ""))
    
    # Обновляем статус
    db.update_payment_request_status(request_id, 'paid', callback.from_user.id)
    
    # Уведомляем сотрудника
    request = db.get_payment_request(request_id)
    
    # Создаём клавиатуру с кнопками для загрузки документов
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    doc_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧾 Прикрепить чек", callback_data=f"upload_check_{request_id}")]
    ])
    
    await callback.bot.send_message(
        request['user_id'],
        f"✅ Заявка #{request_id} оплачена!\n\n"
        f"Сумма: {request['amount']} руб.\n\n"
        "🧾 Пожалуйста, прикрепите чек из «Мой налог» (для самозанятых).",
        reply_markup=doc_keyboard
    )
    
    await callback.message.edit_text(callback.message.text + "\n\n✅ Оплата подтверждена!")
    await callback.answer("✅ Отмечено как оплачено")


@router.callback_query(F.data.startswith("accountant_upload_proof_"))
async def accountant_upload_proof(callback: CallbackQuery, state: FSMContext):
    request_id = int(callback.data.replace("accountant_upload_proof_", ""))
    await state.update_data(accountant_proof_request_id=request_id)
    await callback.message.answer("📎 Прикрепите платёжное поручение (файл):")
    await state.set_state(FinanceActions.accountant_upload_proof_file)
    await callback.answer()


@router.message(FinanceActions.accountant_upload_proof_file)
async def accountant_upload_proof_file(message: Message, state: FSMContext, bot):
    if not message.document:
        await message.answer("❌ Пожалуйста, прикрепите файл платёжного поручения")
        return

    data = await state.get_data()
    request_id = data['accountant_proof_request_id']

    file = await bot.get_file(message.document.file_id)
    os.makedirs("downloads/payment_requests", exist_ok=True)
    file_path = f"downloads/payment_requests/payment_proof_{request_id}_{message.document.file_name}"
    await bot.download_file(file.file_path, file_path)

    db.add_payment_request_document(request_id, 'payment_proof', file_path)
    db.update_payment_request_status(request_id, 'awaiting_payment', message.from_user.id, 'Платёжное поручение загружено')

    await message.answer("✅ Платёжное поручение прикреплено. Статус заявки: Ожидает оплаты.")
    await state.clear()

# Связаться с сотрудником
@router.message(F.text == "👤 Связаться с сотрудником")
async def contact_employee(message: Message, state: FSMContext):
    if not await check_finance(message):
        return
    
    # Получаем список активных сотрудников
    cursor = db.connection.cursor(dictionary=True)
    cursor.execute("SELECT user_id, full_name FROM users WHERE registration_status = 'active'")
    users = cursor.fetchall()
    
    if not users:
        await message.answer("Нет активных сотрудников")
        return
    
    builder = kb.InlineKeyboardBuilder()
    for user in users:
        builder.add(InlineKeyboardButton(
            text=user['full_name'],
            callback_data=f"finance_contact_{user['user_id']}"
        ))
    builder.adjust(1)
    
    await message.answer("Выберите сотрудника:", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("finance_contact_"))
async def finance_contact_user(callback: CallbackQuery, state: FSMContext):
    user_id = int(callback.data.replace("finance_contact_", ""))
    await state.update_data(contact_user_id=user_id)
    
    await callback.message.answer("Введите сообщение для сотрудника:")
    await state.set_state(FinanceActions.send_message)

@router.message(FinanceActions.send_message)
async def finance_send_to_user(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = data['contact_user_id']
    
    await message.bot.send_message(
        user_id,
        f"📢 Сообщение от финансового отдела:\n\n{message.text}"
    )
    
    await message.answer("✅ Сообщение отправлено!")
    await state.clear()
