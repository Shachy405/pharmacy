# -*- coding: utf-8 -*-
"""
Приложение «Склад аптеки»: формы и отчеты для базы pharmacy_warehouse (PostgreSQL).

Запуск:   python pharmacy_app.py
Нужно:    pip install psycopg2-binary
Вход:     логин и пароль пользователя БД (например manager1 / Manager#2026)

Формы (вкладки):  Товары | Приход | Отгрузка | Остатки и поиск
Отчеты (вкладка): накладная на отгрузку, приход за период, остатки по категориям,
                  дефицит, сроки годности. Каждый отчет можно сохранить в CSV и HTML.
"""
import csv
import html
import tkinter as tk
from datetime import date, datetime
from decimal import Decimal
from tkinter import filedialog, messagebox, simpledialog, ttk

import psycopg2
import psycopg2.errors as pgerr

# ------------------------- НАСТРОЙКИ ПОДКЛЮЧЕНИЯ -------------------------
DB_SETTINGS = {"host": "localhost", "port": 5432, "dbname": "pharmacy_warehouse"}
# --------------------------------------------------------------------------

conn = None


def connect(user, password):
    global conn
    conn = psycopg2.connect(user=user, password=password, client_encoding="UTF8", **DB_SETTINGS)


def run(sql, params=None):
    """Выполнить один запрос. Возвращает (названия_колонок, строки)."""
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if cur.description:
                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
            else:
                cols, rows = [], []
        conn.commit()
        return cols, rows
    except Exception:
        conn.rollback()
        raise


def in_transaction(func):
    """Выполнить несколько команд как одну операцию: или все, или ни одной."""
    try:
        with conn.cursor() as cur:
            result = func(cur)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise


def error_text(e):
    """Понятное сообщение об ошибке для пользователя."""
    if isinstance(e, ValueError):
        return str(e)
    if isinstance(e, pgerr.InsufficientPrivilege):
        return "Недостаточно прав у вашей роли для этого действия."
    if isinstance(e, pgerr.UniqueViolation):
        return "Такая запись уже существует (нарушено условие уникальности)."
    if isinstance(e, pgerr.ForeignKeyViolation):
        return "Операция невозможна: запись связана с другими данными."
    if isinstance(e, pgerr.CheckViolation):
        name = getattr(getattr(e, "diag", None), "constraint_name", "") or ""
        return "Введены недопустимые значения (нарушено ограничение %s)." % name
    if isinstance(e, pgerr.RaiseException):
        return e.diag.message_primary
    msg = getattr(getattr(e, "diag", None), "message_primary", None)
    return msg or str(e)


def show_error(e):
    messagebox.showerror("Ошибка", error_text(e))


