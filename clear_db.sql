-- Очистка базы данных для тестирования
-- Выполните эти команды в MySQL клиенте (например, через phpMyAdmin или mysql CLI)

-- Удаление всех записей из дочерних таблиц (с FOREIGN KEY)
DELETE FROM documents;
DELETE FROM uploaded_documents;
DELETE FROM action_logs;
DELETE FROM payment_requests;

-- Удаление всех пользователей
DELETE FROM users;

-- Сброс автоинкрементов (опционально, чтобы ID начинались с 1)
ALTER TABLE users AUTO_INCREMENT = 1;
ALTER TABLE documents AUTO_INCREMENT = 1;
ALTER TABLE payment_requests AUTO_INCREMENT = 1;
ALTER TABLE uploaded_documents AUTO_INCREMENT = 1;
ALTER TABLE action_logs AUTO_INCREMENT = 1;

-- Для полной очистки всех таблиц (раскомментируйте при необходимости):
-- TRUNCATE TABLE users;
-- TRUNCATE TABLE documents;
-- TRUNCATE TABLE payment_requests;
-- TRUNCATE TABLE uploaded_documents;
-- TRUNCATE TABLE action_logs;