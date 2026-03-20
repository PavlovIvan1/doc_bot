from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.types import InlineKeyboardButton
from database import Database
import keyboard as kb
from config import FINANCE_DIRECTOR_ID, ACCOUNTANT_ID

router = Router()
db = Database()

async def check_finance(message: Message):
    """Проверка доступа к фин отделу"""
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