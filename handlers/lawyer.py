from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardButton
import asyncio

from handlers.states import LawyerActions
from database import Database
import keyboard as kb
from config import LAWYER_ID, FINANCE_DIRECTOR_ID

router = Router()
db = Database()

async def check_lawyer(message: Message):
    """Проверка, что пользователь - юрист"""
    if message.from_user.id != LAWYER_ID:
        await message.answer("❌ У вас нет доступа к этому разделу")
        return False
    return True

@router.message(F.text == "📝 Новые запросы на НДА")
async def new_nda_requests(message: Message):
    if not await check_lawyer(message):
        return
    
    users = db.get_pending_nda_requests()
    
    if not users:
        await message.answer("✅ Нет новых запросов на НДА")
        return
    
    for user in users:
        text = f"""
📝 Запрос на НДА от {user['full_name']}

📧 Email: {user['email']}
📞 Телефон: {user['phone']}
🏢 Отдел: {user['department']}
💰 Налогообложение: {user['tax_type']}
📅 Дата начала: {user['start_date']}

Паспортные данные:
{user['passport_data']}

Адрес:
{user['registration_address']}
        """
        
        await message.answer(
            text,
            reply_markup=kb.InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📎 Загрузить НДА", callback_data=f"upload_nda_{user['user_id']}")]
            ])
        )

@router.callback_query(F.data.startswith("upload_nda_"))
async def upload_nda(callback: CallbackQuery, state: FSMContext):
    user_id = int(callback.data.replace("upload_nda_", ""))
    await state.update_data(nda_user_id=user_id)
    
    await callback.message.answer("📎 Отправьте файл НДА для подписания:")
    await state.set_state(LawyerActions.nda_upload)

@router.message(LawyerActions.nda_upload)
async def save_nda(message: Message, state: FSMContext, bot):
    if not message.document:
        await message.answer("❌ Пожалуйста, прикрепите файл NDA")
        return
    
    data = await state.get_data()
    user_id = data['nda_user_id']
    
    # Сохраняем файл
    file = await bot.get_file(message.document.file_id)
    file_path = f"downloads/nda/{user_id}_{message.document.file_name}"
    await bot.download_file(file.file_path, file_path)
    
    # Обновляем статус пользователя
    db.update_user(user_id, nda_status='sent', registration_status='nda_pending')
    
    # Сохраняем документ в БД
    db.add_document(user_id, 'nda', file_path)
    
    # Отправляем сотруднику
    print(f"DEBUG: Sending NDA to user_id={user_id}")
    text = """
Коллега, тебе направлен НДА на подписание.
Важно: подпиши документ и направь файл с твоей подписью в течение 24 часов.
Без подписанного НДА доступ к рабочим чатам и задачам невозможен.
    """
    
    await bot.send_document(
        user_id,
        FSInputFile(file_path),
        caption=text,
        reply_markup=kb.nda_keyboard()
    )
    
    await message.answer(f"✅ НДА отправлен пользователю {user_id}")
    await state.clear()

@router.callback_query(F.data == "upload_signed_nda")
async def upload_signed_nda(callback: CallbackQuery, state: FSMContext):
    print(f"DEBUG: upload_signed_nda called by user {callback.from_user.id}")
    await callback.message.answer("📎 Отправьте подписанный НДА:")
    await state.set_state(LawyerActions.signed_nda_receive)

