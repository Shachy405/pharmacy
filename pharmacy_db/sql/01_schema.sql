-- =====================================================================
-- База данных учета товаров аптечного склада
-- СУБД: PostgreSQL 14+ (рекомендуется 16)
-- Файл 1 из 4: создание таблиц, ограничений, индексов, представлений, триггеров
-- Запускать в базе pharmacy_warehouse (Query Tool в pgAdmin, кнопка F5)
-- Скрипт можно запускать повторно: старые объекты будут удалены.
-- =====================================================================

-- ---------- Удаление старых объектов (для повторного запуска) ----------
DROP VIEW  IF EXISTS v_batch_stock   CASCADE;
DROP VIEW  IF EXISTS v_product_stock CASCADE;
DROP TABLE IF EXISTS write_offs      CASCADE;
DROP TABLE IF EXISTS shipment_items  CASCADE;
DROP TABLE IF EXISTS shipments       CASCADE;
DROP TABLE IF EXISTS receipt_items   CASCADE;
DROP TABLE IF EXISTS receipts        CASCADE;
DROP TABLE IF EXISTS batches         CASCADE;
DROP TABLE IF EXISTS products        CASCADE;
DROP TABLE IF EXISTS customers       CASCADE;
DROP TABLE IF EXISTS employees       CASCADE;
DROP TABLE IF EXISTS storage_locations CASCADE;
DROP TABLE IF EXISTS suppliers       CASCADE;
DROP TABLE IF EXISTS manufacturers   CASCADE;
DROP TABLE IF EXISTS categories      CASCADE;

-- ---------- Справочники ----------

-- Категории (фармакологические группы) товаров
CREATE TABLE categories (
    category_id   SERIAL PRIMARY KEY,
    category_name VARCHAR(80) NOT NULL UNIQUE
);

-- Производители
CREATE TABLE manufacturers (
    manufacturer_id   SERIAL PRIMARY KEY,
    manufacturer_name VARCHAR(120) NOT NULL UNIQUE,
    country           VARCHAR(60)  NOT NULL
);

-- Поставщики
CREATE TABLE suppliers (
    supplier_id   SERIAL PRIMARY KEY,
    supplier_name VARCHAR(120) NOT NULL UNIQUE,
    inn           VARCHAR(12)  NOT NULL UNIQUE CHECK (LENGTH(inn) IN (10, 12)),
    phone         VARCHAR(20),
    address       VARCHAR(200)
);

-- Места хранения на складе (с температурным режимом)
CREATE TABLE storage_locations (
    location_id   SERIAL PRIMARY KEY,
    location_name VARCHAR(60) NOT NULL UNIQUE,
    temp_mode     VARCHAR(30) NOT NULL
                  CHECK (temp_mode IN ('Комнатная (15-25)', 'Прохладное (8-15)', 'Холодильник (2-8)'))
);

-- Сотрудники склада
CREATE TABLE employees (
    employee_id SERIAL PRIMARY KEY,
    full_name   VARCHAR(100) NOT NULL,
    position    VARCHAR(60)  NOT NULL,
    phone       VARCHAR(20),
    hire_date   DATE NOT NULL DEFAULT CURRENT_DATE
);

-- Клиенты склада (аптеки, поликлиники), которым отгружается товар
CREATE TABLE customers (
    customer_id   SERIAL PRIMARY KEY,
    customer_name VARCHAR(120) NOT NULL UNIQUE,
    address       VARCHAR(200),
    phone         VARCHAR(20)
);

-- ---------- Основные таблицы ----------

-- Товары (номенклатура)
CREATE TABLE products (
    product_id      SERIAL PRIMARY KEY,
    product_name    VARCHAR(150) NOT NULL,
    category_id     INTEGER NOT NULL REFERENCES categories(category_id)
                    ON UPDATE CASCADE ON DELETE RESTRICT,
    manufacturer_id INTEGER NOT NULL REFERENCES manufacturers(manufacturer_id)
                    ON UPDATE CASCADE ON DELETE RESTRICT,
    dosage_form     VARCHAR(50) NOT NULL,
    unit            VARCHAR(20) NOT NULL DEFAULT 'уп.',
    barcode         VARCHAR(13) NOT NULL UNIQUE CHECK (LENGTH(barcode) = 13),
    is_prescription BOOLEAN NOT NULL DEFAULT FALSE,
    min_stock       INTEGER NOT NULL DEFAULT 0 CHECK (min_stock >= 0),
    base_price      NUMERIC(10,2) NOT NULL CHECK (base_price > 0)
);

