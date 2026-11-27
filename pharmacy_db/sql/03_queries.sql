-- =====================================================================
-- Файл 3 из 4: SQL-запросы (16 штук)
-- Как запускать в pgAdmin: ВЫДЕЛИТЕ мышью один запрос целиком и нажмите F5.
-- (Если нажать F5 без выделения, выполнится весь файл, а покажется только
-- результат последнего запроса.)
-- =====================================================================


-- ===================== ЗАПРОСЫ НА ВЫБОРКУ =====================

-- [Q01] Выборка с соединением 3 таблиц + сортировка:
-- каталог товаров с категорией и производителем, по алфавиту
SELECT p.product_id, p.product_name, c.category_name, m.manufacturer_name,
       p.dosage_form, p.base_price
FROM products p
JOIN categories c    ON c.category_id = p.category_id
JOIN manufacturers m ON m.manufacturer_id = p.manufacturer_id
ORDER BY p.product_name;

-- [Q02] Фильтрация по условию: рецептурные товары дороже 150 руб., по убыванию цены
SELECT product_name, dosage_form, base_price
FROM products
WHERE is_prescription = TRUE AND base_price > 150
ORDER BY base_price DESC;

-- [Q03] Поиск по части названия (без учета регистра)
SELECT product_id, product_name, base_price
FROM products
WHERE product_name ILIKE '%пара%' OR product_name ILIKE '%ибу%'
ORDER BY product_name;

-- [Q04] Сроки годности: серии, у которых срок истекает в ближайшие 90 дней
SELECT product_name, batch_number, expiry_date, days_left, quantity, location_name
FROM v_batch_stock
WHERE expiry_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 90
  AND quantity > 0
ORDER BY expiry_date;

-- [Q05] Просроченные серии, которые еще числятся на складе (кандидаты на списание)
SELECT product_name, batch_number, expiry_date, quantity, location_name
FROM v_batch_stock
WHERE expiry_date < CURRENT_DATE AND quantity > 0
ORDER BY expiry_date;


-- ============ ГРУППИРОВКА И АГРЕГАТНЫЕ ФУНКЦИИ ============

-- [Q06] Дефицит: товары, остаток которых ниже минимального
SELECT product_name, category_name, min_stock, total_qty,
       min_stock - total_qty AS lacks
FROM v_product_stock
WHERE total_qty < min_stock
ORDER BY lacks DESC;

-- [Q07] Остатки и их стоимость по категориям (GROUP BY, COUNT, SUM)
SELECT category_name,
       COUNT(DISTINCT product_id) AS products_count,
       SUM(quantity)              AS total_qty,
       SUM(stock_value)           AS total_value
FROM v_batch_stock
GROUP BY category_name
ORDER BY total_value DESC;

-- [Q08] Закупки по поставщикам: количество накладных и общая сумма (GROUP BY + HAVING)
SELECT s.supplier_name,
       COUNT(DISTINCT r.receipt_id)           AS receipts_count,
       SUM(ri.quantity * ri.purchase_price)   AS total_sum
FROM suppliers s
JOIN receipts r       ON r.supplier_id = s.supplier_id
JOIN receipt_items ri ON ri.receipt_id = r.receipt_id
GROUP BY s.supplier_name
HAVING SUM(ri.quantity * ri.purchase_price) > 0
ORDER BY total_sum DESC;

-- [Q09] Отгрузки по клиентам: число накладных, штук, сумма
SELECT c.customer_name,
       COUNT(DISTINCT sh.shipment_id)       AS shipments_count,
       SUM(si.quantity)                     AS items_qty,
       SUM(si.quantity * si.sale_price)     AS total_sum
FROM customers c
JOIN shipments sh      ON sh.customer_id = c.customer_id
JOIN shipment_items si ON si.shipment_id = sh.shipment_id
GROUP BY c.customer_name
ORDER BY total_sum DESC;

-- [Q10] Топ-5 самых продаваемых товаров (4 таблицы, LIMIT)
SELECT p.product_name, SUM(si.quantity) AS shipped_qty
FROM shipment_items si
JOIN batches b  ON b.batch_id = si.batch_id
JOIN products p ON p.product_id = b.product_id
GROUP BY p.product_name
ORDER BY shipped_qty DESC
LIMIT 5;

-- [Q11] Динамика: сумма отгрузок по месяцам
SELECT EXTRACT(MONTH FROM sh.shipment_date)  AS month_no,
       COUNT(DISTINCT sh.shipment_id)        AS shipments_count,
       SUM(si.quantity * si.sale_price)      AS total_sum
FROM shipments sh
JOIN shipment_items si ON si.shipment_id = sh.shipment_id
GROUP BY EXTRACT(MONTH FROM sh.shipment_date)
ORDER BY month_no;

-- [Q12] Подзапрос NOT EXISTS: товары, которые ни разу не отгружались
SELECT p.product_name, p.base_price
FROM products p
WHERE NOT EXISTS (
    SELECT 1
    FROM batches b
    JOIN shipment_items si ON si.batch_id = b.batch_id
    WHERE b.product_id = p.product_id
)
ORDER BY p.product_name;

-- [Q13] LEFT JOIN: сколько накладных отгрузки оформил каждый сотрудник (включая нулевых)
SELECT e.full_name, e.position, COUNT(sh.shipment_id) AS shipments_count
FROM employees e
LEFT JOIN shipments sh ON sh.employee_id = e.employee_id
GROUP BY e.full_name, e.position
ORDER BY shipments_count DESC, e.full_name;


-- ============ ЗАПРОСЫ НА ДОБАВЛЕНИЕ, ИЗМЕНЕНИЕ, УДАЛЕНИЕ ============

-- [Q14] INSERT: новый поставщик
INSERT INTO suppliers (supplier_name, inn, phone, address)
VALUES ('ООО «ТестФарм»', '7712345678', '+7 495 999-88-77', 'г. Москва, ул. Тестовая, 1');

-- [Q15] UPDATE: повышение цены на 5% для категории «Витамины и БАД»,
-- и смена телефона поставщика
UPDATE products
SET base_price = ROUND(base_price * 1.05, 2)
WHERE category_id = (SELECT category_id FROM categories WHERE category_name = 'Витамины и БАД');

UPDATE suppliers SET phone = '+7 495 111-00-11' WHERE inn = '7712345678';

-- [Q16] DELETE: удаление тестового поставщика (у него нет накладных, поэтому удаление возможно)
DELETE FROM suppliers WHERE inn = '7712345678';

-- Проверка защиты целостности (эти команды ДОЛЖНЫ завершиться ошибкой — это нормально):
--   1) нельзя отгрузить больше, чем есть:
--      INSERT INTO shipments (doc_number, shipment_date, customer_id, employee_id) VALUES ('РН-ТЕСТ-1', CURRENT_DATE, 1, 5);
--      INSERT INTO shipment_items (shipment_id, batch_id, quantity, sale_price)
--      VALUES ((SELECT MAX(shipment_id) FROM shipments), 1, 99999, 10);
--   2) нельзя удалить категорию, на которую ссылаются товары:
--      DELETE FROM categories WHERE category_id = 1;