@router.message(LawyerActions.signed_nda_receive)
async def receive_signed_nda(message: Message, state: FSMContext, bot):
    print(f"DEBUG: receive_signed_nda called by user {message.from_user.id}")
    print(f"DEBUG: Current state = {await state.get_state()}")
    if not message.document:
        await message.answer("❌ Пожалуйста, прикрепите подписанный NDA")
        return
    
    user_id = message.from_user.id
    
    # Сохраняем подписанный НДА
    file = await bot.get_file(message.document.file_id)
    file_path = f"downloads/nda/signed_{user_id}_{message.document.file_name}"
    await bot.download_file(file.file_path, file_path)
    
    # Обновляем документ в БД
    db.add_document(user_id, 'nda', file_path, status='signed_by_user')
    
    # Уведомляем юриста
    print(f"DEBUG: LAWYER_ID = {LAWYER_ID}, user_id = {user_id}")
    if LAWYER_ID:
        try:
            # Отправляем документ юристу
            print(f"DEBUG: Trying to send document to lawyer...")
            await bot.send_document(
                LAWYER_ID,
                FSInputFile(file_path),
                caption=f"📄 Подрядчик {user_id} загрузил подписанный НДА. Проверьте документ.",
                reply_markup=kb.nda_review_keyboard(user_id)
            )
            print(f"DEBUG: Document sent successfully")
        except Exception as e:
            print(f"Не удалось уведомить юриста: {e}")
            # Пробуем просто отправить сообщение
            try:
                await bot.send_message(
                    LAWYER_ID,
                    f"📄 Подрядчик {user_id} загрузил подписанный НДА. Проверить документ.",
                    reply_markup=kb.nda_review_keyboard(user_id)
                )
            except Exception as e2:
                print(f"Не удалось отправить сообщение юристу: {e2}")
    
    await message.answer("✅ НДА отправлен на проверку юристу")
    await state.clear()

@router.callback_query(F.data.startswith("approve_nda_"))
async def approve_nda(callback: CallbackQuery):
    user_id = int(callback.data.replace("approve_nda_", ""))
    
    # Обновляем статус
    db.update_user(user_id, nda_status='signed', registration_status='active')
    
    # Получаем данные пользователя
    user = db.get_user(user_id)
    
    # Отправляем приветствие с ссылками
    text = f"""
НДА подписан ✅

Добро пожаловать в отдел {user['department']}

Теперь закрепи этот бот у себя и включи уведомления — это важно для ежемесячного расчета и подписания документов.

В конце каждого месяца необходимо:
1. Сдать факт выполненных работ 1 числа каждого месяца
2. Заполнить таблицу мотивации
3. Отправить отчет через кнопку «Сдать факт выполненных работ»

В течение 5-10 дней юрист пришлет договор и акт на подпись.
    """
    
    await callback.bot.send_message(
        user_id,
        text,
        reply_markup=kb.get_chat_links_keyboard(user['department'])
    )
    
    # Отправляем главное меню
    await callback.bot.send_message(
        user_id,
        "Главное меню:",
        reply_markup=kb.main_menu_keyboard()
    )
    
    await callback.message.edit_text("✅ НДА подтвержден, пользователь активирован")

@router.message(F.text == "💰 Запросы на оплату")
async def payment_requests(message: Message):
    if not await check_lawyer(message):
        return
    
    cursor = db.connection.cursor(dictionary=True)
    cursor.execute("""
        SELECT wr.*, u.full_name, u.department 
        FROM work_reports wr
        JOIN users u ON wr.user_id = u.user_id
        WHERE wr.status = 'approved_by_manager'
    """)
    reports = cursor.fetchall()
    
    if not reports:
        await message.answer("✅ Нет запросов на оплату")
        return
    
    for report in reports:
        text = f"""
💰 Запрос на оплату от {report['full_name']}
🏢 Отдел: {report['department']}
📝 Описание: {report['description']}
💵 Сумма: {report['amount']} руб.
💳 Реквизиты: {report['bank_details']}
        """
        await message.answer(
            text,
            reply_markup=kb.payment_request_keyboard(report['id'])
        )

@router.callback_query(F.data.startswith("pay_"))
async def process_payment(callback: CallbackQuery):
    report_id = int(callback.data.replace("pay_", ""))
    
    # Обновляем статус отчета
    db.update_report_status(report_id, 'sent_to_lawyer')
    
    # Уведомляем финдира
    await callback.bot.send_message(
        FINANCE_DIRECTOR_ID,
        f"💰 Новый запрос на оплату #{report_id}"
    )
    
    await callback.message.edit_text(callback.message.text + "\n\n✅ Передано на оплату")