-- Серии (партии) товара: срок годности, место хранения, текущий остаток
CREATE TABLE batches (
    batch_id         SERIAL PRIMARY KEY,
    product_id       INTEGER NOT NULL REFERENCES products(product_id)
                     ON UPDATE CASCADE ON DELETE RESTRICT,
    batch_number     VARCHAR(30) NOT NULL,
    manufacture_date DATE NOT NULL,
    expiry_date      DATE NOT NULL,
    location_id      INTEGER NOT NULL REFERENCES storage_locations(location_id)
                     ON UPDATE CASCADE ON DELETE RESTRICT,
    quantity         INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    UNIQUE (product_id, batch_number),
    CHECK (expiry_date > manufacture_date)
);

-- Приход: заголовок накладной
CREATE TABLE receipts (
    receipt_id   SERIAL PRIMARY KEY,
    doc_number   VARCHAR(20) NOT NULL UNIQUE,
    receipt_date DATE NOT NULL DEFAULT CURRENT_DATE,
    supplier_id  INTEGER NOT NULL REFERENCES suppliers(supplier_id)
                 ON UPDATE CASCADE ON DELETE RESTRICT,
    employee_id  INTEGER NOT NULL REFERENCES employees(employee_id)
                 ON UPDATE CASCADE ON DELETE RESTRICT
);

-- Приход: строки накладной
CREATE TABLE receipt_items (
    item_id        SERIAL PRIMARY KEY,
    receipt_id     INTEGER NOT NULL REFERENCES receipts(receipt_id)
                   ON UPDATE CASCADE ON DELETE CASCADE,
    batch_id       INTEGER NOT NULL REFERENCES batches(batch_id)
                   ON UPDATE CASCADE ON DELETE RESTRICT,
    quantity       INTEGER NOT NULL CHECK (quantity > 0),
    purchase_price NUMERIC(10,2) NOT NULL CHECK (purchase_price > 0)
);

-- Отгрузка: заголовок накладной
CREATE TABLE shipments (
    shipment_id   SERIAL PRIMARY KEY,
    doc_number    VARCHAR(20) NOT NULL UNIQUE,
    shipment_date DATE NOT NULL DEFAULT CURRENT_DATE,
    customer_id   INTEGER NOT NULL REFERENCES customers(customer_id)
                  ON UPDATE CASCADE ON DELETE RESTRICT,
    employee_id   INTEGER NOT NULL REFERENCES employees(employee_id)
                  ON UPDATE CASCADE ON DELETE RESTRICT
);

