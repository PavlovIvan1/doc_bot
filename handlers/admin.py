from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton

from handlers.states import AdminActions
from database import Database
import keyboard as kb
from config import MANAGERS, DEPARTMENTS

router = Router()
db = Database()

# Список админов (в реальном проекте брать из БД или конфига)
ADMIN_IDS = []

async def check_admin(message: Message):
    """Проверка, что пользователь - админ"""
    if message.from_user.id not in ADMIN_IDS:
        # Также проверяем в БД
        admin = db.get_admin(message.from_user.id)
        if not admin:
            await message.answer("❌ У вас нет доступа к админ-панели")
            return False
    return True

@router.message(Command("admin"))
async def admin_panel(message: Message):
    """Открыть админ-панель"""
    if not await check_admin(message):
        return
    
    await message.answer(
        "⚙️ Админ-панель\n\nВыберите действие:",
        reply_markup=kb.admin_main_keyboard()
    )


@router.message(F.text == "/clear_users")
async def clear_all_users(message: Message):
    """Удалить всех пользователей из БД"""
    if not await check_admin(message):
        return
    
    cursor = db.connection.cursor()
    cursor.execute("DELETE FROM users")
    db.connection.commit()
    
    await message.answer("✅ Все пользователи удалены из базы данных")

@router.message(F.text == "👥 Управление пользователями")
async def manage_users(message: Message):
    if not await check_admin(message):
        return
    
    cursor = db.connection.cursor(dictionary=True)
    cursor.execute("SELECT user_id, full_name, department, registration_status, nda_status FROM users")
    users = cursor.fetchall()
    
    if not users:
        await message.answer("Нет пользователей")
        return
    
    await message.answer(
        "👥 Список пользователей:",
        reply_markup=kb.admin_users_list_keyboard(users)
    )

@router.message(F.text == "➕ Добавить пользователя")
async def add_user_start(message: Message, state: FSMContext):
    if not await check_admin(message):
        return
    
    await message.answer("Введите Telegram ID пользователя:")
    await state.set_state(AdminActions.add_user_id)

@router.message(AdminActions.add_user_id)
async def add_user_id(message: Message, state: FSMContext):
    try:
        user_id = int(message.text)
        await state.update_data(new_user_id=user_id)
        
        await message.answer(
            "Выберите роль:",
            reply_markup=kb.admin_role_keyboard()
        )
        await state.set_state(AdminActions.set_role)
    except ValueError:
        await message.answer("❌ Введите корректный Telegram ID (только цифры)")

@router.callback_query(AdminActions.set_role, F.data.startswith("role_"))
async def set_user_role(callback: CallbackQuery, state: FSMContext):
    role = callback.data.replace("role_", "")
    data = await state.get_data()
    user_id = data['new_user_id']
    
    # Добавляем/обновляем админа
    db.add_admin(user_id, role)
    
    await callback.message.edit_text(f"✅ Пользователю {user_id} присвоена роль {role}")
    await state.clear()

@router.message(F.text == "🔄 Изменить роль")
async def change_role_start(message: Message):
    if not await check_admin(message):
        return
    
    admins = db.get_all_admins()
    
    if not admins:
        await message.answer("Нет админов")
        return
    
    builder = InlineKeyboardBuilder()
    for admin in admins:
        builder.add(InlineKeyboardButton(
            text=f"ID: {admin['user_id']} - {admin['role']}",
            callback_data=f"admin_edit_role_{admin['user_id']}"
        ))
    builder.adjust(1)
    
    await message.answer("Выберите админа для изменения роли:", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("admin_edit_role_"))
async def edit_role(callback: CallbackQuery, state: FSMContext):
    user_id = int(callback.data.replace("admin_edit_role_", ""))
    await state.update_data(edit_role_user_id=user_id)
    
    await callback.message.answer(
        "Выберите новую роль:",
        reply_markup=kb.admin_role_keyboard()
    )
    await state.set_state("admin_change_role")

