#!/usr/bin/env python3
"""Console script to clear all users from database"""

import mysql.connector
from config import DB_CONFIG

def clear_users():
    """Удалить всех пользователей из БД"""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Удаляем всех пользователей
        cursor.execute("DELETE FROM users")
        conn.commit()
        
        print("✅ Все пользователи удалены из базы данных")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    clear_users()
