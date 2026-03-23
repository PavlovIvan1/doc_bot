from aiogram.fsm.state import State, StatesGroup

class Registration(StatesGroup):
    """Состояния для регистрации нового сотрудника"""
    full_name = State()
    passport_series = State()
    passport_date = State()
    passport_issued = State()
    passport_code = State()
    birth_date = State()
    address = State()
    inn = State()
    phone = State()
    email = State()
    start_date = State()
    tax_type = State()
    tax_document = State()
    department = State()
    confirm = State()

class NDAProcess(StatesGroup):
    """Состояния для подписания НДА"""
    waiting_for_nda_file = State()
    lawyer_review = State()

class MonthlyReport(StatesGroup):
    """Состояния для ежемесячного отчета"""
    description = State()
    amount = State()
    bank_details = State()
    confirm = State()

class BankDetails(StatesGroup):
    """Состояния для заполнения банковских реквизитов"""
    details = State()

class DocumentUpload(StatesGroup):
    """Состояния для загрузки документов"""
    contract = State()
    act = State()
    invoice = State()
    check = State()

class ManagerActions(StatesGroup):
    """Состояния для действий руководителя"""
    select_department = State()
    review_report = State()
    correction_comment = State()
    change_position = State()
    select_employee = State()

class LawyerActions(StatesGroup):
    """Состояния для действий юриста"""
    nda_upload = State()
    signed_nda_receive = State()
    payment_review = State()
    correction_comment = State()

class PaymentRequest(StatesGroup):
    """Состояния для создания заявки на оплату"""
    amount = State()
    payment_purpose = State()
    counterparty = State()
    project = State()
    contract_number = State()
    invoice_file = State()
    confirm = State()

class PaymentRequestUpload(StatesGroup):
    """Состояния для загрузки документов к заявке"""
    contract = State()
    act = State()
    check = State()
    payment_proof = State()

class AdminActions(StatesGroup):
    """Состояния для админ-панели"""
    select_action = State()
    select_user = State()
    confirm_action = State()
    add_user_id = State()
    set_role = State()