# ------------------------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ -------------------------
def fmt(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "Да" if v else "Нет"
    if isinstance(v, Decimal):
        return "%.2f" % v
    if isinstance(v, (date, datetime)):
        return v.strftime("%Y-%m-%d")
    return str(v)


def parse_date(text, field="Дата"):
    try:
        return datetime.strptime(text.strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("%s должна быть в формате ГГГГ-ММ-ДД (например 2026-10-19)." % field)


def parse_int(text, field, minimum=0):
    try:
        n = int(text.strip())
    except ValueError:
        raise ValueError("%s должно быть целым числом." % field)
    if n < minimum:
        raise ValueError("%s не может быть меньше %d." % (field, minimum))
    return n


def parse_money(text, field):
    try:
        x = Decimal(text.strip().replace(",", "."))
    except Exception:
        raise ValueError("%s должна быть числом (например 125.50)." % field)
    if x <= 0:
        raise ValueError("%s должна быть больше нуля." % field)
    return x


def options(sql):
    """Запрос вида SELECT id, подпись -> словарь {подпись: id}."""
    _, rows = run(sql)
    return {str(r[1]): r[0] for r in rows}


def pick(combo, mapping, field):
    label = combo.get()
    if label not in mapping:
        raise ValueError("Выберите значение в поле «%s»." % field)
    return mapping[label]


class DataTable(ttk.Frame):
    """Таблица с прокруткой и сортировкой по клику на заголовок."""

    def __init__(self, master, height=10):
        super().__init__(master)
        self.tree = ttk.Treeview(self, show="headings", height=height)
        vs = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        hs = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        hs.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.tree.tag_configure("bad", background="#ffd6d6")
        self.tree.tag_configure("warn", background="#fff0c2")
        self.raw = {}
        self._reverse = {}

    def fill(self, headers, rows, widths=None, tag_func=None):
        cols = ["c%d" % i for i in range(len(headers))]
        self.tree["columns"] = cols
        for i, h in enumerate(headers):
            self.tree.heading(cols[i], text=h, command=lambda c=cols[i]: self.sort_by(c))
            self.tree.column(cols[i], width=(widths[i] if widths else 110), anchor="w")
        self.tree.delete(*self.tree.get_children())
        self.raw = {}
        for r in rows:
            tag = tag_func(r) if tag_func else ""
            iid = self.tree.insert("", "end", values=[fmt(v) for v in r], tags=(tag,) if tag else ())
            self.raw[iid] = r

    def sort_by(self, col):
        items = [(self.tree.set(i, col), i) for i in self.tree.get_children("")]

        def key(x):
            try:
                return (0, float(x[0].replace(" ", "").replace(",", ".")), "")
            except ValueError:
                return (1, 0.0, x[0].lower())

        rev = self._reverse.get(col, False)
        items.sort(key=key, reverse=rev)
        for idx, (_, iid) in enumerate(items):
            self.tree.move(iid, "", idx)
        self._reverse[col] = not rev

    def selected_raw(self):
        sel = self.tree.selection()
        return self.raw.get(sel[0]) if sel else None


def expiry_tag(days_left_index):
    def f(row):
        d = row[days_left_index]
        if d is None:
            return ""
        if d < 0:
            return "bad"
        if d <= 90:
            return "warn"
        return ""
    return f


# ------------------------------- ПРИЛОЖЕНИЕ --------------------------------
class App:
    def __init__(self, root, user):
        self.root = root
        root.title("Склад аптеки — пользователь: %s" % user)
        root.geometry("1180x720")
        self.nb = ttk.Notebook(root)
        self.nb.pack(fill="both", expand=True, padx=6, pady=6)
        self.tab_products = ttk.Frame(self.nb)
        self.tab_receipt = ttk.Frame(self.nb)
        self.tab_shipment = ttk.Frame(self.nb)
        self.tab_stock = ttk.Frame(self.nb)
        self.tab_reports = ttk.Frame(self.nb)
        self.nb.add(self.tab_products, text="Форма 1: Товары")
        self.nb.add(self.tab_receipt, text="Форма 2: Приход")
        self.nb.add(self.tab_shipment, text="Форма 3: Отгрузка")
        self.nb.add(self.tab_stock, text="Форма 4: Остатки и поиск")
        self.nb.add(self.tab_reports, text="Отчеты")
        self.build_products()
        self.build_receipt()
        self.build_shipment()
        self.build_stock()
        self.build_reports()
        self.refresh_all()

    # ---------------- общая загрузка справочников ----------------
    def refresh_all(self):
        try:
            self.categories = options("SELECT category_id, category_name FROM categories ORDER BY 2")
            self.manufacturers = options("SELECT manufacturer_id, manufacturer_name FROM manufacturers ORDER BY 2")
            self.suppliers = options("SELECT supplier_id, supplier_name FROM suppliers ORDER BY 2")
            self.employees = options("SELECT employee_id, full_name FROM employees ORDER BY 2")
            self.customers = options("SELECT customer_id, customer_name FROM customers ORDER BY 2")
            self.locations = options("SELECT location_id, location_name FROM storage_locations ORDER BY 2")
            self.products = options("SELECT product_id, product_name FROM products ORDER BY 2")
            _, rows = run(
                "SELECT b.batch_id, p.product_name || ' | серия ' || b.batch_number || ' | до ' || "
                "b.expiry_date || ' | остаток ' || b.quantity, p.base_price "
                "FROM batches b JOIN products p ON p.product_id = b.product_id "
                "WHERE b.quantity > 0 ORDER BY p.product_name, b.expiry_date")
            self.batches = {r[1]: r[0] for r in rows}
            self.batch_price = {r[1]: r[2] for r in rows}
            _, rows = run("SELECT doc_number FROM shipments ORDER BY shipment_date DESC, shipment_id DESC")
            self.shipment_docs = [r[0] for r in rows]
        except Exception as e:
            show_error(e)
            return
        self.cb_category["values"] = list(self.categories)
        self.cb_manuf["values"] = list(self.manufacturers)
        self.rc_supplier["values"] = list(self.suppliers)
        self.rc_employee["values"] = list(self.employees)
        self.rc_product["values"] = list(self.products)
        self.rc_location["values"] = list(self.locations)
        self.sh_customer["values"] = list(self.customers)
        self.sh_employee["values"] = list(self.employees)
        self.sh_batch["values"] = list(self.batches)
        self.st_category["values"] = ["Все категории"] + list(self.categories)
        if not self.st_category.get():
            self.st_category.set("Все категории")
        self.rp_doc["values"] = self.shipment_docs
        self.load_products()
        self.load_receipt_lines()
        self.load_shipment_lines()
        self.search_stock()

    # ---------------- Форма 1: товары ----------------
    def build_products(self):
        t = self.tab_products
        self.pr_table = DataTable(t, height=14)
        self.pr_table.pack(fill="both", expand=True, padx=6, pady=6)
        self.pr_table.tree.bind("<<TreeviewSelect>>", self.on_product_select)
        f = ttk.LabelFrame(t, text="Карточка товара (выберите строку в таблице, чтобы редактировать)")
        f.pack(fill="x", padx=6, pady=6)
        self.pr_name = ttk.Entry(f, width=40)
        self.cb_category = ttk.Combobox(f, width=34, state="readonly")
        self.cb_manuf = ttk.Combobox(f, width=34, state="readonly")
        self.pr_form = ttk.Entry(f, width=24)
        self.pr_unit = ttk.Entry(f, width=10)
        self.pr_barcode = ttk.Entry(f, width=18)
        self.pr_rx = tk.BooleanVar()
        self.pr_min = ttk.Entry(f, width=10)
        self.pr_price = ttk.Entry(f, width=12)
        fields = [("Название", self.pr_name), ("Категория", self.cb_category),
                  ("Производитель", self.cb_manuf), ("Лекарственная форма", self.pr_form),
                  ("Ед. изм.", self.pr_unit), ("Штрихкод (13 цифр)", self.pr_barcode),
                  ("Мин. остаток", self.pr_min), ("Цена, руб.", self.pr_price)]
        for i, (label, w) in enumerate(fields):
            ttk.Label(f, text=label).grid(row=i // 2, column=(i % 2) * 2, sticky="e", padx=4, pady=3)
            w.grid(row=i // 2, column=(i % 2) * 2 + 1, sticky="w", padx=4, pady=3)
        ttk.Checkbutton(f, text="Рецептурный", variable=self.pr_rx).grid(row=4, column=1, sticky="w", padx=4)
        b = ttk.Frame(f)
        b.grid(row=5, column=0, columnspan=4, pady=6)
        ttk.Button(b, text="Добавить", command=self.add_product).pack(side="left", padx=4)
        ttk.Button(b, text="Сохранить изменения", command=self.update_product).pack(side="left", padx=4)
        ttk.Button(b, text="Удалить", command=self.delete_product).pack(side="left", padx=4)
        ttk.Button(b, text="Очистить форму", command=self.clear_product).pack(side="left", padx=4)

    def load_products(self):
        try:
            _, rows = run(
                "SELECT p.product_id, p.product_name, c.category_name, m.manufacturer_name, p.dosage_form, "
                "p.unit, p.barcode, p.is_prescription, p.min_stock, p.base_price "
                "FROM products p JOIN categories c ON c.category_id = p.category_id "
                "JOIN manufacturers m ON m.manufacturer_id = p.manufacturer_id ORDER BY p.product_name")
        except Exception as e:
            show_error(e)
            return
        self.pr_table.fill(["ID", "Название", "Категория", "Производитель", "Форма", "Ед.", "Штрихкод",
                            "Рецепт", "Мин.ост.", "Цена"], rows,
                           widths=[40, 250, 190, 120, 130, 40, 110, 60, 70, 70])

    def on_product_select(self, _event=None):
        r = self.pr_table.selected_raw()
        if not r:
            return
        self.pr_name.delete(0, "end"); self.pr_name.insert(0, r[1])
        self.cb_category.set(r[2]); self.cb_manuf.set(r[3])
        self.pr_form.delete(0, "end"); self.pr_form.insert(0, r[4])
        self.pr_unit.delete(0, "end"); self.pr_unit.insert(0, r[5])
        self.pr_barcode.delete(0, "end"); self.pr_barcode.insert(0, r[6])
        self.pr_rx.set(bool(r[7]))
        self.pr_min.delete(0, "end"); self.pr_min.insert(0, str(r[8]))
        self.pr_price.delete(0, "end"); self.pr_price.insert(0, fmt(r[9]))

    def clear_product(self):
        for e in (self.pr_name, self.pr_form, self.pr_unit, self.pr_barcode, self.pr_min, self.pr_price):
            e.delete(0, "end")
        self.cb_category.set(""); self.cb_manuf.set(""); self.pr_rx.set(False)

    def read_product_form(self):
        name = self.pr_name.get().strip()
        if not name:
            raise ValueError("Введите название товара.")
        barcode = self.pr_barcode.get().strip()
        if not (barcode.isdigit() and len(barcode) == 13):
            raise ValueError("Штрихкод должен состоять ровно из 13 цифр.")
        form = self.pr_form.get().strip()
        if not form:
            raise ValueError("Введите лекарственную форму.")
        return (name, pick(self.cb_category, self.categories, "Категория"),
                pick(self.cb_manuf, self.manufacturers, "Производитель"), form,
                self.pr_unit.get().strip() or "уп.", barcode, self.pr_rx.get(),
                parse_int(self.pr_min.get() or "0", "Мин. остаток"),
                parse_money(self.pr_price.get(), "Цена"))

    def add_product(self):
        try:
            v = self.read_product_form()
            run("INSERT INTO products (product_name, category_id, manufacturer_id, dosage_form, unit, barcode, "
                "is_prescription, min_stock, base_price) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", v)
        except Exception as e:
            return show_error(e)
        self.refresh_all(); self.clear_product()
        messagebox.showinfo("Готово", "Товар добавлен.")

    def update_product(self):
        r = self.pr_table.selected_raw()
        if not r:
            return messagebox.showwarning("Внимание", "Сначала выберите товар в таблице.")
        try:
            v = self.read_product_form()
            run("UPDATE products SET product_name=%s, category_id=%s, manufacturer_id=%s, dosage_form=%s, unit=%s, "
                "barcode=%s, is_prescription=%s, min_stock=%s, base_price=%s WHERE product_id=%s", v + (r[0],))
        except Exception as e:
            return show_error(e)
        self.refresh_all()
        messagebox.showinfo("Готово", "Изменения сохранены.")

    def delete_product(self):
        r = self.pr_table.selected_raw()
        if not r:
            return messagebox.showwarning("Внимание", "Сначала выберите товар в таблице.")
        if not messagebox.askyesno("Подтверждение", "Удалить товар «%s»?" % r[1]):
            return
        try:
            run("DELETE FROM products WHERE product_id=%s", (r[0],))
        except Exception as e:
            return show_error(e)
        self.refresh_all(); self.clear_product()

    # ---------------- Форма 2: приход ----------------
    def build_receipt(self):
        t = self.tab_receipt
        f = ttk.LabelFrame(t, text="Приходная накладная (если номер уже есть — добавится еще одна строка в нее)")
        f.pack(fill="x", padx=6, pady=6)
        self.rc_doc = ttk.Entry(f, width=20)
        self.rc_date = ttk.Entry(f, width=14)
        self.rc_date.insert(0, date.today().isoformat())
        self.rc_supplier = ttk.Combobox(f, width=34, state="readonly")
        self.rc_employee = ttk.Combobox(f, width=34, state="readonly")
        self.rc_product = ttk.Combobox(f, width=40, state="readonly")
        self.rc_batch = ttk.Entry(f, width=20)
        self.rc_mfg = ttk.Entry(f, width=14)
        self.rc_exp = ttk.Entry(f, width=14)
        self.rc_location = ttk.Combobox(f, width=34, state="readonly")
        self.rc_qty = ttk.Entry(f, width=10)
        self.rc_price = ttk.Entry(f, width=12)
        fields = [("Номер накладной", self.rc_doc), ("Дата (ГГГГ-ММ-ДД)", self.rc_date),
                  ("Поставщик", self.rc_supplier), ("Принял сотрудник", self.rc_employee),
                  ("Товар", self.rc_product), ("Номер серии", self.rc_batch),
                  ("Дата производства", self.rc_mfg), ("Срок годности до", self.rc_exp),
                  ("Место хранения", self.rc_location), ("Количество", self.rc_qty),
                  ("Закупочная цена", self.rc_price)]
        for i, (label, w) in enumerate(fields):
            ttk.Label(f, text=label).grid(row=i // 2, column=(i % 2) * 2, sticky="e", padx=4, pady=3)
            w.grid(row=i // 2, column=(i % 2) * 2 + 1, sticky="w", padx=4, pady=3)
        ttk.Button(f, text="Провести приход", command=self.save_receipt).grid(row=6, column=0, columnspan=4, pady=8)
        ttk.Label(t, text="Последние строки приходов:").pack(anchor="w", padx=8)
        self.rc_table = DataTable(t, height=10)
        self.rc_table.pack(fill="both", expand=True, padx=6, pady=6)

    def load_receipt_lines(self):
        try:
            _, rows = run(
                "SELECT r.doc_number, r.receipt_date, s.supplier_name, p.product_name, b.batch_number, "
                "ri.quantity, ri.purchase_price FROM receipt_items ri "
                "JOIN receipts r ON r.receipt_id = ri.receipt_id JOIN suppliers s ON s.supplier_id = r.supplier_id "
                "JOIN batches b ON b.batch_id = ri.batch_id JOIN products p ON p.product_id = b.product_id "
                "ORDER BY r.receipt_date DESC, ri.item_id DESC LIMIT 30")
        except Exception as e:
            return show_error(e)
        self.rc_table.fill(["Накладная", "Дата", "Поставщик", "Товар", "Серия", "Кол-во", "Цена"], rows,
                           widths=[100, 90, 200, 260, 120, 70, 80])

    def save_receipt(self):
        try:
            doc = self.rc_doc.get().strip()
            if not doc:
                raise ValueError("Введите номер накладной.")
            d = parse_date(self.rc_date.get(), "Дата накладной")
            supplier = pick(self.rc_supplier, self.suppliers, "Поставщик")
            emp = pick(self.rc_employee, self.employees, "Принял сотрудник")
            prod = pick(self.rc_product, self.products, "Товар")
            number = self.rc_batch.get().strip()
            if not number:
                raise ValueError("Введите номер серии.")
            mfg = parse_date(self.rc_mfg.get(), "Дата производства")
            exp = parse_date(self.rc_exp.get(), "Срок годности")
            if exp <= mfg:
                raise ValueError("Срок годности должен быть позже даты производства.")
            loc = pick(self.rc_location, self.locations, "Место хранения")
            qty = parse_int(self.rc_qty.get(), "Количество", 1)
            price = parse_money(self.rc_price.get(), "Закупочная цена")

            def work(cur):
                cur.execute("SELECT receipt_id FROM receipts WHERE doc_number=%s", (doc,))
                r = cur.fetchone()
                if r:
                    rid = r[0]
                else:
                    cur.execute("INSERT INTO receipts (doc_number, receipt_date, supplier_id, employee_id) "
                                "VALUES (%s,%s,%s,%s) RETURNING receipt_id", (doc, d, supplier, emp))
                    rid = cur.fetchone()[0]
                cur.execute("SELECT batch_id FROM batches WHERE product_id=%s AND batch_number=%s", (prod, number))
                b = cur.fetchone()
                if b:
                    bid = b[0]
                else:
                    cur.execute("INSERT INTO batches (product_id, batch_number, manufacture_date, expiry_date, "
                                "location_id, quantity) VALUES (%s,%s,%s,%s,%s,0) RETURNING batch_id",
                                (prod, number, mfg, exp, loc))
                    bid = cur.fetchone()[0]
                cur.execute("INSERT INTO receipt_items (receipt_id, batch_id, quantity, purchase_price) "
                            "VALUES (%s,%s,%s,%s)", (rid, bid, qty, price))

            in_transaction(work)
        except Exception as e:
            return show_error(e)
        for e_ in (self.rc_batch, self.rc_mfg, self.rc_exp, self.rc_qty, self.rc_price):
            e_.delete(0, "end")
        self.refresh_all()
        messagebox.showinfo("Готово", "Приход проведен, остаток увеличен.")

    # ---------------- Форма 3: отгрузка ----------------
    def build_shipment(self):
        t = self.tab_shipment
        f = ttk.LabelFrame(t, text="Накладная на отгрузку (если номер уже есть — добавится еще одна строка в нее)")
        f.pack(fill="x", padx=6, pady=6)
        self.sh_doc = ttk.Entry(f, width=20)
        self.sh_date = ttk.Entry(f, width=14)
        self.sh_date.insert(0, date.today().isoformat())
        self.sh_customer = ttk.Combobox(f, width=34, state="readonly")
        self.sh_employee = ttk.Combobox(f, width=34, state="readonly")
        self.sh_batch = ttk.Combobox(f, width=80, state="readonly")
        self.sh_batch.bind("<<ComboboxSelected>>", self.on_batch_pick)
        self.sh_qty = ttk.Entry(f, width=10)
        self.sh_price = ttk.Entry(f, width=12)
        fields = [("Номер накладной", self.sh_doc, 0, 0), ("Дата (ГГГГ-ММ-ДД)", self.sh_date, 0, 2),
                  ("Клиент", self.sh_customer, 1, 0), ("Отпустил сотрудник", self.sh_employee, 1, 2),
                  ("Серия товара", self.sh_batch, 2, 0), ("Количество", self.sh_qty, 3, 0),
                  ("Цена за единицу", self.sh_price, 3, 2)]
        for label, w, r, c in fields:
            ttk.Label(f, text=label).grid(row=r, column=c, sticky="e", padx=4, pady=3)
            w.grid(row=r, column=c + 1, sticky="w", padx=4, pady=3, columnspan=3 if w is self.sh_batch else 1)
        ttk.Button(f, text="Провести отгрузку", command=self.save_shipment).grid(row=4, column=0, columnspan=4, pady=8)
        ttk.Label(t, text="Последние строки отгрузок:").pack(anchor="w", padx=8)
        self.sh_table = DataTable(t, height=10)
        self.sh_table.pack(fill="both", expand=True, padx=6, pady=6)

    def on_batch_pick(self, _event=None):
        price = self.batch_price.get(self.sh_batch.get())
        if price is not None:
            self.sh_price.delete(0, "end")
            self.sh_price.insert(0, fmt(price))

    def load_shipment_lines(self):
        try:
            _, rows = run(
                "SELECT sh.doc_number, sh.shipment_date, c.customer_name, p.product_name, b.batch_number, "
                "si.quantity, si.sale_price FROM shipment_items si "
                "JOIN shipments sh ON sh.shipment_id = si.shipment_id JOIN customers c ON c.customer_id = sh.customer_id "
                "JOIN batches b ON b.batch_id = si.batch_id JOIN products p ON p.product_id = b.product_id "
                "ORDER BY sh.shipment_date DESC, si.item_id DESC LIMIT 30")
        except Exception as e:
            return show_error(e)
        self.sh_table.fill(["Накладная", "Дата", "Клиент", "Товар", "Серия", "Кол-во", "Цена"], rows,
                           widths=[100, 90, 200, 260, 120, 70, 80])

    def save_shipment(self):
        try:
            doc = self.sh_doc.get().strip()
            if not doc:
                raise ValueError("Введите номер накладной.")
            d = parse_date(self.sh_date.get(), "Дата накладной")
            cust = pick(self.sh_customer, self.customers, "Клиент")
            emp = pick(self.sh_employee, self.employees, "Отпустил сотрудник")
            bid = pick(self.sh_batch, self.batches, "Серия товара")
            qty = parse_int(self.sh_qty.get(), "Количество", 1)
            price = parse_money(self.sh_price.get(), "Цена за единицу")

            def work(cur):
                cur.execute("SELECT shipment_id FROM shipments WHERE doc_number=%s", (doc,))
                r = cur.fetchone()
                if r:
                    sid = r[0]
                else:
                    cur.execute("INSERT INTO shipments (doc_number, shipment_date, customer_id, employee_id) "
                                "VALUES (%s,%s,%s,%s) RETURNING shipment_id", (doc, d, cust, emp))
                    sid = cur.fetchone()[0]
                cur.execute("INSERT INTO shipment_items (shipment_id, batch_id, quantity, sale_price) "
                            "VALUES (%s,%s,%s,%s)", (sid, bid, qty, price))

            in_transaction(work)
        except Exception as e:
            return show_error(e)
        self.sh_qty.delete(0, "end")
        self.sh_batch.set("")
        self.refresh_all()
        messagebox.showinfo("Готово", "Отгрузка проведена, остаток уменьшен.")

    # ---------------- Форма 4: остатки и поиск ----------------
    def build_stock(self):
        t = self.tab_stock
        f = ttk.LabelFrame(t, text="Поиск и фильтры")
        f.pack(fill="x", padx=6, pady=6)
        ttk.Label(f, text="Название содержит:").grid(row=0, column=0, padx=4, pady=4)
        self.st_name = ttk.Entry(f, width=28)
        self.st_name.grid(row=0, column=1, padx=4)
        ttk.Label(f, text="Категория:").grid(row=0, column=2, padx=4)
        self.st_category = ttk.Combobox(f, width=32, state="readonly")
        self.st_category.grid(row=0, column=3, padx=4)
        self.st_exp = tk.BooleanVar()
        self.st_nonzero = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, text="Срок годности ≤ 90 дней (и просроченные)", variable=self.st_exp).grid(row=1, column=0, columnspan=2, sticky="w", padx=4)
        ttk.Checkbutton(f, text="Только с остатком > 0", variable=self.st_nonzero).grid(row=1, column=2, columnspan=2, sticky="w", padx=4)
        ttk.Button(f, text="Найти", command=self.search_stock).grid(row=0, column=4, padx=8)
        ttk.Button(f, text="Сбросить", command=self.reset_stock).grid(row=1, column=4, padx=8)
        ttk.Label(t, text="Красный — просрочено, желтый — срок истекает в ближайшие 90 дней. "
                          "Клик по заголовку столбца — сортировка.").pack(anchor="w", padx=8)
        self.st_table = DataTable(t, height=18)
        self.st_table.pack(fill="both", expand=True, padx=6, pady=6)
        self.st_total = ttk.Label(t, text="")
        self.st_total.pack(anchor="w", padx=8, pady=2)

    def reset_stock(self):
        self.st_name.delete(0, "end")
        self.st_category.set("Все категории")
        self.st_exp.set(False)
        self.st_nonzero.set(True)
        self.search_stock()

    def search_stock(self):
        sql = ("SELECT product_name, category_name, batch_number, expiry_date, days_left, location_name, quantity "
               "FROM v_batch_stock WHERE 1=1")
        params = []
        if self.st_name.get().strip():
            sql += " AND product_name ILIKE %s"
            params.append("%" + self.st_name.get().strip() + "%")
        cat = self.st_category.get()
        if cat and cat != "Все категории":
            sql += " AND category_name = %s"
            params.append(cat)
        if self.st_exp.get():
            sql += " AND days_left <= 90"
        if self.st_nonzero.get():
            sql += " AND quantity > 0"
        sql += " ORDER BY product_name, expiry_date"
        try:
            _, rows = run(sql, params)
        except Exception as e:
            return show_error(e)
        self.st_table.fill(["Товар", "Категория", "Серия", "Годен до", "Дней до конца", "Место", "Остаток"], rows,
                           widths=[260, 200, 120, 90, 100, 170, 70], tag_func=expiry_tag(4))
        self.st_total.config(text="Найдено серий: %d, всего единиц: %d" % (len(rows), sum(r[6] for r in rows)))

    # ---------------- Отчеты ----------------
    def build_reports(self):
        t = self.tab_reports
        top = ttk.LabelFrame(t, text="Выберите отчет")
        top.pack(fill="x", padx=6, pady=6)
        ttk.Label(top, text="Накладная отгрузки №").grid(row=0, column=0, padx=4, pady=4)
        self.rp_doc = ttk.Combobox(top, width=18, state="readonly")
        self.rp_doc.grid(row=0, column=1)
        ttk.Button(top, text="Отчет 1: Накладная на отгрузку", command=self.report_shipment).grid(row=0, column=2, padx=8)
        ttk.Label(top, text="Период с").grid(row=1, column=0, sticky="e", padx=4, pady=4)
        self.rp_from = ttk.Entry(top, width=14)
        self.rp_from.insert(0, "%d-01-01" % date.today().year)
        self.rp_from.grid(row=1, column=1, sticky="w")
        ttk.Label(top, text="по").grid(row=1, column=1, sticky="e", padx=(0, 90))
        self.rp_to = ttk.Entry(top, width=14)
        self.rp_to.insert(0, date.today().isoformat())
        self.rp_to.grid(row=1, column=1, sticky="e")
        ttk.Button(top, text="Отчет 2: Приход за период", command=self.report_receipts).grid(row=1, column=2, padx=8)
        ttk.Button(top, text="Отчет 3: Остатки по категориям (сводный)", command=self.report_categories).grid(row=0, column=3, padx=8)
        ttk.Button(top, text="Отчет 4: Дефицит товаров", command=self.report_shortage).grid(row=1, column=3, padx=8)
        ttk.Button(top, text="Отчет 5: Сроки годности", command=self.report_expiry).grid(row=0, column=4, padx=8)
        self.rp_title = ttk.Label(t, text="Отчет не выбран", font=("Segoe UI", 12, "bold"))
        self.rp_title.pack(anchor="w", padx=8)
        self.rp_sub = ttk.Label(t, text="")
        self.rp_sub.pack(anchor="w", padx=8)
        self.rp_table = DataTable(t, height=16)
        self.rp_table.pack(fill="both", expand=True, padx=6, pady=6)
        self.rp_footer = ttk.Label(t, text="", font=("Segoe UI", 10, "bold"))
        self.rp_footer.pack(anchor="w", padx=8)
        b = ttk.Frame(t)
        b.pack(pady=6)
        ttk.Button(b, text="Сохранить в CSV (Excel)", command=lambda: self.export("csv")).pack(side="left", padx=6)
        ttk.Button(b, text="Сохранить в HTML (для печати)", command=lambda: self.export("html")).pack(side="left", padx=6)
        self.rp_data = None

    def show_report(self, title, sub, headers, rows, footer="", widths=None, tag_func=None):
        self.rp_title.config(text=title)
        self.rp_sub.config(text=sub)
        self.rp_table.fill(headers, rows, widths=widths, tag_func=tag_func)
        self.rp_footer.config(text=footer)
        self.rp_data = (title, sub, headers, [[fmt(v) for v in r] for r in rows], footer)

    def report_shipment(self):
        doc = self.rp_doc.get()
        if not doc:
            return messagebox.showwarning("Внимание", "Выберите номер накладной.")
        try:
            _, h = run("SELECT sh.shipment_date, c.customer_name, e.full_name FROM shipments sh "
                       "JOIN customers c ON c.customer_id = sh.customer_id "
                       "JOIN employees e ON e.employee_id = sh.employee_id WHERE sh.doc_number=%s", (doc,))
            _, rows = run("SELECT p.product_name, b.batch_number, b.expiry_date, si.quantity, si.sale_price, "
                          "si.quantity * si.sale_price FROM shipment_items si "
                          "JOIN shipments sh ON sh.shipment_id = si.shipment_id "
                          "JOIN batches b ON b.batch_id = si.batch_id JOIN products p ON p.product_id = b.product_id "
                          "WHERE sh.doc_number=%s ORDER BY p.product_name", (doc,))
        except Exception as e:
            return show_error(e)
        total = sum(r[5] for r in rows)
        sub = "Дата: %s. Клиент: %s. Отпустил: %s" % (fmt(h[0][0]), h[0][1], h[0][2]) if h else ""
        self.show_report("Накладная на отгрузку № %s" % doc, sub,
                         ["Товар", "Серия", "Годен до", "Кол-во", "Цена", "Сумма"], rows,
                         "ИТОГО: %s руб. Позиций: %d" % (fmt(total), len(rows)), [300, 120, 100, 70, 90, 100])

    def report_receipts(self):
        try:
            d1 = parse_date(self.rp_from.get(), "Начало периода")
            d2 = parse_date(self.rp_to.get(), "Конец периода")
            _, rows = run("SELECT r.receipt_date, r.doc_number, s.supplier_name, p.product_name, b.batch_number, "
                          "ri.quantity, ri.purchase_price, ri.quantity * ri.purchase_price FROM receipt_items ri "
                          "JOIN receipts r ON r.receipt_id = ri.receipt_id JOIN suppliers s ON s.supplier_id = r.supplier_id "
                          "JOIN batches b ON b.batch_id = ri.batch_id JOIN products p ON p.product_id = b.product_id "
                          "WHERE r.receipt_date BETWEEN %s AND %s ORDER BY r.receipt_date, r.doc_number", (d1, d2))
        except Exception as e:
            return show_error(e)
        total = sum(r[7] for r in rows)
        self.show_report("Приход товара за период", "С %s по %s" % (d1, d2),
                         ["Дата", "Накладная", "Поставщик", "Товар", "Серия", "Кол-во", "Цена", "Сумма"], rows,
                         "ИТОГО закуплено на: %s руб. Строк: %d" % (fmt(total), len(rows)),
                         [90, 100, 190, 250, 110, 60, 80, 90])

    def report_categories(self):
        try:
            _, rows = run("SELECT category_name, COUNT(DISTINCT product_id), SUM(quantity), SUM(stock_value) "
                          "FROM v_batch_stock GROUP BY category_name ORDER BY SUM(stock_value) DESC")
        except Exception as e:
            return show_error(e)
        total = sum(r[3] for r in rows)
        self.show_report("Сводный отчет: остатки и их стоимость по категориям", "На %s" % date.today(),
                         ["Категория", "Товаров", "Единиц на складе", "Стоимость, руб."], rows,
                         "ИТОГО стоимость остатков: %s руб." % fmt(total), [300, 90, 150, 140])

    def report_shortage(self):
        try:
            _, rows = run("SELECT product_name, category_name, min_stock, total_qty, min_stock - total_qty "
                          "FROM v_product_stock WHERE total_qty < min_stock ORDER BY 5 DESC")
        except Exception as e:
            return show_error(e)
        self.show_report("Дефицит: остаток ниже минимального", "Товары, которые нужно заказать у поставщика",
                         ["Товар", "Категория", "Мин. остаток", "Сейчас на складе", "Не хватает"], rows,
                         "Позиций в дефиците: %d" % len(rows), [280, 220, 100, 130, 100])

    def report_expiry(self):
        try:
            _, rows = run("SELECT product_name, batch_number, expiry_date, days_left, quantity, location_name "
                          "FROM v_batch_stock WHERE days_left <= 90 AND quantity > 0 ORDER BY expiry_date")
        except Exception as e:
            return show_error(e)
        self.show_report("Контроль сроков годности", "Просроченные и истекающие в ближайшие 90 дней",
                         ["Товар", "Серия", "Годен до", "Дней осталось", "Остаток", "Место"], rows,
                         "Серий к вниманию: %d (красный — уже просрочено)" % len(rows),
                         [280, 120, 100, 110, 80, 180], tag_func=expiry_tag(3))

    def export(self, kind):
        if not self.rp_data:
            return messagebox.showwarning("Внимание", "Сначала сформируйте отчет.")
        title, sub, headers, rows, footer = self.rp_data
        path = filedialog.asksaveasfilename(defaultextension=".%s" % kind, filetypes=[(kind.upper(), "*.%s" % kind)])
        if not path:
            return
        try:
            if kind == "csv":
                with open(path, "w", newline="", encoding="utf-8-sig") as f:
                    w = csv.writer(f, delimiter=";")
                    w.writerow([title])
                    w.writerow([sub])
                    w.writerow(headers)
                    w.writerows(rows)
                    w.writerow([footer])
            else:
                head = "".join("<th>%s</th>" % html.escape(h) for h in headers)
                body = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % html.escape(c) for c in r) for r in rows)
                with open(path, "w", encoding="utf-8") as f:
                    f.write("<html><head><meta charset='utf-8'><title>%s</title><style>"
                            "body{font-family:Arial;margin:30px}table{border-collapse:collapse;width:100%%}"
                            "th,td{border:1px solid #444;padding:5px 8px;font-size:13px}th{background:#eee}"
                            "</style></head><body><h2>%s</h2><p>%s</p><table><tr>%s</tr>%s</table>"
                            "<p><b>%s</b></p><p>Сформировано: %s</p></body></html>"
                            % (html.escape(title), html.escape(title), html.escape(sub), head, body,
                               html.escape(footer), datetime.now().strftime("%Y-%m-%d %H:%M")))
        except OSError as e:
            return messagebox.showerror("Ошибка", "Не удалось сохранить файл: %s" % e)
        messagebox.showinfo("Готово", "Файл сохранен:\n%s" % path)


def main():
    root = tk.Tk()
    root.withdraw()
    user = None
    while True:
        user = simpledialog.askstring("Вход в систему", "Логин пользователя БД:", initialvalue="manager1", parent=root)
        if not user:
            return
        password = simpledialog.askstring("Вход в систему", "Пароль для %s:" % user, show="*", parent=root)
        if password is None:
            return
        try:
            connect(user, password)
            break
        except Exception as e:
            try:
                text = str(e)
            except Exception:
                text = "неверный логин/пароль или сервер PostgreSQL не запущен"
            messagebox.showerror("Ошибка входа", "Не удалось подключиться к базе.\n\n%s" % text, parent=root)
    root.deiconify()
    App(root, user)
    root.mainloop()


if __name__ == "__main__":
    main()
