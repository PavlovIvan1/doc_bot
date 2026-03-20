from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from datetime import datetime
from aiogram.utils.keyboard import InlineKeyboardButton

from handlers.states import MonthlyReport, BankDetails, DocumentUpload
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