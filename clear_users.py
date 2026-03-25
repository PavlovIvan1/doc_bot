#!/usr/bin/env python3
"""Console script to clear all users from database"""

import mysql.connector
from config import DB_CONFIG

def clear_users():
    """Удалить всех пользователей из БД"""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Отключаем проверку foreign keys
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        
        # Удаляем все связанные записи в правильном порядке
        cursor.execute("DELETE FROM payment_request_documents")
        cursor.execute("DELETE FROM payment_request_history")
        cursor.execute("DELETE FROM payment_requests")
        cursor.execute("DELETE FROM work_reports")
        cursor.execute("DELETE FROM documents")
        cursor.execute("DELETE FROM data_change_requests")
        cursor.execute("DELETE FROM admins")
        
        # Теперь удаляем пользователей
        cursor.execute("DELETE FROM users")
        
        # Включаем проверку foreign keys обратно
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        
        conn.commit()
        
        print("✅ Все пользователи и связанные записи удалены из базы данных")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    clear_users()
