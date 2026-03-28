import mysql.connector
from mysql.connector import Error
from config import DB_CONFIG
from datetime import datetime

class Database:
    def __init__(self):
        self.connection = None
        self.connect()

    def connect(self):
        try:
            self.connection = mysql.connector.connect(**DB_CONFIG)
            self.create_tables()
        except Error as e:
            print(f"Error connecting to MySQL: {e}")

    def create_tables(self):
        """Создание всех необходимых таблиц."""
        cursor = self.connection.cursor()
        cursor.execute("SET SESSION wait_timeout=31536000")
        
        # Таблица пользователей
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                telegram_login VARCHAR(255),
                full_name VARCHAR(255),
                passport_data VARCHAR(20),
                passport_series VARCHAR(20),
                passport_number VARCHAR(20),
                passport_date DATE,
                passport_issued TEXT,
                passport_code VARCHAR(20),
                birth_date DATE,
                registration_address TEXT,
                inn VARCHAR(20),
                phone VARCHAR(20),
                email VARCHAR(255),
                start_date DATE,
                tax_type ENUM('self_employed_npd', 'ip_npd', 'ip_usn'),
                tax_document_path VARCHAR(500),
                department VARCHAR(100),
                position VARCHAR(255),
                bank_details TEXT,
                registration_status ENUM('draft', 'pending', 'nda_pending', 'active', 'rejected', 'fired') DEFAULT 'draft',
                nda_status ENUM('not_sent', 'sent', 'signed', 'rejected', 'signed_by_user') DEFAULT 'not_sent',
                nda_file_path VARCHAR(500),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_email (email)
            )
        """)
        
        # Миграция: добавляем колонку passport_data если её нет
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN passport_data VARCHAR(20)")
            self.connection.commit()
        except:
            pass  # Колонка уже существует
        
        # Миграция: добавляем 'signed_by_user' в nda_status ENUM
        try:
            cursor.execute("ALTER TABLE users MODIFY COLUMN nda_status ENUM('not_sent', 'sent', 'signed', 'rejected', 'signed_by_user') DEFAULT 'not_sent'")
            self.connection.commit()
        except:
            pass  # Уже обновлено
        
        # Таблица для отчетов о работе
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS work_reports (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id BIGINT,
                report_month DATE,
                description TEXT,
                amount DECIMAL(10,2),
                bank_details TEXT,
                status ENUM('pending', 'approved_by_manager', 'rejected', 'sent_to_lawyer', 'payment_order_created', 'paid') DEFAULT 'pending',
                manager_comment TEXT,
                manager_id BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        # Миграция: расширяем статусы work_reports для этапов оплаты
        try:
            cursor.execute(
                "ALTER TABLE work_reports MODIFY COLUMN status ENUM('pending', 'approved_by_manager', 'rejected', 'sent_to_lawyer', 'payment_order_created', 'paid') DEFAULT 'pending'"
            )
            self.connection.commit()
        except:
            pass
        
        # Таблица документов
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id BIGINT,
                doc_type ENUM('nda', 'contract', 'act', 'invoice', 'check'),
                file_path VARCHAR(500),
                month DATE,
                status ENUM('sent', 'signed_by_user', 'approved_by_lawyer', 'paid', 'rejected'),
                lawyer_comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # Таблица для уведомлений о смене данных
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS data_change_requests (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id BIGINT,
                change_type ENUM('tax_type', 'last_name'),
                old_value TEXT,
                new_value TEXT,
                status ENUM('pending', 'approved', 'rejected') DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # Таблица заявок на оплату
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payment_requests (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id BIGINT,
                amount DECIMAL(12,2),
                payment_purpose TEXT,
                counterparty VARCHAR(255),
                project VARCHAR(255),
                contract_number VARCHAR(100),
                status ENUM(
                    'pending_manager',    # Ожидает проверки руководителя
                    'pending_finance',    # Ожидает проверки финансов
                    'approved',           # Одобрено
                    'rejected',          # Отклонено
                    'awaiting_payment',   # Ожидает оплаты
                    'paid',               # Оплачено
                    'documents_uploaded', # Документы загружены
                    'closed'              # Закрыто
                ) DEFAULT 'pending_manager',
                manager_id BIGINT,
                manager_comment TEXT,
                finance_id BIGINT,
                finance_comment TEXT,
                payment_proof_path VARCHAR(500),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # Таблица документов заявок
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payment_request_documents (
                id INT AUTO_INCREMENT PRIMARY KEY,
                payment_request_id INT,
                doc_type ENUM('invoice', 'contract', 'act', 'payment_proof', 'check'),
                file_path VARCHAR(500),
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (payment_request_id) REFERENCES payment_requests(id)
            )
        """)
        
        # Таблица истории статусов
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payment_request_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                payment_request_id INT,
                old_status VARCHAR(50),
                new_status VARCHAR(50),
                comment TEXT,
                changed_by BIGINT,
                changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (payment_request_id) REFERENCES payment_requests(id)
            )
        """)
        
        # Таблица админов
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id BIGINT PRIMARY KEY,
                role ENUM('super_admin', 'manager_admin', 'finance_admin') DEFAULT 'super_admin',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        self.connection.commit()

    # ----- ПОЛЬЗОВАТЕЛИ -----
    def add_user(self, user_id, **kwargs):
        cursor = self.connection.cursor()
        placeholders = ', '.join(['%s'] * len(kwargs))
        columns = ', '.join(kwargs.keys())
        query = f"INSERT INTO users (user_id, {columns}) VALUES (%s, {placeholders})"
        values = [user_id] + list(kwargs.values())
        cursor.execute(query, values)
        self.connection.commit()
        return cursor.lastrowid

    def get_user(self, user_id):
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        return cursor.fetchone()

    def update_user(self, user_id, **kwargs):
        cursor = self.connection.cursor()
        set_clause = ', '.join([f"{k} = %s" for k in kwargs])
        values = list(kwargs.values()) + [user_id]
        cursor.execute(f"UPDATE users SET {set_clause} WHERE user_id = %s", values)
        self.connection.commit()

    def get_users_by_department(self, department, status='active'):
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM users WHERE department = %s AND registration_status = %s",
            (department, status)
        )
        return cursor.fetchall()

    def get_pending_users(self):
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE registration_status = 'pending'")
        return cursor.fetchall()

    # ----- ОТЧЕТЫ -----
    def add_report(self, user_id, month, description, amount, bank_details):
        cursor = self.connection.cursor()
        cursor.execute(
            """INSERT INTO work_reports 
               (user_id, report_month, description, amount, bank_details) 
               VALUES (%s, %s, %s, %s, %s)""",
            (user_id, month, description, amount, bank_details)
        )
        self.connection.commit()
        return cursor.lastrowid

    def get_pending_reports_by_department(self, department):
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT wr.*, u.full_name, u.department 
            FROM work_reports wr
            JOIN users u ON wr.user_id = u.user_id
            WHERE u.department = %s AND wr.status = 'pending'
            ORDER BY wr.created_at DESC
        """, (department,))
        return cursor.fetchall()

    def get_reports_by_user(self, user_id, month=None):
        cursor = self.connection.cursor(dictionary=True)
        if month:
            cursor.execute(
                "SELECT * FROM work_reports WHERE user_id = %s AND report_month = %s",
                (user_id, month)
            )
        else:
            cursor.execute(
                "SELECT * FROM work_reports WHERE user_id = %s ORDER BY report_month DESC",
                (user_id,)
            )
        return cursor.fetchall()

    def update_report_status(self, report_id, status, manager_comment=None, manager_id=None):
        cursor = self.connection.cursor()
        if manager_comment:
            cursor.execute(
                "UPDATE work_reports SET status = %s, manager_comment = %s, manager_id = %s WHERE id = %s",
                (status, manager_comment, manager_id, report_id)
            )
        else:
            cursor.execute(
                "UPDATE work_reports SET status = %s, manager_id = %s WHERE id = %s",
                (status, manager_id, report_id)
            )
        self.connection.commit()

    # ----- ДОКУМЕНТЫ -----
    def add_document(self, user_id, doc_type, file_path, month=None, status='sent'):
        cursor = self.connection.cursor()
        cursor.execute(
            "INSERT INTO documents (user_id, doc_type, file_path, month, status) VALUES (%s, %s, %s, %s, %s)",
            (user_id, doc_type, file_path, month, status)
        )
        self.connection.commit()
        return cursor.lastrowid

    def get_user_documents(self, user_id, doc_type=None):
        cursor = self.connection.cursor(dictionary=True)
        if doc_type:
            cursor.execute(
                "SELECT * FROM documents WHERE user_id = %s AND doc_type = %s ORDER BY created_at DESC",
                (user_id, doc_type)
            )
        else:
            cursor.execute(
                "SELECT * FROM documents WHERE user_id = %s ORDER BY created_at DESC",
                (user_id,)
            )
        return cursor.fetchall()

    def get_pending_nda_requests(self):
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT u.* FROM users u
            WHERE u.nda_status = 'not_sent' AND u.registration_status = 'pending'
        """)
        return cursor.fetchall()

    def update_document_status(self, doc_id, status, comment=None):
        cursor = self.connection.cursor()
        if comment:
            cursor.execute(
                "UPDATE documents SET status = %s, lawyer_comment = %s WHERE id = %s",
                (status, comment, doc_id)
            )
        else:
            cursor.execute(
                "UPDATE documents SET status = %s WHERE id = %s",
                (status, doc_id)
            )
        self.connection.commit()

    # ----- ЗАПРОСЫ НА ИЗМЕНЕНИЕ -----
    def add_change_request(self, user_id, change_type, new_value):
        cursor = self.connection.cursor()
        cursor.execute(
            "INSERT INTO data_change_requests (user_id, change_type, new_value) VALUES (%s, %s, %s)",
            (user_id, change_type, new_value)
        )
        self.connection.commit()
        return cursor.lastrowid

    def get_pending_change_requests(self):
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT dcr.*, u.full_name, u.department 
            FROM data_change_requests dcr
            JOIN users u ON dcr.user_id = u.user_id
            WHERE dcr.status = 'pending'
        """)
        return cursor.fetchall()

    # ----- ЗАЯВКИ НА ОПЛАТУ -----
    def add_payment_request(self, user_id, amount, payment_purpose, counterparty, project, contract_number=None):
        cursor = self.connection.cursor()
        cursor.execute(
            """INSERT INTO payment_requests 
               (user_id, amount, payment_purpose, counterparty, project, contract_number, status) 
               VALUES (%s, %s, %s, %s, %s, %s, 'pending_manager')""",
            (user_id, amount, payment_purpose, counterparty, project, contract_number)
        )
        self.connection.commit()
        return cursor.lastrowid

    def get_payment_request(self, request_id):
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT pr.*, u.full_name, u.department, u.telegram_login FROM payment_requests pr JOIN users u ON pr.user_id = u.user_id WHERE pr.id = %s",
            (request_id,)
        )
        return cursor.fetchone()

    def get_user_payment_requests(self, user_id):
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM payment_requests WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,)
        )
        return cursor.fetchall()

    def get_pending_payment_requests_for_manager(self, department):
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT pr.*, u.full_name, u.department 
            FROM payment_requests pr
            JOIN users u ON pr.user_id = u.user_id
            WHERE pr.status = 'pending_manager' AND u.department = %s
            ORDER BY pr.created_at DESC
        """, (department,))
        return cursor.fetchall()

    def get_pending_payment_requests_for_finance(self):
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT pr.*, u.full_name, u.department 
            FROM payment_requests pr
            JOIN users u ON pr.user_id = u.user_id
            WHERE pr.status IN ('pending_finance', 'approved')
            ORDER BY pr.created_at DESC
        """)
        return cursor.fetchall()

    def get_payment_requests_for_accountant(self):
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT pr.*, u.full_name, u.department, u.bank_details 
            FROM payment_requests pr
            JOIN users u ON pr.user_id = u.user_id
            WHERE pr.status IN ('approved', 'awaiting_payment')
            ORDER BY pr.created_at DESC
        """)
        return cursor.fetchall()

    def update_payment_request_status(self, request_id, status, user_id=None, comment=None):
        cursor = self.connection.cursor()
        
        # Получаем старый статус
        cursor.execute("SELECT status FROM payment_requests WHERE id = %s", (request_id,))
        old_status = cursor.fetchone()[0]
        
        if user_id and comment:
            if status == 'rejected':
                cursor.execute(
                    "UPDATE payment_requests SET status = %s, manager_id = %s, manager_comment = %s WHERE id = %s",
                    (status, user_id, comment, request_id)
                )
            elif status == 'paid':
                cursor.execute(
                    "UPDATE payment_requests SET status = %s, finance_id = %s WHERE id = %s",
                    (status, user_id, request_id)
                )
            else:
                cursor.execute(
                    "UPDATE payment_requests SET status = %s, finance_id = %s, finance_comment = %s WHERE id = %s",
                    (status, user_id, comment, request_id)
                )
        elif user_id:
            cursor.execute(
                "UPDATE payment_requests SET status = %s, manager_id = %s WHERE id = %s",
                (status, user_id, request_id)
            )
        else:
            cursor.execute(
                "UPDATE payment_requests SET status = %s WHERE id = %s",
                (status, request_id)
            )
        
        # Записываем историю
        cursor.execute(
            "INSERT INTO payment_request_history (payment_request_id, old_status, new_status, comment, changed_by) VALUES (%s, %s, %s, %s, %s)",
            (request_id, old_status, status, comment, user_id)
        )
        
        self.connection.commit()

    def add_payment_request_document(self, request_id, doc_type, file_path):
        cursor = self.connection.cursor()
        cursor.execute(
            "INSERT INTO payment_request_documents (payment_request_id, doc_type, file_path) VALUES (%s, %s, %s)",
            (request_id, doc_type, file_path)
        )
        self.connection.commit()
        return cursor.lastrowid

    def get_payment_request_documents(self, request_id):
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM payment_request_documents WHERE payment_request_id = %s",
            (request_id,)
        )
        return cursor.fetchall()

    def get_payment_request_history(self, request_id):
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM payment_request_history WHERE payment_request_id = %s ORDER BY changed_at ASC",
            (request_id,)
        )
        return cursor.fetchall()

    # ----- АДМИНИСТРАТОРЫ -----
    def add_admin(self, user_id, role='super_admin'):
        cursor = self.connection.cursor()
        cursor.execute(
            "INSERT INTO admins (user_id, role) VALUES (%s, %s) ON DUPLICATE KEY UPDATE role = %s",
            (user_id, role, role)
        )
        self.connection.commit()

    def get_admin(self, user_id):
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM admins WHERE user_id = %s", (user_id,))
        return cursor.fetchone()

    def get_all_admins(self):
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM admins")
        return cursor.fetchall()
