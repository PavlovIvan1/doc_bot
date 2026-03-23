import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_CONFIG = {
    'host': os.getenv("DB_HOST"),
    'user': os.getenv("DB_USER"),
    'password': os.getenv("DB_PASSWORD"),
    'database': os.getenv("DB_NAME"),
    'port': 3306,
    'autocommit': True,
    'use_pure': True
}

# ID сотрудников
LAWYER_ID = int(os.getenv("LAWYER_ID", 0))
FINANCE_DIRECTOR_ID = int(os.getenv("FINANCE_DIRECTOR_ID", 0))
ACCOUNTANT_ID = int(os.getenv("ACCOUNTANT_ID", 0))
MY_ID = int(os.getenv("MY_ID", 0))

# Ссылки на чаты отделов
DEPARTMENT_CHATS = {
    'Отдел контента': os.getenv("CHAT_CONTENT"),
    'Отдел маркетинга': os.getenv("CHAT_MARKETING"),
    'Отдел продаж': os.getenv("CHAT_SALES"),
    'Департамент продукта': os.getenv("CHAT_PRODUCT"),
    'Отдел контроля качества': os.getenv("CHAT_QUALITY"),
    'Финансово-юридический отдел': os.getenv("CHAT_FINANCE")
}

COMMUNITY_CHAT = os.getenv("COMMUNITY_CHAT")
CHANNEL_NEWS = os.getenv("CHANNEL_NEWS")
CONSENT_LINK = os.getenv("CONSENT_LINK")

# Руководители отделов (user_id: department)
# Заполняется ниже после DEPARTMENTS

# Доступные отделы
DEPARTMENTS = [
    'Отдел контента',
    'Отдел маркетинга',
    'Отдел продаж',
    'Департамент продукта',
    'Отдел контроля качества',
    'Финансово-юридический отдел'
]

# Руководители отделов (user_id: department)
# Можно указать в .env как: MANAGER_123456789="Название_отдела"
MANAGERS = {}

# Загружаем руководителей из переменных окружения
# Поддерживаем несколько отделов для одного менеджера
for key, value in os.environ.items():
    if key.startswith('MANAGER_') and value in DEPARTMENTS:
        try:
            user_id = int(key.replace('MANAGER_', ''))
            if user_id not in MANAGERS:
                MANAGERS[user_id] = []
            MANAGERS[user_id].append(value)
        except ValueError:
            pass

# Если не загружено из .env, используем пример (для тестирования)
if not MANAGERS:
    MANAGERS = {
        123456789: ['Отдел контента', 'Отдел маркетинга'],
    }

# Типы налогообложения
TAX_TYPES = {
    'self_employed_npd': 'Самозанятый (НПД)',
    'ip_npd': 'ИП на НПД',
    'ip_usn': 'ИП на УСН'
}