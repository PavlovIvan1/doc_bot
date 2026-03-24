import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from config import BOT_TOKEN, LAWYER_ID, FINANCE_DIRECTOR_ID, ACCOUNTANT_ID, MANAGERS
import keyboard as kb
from handlers import registration, personal_cabinet, manager, lawyer, finance, admin

logging.basicConfig(level=logging.INFO)

# Создаем папки для загрузок
os.makedirs("downloads/nda", exist_ok=True)
os.makedirs("downloads/tax_docs", exist_ok=True)

async def set_commands(bot: Bot):
    """Установка команд бота"""
    commands = [
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="help", description="Помощь"),
        BotCommand(command="cancel", description="Отменить действие"),
        BotCommand(command="main_menu", description="Главное меню"),
        BotCommand(command="clear_db", description="[ТЕСТ] Очистить БД"),
        # Тестовые команды для открытия меню разных ролей
        BotCommand(command="menu_lawyer", description="[ТЕСТ] Меню юриста"),
        BotCommand(command="menu_finance", description="[ТЕСТ] Меню финансов"),
        BotCommand(command="menu_manager", description="[ТЕСТ] Меню руководителя"),
        BotCommand(command="menu_user", description="[ТЕСТ] Меню сотрудника"),
        BotCommand(command="menu_admin", description="[ТЕСТ] Админ-панель"),
    ]
    await bot.set_my_commands(commands)

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # Подключаем роутеры
    dp.include_router(registration.router)
    dp.include_router(personal_cabinet.router)
    dp.include_router(manager.router)
    dp.include_router(lawyer.router)
    dp.include_router(finance.router)
    dp.include_router(admin.router)

    await set_commands(bot)
    await bot.delete_webhook(drop_pending_updates=True)
    
    logging.info("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())