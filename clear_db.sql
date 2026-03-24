-- Очистка базы данных для тестирования
-- Выполните эти команды в MySQL клиенте

-- Удаление всех записей из дочерних таблиц (с FOREIGN KEY)
DELETE FROM payment_request_documents;
DELETE FROM payment_request_history;
DELETE FROM data_change_requests;
DELETE FROM work_reports;
DELETE FROM documents;
DELETE FROM payment_requests;
DELETE FROM admins;

-- Удаление всех пользователей (последней, т.к. на неё ссылаются)
DELETE FROM users;

-- Сброс автоинкрементов
ALTER TABLE users AUTO_INCREMENT = 1;
ALTER TABLE documents AUTO_INCREMENT = 1;
ALTER TABLE payment_requests AUTO_INCREMENT = 1;
ALTER TABLE admins AUTO_INCREMENT = 1;
ALTER TABLE data_change_requests AUTO_INCREMENT = 1;
ALTER TABLE work_reports AUTO_INCREMENT = 1;
ALTER TABLE payment_request_documents AUTO_INCREMENT = 1;
ALTER TABLE payment_request_history AUTO_INCREMENT = 1;