-- =====================================================================
-- Файл 4 из 4: роли пользователей и права доступа
-- Запускать под пользователем postgres в базе pharmacy_warehouse ПОСЛЕ файлов 01 и 02.
-- Если роли уже существуют, команды CREATE ROLE/USER выдадут "already exists" —
-- это не страшно, остальные команды продолжат работать (выполняйте по частям).
-- ВАЖНО: пароли ниже учебные. В реальной работе замените их на свои.
-- =====================================================================

-- 1. Закрываем доступ "всем по умолчанию"
REVOKE ALL ON ALL TABLES    IN SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC;
REVOKE CONNECT ON DATABASE pharmacy_warehouse FROM PUBLIC;

-- 2. Групповые роли (без права входа) - это "должности"
CREATE ROLE pharm_admin;   -- администратор БД склада
CREATE ROLE pharm_manager; -- менеджер: работает с данными, но не удаляет
CREATE ROLE pharm_keeper;  -- кладовщик: оформляет приход, отгрузку, списание
CREATE ROLE pharm_viewer;  -- наблюдатель: только просмотр

-- 3. Подключение к базе и использование схемы
GRANT CONNECT ON DATABASE pharmacy_warehouse
    TO pharm_admin, pharm_manager, pharm_keeper, pharm_viewer;
GRANT USAGE ON SCHEMA public
    TO pharm_admin, pharm_manager, pharm_keeper, pharm_viewer;

-- 4. Права ролей
-- 4.1 Администратор: все права
GRANT ALL ON ALL TABLES    IN SCHEMA public TO pharm_admin;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO pharm_admin;

-- 4.2 Менеджер: чтение везде; добавление и изменение; удаление запрещено
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO pharm_manager;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO pharm_manager;
-- остаток серий меняют только триггеры, вручную - нельзя
REVOKE UPDATE ON batches FROM pharm_manager;
GRANT  UPDATE (batch_number, manufacture_date, expiry_date, location_id) ON batches TO pharm_manager;

-- 4.3 Кладовщик: чтение везде; добавление только складских операций
GRANT SELECT ON ALL TABLES IN SCHEMA public TO pharm_keeper;
GRANT INSERT ON batches, receipts, receipt_items,
                shipments, shipment_items, write_offs TO pharm_keeper;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO pharm_keeper;

-- 4.4 Наблюдатель: только чтение
GRANT SELECT ON ALL TABLES IN SCHEMA public TO pharm_viewer;

-- 5. Учебные учетные записи (логины для входа в приложение)
CREATE USER admin_pharm WITH PASSWORD 'Admin#2026'   IN ROLE pharm_admin;
CREATE USER manager1    WITH PASSWORD 'Manager#2026' IN ROLE pharm_manager;
CREATE USER keeper1     WITH PASSWORD 'Keeper#2026'  IN ROLE pharm_keeper;
CREATE USER viewer1     WITH PASSWORD 'Viewer#2026'  IN ROLE pharm_viewer;

-- 6. Проверка (посмотреть, какие роли есть)
SELECT rolname, rolcanlogin FROM pg_roles
WHERE rolname LIKE 'pharm_%' OR rolname IN ('admin_pharm','manager1','keeper1','viewer1')
ORDER BY rolname;

-- Как проверить права: в pgAdmin создайте подключение под viewer1 и выполните
--   DELETE FROM products;   -> ERROR: permission denied for table products
-- А под keeper1:
--   UPDATE batches SET quantity = 99999;  -> permission denied (остаток меняют только триггеры)