-- Отгрузка: строки накладной
CREATE TABLE shipment_items (
    item_id     SERIAL PRIMARY KEY,
    shipment_id INTEGER NOT NULL REFERENCES shipments(shipment_id)
                ON UPDATE CASCADE ON DELETE CASCADE,
    batch_id    INTEGER NOT NULL REFERENCES batches(batch_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
    quantity    INTEGER NOT NULL CHECK (quantity > 0),
    sale_price  NUMERIC(10,2) NOT NULL CHECK (sale_price > 0)
);

-- Списание (просрочка, брак, повреждение)
CREATE TABLE write_offs (
    writeoff_id   SERIAL PRIMARY KEY,
    batch_id      INTEGER NOT NULL REFERENCES batches(batch_id)
                  ON UPDATE CASCADE ON DELETE RESTRICT,
    employee_id   INTEGER NOT NULL REFERENCES employees(employee_id)
                  ON UPDATE CASCADE ON DELETE RESTRICT,
    writeoff_date DATE NOT NULL DEFAULT CURRENT_DATE,
    quantity      INTEGER NOT NULL CHECK (quantity > 0),
    reason        VARCHAR(30) NOT NULL
                  CHECK (reason IN ('Истек срок годности', 'Брак', 'Повреждение упаковки', 'Иное'))
);

-- ---------- Индексы (ускоряют поиск, фильтрацию, сортировку, соединения) ----------
CREATE INDEX idx_products_name      ON products(product_name);
CREATE INDEX idx_products_category  ON products(category_id);
CREATE INDEX idx_batches_product    ON batches(product_id);
CREATE INDEX idx_batches_expiry     ON batches(expiry_date);
CREATE INDEX idx_receipts_date      ON receipts(receipt_date);
CREATE INDEX idx_receipt_items_rcpt ON receipt_items(receipt_id);
CREATE INDEX idx_receipt_items_batch ON receipt_items(batch_id);
CREATE INDEX idx_shipments_date     ON shipments(shipment_date);
CREATE INDEX idx_shipments_customer ON shipments(customer_id);
CREATE INDEX idx_shipment_items_shp ON shipment_items(shipment_id);
CREATE INDEX idx_shipment_items_batch ON shipment_items(batch_id);
CREATE INDEX idx_write_offs_batch   ON write_offs(batch_id);

-- ---------- Представления ----------

-- Остатки по сериям: срок годности, сколько дней осталось, стоимость остатка
CREATE VIEW v_batch_stock AS
SELECT b.batch_id,
       p.product_id,
       p.product_name,
       c.category_name,
       b.batch_number,
       b.expiry_date,
       (b.expiry_date - CURRENT_DATE) AS days_left,
       l.location_name,
       b.quantity,
       p.base_price,
       b.quantity * p.base_price AS stock_value
FROM batches b
JOIN products p          ON p.product_id  = b.product_id
JOIN categories c        ON c.category_id = p.category_id
JOIN storage_locations l ON l.location_id = b.location_id;

-- Остатки по товарам в целом (сумма по всем сериям)
CREATE VIEW v_product_stock AS
SELECT p.product_id,
       p.product_name,
       c.category_name,
       p.min_stock,
       COALESCE(SUM(b.quantity), 0) AS total_qty
FROM products p
JOIN categories c ON c.category_id = p.category_id
LEFT JOIN batches b ON b.product_id = p.product_id
GROUP BY p.product_id, p.product_name, c.category_name, p.min_stock;

-- >>> TRIGGERS (PostgreSQL / PL/pgSQL)
-- Остаток серии пересчитывается автоматически. Функции SECURITY DEFINER:
-- они выполняются с правами владельца, поэтому кладовщик может провести
-- накладную, но не может вручную менять поле quantity в таблице batches.

-- Приход: остаток серии увеличивается
CREATE OR REPLACE FUNCTION fn_receipt_item_insert() RETURNS TRIGGER AS $$
BEGIN
    UPDATE batches SET quantity = quantity + NEW.quantity
    WHERE batch_id = NEW.batch_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

CREATE TRIGGER trg_receipt_item_insert
BEFORE INSERT ON receipt_items
FOR EACH ROW EXECUTE FUNCTION fn_receipt_item_insert();

-- Отгрузка: проверка остатка и срока годности, затем уменьшение остатка
CREATE OR REPLACE FUNCTION fn_shipment_item_insert() RETURNS TRIGGER AS $$
DECLARE
    v_qty  INTEGER;
    v_exp  DATE;
    v_date DATE;
BEGIN
    SELECT quantity, expiry_date INTO v_qty, v_exp
    FROM batches WHERE batch_id = NEW.batch_id FOR UPDATE;

    SELECT shipment_date INTO v_date
    FROM shipments WHERE shipment_id = NEW.shipment_id;

    IF v_exp < v_date THEN
        RAISE EXCEPTION 'Нельзя отгрузить серию с истекшим сроком годности (серия № %)', NEW.batch_id;
    END IF;
    IF v_qty < NEW.quantity THEN
        RAISE EXCEPTION 'Недостаточно товара на складе: в наличии %, требуется %', v_qty, NEW.quantity;
    END IF;

    UPDATE batches SET quantity = quantity - NEW.quantity
    WHERE batch_id = NEW.batch_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

CREATE TRIGGER trg_shipment_item_insert
BEFORE INSERT ON shipment_items
FOR EACH ROW EXECUTE FUNCTION fn_shipment_item_insert();

-- Списание: проверка остатка, затем уменьшение остатка
CREATE OR REPLACE FUNCTION fn_write_off_insert() RETURNS TRIGGER AS $$
DECLARE
    v_qty INTEGER;
BEGIN
    SELECT quantity INTO v_qty
    FROM batches WHERE batch_id = NEW.batch_id FOR UPDATE;

    IF v_qty < NEW.quantity THEN
        RAISE EXCEPTION 'Нельзя списать больше, чем есть на складе: в наличии %, списывается %', v_qty, NEW.quantity;
    END IF;

    UPDATE batches SET quantity = quantity - NEW.quantity
    WHERE batch_id = NEW.batch_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

CREATE TRIGGER trg_write_off_insert
BEFORE INSERT ON write_offs
FOR EACH ROW EXECUTE FUNCTION fn_write_off_insert();
-- <<< TRIGGERS
