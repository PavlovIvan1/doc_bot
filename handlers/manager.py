from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton

from handlers.states import ManagerActions
from database import Database
import keyboard as kb
from config import MANAGERS, DEPARTMENTS
from config import is_whitelisted

router = Router()
db = Database()

async def check_manager(message: Message):
    """Проверка, что пользователь - руководитель"""
    if not is_whitelisted(message.from_user.id):
        await message.answer("⛔ Доступ к боту ограничен. Обратитесь к администратору.")
        return False

    if message.from_user.id not in MANAGERS:
        await message.answer("❌ У вас нет доступа к этому разделу")
        return False
    return True

def get_manager_department(user_id):
    """Получить первый отдел менеджера"""
    if user_id in MANAGERS:
        depts = MANAGERS[user_id]
        if isinstance(depts, list):
            return depts[0] if depts else None
        return depts
    return None

@router.message(F.text == "👥 Выбрать отдел")
async def select_department(message: Message):
    if not await check_manager(message):
        return
    
    await message.answer(
        "Выберите отдел:",
        reply_markup=kb.departments_select_keyboard()
    )

@router.callback_query(F.data.startswith("select_dept_"))
async def department_selected(callback: CallbackQuery, state: FSMContext):
    department = callback.data.replace("select_dept_", "")
    await state.update_data(selected_department=department)
    
    await callback.message.edit_text(
        f"Выбран отдел: {department}\n\n"
        "Выберите действие:",
        reply_markup=kb.InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Отчеты на проверку", callback_data="manager_reports")],
            [InlineKeyboardButton(text="🔄 Изменить должность", callback_data="manager_change_position")],
            [InlineKeyboardButton(text="🚫 Уволить", callback_data="manager_fire")]
        ])
    )

@router.message(F.text == "📊 Отчёты на проверку")
async def reports_to_check(message: Message):
    if not await check_manager(message):
        return
    
    department = get_manager_department(message.from_user.id)
    if not department:
        await message.answer("❌ У вас не назначен отдел")
        return
    reports = db.get_pending_reports_by_department(department)
    
    if not reports:
        await message.answer("✅ Нет непроверенных отчетов")
        return
    
    for report in reports:
        text = f"""
👤 Сотрудник: {report['full_name']}
📝 Описание:
{report['description']}
💰 Сумма: {report['amount']} руб.
💳 Реквизиты: {report['bank_details']}
        """
        await message.answer(
            text,
            reply_markup=kb.report_review_keyboard(report['id'])
        )

@router.callback_query(F.data.startswith("approve_report_"))
async def approve_report(callback: CallbackQuery):
    report_id = int(callback.data.replace("approve_report_", ""))
    
    # Обновляем статус отчета
    db.update_report_status(report_id, 'approved_by_manager', manager_id=callback.from_user.id)
    
    # Получаем данные отчета
    cursor = db.connection.cursor(dictionary=True)
    cursor.execute("SELECT * FROM work_reports WHERE id = %s", (report_id,))
    report = cursor.fetchone()
    
    # Уведомляем юриста
    from config import LAWYER_ID
    await callback.bot.send_message(
        LAWYER_ID,
        f"✅ Подтвержден объем работ\n"
        f"Сотрудник ID: {report['user_id']}\n"
        f"Сумма: {report['amount']} руб.\n"
        f"Месяц: {report['report_month']}"
    )
    
    await callback.message.edit_text(callback.message.text + "\n\n✅ Отчет подтвержден!")

@router.callback_query(F.data.startswith("edit_report_"))
async def edit_report_request(callback: CallbackQuery, state: FSMContext):
    report_id = int(callback.data.replace("edit_report_", ""))
    await state.update_data(edit_report_id=report_id)
    
    await callback.message.answer("✏️ Напишите комментарий, что нужно исправить:")
    await state.set_state(ManagerActions.correction_comment)

@router.message(ManagerActions.correction_comment)
async def send_correction(message: Message, state: FSMContext):
    data = await state.get_data()
    report_id = data['edit_report_id']
    
    # Обновляем статус отчета
    db.update_report_status(report_id, 'rejected', message.text, message.from_user.id)
    
    # Получаем данные отчета
    cursor = db.connection.cursor(dictionary=True)
    cursor.execute("SELECT * FROM work_reports WHERE id = %s", (report_id,))
    report = cursor.fetchone()
    
    # Уведомляем сотрудника
    await message.bot.send_message(
        report['user_id'],
        f"❌ Ваш отчет требует корректировки:\n\n{message.text}"
    )
    
    await message.answer("✅ Комментарий отправлен сотруднику")
    await state.clear()