@router.callback_query(F.data == "role_super_admin")
async def change_role_to_super_admin(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_id = data.get('edit_role_user_id')
    
    if user_id:
        role = "super_admin"
        db.add_admin(user_id, role)
        await callback.message.edit_text(f"✅ Роль изменена на {role}")
    
    await state.clear()

@router.callback_query(F.data == "role_manager_admin")
async def change_role_to_manager_admin(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_id = data.get('edit_role_user_id')
    
    if user_id:
        role = "manager_admin"
        db.add_admin(user_id, role)
        await callback.message.edit_text(f"✅ Роль изменена на {role}")
    
    await state.clear()

@router.callback_query(F.data == "role_finance_admin")
async def change_role_to_finance_admin(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_id = data.get('edit_role_user_id')
    
    if user_id:
        role = "finance_admin"
        db.add_admin(user_id, role)
        await callback.message.edit_text(f"✅ Роль изменена на {role}")
    
    await state.clear()

@router.message(F.text == "🚫 Заблокировать пользователя")
async def block_user_start(message: Message, state: FSMContext):
    if not await check_admin(message):
        return
    
    cursor = db.connection.cursor(dictionary=True)
    cursor.execute("SELECT user_id, full_name, registration_status FROM users WHERE registration_status = 'active'")
    users = cursor.fetchall()
    
    if not users:
        await message.answer("Нет активных пользователей")
        return
    
    builder = InlineKeyboardBuilder()
    for user in users:
        builder.add(InlineKeyboardButton(
            text=user['full_name'],
            callback_data=f"block_user_{user['user_id']}"
        ))
    builder.adjust(1)
    
    await message.answer("Выберите пользователя для блокировки:", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("block_user_"))
async def block_user(callback: CallbackQuery):
    user_id = int(callback.data.replace("block_user_", ""))
    
    db.update_user(user_id, registration_status='fired')
    
    await callback.bot.send_message(
        user_id,
        "❌ Ваш доступ заблокирован администратором."
    )
    
    await callback.message.edit_text(f"✅ Пользователь {user_id} заблокирован")

@router.message(F.text == "📊 Статистика")
async def statistics(message: Message):
    if not await check_admin(message):
        return
    
    cursor = db.connection.cursor(dictionary=True)
    
    # Всего пользователей
    cursor.execute("SELECT COUNT(*) as total FROM users")
    total = cursor.fetchone()['total']
    
    # По статусам
    cursor.execute("SELECT registration_status, COUNT(*) as count FROM users GROUP BY registration_status")
    statuses = cursor.fetchall()
    
    # По отделам
    cursor.execute("SELECT department, COUNT(*) as count FROM users WHERE registration_status = 'active' GROUP BY department")
    departments = cursor.fetchall()
    
    # Заявки на оплату
    cursor.execute("SELECT status, COUNT(*) as count FROM payment_requests GROUP BY status")
    payment_statuses = cursor.fetchall()
    
    status_text = "\\n".join([f"  {s['registration_status']}: {s['count']}" for s in statuses])
    dept_text = "\\n".join([f"  {d['department']}: {d['count']}" for d in departments]) or "Нет данных"
    payment_text = "\\n".join([f"  {p['status']}: {p['count']}" for p in payment_statuses]) or "Нет заявок"
    
    text = f"""
📊 Статистика системы

👥 Пользователи:
  Всего: {total}
{status_text}

🏢 По отделам:
{dept_text}

💰 Заявки на оплату:
{payment_text}
    """
    
    await message.answer(text)

# Команда для добавления админа (только для супер-админа)
@router.message(Command("addadmin"))
async def add_admin_command(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        admin = db.get_admin(message.from_user.id)
        if not admin or admin['role'] != 'super_admin':
            await message.answer("❌ У вас нет доступа")
            return
    
    try:
        # Использование: /addadmin <telegram_id> <role>
        parts = message.text.split()
        if len(parts) < 3:
            await message.answer("Использование: /addadmin <telegram_id> <role>")
            return
        
        user_id = int(parts[1])
        role = parts[2]
        
        if role not in ['super_admin', 'manager_admin', 'finance_admin']:
            await message.answer("Роль должна быть: super_admin, manager_admin или finance_admin")
            return
        
        db.add_admin(user_id, role)
        await message.answer(f"✅ Админ {user_id} добавлен с ролью {role}")
    except ValueError:
        await message.answer("❌ Неверный формат команды")

# Команда для проверки просроченных актов
@router.message(Command("check_overdue"))
async def check_overdue_acts(message: Message):
    if not await check_admin(message):
        return
    
    from datetime import datetime, timedelta
    
    # Находим оплаченные заявки старше 5 дней без актов
    cursor = db.connection.cursor(dictionary=True)
    five_days_ago = datetime.now() - timedelta(days=5)
    
    cursor.execute("""
        SELECT pr.*, u.full_name, u.telegram_login 
        FROM payment_requests pr
        JOIN users u ON pr.user_id = u.user_id
        WHERE pr.status = 'paid' 
        AND pr.created_at < %s
    """, (five_days_ago,))
    
    requests = cursor.fetchall()
    
    overdue_count = 0
    sent_notifications = 0
    
    for req in requests:
        # Проверяем есть ли акт
        cursor.execute(
            "SELECT id FROM payment_request_documents WHERE payment_request_id = %s AND doc_type = 'act'",
            (req['id'],)
        )
        act_doc = cursor.fetchone()
        
        if not act_doc:
            overdue_count += 1
            # Отправляем напоминание сотруднику
            try:
                await message.bot.send_message(
                    req['user_id'],
                    f"⚠️ Напоминание по заявке #{req['id']}\n\n"
                    f"Вы получили оплату {five_days_ago.strftime('%d.%m.%Y')}, "
                    f"но акт и чек ещё не загружены.\n\n"
                    f"Пожалуйста, загрузите закрывающие документы.\n"
                    f"Без них заявка не будет закрыта."
                )
                sent_notifications += 1
            except:
                pass
    
    await message.answer(
        f"📊 Проверка завершена:\n\n"
        f"Всего просроченных заявок: {overdue_count}\n"
        f"Отправлено уведомлений: {sent_notifications}"
    )