@router.callback_query(F.data == "manager_change_position")
async def change_position_employee_list(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    department = data.get('selected_department')
    
    employees = db.get_users_by_department(department)
    
    await callback.message.edit_text(
        "Выберите сотрудника для изменения должности:",
        reply_markup=kb.employee_list_keyboard(employees, "position")
    )

@router.callback_query(F.data.startswith("position_"))
async def change_position_employee(callback: CallbackQuery, state: FSMContext):
    user_id = int(callback.data.replace("position_", ""))
    await state.update_data(change_position_user_id=user_id)
    
    await callback.message.answer("Введите новую должность:")
    await state.set_state(ManagerActions.change_position)

@router.message(ManagerActions.change_position)
async def set_new_position(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = data['change_position_user_id']
    
    # Обновляем должность
    db.update_user(user_id, position=message.text)
    
    # Уведомляем сотрудника
    await message.bot.send_message(
        user_id,
        f"🔄 Ваша должность изменена на: {message.text}"
    )
    
    await message.answer("✅ Должность изменена")
    await state.clear()

# Увольнение сотрудника
@router.callback_query(F.data == "manager_fire")
async def fire_employee_list(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    department = data.get('selected_department')
    
    employees = db.get_users_by_department(department)
    
    await callback.message.edit_text(
        "Выберите сотрудника для увольнения:",
        reply_markup=kb.employee_list_keyboard(employees, "fire")
    )

@router.callback_query(F.data.startswith("fire_"))
async def fire_employee(callback: CallbackQuery):
    user_id = int(callback.data.replace("fire_", ""))
    
    # Обновляем статус
    db.update_user(user_id, registration_status='fired')
    
    # Уведомляем сотрудника
    await callback.bot.send_message(
        user_id,
        "❌ Вы были уволены. Доступ к боту заблокирован."
    )
    
    await callback.message.edit_text("✅ Сотрудник уволен")

# ----- ЗАЯВКИ НА ОПЛАТУ -----

@router.message(F.text == "💰 Заявки на оплату")
async def payment_requests_list(message: Message):
    if not await check_manager(message):
        return
    
    department = get_manager_department(message.from_user.id)
    if not department:
        await message.answer("❌ У вас не назначен отдел")
        return
    requests = db.get_pending_payment_requests_for_manager(department)
    
    if not requests:
        await message.answer("✅ Нет заявок на оплату")
        return
    
    for req in requests:
        text = f"""
💰 Заявка #{req['id']}

👤 Сотрудник: {req['full_name']}
💵 Сумма: {req['amount']} руб.
📝 Назначение: {req['payment_purpose']}
🏢 Контрагент: {req['counterparty']}
📁 Проект: {req['project']}
        """
        await message.answer(
            text,
            reply_markup=kb.manager_payment_review_keyboard(req['id'])
        )

@router.callback_query(F.data.startswith("manager_approve_"))
async def manager_approve_payment(callback: CallbackQuery):
    request_id = int(callback.data.replace("manager_approve_", ""))
    
    # Обновляем статус
    db.update_payment_request_status(request_id, 'pending_finance', callback.from_user.id)
    
    # Уведомляем сотрудника
    request = db.get_payment_request(request_id)
    await callback.bot.send_message(
        request['user_id'],
        f"✅ Ваша заявка #{request_id} одобрена руководителем!\n\n"
        "Передана на проверку финансовому отделу."
    )
    
    # Уведомляем финансовый отдел
    from config import FINANCE_DIRECTOR_ID
    await callback.bot.send_message(
        FINANCE_DIRECTOR_ID,
        f"📋 Заявка #{request_id} одобрена руководителем\n\n"
        f"Сумма: {request['amount']} руб.\n"
        f"Контрагент: {request['counterparty']}",
        reply_markup=kb.finance_review_keyboard(request_id)
    )
    
    await callback.message.edit_text(callback.message.text + "\n\n✅ Заявка одобрена!")

@router.callback_query(F.data.startswith("manager_reject_"))
async def manager_reject_payment(callback: CallbackQuery, state: FSMContext):
    request_id = int(callback.data.replace("manager_reject_", ""))
    await state.update_data(reject_request_id=request_id)
    
    await callback.message.answer("❌ Напишите причину отклонения:")
    await state.set_state(ManagerActions.payment_reject_comment)

@router.message(ManagerActions.payment_reject_comment)
async def manager_reject_reason(message: Message, state: FSMContext):
    data = await state.get_data()
    request_id = data['reject_request_id']
    
    # Обновляем статус
    db.update_payment_request_status(
        request_id, 'rejected', message.from_user.id, message.text
    )
    
    # Уведомляем сотрудника
    request = db.get_payment_request(request_id)
    await message.bot.send_message(
        request['user_id'],
        f"❌ Ваша заявка #{request_id} отклонена\n\n"
        f"Причина: {message.text}"
    )
    
    await message.answer("✅ Заявка отклонена, сотрудник уведомлён")
    await state.clear()
