# Requirements:
# pip install faker mysql-connector-python python-dotenv

import mysql.connector
from faker import Faker
import random
import json
import hashlib
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

fake = Faker()

MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "localhost"),
    "port": int(os.getenv("MYSQL_PORT", 3306)),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", "1234"),
    "database": os.getenv("MYSQL_DATABASE", "migration_db"),
}

ROWS_PER_TABLE = 10_000  # ~1M total across 100 tables


def connect_db():
    """Establishes and returns a connection to the MySQL server."""
    try:
        conn = mysql.connector.connect(
            host=MYSQL_CONFIG["host"],
            port=MYSQL_CONFIG["port"],
            user=MYSQL_CONFIG["user"],
            password=MYSQL_CONFIG["password"],
            database=MYSQL_CONFIG["database"]
        )
        return conn
    except Exception as e:
        print(f"[FAIL] Connection to MySQL failed: {e}")
        raise e


def check_and_initialize_schema(conn):
    """Checks if the database and required tables exist in MySQL. If not, runs schema.sql."""
    cursor = conn.cursor()
    try:
        # Check if database exists
        cursor.execute("SHOW DATABASES LIKE %s", (MYSQL_CONFIG["database"],))
        db_exists = cursor.fetchone()
        
        table_count = 0
        if db_exists:
            # Switch to database
            cursor.execute(f"USE `{MYSQL_CONFIG['database']}`")
            cursor.execute("SHOW TABLES")
            table_count = len(cursor.fetchall())
            
        if not db_exists or table_count < 100:
            print(f"MySQL Schema status: exists={bool(db_exists)}, tables={table_count}. Expected 100 tables.")
            print("Initializing MySQL schema from schema.sql...")
            script_dir = os.path.dirname(os.path.abspath(__file__))
            schema_path = os.path.join(script_dir, "schema.sql")
            with open(schema_path, "r", encoding="utf-8") as f:
                sql = f.read()
            
            # Split SQL file by semicolons, filtering out comments and empty statements
            statements = []
            current_stmt = []
            for line in sql.splitlines():
                stripped = line.strip()
                if stripped.startswith("--") or not stripped:
                    continue
                current_stmt.append(line)
                if stripped.endswith(";"):
                    statements.append("\n".join(current_stmt))
                    current_stmt = []
                    
            for stmt in statements:
                stmt_str = stmt.strip()
                if stmt_str:
                    cursor.execute(stmt_str)
            conn.commit()
            print("[OK] MySQL Schema and tables initialized successfully.")
        else:
            print(f"[OK] MySQL Schema has {table_count} tables. Ready for data generation.")
            # Ensure database is selected
            cursor.execute(f"USE `{MYSQL_CONFIG['database']}`")
    except Exception as e:
        conn.rollback()
        print(f"[FAIL] MySQL Schema verification/initialization failed: {e}")
        raise e
    finally:
        cursor.close()


def truncate_tables(conn):
    """Truncates all tables in the schema using FOREIGN_KEY_CHECKS to allow multiple runs."""
    cursor = conn.cursor()
    try:
        cursor.execute(f"USE `{MYSQL_CONFIG['database']}`")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        cursor.execute("SHOW TABLES")
        tables = [row[0] for row in cursor.fetchall()]
        for table in tables:
            cursor.execute(f"TRUNCATE TABLE `{table}`")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        conn.commit()
        print("[OK] All existing MySQL tables truncated successfully.")
    except Exception as e:
        conn.rollback()
        print(f"[FAIL] MySQL Truncation failed: {e}")
        raise e
    finally:
        cursor.close()


def insert_batch(conn, query, data, table_name):
    """Inserts a batch of rows in MySQL using optimized multi-row INSERTs."""
    if not data:
        return
    cursor = conn.cursor()
    
    # query is like: "INSERT INTO countries (name, iso_code) VALUES %s"
    # We replace "VALUES %s" with multi-row placeholders: "VALUES (%s, %s), (%s, %s)..."
    parts = query.split(" VALUES ")
    if len(parts) != 2:
        parts = query.split(" values ")
    prefix = parts[0]
    num_cols = len(data[0])
    
    chunk_size = 1000
    try:
        # Switch to database just in case
        cursor.execute(f"USE `{MYSQL_CONFIG['database']}`")
        for i in range(0, len(data), chunk_size):
            chunk = data[i:i+chunk_size]
            row_placeholder = "(" + ", ".join(["%s"] * num_cols) + ")"
            placeholders = ", ".join([row_placeholder] * len(chunk))
            mysql_query = f"{prefix} VALUES {placeholders}"
            
            # Flatten the chunk values
            flat_vals = []
            for row in chunk:
                # Replace dict/list with json string for MySQL JSON columns
                processed_row = []
                for val in row:
                    if isinstance(val, (dict, list)):
                        processed_row.append(json.dumps(val))
                    else:
                        processed_row.append(val)
                flat_vals.extend(processed_row)
                
            cursor.execute(mysql_query, flat_vals)
        conn.commit()
        print(f"[OK] Inserted {len(data):,} rows into {table_name}")
    except Exception as e:
        conn.rollback()
        print(f"[FAIL] Failed to insert rows into {table_name}: {e}")
        raise e
    finally:
        cursor.close()


# ============================================================
# SECTION 1: E-COMMERCE DEPENDENT TABLES (20)
# ============================================================

def insert_countries(conn):
    """Inserts 10,000 countries."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        name = f"Country {i} {fake.country()}"[:100]
        iso_code = f"C{i}"
        data.append((name, iso_code))
    query = f"INSERT INTO countries (name, iso_code) VALUES %s"
    insert_batch(conn, query, data, "countries")


def insert_regions(conn):
    """Inserts 10,000 regions."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        country_id = i
        name = f"Region {i} {fake.state()}"[:100]
        code = f"REG-{i}"
        data.append((country_id, name, code))
    query = f"INSERT INTO regions (country_id, name, code) VALUES %s"
    insert_batch(conn, query, data, "regions")


def insert_addresses(conn):
    """Inserts 10,000 addresses."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        region_id = i
        street_address = fake.street_address()[:255]
        city = fake.city()[:100]
        postal_code = fake.postcode()[:20]
        data.append((region_id, street_address, city, postal_code))
    query = f"INSERT INTO addresses (region_id, street_address, city, postal_code) VALUES %s"
    insert_batch(conn, query, data, "addresses")


def insert_customers(conn):
    """Inserts 10,000 customers."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        address_id = i
        first_name = fake.first_name()[:100]
        last_name = fake.last_name()[:100]
        email = f"customer_{i}_{fake.email()}"[:150]
        phone = fake.phone_number()[:50]
        data.append((address_id, first_name, last_name, email, phone))
    query = f"INSERT INTO customers (address_id, first_name, last_name, email, phone) VALUES %s"
    insert_batch(conn, query, data, "customers")


def insert_suppliers(conn):
    """Inserts 10,000 suppliers."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        name = f"Supplier {i} {fake.company()}"[:150]
        contact_name = fake.name()[:100]
        email = f"supplier_{i}_{fake.email()}"[:150]
        phone = fake.phone_number()[:50]
        data.append((name, contact_name, email, phone))
    query = f"INSERT INTO suppliers (name, contact_name, email, phone) VALUES %s"
    insert_batch(conn, query, data, "suppliers")


def insert_products(conn):
    """Inserts 10,000 products."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        name = f"Product {i} {fake.catch_phrase()[:100]}"[:150]
        sku = f"PROD-SKU-{i:05d}-{fake.hexify(text='^^^^')}"
        description = fake.paragraph()
        price = round(random.uniform(1, 9999), 2)
        data.append((name, sku, description, price))
    query = f"INSERT INTO products (name, sku, description, price) VALUES %s"
    insert_batch(conn, query, data, "products")


def insert_product_categories(conn):
    """Inserts 10,000 product categories."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        name = f"Category {i} {fake.bs()[:80]}"[:100]
        description = fake.sentence()
        data.append((name, description))
    query = f"INSERT INTO product_categories (name, description) VALUES %s"
    insert_batch(conn, query, data, "product_categories")


def insert_product_variants(conn):
    """Inserts 10,000 product variants."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        product_id = i
        category_id = i
        sku = f"VAR-SKU-{i:05d}-{fake.hexify(text='^^^^')}"
        price_modifier = round(random.uniform(-50, 150), 2)
        option_name = random.choice(["Size", "Color", "Material", "Style"])[:50]
        option_value = random.choice(["S", "M", "L", "XL", "Red", "Blue", "Green", "Cotton", "Wool", "Classic", "Modern"])[:50]
        data.append((product_id, category_id, sku, price_modifier, option_name, option_value))
    query = f"INSERT INTO product_variants (product_id, category_id, sku, price_modifier, option_name, option_value) VALUES %s"
    insert_batch(conn, query, data, "product_variants")


def insert_inventory(conn):
    """Inserts 10,000 inventory items."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        variant_id = i
        quantity = random.randint(0, 1000)
        warehouse_code = f"WH-{random.randint(1, 100)}"
        data.append((variant_id, quantity, warehouse_code))
    query = f"INSERT INTO inventory (variant_id, quantity, warehouse_code) VALUES %s"
    insert_batch(conn, query, data, "inventory")


def insert_payment_methods(conn):
    """Inserts 10,000 payment methods."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        name = f"Payment Method {i} {fake.credit_card_provider()}"[:50]
        is_active = random.choice([True, False])
        data.append((name, is_active))
    query = f"INSERT INTO payment_methods (name, is_active) VALUES %s"
    insert_batch(conn, query, data, "payment_methods")


def insert_orders(conn):
    """Inserts 10,000 orders."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        customer_id = i
        payment_method_id = i
        order_number = f"ORD-{i:06d}-{fake.hexify(text='^^^^')}"
        total_amount = round(random.uniform(5, 5000), 2)
        status = random.choice(["Pending", "Processing", "Shipped", "Delivered", "Cancelled", "Refunded"])[:50]
        data.append((customer_id, payment_method_id, order_number, total_amount, status))
    query = f"INSERT INTO orders (customer_id, payment_method_id, order_number, total_amount, status) VALUES %s"
    insert_batch(conn, query, data, "orders")


def insert_order_items(conn):
    """Inserts 10,000 order items."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        order_id = i
        variant_id = i
        quantity = random.randint(1, 10)
        unit_price = round(random.uniform(1, 1000), 2)
        data.append((order_id, variant_id, quantity, unit_price))
    query = f"INSERT INTO order_items (order_id, variant_id, quantity, unit_price) VALUES %s"
    insert_batch(conn, query, data, "order_items")


def insert_supplier_products(conn):
    """Inserts 10,000 supplier products."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        supplier_id = i
        product_id = i
        wholesale_price = round(random.uniform(1, 5000), 2)
        lead_time_days = random.randint(1, 45)
        data.append((supplier_id, product_id, wholesale_price, lead_time_days))
    query = f"INSERT INTO supplier_products (supplier_id, product_id, wholesale_price, lead_time_days) VALUES %s"
    insert_batch(conn, query, data, "supplier_products")


def insert_payments(conn):
    """Inserts 10,000 payments."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        order_id = i
        payment_method_id = i
        transaction_reference = f"TXN-{i:07d}-{fake.hexify(text='^^^^')}"
        amount = round(random.uniform(5, 5000), 2)
        status = random.choice(["Successful", "Failed", "Pending"])[:50]
        data.append((order_id, payment_method_id, transaction_reference, amount, status))
    query = f"INSERT INTO payments (order_id, payment_method_id, transaction_reference, amount, status) VALUES %s"
    insert_batch(conn, query, data, "payments")


def insert_coupons(conn):
    """Inserts 10,000 coupons."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        code = f"COUPON-{i:05d}-{fake.hexify(text='^^^^')}"
        discount_type = random.choice(["Percentage", "Flat"])[:20]
        discount_value = round(random.uniform(1, 100), 2)
        expires_at = datetime.now() + timedelta(days=random.randint(1, 365))
        data.append((code, discount_type, discount_value, expires_at))
    query = f"INSERT INTO coupons (code, discount_type, discount_value, expires_at) VALUES %s"
    insert_batch(conn, query, data, "coupons")


def insert_coupon_usage(conn):
    """Inserts 10,000 coupon usage records."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        coupon_id = i
        customer_id = i
        used_at = datetime.now() - timedelta(days=random.randint(0, 30))
        data.append((coupon_id, customer_id, used_at))
    query = f"INSERT INTO coupon_usage (coupon_id, customer_id, used_at) VALUES %s"
    insert_batch(conn, query, data, "coupon_usage")


def insert_shipment_tracking(conn):
    """Inserts 10,000 shipment tracking records."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        order_id = i
        tracking_number = f"TRACK-{i:07d}-{fake.hexify(text='^^^^')}"
        carrier = random.choice(["FedEx", "UPS", "DHL", "USPS"])[:50]
        status = random.choice(["Pre-Transit", "In Transit", "Out for Delivery", "Delivered", "Exception"])[:50]
        shipped_at = datetime.now() - timedelta(days=random.randint(1, 10))
        data.append((order_id, tracking_number, carrier, status, shipped_at))
    query = f"INSERT INTO shipment_tracking (order_id, tracking_number, carrier, status, shipped_at) VALUES %s"
    insert_batch(conn, query, data, "shipment_tracking")


def insert_reviews(conn):
    """Inserts 10,000 reviews."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        customer_id = i
        product_id = i
        rating = random.randint(1, 5)
        review_text = fake.paragraph()
        data.append((customer_id, product_id, rating, review_text))
    query = f"INSERT INTO reviews (customer_id, product_id, rating, review_text) VALUES %s"
    insert_batch(conn, query, data, "reviews")


def insert_carts(conn):
    """Inserts 10,000 carts."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        customer_id = i
        data.append((customer_id,))
    query = f"INSERT INTO carts (customer_id) VALUES %s"
    insert_batch(conn, query, data, "carts")


def insert_cart_items(conn):
    """Inserts 10,000 cart items."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        cart_id = i
        variant_id = i
        quantity = random.randint(1, 5)
        data.append((cart_id, variant_id, quantity))
    query = f"INSERT INTO cart_items (cart_id, variant_id, quantity) VALUES %s"
    insert_batch(conn, query, data, "cart_items")


# ============================================================
# SECTION 2: INDEPENDENT TABLES (80)
# ============================================================

# --- Domain: HR / Employees (11 tables) ---

def insert_employees(conn):
    """Inserts 10,000 employees."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        first_name = fake.first_name()[:50]
        last_name = fake.last_name()[:50]
        email = f"emp_{i}_{fake.email()}"[:100]
        phone_number = fake.phone_number()[:50]
        hire_date = fake.date_between(start_date='-10y', end_date='today')
        status = random.choice(["Active", "Inactive", "Suspended", "On Leave"])[:20]
        data.append((first_name, last_name, email, phone_number, hire_date, status))
    query = f"INSERT INTO employees (first_name, last_name, email, phone_number, hire_date, status) VALUES %s"
    insert_batch(conn, query, data, "employees")


def insert_departments(conn):
    """Inserts 10,000 departments."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        dept_name = f"Department {i} {fake.job()}"[:100]
        code = f"DEPT-{i}"
        budget = round(random.uniform(50000, 2000000), 2)
        manager_name = fake.name()[:100]
        data.append((dept_name, code, budget, manager_name))
    query = f"INSERT INTO departments (dept_name, code, budget, manager_name) VALUES %s"
    insert_batch(conn, query, data, "departments")


def insert_job_roles(conn):
    """Inserts 10,000 job roles."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        title = f"Role {i} {fake.job()}"[:100]
        description = fake.sentence()
        min_salary = round(random.uniform(30000, 80000), 2)
        max_salary = round(random.uniform(85000, 250000), 2)
        grade = random.choice(["G1", "G2", "G3", "G4", "G5"])[:5]
        data.append((title, description, min_salary, max_salary, grade))
    query = f"INSERT INTO job_roles (title, description, min_salary, max_salary, grade) VALUES %s"
    insert_batch(conn, query, data, "job_roles")


def insert_payroll_records(conn):
    """Inserts 10,000 payroll records."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        employee_ref = f"EMP-{i:05d}"
        pay_period = random.choice(["2026-01", "2026-02", "2026-03", "2026-04", "2026-05"])[:20]
        gross_pay = round(random.uniform(2500, 15000), 2)
        deductions = round(gross_pay * random.uniform(0.15, 0.35), 2)
        net_pay = round(gross_pay - deductions, 2)
        payment_date = fake.date_between(start_date='-1y', end_date='today')
        data.append((employee_ref, pay_period, gross_pay, deductions, net_pay, payment_date))
    query = f"INSERT INTO payroll_records (employee_ref, pay_period, gross_pay, deductions, net_pay, payment_date) VALUES %s"
    insert_batch(conn, query, data, "payroll_records")


def insert_leave_requests(conn):
    """Inserts 10,000 leave requests."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        employee_ref = f"EMP-{i:05d}"
        leave_type = random.choice(["Sick", "Vacation", "Maternity", "Paternity", "Bereavement", "Unpaid"])[:50]
        start_date = fake.date_between(start_date='-1y', end_date='+1y')
        end_date = start_date + timedelta(days=random.randint(1, 14))
        status = random.choice(["Pending", "Approved", "Rejected"])[:20]
        approved_by = fake.name()[:100]
        data.append((employee_ref, leave_type, start_date, end_date, status, approved_by))
    query = f"INSERT INTO leave_requests (employee_ref, leave_type, start_date, end_date, status, approved_by) VALUES %s"
    insert_batch(conn, query, data, "leave_requests")


def insert_benefits_packages(conn):
    """Inserts 10,000 benefits packages."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        package_name = f"Benefits Package {i} {fake.word().capitalize()}"[:100]
        provider = fake.company()[:100]
        monthly_premium = round(random.uniform(50, 1000), 2)
        coverage_details = fake.text()
        is_active = random.choice([True, False])
        data.append((package_name, provider, monthly_premium, coverage_details, is_active))
    query = f"INSERT INTO benefits_packages (package_name, provider, monthly_premium, coverage_details, is_active) VALUES %s"
    insert_batch(conn, query, data, "benefits_packages")


def insert_employee_skills(conn):
    """Inserts 10,000 employee skill records."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        employee_ref = f"EMP-{i:05d}"
        skill_name = f"Skill {fake.word().capitalize()}"[:100]
        proficiency_level = random.choice(["Beginner", "Intermediate", "Advanced", "Expert"])[:20]
        years_experience = random.randint(0, 15)
        certified = random.choice([True, False])
        data.append((employee_ref, skill_name, proficiency_level, years_experience, certified))
    query = f"INSERT INTO employee_skills (employee_ref, skill_name, proficiency_level, years_experience, certified) VALUES %s"
    insert_batch(conn, query, data, "employee_skills")


def insert_performance_reviews(conn):
    """Inserts 10,000 performance reviews."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        employee_ref = f"EMP-{i:05d}"
        reviewer_name = fake.name()[:100]
        review_date = fake.date_between(start_date='-2y', end_date='today')
        rating = random.randint(1, 5)
        achievements = fake.paragraph()
        improvement_areas = fake.paragraph()
        data.append((employee_ref, reviewer_name, review_date, rating, achievements, improvement_areas))
    query = f"INSERT INTO performance_reviews (employee_ref, reviewer_name, review_date, rating, achievements, improvement_areas) VALUES %s"
    insert_batch(conn, query, data, "performance_reviews")


def insert_timesheets(conn):
    """Inserts 10,000 timesheets."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        employee_ref = f"EMP-{i:05d}"
        work_date = fake.date_between(start_date='-60d', end_date='today')
        regular_hours = round(random.uniform(6.0, 8.0), 2)
        overtime_hours = round(random.uniform(0.0, 4.0), 2)
        description = fake.sentence()
        is_approved = random.choice([True, False])
        data.append((employee_ref, work_date, regular_hours, overtime_hours, description, is_approved))
    query = f"INSERT INTO timesheets (employee_ref, work_date, regular_hours, overtime_hours, description, is_approved) VALUES %s"
    insert_batch(conn, query, data, "timesheets")


def insert_training_sessions(conn):
    """Inserts 10,000 training sessions."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        topic = f"Training Session {i} on {fake.word().capitalize()}"[:150]
        trainer = fake.name()[:100]
        scheduled_at = datetime.now() + timedelta(days=random.randint(-180, 180))
        duration_hours = random.randint(1, 8)
        max_participants = random.randint(5, 50)
        data.append((topic, trainer, scheduled_at, duration_hours, max_participants))
    query = f"INSERT INTO training_sessions (topic, trainer, scheduled_at, duration_hours, max_participants) VALUES %s"
    insert_batch(conn, query, data, "training_sessions")


def insert_employment_contracts(conn):
    """Inserts 10,000 employment contracts."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        employee_ref = f"EMP-{i:05d}"
        contract_type = random.choice(["Full-time", "Part-time", "Contractor", "Intern"])[:50]
        start_date = fake.date_between(start_date='-5y', end_date='today')
        end_date = start_date + timedelta(days=random.randint(180, 1000)) if random.choice([True, False]) else None
        salary_rate = round(random.uniform(15, 120), 2)
        terms = fake.text()
        data.append((employee_ref, contract_type, start_date, end_date, salary_rate, terms))
    query = f"INSERT INTO employment_contracts (employee_ref, contract_type, start_date, end_date, salary_rate, terms) VALUES %s"
    insert_batch(conn, query, data, "employment_contracts")


# --- Domain: Finance / Accounting (11 tables) ---

def insert_gl_accounts(conn):
    """Inserts 10,000 GL accounts."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        account_code = f"GL-{i:05d}"
        account_name = f"Account {i} {fake.word().capitalize()}"[:100]
        account_type = random.choice(["Asset", "Liability", "Equity", "Revenue", "Expense"])[:50]
        currency = random.choice(["USD", "EUR", "GBP", "JPY", "CAD"])[:3]
        is_active = random.choice([True, False])
        current_balance = round(random.uniform(-50000, 1000000), 2)
        data.append((account_code, account_name, account_type, currency, is_active, current_balance))
    query = f"INSERT INTO gl_accounts (account_code, account_name, account_type, currency, is_active, current_balance) VALUES %s"
    insert_batch(conn, query, data, "gl_accounts")


def insert_journal_entries(conn):
    """Inserts 10,000 journal entries."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        entry_date = datetime.now() - timedelta(days=random.randint(0, 365))
        description = f"Journal entry {i} for general transactions"
        source_doc = f"DOC-{i:05d}"[:50]
        created_by = fake.name()[:100]
        total_amount = round(random.uniform(10, 50000), 2)
        posted = random.choice([True, False])
        data.append((entry_date, description, source_doc, created_by, total_amount, posted))
    query = f"INSERT INTO journal_entries (entry_date, description, source_doc, created_by, total_amount, posted) VALUES %s"
    insert_batch(conn, query, data, "journal_entries")


def insert_tax_records(conn):
    """Inserts 10,000 tax records."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        tax_period = f"Q{random.randint(1, 4)}-{random.randint(2020, 2026)}"[:10]
        jurisdiction = fake.country()[:50]
        tax_type = random.choice(["Sales Tax", "Corporate Income Tax", "Value Added Tax", "Payroll Tax"])[:50]
        gross_amount = round(random.uniform(10000, 1000000), 2)
        tax_rate = round(random.uniform(0.05, 0.35), 4)
        tax_amount = round(gross_amount * tax_rate, 2)
        paid = random.choice([True, False])
        data.append((tax_period, jurisdiction, tax_type, gross_amount, tax_rate, tax_amount, paid))
    query = f"INSERT INTO tax_records (tax_period, jurisdiction, tax_type, gross_amount, tax_rate, tax_amount, paid) VALUES %s"
    insert_batch(conn, query, data, "tax_records")


def insert_budget_allocations(conn):
    """Inserts 10,000 budget allocations."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        fiscal_year = random.randint(2020, 2028)
        department_code = f"DEPT-{i}"
        allocated_amount = round(random.uniform(10000, 5000000), 2)
        spent_amount = round(allocated_amount * random.uniform(0, 1.1), 2)
        notes = fake.sentence()
        approved_by = fake.name()[:100]
        data.append((fiscal_year, department_code, allocated_amount, spent_amount, notes, approved_by))
    query = f"INSERT INTO budget_allocations (fiscal_year, department_code, allocated_amount, spent_amount, notes, approved_by) VALUES %s"
    insert_batch(conn, query, data, "budget_allocations")


def insert_invoices(conn):
    """Inserts 10,000 invoices."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        invoice_number = f"INV-{i:05d}-{fake.hexify(text='^^^^')}"
        customer_ref = f"CUST-{i:05d}"
        issue_date = fake.date_between(start_date='-1y', end_date='today')
        due_date = issue_date + timedelta(days=random.randint(15, 90))
        subtotal = round(random.uniform(10, 25000), 2)
        tax_amount = round(subtotal * 0.08, 2)
        total_amount = round(subtotal + tax_amount, 2)
        status = random.choice(["Draft", "Sent", "Paid", "Overdue", "Cancelled"])[:20]
        data.append((invoice_number, customer_ref, issue_date, due_date, subtotal, tax_amount, total_amount, status))
    query = f"INSERT INTO invoices (invoice_number, customer_ref, issue_date, due_date, subtotal, tax_amount, total_amount, status) VALUES %s"
    insert_batch(conn, query, data, "invoices")


def insert_expense_reports(conn):
    """Inserts 10,000 expense reports."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        employee_ref = f"EMP-{i:05d}"
        purpose = f"Travel/Supplies {fake.word().capitalize()}"[:255]
        total_claimed = round(random.uniform(5, 5000), 2)
        status = random.choice(["Draft", "Submitted", "Approved", "Paid", "Rejected"])[:20]
        approved_date = fake.date_between(start_date='-1y', end_date='today') if status in ["Approved", "Paid"] else None
        audited = random.choice([True, False])
        data.append((employee_ref, purpose, total_claimed, status, approved_date, audited))
    query = f"INSERT INTO expense_reports (employee_ref, purpose, total_claimed, status, approved_date, audited) VALUES %s"
    insert_batch(conn, query, data, "expense_reports")


def insert_bank_transactions(conn):
    """Inserts 10,000 bank transactions."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        bank_account_no = f"ACT-{i:05d}"
        transaction_date = datetime.now() - timedelta(days=random.randint(0, 365))
        amount = round(random.uniform(-5000, 10000), 2)
        transaction_type = random.choice(["DEBIT", "CREDIT"])[:10]
        description = f"Bank transaction {i} description"[:255]
        reference_no = f"REF-{i:07d}-{fake.hexify(text='^^^^')}"
        reconciled = random.choice([True, False])
        data.append((bank_account_no, transaction_date, amount, transaction_type, description, reference_no, reconciled))
    query = f"INSERT INTO bank_transactions (bank_account_no, transaction_date, amount, transaction_type, description, reference_no, reconciled) VALUES %s"
    insert_batch(conn, query, data, "bank_transactions")


def insert_purchase_orders(conn):
    """Inserts 10,000 purchase orders."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        po_number = f"PO-{i:05d}-{fake.hexify(text='^^^^')}"
        vendor_ref = f"VEND-{i:05d}"
        order_date = fake.date_between(start_date='-1y', end_date='today')
        expected_delivery = order_date + timedelta(days=random.randint(5, 30))
        total_amount = round(random.uniform(50, 100000), 2)
        status = random.choice(["Draft", "Approved", "Sent", "Received", "Cancelled"])[:20]
        terms = fake.text()
        data.append((po_number, vendor_ref, order_date, expected_delivery, total_amount, status, terms))
    query = f"INSERT INTO purchase_orders (po_number, vendor_ref, order_date, expected_delivery, total_amount, status, terms) VALUES %s"
    insert_batch(conn, query, data, "purchase_orders")


def insert_depreciation_schedules(conn):
    """Inserts 10,000 depreciation schedules."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        asset_ref = f"ASSET-{i:05d}"
        purchase_cost = round(random.uniform(1000, 500000), 2)
        salvage_value = round(purchase_cost * random.uniform(0.05, 0.20), 2)
        useful_life_years = random.randint(3, 30)
        depreciation_method = random.choice(["Straight-Line", "Double-Declining Balance", "Sum-of-the-Years-Digits"])[:50]
        accumulated_depreciation = round(random.uniform(0, purchase_cost - salvage_value), 2)
        data.append((asset_ref, purchase_cost, salvage_value, useful_life_years, depreciation_method, accumulated_depreciation))
    query = f"INSERT INTO depreciation_schedules (asset_ref, purchase_cost, salvage_value, useful_life_years, depreciation_method, accumulated_depreciation) VALUES %s"
    insert_batch(conn, query, data, "depreciation_schedules")


def insert_fiscal_periods(conn):
    """Inserts 10,000 fiscal periods."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        period_name = f"FY-{i}-{fake.hexify(text='^^^^')}"
        start_date = fake.date_between(start_date='-5y', end_date='+5y')
        end_date = start_date + timedelta(days=30)
        is_closed = random.choice([True, False])
        closed_by = fake.name()[:100] if is_closed else None
        data.append((period_name, start_date, end_date, is_closed, closed_by))
    query = f"INSERT INTO fiscal_periods (period_name, start_date, end_date, is_closed, closed_by) VALUES %s"
    insert_batch(conn, query, data, "fiscal_periods")


def insert_currency_rates(conn):
    """Inserts 10,000 currency rates."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        from_currency = random.choice(["USD", "EUR", "GBP", "JPY", "CAD", "AUD"])[:3]
        to_currency = random.choice(["USD", "EUR", "GBP", "JPY", "CAD", "AUD"])[:3]
        exchange_rate = round(random.uniform(0.005, 500), 6)
        effective_date = fake.date_between(start_date='-2y', end_date='+1y')
        source_name = f"Provider {i} Feed"[:100]
        data.append((from_currency, to_currency, exchange_rate, effective_date, source_name))
    query = f"INSERT INTO currency_rates (from_currency, to_currency, exchange_rate, effective_date, source_name) VALUES %s"
    insert_batch(conn, query, data, "currency_rates")


# --- Domain: Logistics (11 tables) ---

def insert_warehouses(conn):
    """Inserts 10,000 warehouses."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        code = f"WH-{i}-{fake.hexify(text='^^')}"
        location_name = f"Warehouse {i} {fake.city()}"[:150]
        address = fake.address()[:255]
        capacity_cubic_meters = round(random.uniform(5000, 100000), 2)
        manager_name = fake.name()[:100]
        is_active = random.choice([True, False])
        data.append((code, location_name, address, capacity_cubic_meters, manager_name, is_active))
    query = f"INSERT INTO warehouses (code, location_name, address, capacity_cubic_meters, manager_name, is_active) VALUES %s"
    insert_batch(conn, query, data, "warehouses")


def insert_vehicles(conn):
    """Inserts 10,000 vehicles."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        vin = f"VIN-{i:08d}-{fake.hexify(text='^^^')}"
        license_plate = f"LP-{i:07d}-{fake.hexify(text='^')}"
        make = random.choice(["Ford", "Chevrolet", "Volvo", "Peterbilt", "Freightliner"])[:50]
        model = f"Model {random.choice(['F-150', 'Silverado', 'VNL', '579', 'Cascadia'])}"[:50]
        year = random.randint(2010, 2026)
        fuel_type = random.choice(["Diesel", "Gasoline", "Electric", "Hybrid"])[:20]
        payload_capacity_lbs = random.randint(1500, 80000)
        data.append((vin, license_plate, make, model, year, fuel_type, payload_capacity_lbs))
    query = f"INSERT INTO vehicles (vin, license_plate, make, model, year, fuel_type, payload_capacity_lbs) VALUES %s"
    insert_batch(conn, query, data, "vehicles")


def insert_delivery_routes(conn):
    """Inserts 10,000 delivery routes."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        route_code = f"ROUTE-{i}-{fake.hexify(text='^^')}"
        start_location = fake.city()[:150]
        end_location = fake.city()[:150]
        distance_km = round(random.uniform(10, 3000), 2)
        estimated_duration_hours = round(distance_km / random.uniform(60, 90), 2)
        active = random.choice([True, False])
        data.append((route_code, start_location, end_location, distance_km, estimated_duration_hours, active))
    query = f"INSERT INTO delivery_routes (route_code, start_location, end_location, distance_km, estimated_duration_hours, active) VALUES %s"
    insert_batch(conn, query, data, "delivery_routes")


def insert_fuel_logs(conn):
    """Inserts 10,000 fuel logs."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        vehicle_ref = f"VEH-{i:05d}"
        log_date = datetime.now() - timedelta(days=random.randint(0, 180))
        gallons = round(random.uniform(10, 150), 2)
        price_per_gallon = round(random.uniform(2.5, 5.5), 2)
        total_cost = round(gallons * price_per_gallon, 2)
        odometer_reading = random.randint(5000, 500000)
        data.append((vehicle_ref, log_date, gallons, price_per_gallon, total_cost, odometer_reading))
    query = f"INSERT INTO fuel_logs (vehicle_ref, log_date, gallons, price_per_gallon, total_cost, odometer_reading) VALUES %s"
    insert_batch(conn, query, data, "fuel_logs")


def insert_maintenance_records(conn):
    """Inserts 10,000 maintenance records."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        vehicle_ref = f"VEH-{i:05d}"
        maintenance_date = fake.date_between(start_date='-2y', end_date='today')
        service_type = random.choice(["Oil Change", "Tire Rotation", "Brake Replacement", "Engine Tuning", "Inspection"])[:100]
        description = fake.sentence()
        cost = round(random.uniform(50, 5000), 2)
        vendor_name = f"{fake.company()} Auto Repair"[:100]
        next_due_date = maintenance_date + timedelta(days=random.randint(90, 365))
        data.append((vehicle_ref, maintenance_date, service_type, description, cost, vendor_name, next_due_date))
    query = f"INSERT INTO maintenance_records (vehicle_ref, maintenance_date, service_type, description, cost, vendor_name, next_due_date) VALUES %s"
    insert_batch(conn, query, data, "maintenance_records")


def insert_shipping_containers(conn):
    """Inserts 10,000 shipping containers."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        container_no = f"CONT-{i:05d}-{fake.hexify(text='^^')}"
        size_feet = random.choice([20, 40, 45])
        tare_weight_kg = random.randint(2000, 5000)
        max_payload_kg = random.randint(20000, 32000)
        owner_company = fake.company()[:100]
        status = random.choice(["Empty", "Loaded", "Transit", "Customs", "Maintenance"])[:20]
        data.append((container_no, size_feet, tare_weight_kg, max_payload_kg, owner_company, status))
    query = f"INSERT INTO shipping_containers (container_no, size_feet, tare_weight_kg, max_payload_kg, owner_company, status) VALUES %s"
    insert_batch(conn, query, data, "shipping_containers")


def insert_freight_carriers(conn):
    """Inserts 10,000 freight carriers."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        carrier_name = f"Carrier {i} {fake.company()}"[:100]
        # SCAC code generator (unique 4-char string)
        scac_n = i
        res = []
        for _ in range(4):
            res.append(chr(65 + (scac_n % 26)))
            scac_n //= 26
        scac_code = "".join(res)
        contact_email = f"carrier_{i}_{fake.email()}"[:100]
        contact_phone = fake.phone_number()[:50]
        rating = round(random.uniform(1.0, 5.0), 2)
        is_preferred = random.choice([True, False])
        data.append((carrier_name, scac_code, contact_email, contact_phone, rating, is_preferred))
    query = f"INSERT INTO freight_carriers (carrier_name, scac_code, contact_email, contact_phone, rating, is_preferred) VALUES %s"
    insert_batch(conn, query, data, "freight_carriers")


def insert_port_records(conn):
    """Inserts 10,000 port records."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        port_code = f"PRT-{i}-{fake.hexify(text='^')}"[:10]
        port_name = f"Port of {fake.city()}"[:100]
        country = fake.country()[:100]
        terminal_count = random.randint(2, 25)
        daily_vessel_capacity = random.randint(5, 100)
        latitude = round(random.uniform(-90.0, 90.0), 6)
        longitude = round(random.uniform(-180.0, 180.0), 6)
        data.append((port_code, port_name, country, terminal_count, daily_vessel_capacity, latitude, longitude))
    query = f"INSERT INTO port_records (port_code, port_name, country, terminal_count, daily_vessel_capacity, latitude, longitude) VALUES %s"
    insert_batch(conn, query, data, "port_records")


def insert_customs_declarations(conn):
    """Inserts 10,000 customs declarations."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        declaration_ref = f"DEC-{i:05d}-{fake.hexify(text='^^^^')}"
        shipper_name = fake.company()[:100]
        consignee_name = fake.name()[:100]
        declared_value_usd = round(random.uniform(100, 1000000), 2)
        duty_amount_usd = round(declared_value_usd * random.uniform(0.02, 0.15), 2)
        status = random.choice(["Submitted", "Under Review", "Cleared", "Rejected", "Held"])[:20]
        clearance_date = fake.date_between(start_date='-1y', end_date='today') if status == "Cleared" else None
        data.append((declaration_ref, shipper_name, consignee_name, declared_value_usd, duty_amount_usd, status, clearance_date))
    query = f"INSERT INTO customs_declarations (declaration_ref, shipper_name, consignee_name, declared_value_usd, duty_amount_usd, status, clearance_date) VALUES %s"
    insert_batch(conn, query, data, "customs_declarations")


def insert_cargo_manifests(conn):
    """Inserts 10,000 cargo manifests."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        manifest_no = f"MAN-{i:05d}-{fake.hexify(text='^^^^')}"
        vessel_name = f"SS {fake.first_name()[:30]} {fake.word().capitalize()[:30]}"[:100]
        voyage_number = f"VY-{i:05d}"[:20]
        load_port_code = f"LPT-{random.randint(1, 1000)}"[:10]
        discharge_port_code = f"DPT-{random.randint(1, 1000)}"[:10]
        total_weight_tons = round(random.uniform(500, 200000), 2)
        container_count = random.randint(50, 5000)
        data.append((manifest_no, vessel_name, voyage_number, load_port_code, discharge_port_code, total_weight_tons, container_count))
    query = f"INSERT INTO cargo_manifests (manifest_no, vessel_name, voyage_number, load_port_code, discharge_port_code, total_weight_tons, container_count) VALUES %s"
    insert_batch(conn, query, data, "cargo_manifests")


def insert_driver_logs(conn):
    """Inserts 10,000 driver logs."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        driver_license = f"DL-{i:05d}-{fake.hexify(text='^^^^')}"
        driver_name = fake.name()[:100]
        log_date = fake.date_between(start_date='-90d', end_date='today')
        on_duty_hours = round(random.uniform(4.0, 14.0), 2)
        driving_hours = round(min(on_duty_hours, random.uniform(2.0, 11.0)), 2)
        sleeper_berth_hours = round(random.uniform(0.0, 8.0), 2)
        violation_occurred = random.choice([True, False])
        data.append((driver_license, driver_name, log_date, on_duty_hours, driving_hours, sleeper_berth_hours, violation_occurred))
    query = f"INSERT INTO driver_logs (driver_license, driver_name, log_date, on_duty_hours, driving_hours, sleeper_berth_hours, violation_occurred) VALUES %s"
    insert_batch(conn, query, data, "driver_logs")


# --- Domain: CRM / Marketing (11 tables) ---

def insert_leads(conn):
    """Inserts 10,000 leads."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        first_name = fake.first_name()[:50]
        last_name = fake.last_name()[:50]
        email = f"lead_{i}_{fake.email()}"[:100]
        phone = fake.phone_number()[:50]
        company = fake.company()[:100]
        source = random.choice(["Webinar", "Website Inquiry", "Referral", "Cold Call", "Ad Campaign"])[:50]
        score = random.randint(-20, 120)
        status = random.choice(["New", "Contacted", "Qualified", "Unqualified", "Nurturing"])[:20]
        data.append((first_name, last_name, email, phone, company, source, score, status))
    query = f"INSERT INTO leads (first_name, last_name, email, phone, company, source, score, status) VALUES %s"
    insert_batch(conn, query, data, "leads")


def insert_campaigns(conn):
    """Inserts 10,000 marketing campaigns."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        name = f"Campaign {i} {fake.bs()[:60]}"[:100]
        description = fake.sentence()
        campaign_type = random.choice(["Email", "SMS", "Social Media", "PPC", "SEO", "Trade Show"])[:50]
        start_date = fake.date_between(start_date='-1y', end_date='+1y')
        end_date = start_date + timedelta(days=random.randint(7, 120))
        budget = round(random.uniform(500, 250000), 2)
        actual_cost = round(budget * random.uniform(0.8, 1.3), 2)
        data.append((name, description, campaign_type, start_date, end_date, budget, actual_cost))
    query = f"INSERT INTO campaigns (name, description, type, start_date, end_date, budget, actual_cost) VALUES %s"
    insert_batch(conn, query, data, "campaigns")


def insert_email_logs(conn):
    """Inserts 10,000 email logs."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        campaign_ref = f"CAMP-{i:05d}"
        recipient_email = f"recipient_{i}_{fake.email()}"[:100]
        sent_at = datetime.now() - timedelta(days=random.randint(0, 180))
        status = random.choice(["Sent", "Delivered", "Failed"])[:20]
        opened = random.choice([True, False]) if status == "Delivered" else False
        clicked = random.choice([True, False]) if opened else False
        bounced = random.choice([True, False]) if status == "Failed" else False
        data.append((campaign_ref, recipient_email, sent_at, status, opened, clicked, bounced))
    query = f"INSERT INTO email_logs (campaign_ref, recipient_email, sent_at, status, opened, clicked, bounced) VALUES %s"
    insert_batch(conn, query, data, "email_logs")


def insert_sms_logs(conn):
    """Inserts 10,000 SMS logs."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        campaign_ref = f"CAMP-{i:05d}"
        recipient_phone = fake.phone_number()[:50]
        sent_at = datetime.now() - timedelta(days=random.randint(0, 90))
        message_body = f"Hello, check out our campaign promo {i}! {fake.sentence()}"
        status = random.choice(["Sent", "Delivered", "Undelivered", "Failed"])[:20]
        carrier_code = random.choice(["ATT", "VERIZON", "TMOBILE", "SPRINT"])[:20]
        cost = round(random.uniform(0.005, 0.05), 4)
        data.append((campaign_ref, recipient_phone, sent_at, message_body, status, carrier_code, cost))
    query = f"INSERT INTO sms_logs (campaign_ref, recipient_phone, sent_at, message_body, status, carrier_code, cost) VALUES %s"
    insert_batch(conn, query, data, "sms_logs")


def insert_survey_responses(conn):
    """Inserts 10,000 survey responses."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        survey_name = f"Customer Satisfaction Q{random.randint(1,4)} {random.randint(2020, 2026)}"[:100]
        responder_email = f"survey_{i}_{fake.email()}"[:100]
        question_id = random.randint(1, 15)
        answer_score = random.randint(1, 10)
        comments = fake.sentence() if random.choice([True, False]) else None
        submitted_at = datetime.now() - timedelta(days=random.randint(0, 365))
        data.append((survey_name, responder_email, question_id, answer_score, comments, submitted_at))
    query = f"INSERT INTO survey_responses (survey_name, responder_email, question_id, answer_score, comments, submitted_at) VALUES %s"
    insert_batch(conn, query, data, "survey_responses")


def insert_marketing_lists(conn):
    """Inserts 10,000 marketing lists."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        list_name = f"List {i} {fake.bs()[:60]}"[:100]
        description = fake.sentence()
        segment_criteria = random.choice(["Active Users", "Recent Leads", "High Value Customers", "Geo-targeted"])[:255]
        is_smart_list = random.choice([True, False])
        member_count = random.randint(0, 50000)
        last_synced_at = datetime.now() - timedelta(hours=random.randint(1, 72)) if is_smart_list else None
        data.append((list_name, description, segment_criteria, is_smart_list, member_count, last_synced_at))
    query = f"INSERT INTO marketing_lists (list_name, description, segment_criteria, is_smart_list, member_count, last_synced_at) VALUES %s"
    insert_batch(conn, query, data, "marketing_lists")


def insert_sales_pipelines(conn):
    """Inserts 10,000 sales pipeline configs/stages."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        pipeline_name = f"Pipeline {i} {fake.word().capitalize()}"[:100]
        stage_name = random.choice(["Discovery", "Qualifying", "Demo", "Proposal", "Negotiation", "Closed Won", "Closed Lost"])[:50]
        display_order = random.randint(1, 10)
        probability_pct = random.randint(0, 100)
        description = fake.sentence()
        is_active = random.choice([True, False])
        data.append((pipeline_name, stage_name, display_order, probability_pct, description, is_active))
    query = f"INSERT INTO sales_pipelines (pipeline_name, stage_name, display_order, probability_pct, description, is_active) VALUES %s"
    insert_batch(conn, query, data, "sales_pipelines")


def insert_customer_feedback(conn):
    """Inserts 10,000 customer feedback records."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        customer_ref = f"CUST-{i:05d}"
        feedback_type = random.choice(["Complaint", "Compliment", "Suggestion", "Bug Report"])[:20]
        subject = f"Feedback Subject {i} {fake.word()}"[:150]
        details = fake.paragraph()
        severity = random.choice(["Low", "Medium", "High", "Critical"])[:10]
        assigned_to = fake.name()[:100]
        resolved = random.choice([True, False])
        data.append((customer_ref, feedback_type, subject, details, severity, assigned_to, resolved))
    query = f"INSERT INTO customer_feedback (customer_ref, feedback_type, subject, details, severity, assigned_to, resolved) VALUES %s"
    insert_batch(conn, query, data, "customer_feedback")


def insert_webinar_attendees(conn):
    """Inserts 10,000 webinar attendee records."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        webinar_id = f"WEB-{i:05d}"
        first_name = fake.first_name()[:50]
        last_name = fake.last_name()[:50]
        email = f"webinar_{i}_{fake.email()}"[:100]
        registered_at = datetime.now() - timedelta(days=random.randint(1, 60))
        attended = random.choice([True, False])
        duration_minutes = random.randint(5, 90) if attended else 0
        data.append((webinar_id, first_name, last_name, email, registered_at, attended, duration_minutes))
    query = f"INSERT INTO webinar_attendees (webinar_id, first_name, last_name, email, registered_at, attended, duration_minutes) VALUES %s"
    insert_batch(conn, query, data, "webinar_attendees")


def insert_competitor_trackers(conn):
    """Inserts 10,000 competitor tracking records."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        competitor_name = f"Competitor {i} {fake.company()}"[:100]
        product_name = f"Competing Product {i} {fake.word()}"[:100]
        url = f"https://www.competitor-{i}.com/product"[:255]
        monitored_price = round(random.uniform(5, 10000), 2)
        availability = random.choice(["In Stock", "Out of Stock", "Backorder"])[:20]
        last_checked_at = datetime.now() - timedelta(hours=random.randint(1, 168))
        data.append((competitor_name, product_name, url, monitored_price, availability, last_checked_at))
    query = f"INSERT INTO competitor_trackers (competitor_name, product_name, url, monitored_price, availability, last_checked_at) VALUES %s"
    insert_batch(conn, query, data, "competitor_trackers")


def insert_referral_programs(conn):
    """Inserts 10,000 referral programs."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        program_name = f"Referral Program {i} {fake.word().capitalize()}"[:100]
        referral_code_prefix = f"REF{i:03d}"[:10]
        reward_type = random.choice(["Discount", "Cashback", "Gift Card", "Points"])[:50]
        reward_value = round(random.uniform(5, 200), 2)
        max_referrals = random.choice([5, 10, 20, 50, None])
        is_active = random.choice([True, False])
        data.append((program_name, referral_code_prefix, reward_type, reward_value, max_referrals, is_active))
    query = f"INSERT INTO referral_programs (program_name, referral_code_prefix, reward_type, reward_value, max_referrals, is_active) VALUES %s"
    insert_batch(conn, query, data, "referral_programs")


# --- Domain: IT / System (12 tables) ---

def insert_audit_logs(conn):
    """Inserts 10,000 audit logs."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        username = fake.user_name()[:100]
        action = random.choice(["INSERT", "UPDATE", "DELETE", "LOGIN", "EXPORT"])[:50]
        table_name = random.choice(["customers", "orders", "payments", "products", "employees"])[:100]
        row_id = str(random.randint(1, 100000))[:100]
        old_val = {"state": "previous", "status": "draft", "id": i}
        new_val = {"state": "updated", "status": "active", "id": i}
        ip_address = fake.ipv4()[:50]
        data.append((username, action, table_name, row_id, json.dumps(old_val), json.dumps(new_val), ip_address))
    query = f"INSERT INTO audit_logs (username, action, table_name, row_id, old_values, new_values, ip_address) VALUES %s"
    insert_batch(conn, query, data, "audit_logs")


def insert_error_logs(conn):
    """Inserts 10,000 error logs."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        app_name = random.choice(["Admin Portal", "Payment Gate", "Job Worker", "API Gateway"])[:100]
        error_class = random.choice(["NullPointerException", "DatabaseTimeoutException", "ConnectionError", "ValueError"])[:100]
        error_message = f"Error {i} occurred: {fake.sentence()}"
        stack_trace = fake.text()
        severity = random.choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])[:20]
        is_resolved = random.choice([True, False])
        resolved_by = fake.name()[:100] if is_resolved else None
        data.append((app_name, error_class, error_message, stack_trace, severity, is_resolved, resolved_by))
    query = f"INSERT INTO error_logs (app_name, error_class, error_message, stack_trace, severity, is_resolved, resolved_by) VALUES %s"
    insert_batch(conn, query, data, "error_logs")


def insert_system_configs(conn):
    """Inserts 10,000 system configs."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        config_key = f"system.config.key.{i}"[:100]
        config_value = fake.sentence()
        data_type = random.choice(["STRING", "INT", "BOOLEAN", "FLOAT"])[:20]
        category = random.choice(["Security", "UI", "Performance", "Notifications"])[:50]
        is_encrypted = random.choice([True, False])
        description = fake.sentence()
        data.append((config_key, config_value, data_type, category, is_encrypted, description))
    query = f"INSERT INTO system_configs (config_key, config_value, data_type, category, is_encrypted, description) VALUES %s"
    insert_batch(conn, query, data, "system_configs")


def insert_api_keys(conn):
    """Inserts 10,000 API keys."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        key_name = f"API Key {i} {fake.word()}"[:100]
        hashed_key = hashlib.sha256(f"API_KEY_{i}_{fake.word()}".encode()).hexdigest()[:64]
        scopes = "read,write,admin" if i % 10 == 0 else "read,write"
        rate_limit_rpm = random.choice([60, 120, 300, 1000])
        is_active = random.choice([True, False])
        expires_at = datetime.now() + timedelta(days=random.randint(30, 365))
        data.append((key_name, hashed_key, scopes, rate_limit_rpm, is_active, expires_at))
    query = f"INSERT INTO api_keys (key_name, hashed_key, scopes, rate_limit_rpm, is_active, expires_at) VALUES %s"
    insert_batch(conn, query, data, "api_keys")


def insert_scheduled_jobs(conn):
    """Inserts 10,000 scheduled jobs."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        job_name = f"Job-{i}-{fake.hexify(text='^^^^')}"[:100]
        job_group = random.choice(["Reports", "Database", "CleanUp", "Sync"])[:50]
        cron_expression = random.choice(["0 0 * * *", "*/5 * * * *", "0 */2 * * *", "0 0 1 * *"])[:50]
        class_name = f"com.migration.jobs.JobWorker{i}"[:255]
        is_concurrent = random.choice([True, False])
        description = fake.sentence()
        data.append((job_name, job_group, cron_expression, class_name, is_concurrent, description))
    query = f"INSERT INTO scheduled_jobs (job_name, job_group, cron_expression, class_name, is_concurrent, description) VALUES %s"
    insert_batch(conn, query, data, "scheduled_jobs")


def insert_user_sessions(conn):
    """Inserts 10,000 user sessions."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        session_id = f"SESS-{i:05d}-{hashlib.sha256(str(i).encode()).hexdigest()[:60]}"[:100]
        username = fake.user_name()[:100]
        ip_address = fake.ipv4()[:50]
        user_agent = fake.user_agent()[:255]
        payload = f"session_payload_data_serialized_{i}"
        last_activity = datetime.now() - timedelta(minutes=random.randint(1, 1440))
        data.append((session_id, username, ip_address, user_agent, payload, last_activity))
    query = f"INSERT INTO user_sessions (session_id, username, ip_address, user_agent, payload, last_activity) VALUES %s"
    insert_batch(conn, query, data, "user_sessions")


def insert_server_metrics(conn):
    """Inserts 10,000 server metrics."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        server_id = f"SRV-{random.randint(1, 100)}"[:50]
        cpu_pct = round(random.uniform(1.0, 99.9), 2)
        ram_pct = round(random.uniform(5.0, 95.0), 2)
        disk_pct = round(random.uniform(10.0, 90.0), 2)
        network_in_mb = round(random.uniform(0.1, 1000.0), 2)
        network_out_mb = round(random.uniform(0.1, 1000.0), 2)
        recorded_at = datetime.now() - timedelta(minutes=random.randint(1, 10000))
        data.append((server_id, cpu_pct, ram_pct, disk_pct, network_in_mb, network_out_mb, recorded_at))
    query = f"INSERT INTO server_metrics (server_id, cpu_pct, ram_pct, disk_pct, network_in_mb, network_out_mb, recorded_at) VALUES %s"
    insert_batch(conn, query, data, "server_metrics")


def insert_backup_schedules(conn):
    """Inserts 10,000 backup schedules."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        backup_name = f"Backup-{i}-{fake.word()}"[:100]
        source_path = f"/var/data/db_source_{i}"[:255]
        dest_bucket = f"s3://db-backup-bucket-{i}"[:100]
        backup_type = random.choice(["FULL", "DIFF", "INCR"])[:10]
        compression = random.choice(["gzip", "zip", "zstd", "tar"])[:10]
        retention_days = random.choice([7, 30, 90, 365])
        is_active = random.choice([True, False])
        data.append((backup_name, source_path, dest_bucket, backup_type, compression, retention_days, is_active))
    query = f"INSERT INTO backup_schedules (backup_name, source_path, dest_bucket, backup_type, compression, retention_days, is_active) VALUES %s"
    insert_batch(conn, query, data, "backup_schedules")


def insert_security_policies(conn):
    """Inserts 10,000 security policies."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        policy_code = f"POL-{i}-{fake.hexify(text='^^')}"[:50]
        policy_name = f"Security Policy {i} {fake.catch_phrase()[:80]}"[:150]
        description = fake.sentence()
        min_privilege_level = random.choice(["Guest", "User", "Manager", "Admin"])[:20]
        enforced = random.choice([True, False])
        last_reviewed_at = datetime.now() - timedelta(days=random.randint(0, 365))
        data.append((policy_code, policy_name, description, min_privilege_level, enforced, last_reviewed_at))
    query = f"INSERT INTO security_policies (policy_code, policy_name, description, min_privilege_level, enforced, last_reviewed_at) VALUES %s"
    insert_batch(conn, query, data, "security_policies")


def insert_network_nodes(conn):
    """Inserts 10,000 network nodes."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        node_name = f"NODE-{i}-{fake.word()}"[:100]
        node_type = random.choice(["Router", "Switch", "Server", "Firewall", "Load Balancer"])[:50]
        # Sequential IP generation to guarantee uniqueness
        ip_address = f"10.{(i // 256) // 256}.{(i // 256) % 256}.{i % 256}"[:50]
        # Sequential MAC generation to guarantee uniqueness
        mac_address = f"00:11:22:33:{(i // 256):02x}:{i % 256:02x}"[:50]
        subnet_mask = "255.255.255.0"[:50]
        gateway = "10.0.0.1"[:50]
        rack_unit = random.choice([random.randint(1, 42), None])
        data.append((node_name, node_type, ip_address, mac_address, subnet_mask, gateway, rack_unit))
    query = f"INSERT INTO network_nodes (node_name, node_type, ip_address, mac_address, subnet_mask, gateway, rack_unit) VALUES %s"
    insert_batch(conn, query, data, "network_nodes")


def insert_access_tokens(conn):
    """Inserts 10,000 access tokens."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        jti = f"JTI-{i:05d}-{hashlib.sha256(str(i).encode()).hexdigest()[:60]}"[:100]
        subject = f"SUB-{random.randint(1, 100000)}"[:100]
        issuer = "auth.migration-service.com"[:100]
        audience = "client-app-audience"[:100]
        expires_at = datetime.now() + timedelta(hours=random.randint(1, 168))
        is_blacklisted = random.choice([True, False])
        data.append((jti, subject, issuer, audience, expires_at, is_blacklisted))
    query = f"INSERT INTO access_tokens (jti, subject, issuer, audience, expires_at, is_blacklisted) VALUES %s"
    insert_batch(conn, query, data, "access_tokens")


def insert_ip_whitelists(conn):
    """Inserts 10,000 IP whitelist rules."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        # Unique CIDR block block to avoid unique constraint error
        cidr_block = f"192.168.{(i // 256)}.{i % 256}/32"[:50]
        description = f"Whitelist for partner {i}"[:255]
        environment = random.choice(["Prod", "Staging", "Dev", "Test"])[:20]
        requested_by = fake.name()[:100]
        approved_by = fake.name()[:100]
        expiry_date = datetime.now() + timedelta(days=random.randint(30, 365))
        data.append((cidr_block, description, environment, requested_by, approved_by, expiry_date))
    query = f"INSERT INTO ip_whitelists (cidr_block, description, environment, requested_by, approved_by, expiry_date) VALUES %s"
    insert_batch(conn, query, data, "ip_whitelists")


# --- Domain: Content / CMS (12 tables) ---

def insert_articles(conn):
    """Inserts 10,000 articles."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        title = f"Article {i} {fake.sentence()[:100]}"[:150]
        slug = f"article-slug-{i}-{fake.hexify(text='^^^^')}"[:150]
        body = fake.text(max_nb_chars=1000)
        author_name = fake.name()[:100]
        publish_date = datetime.now() - timedelta(days=random.randint(0, 1000))
        status = random.choice(["Draft", "Published", "Archived"])[:20]
        view_count = random.randint(0, 100000)
        data.append((title, slug, body, author_name, publish_date, status, view_count))
    query = f"INSERT INTO articles (title, slug, body, author_name, publish_date, status, view_count) VALUES %s"
    insert_batch(conn, query, data, "articles")


def insert_tags(conn):
    """Inserts 10,000 tags."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        name = f"Tag {i} {fake.word()}"[:50]
        slug = f"tag-slug-{i}-{fake.hexify(text='^^')}"[:50]
        description = fake.sentence()
        color_hex = fake.hex_color()[:7]
        post_count = random.randint(0, 5000)
        data.append((name, slug, description, color_hex, post_count))
    query = f"INSERT INTO tags (name, slug, description, color_hex, post_count) VALUES %s"
    insert_batch(conn, query, data, "tags")


def insert_media_files(conn):
    """Inserts 10,000 media files."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        file_name = f"file_{i}_{fake.file_name()}"[:255]
        file_path = f"/assets/media/{i}/file_{hashlib.md5(str(i).encode()).hexdigest()[:10]}.png"[:255]
        mime_type = random.choice(["image/png", "image/jpeg", "image/gif", "application/pdf"])[:100]
        file_size_bytes = random.randint(1024, 104857600)
        dimensions = "1920x1080" if "image" in mime_type else None
        caption = fake.sentence()
        uploaded_by = fake.user_name()[:100]
        data.append((file_name, file_path, mime_type, file_size_bytes, dimensions, caption, uploaded_by))
    query = f"INSERT INTO media_files (file_name, file_path, mime_type, file_size_bytes, dimensions, caption, uploaded_by) VALUES %s"
    insert_batch(conn, query, data, "media_files")


def insert_comments(conn):
    """Inserts 10,000 comments."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        article_ref = f"slug-{i:05d}"[:150]
        author_name = fake.name()[:100]
        author_email = fake.email()[:100]
        body = fake.paragraph()
        ip_address = fake.ipv4()[:50]
        is_approved = random.choice([True, False])
        likes = random.randint(0, 500)
        data.append((article_ref, author_name, author_email, body, ip_address, is_approved, likes))
    query = f"INSERT INTO comments (article_ref, author_name, author_email, body, ip_address, is_approved, likes) VALUES %s"
    insert_batch(conn, query, data, "comments")


def insert_page_views(conn):
    """Inserts 10,000 page views."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        page_url = f"https://www.mysite.com/blog/article-{random.randint(1, 1000)}"[:255]
        referrer_url = f"https://www.google.com/search?q={fake.word()}"[:255]
        user_agent = fake.user_agent()[:255]
        session_id = f"SESS-{random.randint(1, 100000)}"[:100]
        load_time_ms = random.randint(50, 4000)
        ip_address = fake.ipv4()[:50]
        viewed_at = datetime.now() - timedelta(minutes=random.randint(1, 50000))
        data.append((page_url, referrer_url, user_agent, session_id, load_time_ms, ip_address, viewed_at))
    query = f"INSERT INTO page_views (page_url, referrer_url, user_agent, session_id, load_time_ms, ip_address, viewed_at) VALUES %s"
    insert_batch(conn, query, data, "page_views")


def insert_newsletters(conn):
    """Inserts 10,000 newsletters."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        code = f"NL-CODE-{i}-{fake.hexify(text='^^')}"[:50]
        title = f"Newsletter Edition {i} - {fake.word().capitalize()}"[:150]
        description = fake.sentence()
        schedule_day = random.choice(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])[:20]
        subscriber_count = random.randint(0, 100000)
        is_active = random.choice([True, False])
        data.append((code, title, description, schedule_day, subscriber_count, is_active))
    query = f"INSERT INTO newsletters (code, title, description, schedule_day, subscriber_count, is_active) VALUES %s"
    insert_batch(conn, query, data, "newsletters")


def insert_faq_items(conn):
    """Inserts 10,000 FAQ items."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        question = f"Question {i}: {fake.sentence()[:-1]}?"
        answer = fake.paragraph()
        category = random.choice(["Billing", "Technical", "Accounts", "Returns", "Shipping"])[:50]
        sort_order = i
        is_published = random.choice([True, False])
        helpful_votes = random.randint(0, 1000)
        unhelpful_votes = random.randint(0, 100)
        data.append((question, answer, category, sort_order, is_published, helpful_votes, unhelpful_votes))
    query = f"INSERT INTO faq_items (question, answer, category, sort_order, is_published, helpful_votes, unhelpful_votes) VALUES %s"
    insert_batch(conn, query, data, "faq_items")


def insert_site_menus(conn):
    """Inserts 10,000 site menu items."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        menu_name = f"Menu {i} {fake.word()}"[:50]
        location_code = f"LOC-{i}-{fake.hexify(text='^^')}"[:20]
        is_hierarchical = random.choice([True, False])
        item_count = random.randint(1, 15)
        theme_class = f"theme-menu-{random.choice(['dark', 'light', 'custom'])}"[:50]
        data.append((menu_name, location_code, is_hierarchical, item_count, theme_class))
    query = f"INSERT INTO site_menus (menu_name, location_code, is_hierarchical, item_count, theme_class) VALUES %s"
    insert_batch(conn, query, data, "site_menus")


def insert_seo_metadata(conn):
    """Inserts 10,000 SEO metadata templates."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        path_pattern = f"/pages/pattern/{i}/{fake.hexify(text='^^')}"[:255]
        title_template = f"Title {i} - {fake.word().capitalize()}"[:255]
        meta_description = fake.sentence()
        meta_keywords = f"key1,key2,keyword_{i}"[:255]
        og_type = random.choice(["website", "article", "profile"])[:50]
        robots_txt = random.choice(["index, follow", "noindex, nofollow", "index, nofollow"])[:50]
        data.append((path_pattern, title_template, meta_description, meta_keywords, og_type, robots_txt))
    query = f"INSERT INTO seo_metadata (path_pattern, title_template, meta_description, meta_keywords, og_type, robots_txt) VALUES %s"
    insert_batch(conn, query, data, "seo_metadata")


def insert_content_templates(conn):
    """Inserts 10,000 content templates."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        template_name = f"Template {i} {fake.word().capitalize()}"[:100]
        theme_name = f"Theme {random.choice(['Default', 'Material', 'Bootstrap', 'Vibrant'])}"[:50]
        markup = f"<html><body><h1>{template_name}</h1><div>{{content}}</div></body></html>"
        variables = {"author": "admin", "version": "1.0", "id": i}
        is_default = random.choice([True, False])
        data.append((template_name, theme_name, markup, json.dumps(variables), is_default))
    query = f"INSERT INTO content_templates (template_name, theme_name, markup, variables_json, is_default) VALUES %s"
    insert_batch(conn, query, data, "content_templates")


def insert_poll_questions(conn):
    """Inserts 10,000 poll questions."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        question = f"Question {i} : Which is your favorite {fake.word()}?"
        choices = {"options": [fake.word(), fake.word(), fake.word()]}
        total_votes = random.randint(0, 10000)
        allow_multiple = random.choice([True, False])
        start_date = fake.date_between(start_date='-30d', end_date='today')
        end_date = start_date + timedelta(days=30)
        data.append((question, json.dumps(choices), total_votes, allow_multiple, start_date, end_date))
    query = f"INSERT INTO poll_questions (question, choices_json, total_votes, allow_multiple, start_date, end_date) VALUES %s"
    insert_batch(conn, query, data, "poll_questions")


def insert_banner_ads(conn):
    """Inserts 10,000 banner ads."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        ad_name = f"Ad {i} {fake.company()}"[:100]
        image_url = f"https://cdn.adserver.com/banners/img_{i}.jpg"[:255]
        target_url = f"https://www.targetsite.com/promo?id={i}"[:255]
        zone_code = random.choice(["HEADER", "SIDEBAR", "FOOTER", "POPUP"])[:20]
        impressions = random.randint(0, 1000000)
        clicks = random.randint(0, impressions) if impressions > 0 else 0
        is_active = random.choice([True, False])
        data.append((ad_name, image_url, target_url, zone_code, impressions, clicks, is_active))
    query = f"INSERT INTO banner_ads (ad_name, image_url, target_url, zone_code, impressions, clicks, is_active) VALUES %s"
    insert_batch(conn, query, data, "banner_ads")


# --- Domain: Education (12 tables) ---

def insert_courses(conn):
    """Inserts 10,000 courses."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        course_code = f"CS-{i}-{fake.hexify(text='^^')}"[:20]
        title = f"Course {i}: Intro to {fake.word().capitalize()}"[:150]
        description = fake.paragraph()
        credits = random.choice([1, 2, 3, 4, 5])
        department = f"Department of {fake.word().capitalize()}"[:100]
        syllabus_url = f"https://university.edu/syllabus/cs-{i}.pdf"[:255]
        data.append((course_code, title, description, credits, department, syllabus_url))
    query = f"INSERT INTO courses (course_code, title, description, credits, department, syllabus_url) VALUES %s"
    insert_batch(conn, query, data, "courses")


def insert_enrollments(conn):
    """Inserts 10,000 enrollments."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        student_ref = f"STU-{i:05d}"
        course_ref = f"CS-{i:03d}"[:20]
        enrollment_date = fake.date_between(start_date='-2y', end_date='today')
        status = random.choice(["Enrolled", "Completed", "Dropped", "Withdrawn"])[:20]
        final_grade = random.choice(["A", "B", "C", "D", "F", "W", None])
        paid = random.choice([True, False])
        data.append((student_ref, course_ref, enrollment_date, status, final_grade, paid))
    query = f"INSERT INTO enrollments (student_ref, course_ref, enrollment_date, status, final_grade, paid) VALUES %s"
    insert_batch(conn, query, data, "enrollments")


def insert_certificates(conn):
    """Inserts 10,000 certificates."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        certificate_no = f"CERT-{i:05d}-{fake.hexify(text='^^^^')}"
        recipient_name = fake.name()[:100]
        course_title = f"Course {i} Graduation"[:150]
        issue_date = fake.date_between(start_date='-3y', end_date='today')
        grade_achieved = random.choice(["Pass", "Merit", "Distinction", "A", "B"])[:10]
        verification_hash = hashlib.sha256(f"CERT_{i}_{fake.word()}".encode()).hexdigest()[:64]
        data.append((certificate_no, recipient_name, course_title, issue_date, grade_achieved, verification_hash))
    query = f"INSERT INTO certificates (certificate_no, recipient_name, course_title, issue_date, grade_achieved, verification_hash) VALUES %s"
    insert_batch(conn, query, data, "certificates")


def insert_instructors(conn):
    """Inserts 10,000 instructors."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        first_name = fake.first_name()[:50]
        last_name = fake.last_name()[:50]
        email = f"instructor_{i}_{fake.email()}"[:100]
        office = f"Room {random.randint(100, 999)}"[:50]
        biography = fake.text(max_nb_chars=500)
        department = f"Department of {fake.word().capitalize()}"[:100]
        is_tenured = random.choice([True, False])
        data.append((first_name, last_name, email, office, biography, department, is_tenured))
    query = f"INSERT INTO instructors (first_name, last_name, email, office, biography, department, is_tenured) VALUES %s"
    insert_batch(conn, query, data, "instructors")


def insert_quiz_results(conn):
    """Inserts 10,000 quiz results."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        student_ref = f"STU-{i:05d}"
        quiz_name = f"Quiz {i} on {fake.word().capitalize()}"[:100]
        max_score = round(random.choice([10.0, 20.0, 50.0, 100.0]), 2)
        score = round(random.uniform(0, max_score), 2)
        time_taken_seconds = random.randint(60, 3600)
        submitted_at = datetime.now() - timedelta(days=random.randint(1, 30))
        data.append((student_ref, quiz_name, score, max_score, time_taken_seconds, submitted_at))
    query = f"INSERT INTO quiz_results (student_ref, quiz_name, score, max_score, time_taken_seconds, submitted_at) VALUES %s"
    insert_batch(conn, query, data, "quiz_results")


def insert_student_grades(conn):
    """Inserts 10,000 student grades."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        student_ref = f"STU-{i:05d}"
        term_name = f"Term-{i}"[:20]
        gpa = round(random.uniform(1.0, 4.0), 2)
        total_credits = random.choice([12, 15, 18, 20, 24])
        academic_standing = random.choice(["Good", "Probation", "Suspended", "Honor Roll"])[:50]
        notes = fake.sentence()
        data.append((student_ref, term_name, gpa, total_credits, academic_standing, notes))
    query = f"INSERT INTO student_grades (student_ref, term_name, gpa, total_credits, academic_standing, notes) VALUES %s"
    insert_batch(conn, query, data, "student_grades")


def insert_academic_terms(conn):
    """Inserts 10,000 academic terms."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        term_name = f"Term-{i}-{fake.hexify(text='^^')}"[:20]
        start_date = fake.date_between(start_date='-5y', end_date='+5y')
        end_date = start_date + timedelta(days=120)
        class_days = random.randint(80, 100)
        exam_start_date = end_date - timedelta(days=7)
        is_active = random.choice([True, False])
        data.append((term_name, start_date, end_date, class_days, exam_start_date, is_active))
    query = f"INSERT INTO academic_terms (term_name, start_date, end_date, class_days, exam_start_date, is_active) VALUES %s"
    insert_batch(conn, query, data, "academic_terms")


def insert_classrooms(conn):
    """Inserts 10,000 classrooms."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        building = f"Building {i // 100} {fake.street_name()}"[:100]
        room_number = f"Room-{i % 100}-{fake.hexify(text='^')}"[:20]
        capacity = random.randint(10, 300)
        has_projector = random.choice([True, False])
        has_lab_equipment = random.choice([True, False])
        data.append((building, room_number, capacity, has_projector, has_lab_equipment))
    query = f"INSERT INTO classrooms (building, room_number, capacity, has_projector, has_lab_equipment) VALUES %s"
    insert_batch(conn, query, data, "classrooms")


def insert_textbooks(conn):
    """Inserts 10,000 textbooks."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        isbn = f"978-0-12-{i:06d}"[:20]
        title = f"Textbook of {fake.word().capitalize()} Vol {i}"[:255]
        author = fake.name()[:150]
        publisher = fake.company()[:150]
        edition = random.randint(1, 15)
        price = round(random.uniform(19, 250), 2)
        data.append((isbn, title, author, publisher, edition, price))
    query = f"INSERT INTO textbooks (isbn, title, author, publisher, edition, price) VALUES %s"
    insert_batch(conn, query, data, "textbooks")


def insert_tuition_fees(conn):
    """Inserts 10,000 tuition fee items."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        fee_code = f"FEE-{i}-{fake.hexify(text='^^')}"[:20]
        description = f"Tuition payment details for {fake.word()}"[:255]
        amount = round(random.uniform(100, 15000), 2)
        semester = random.choice(["Fall 2026", "Spring 2026", "Summer 2026"])[:20]
        due_date = fake.date_between(start_date='today', end_date='+90d')
        is_refundable = random.choice([True, False])
        data.append((fee_code, description, amount, semester, due_date, is_refundable))
    query = f"INSERT INTO tuition_fees (fee_code, description, amount, semester, due_date, is_refundable) VALUES %s"
    insert_batch(conn, query, data, "tuition_fees")


def insert_alumni_records(conn):
    """Inserts 10,000 alumni records."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        student_ref = f"STU-{i}-{fake.hexify(text='^^')}"[:50]
        graduation_year = random.randint(1980, 2025)
        degree_program = f"Bachelor of {fake.word().capitalize()}"[:100]
        contact_email = f"alumni_{i}_{fake.email()}"[:100]
        donation_total = round(random.uniform(0, 100000), 2)
        current_employer = fake.company()[:150]
        data.append((student_ref, graduation_year, degree_program, contact_email, donation_total, current_employer))
    query = f"INSERT INTO alumni_records (student_ref, graduation_year, degree_program, contact_email, donation_total, current_employer) VALUES %s"
    insert_batch(conn, query, data, "alumni_records")


def insert_degree_programs(conn):
    """Inserts 10,000 degree programs."""
    data = []
    for i in range(1, ROWS_PER_TABLE + 1):
        program_name = f"Degree in {fake.job()} Science {i}"[:100]
        degree_type = random.choice(["BS", "BA", "MS", "MA", "PhD", "MBA"])[:10]
        minimum_credits = random.choice([60, 120, 180, 240])
        head_of_program = fake.name()[:100]
        department = f"Department of {fake.word().capitalize()}"[:100]
        accreditation_expiry = fake.date_between(start_date='today', end_date='+10y')
        data.append((program_name, degree_type, minimum_credits, head_of_program, department, accreditation_expiry))
    query = f"INSERT INTO degree_programs (program_name, degree_type, minimum_credits, head_of_program, department, accreditation_expiry) VALUES %s"
    insert_batch(conn, query, data, "degree_programs")


# ============================================================
# MAIN RUNNER
# ============================================================

def main():
    print("============================================================")
    print("Database Migration Data Generator Started")
    print(f"Target Tables: 100 | Target Rows per Table: {ROWS_PER_TABLE:,}")
    print(f"Expected Total Rows: {100 * ROWS_PER_TABLE:,}")
    print("============================================================")

    conn = None
    try:
        conn = connect_db()

        # Step 1: Clean existing data in correct dependency order
        print("\nStep 1: Truncating existing tables...")
        truncate_tables(conn)

        # Step 2: Insert dependent tables (in order of FK dependencies)
        print("\nStep 2: Populating dependent e-commerce tables...")
        insert_countries(conn)
        insert_regions(conn)
        insert_addresses(conn)
        insert_customers(conn)
        insert_suppliers(conn)
        insert_products(conn)
        insert_product_categories(conn)
        insert_product_variants(conn)
        insert_inventory(conn)
        insert_payment_methods(conn)
        insert_orders(conn)
        insert_order_items(conn)
        insert_supplier_products(conn)
        insert_payments(conn)
        insert_coupons(conn)
        insert_coupon_usage(conn)
        insert_shipment_tracking(conn)
        insert_reviews(conn)
        insert_carts(conn)
        insert_cart_items(conn)

        # Step 3: Insert independent tables
        print("\nStep 3: Populating independent tables (mixed domains)...")
        
        # HR Domain
        insert_employees(conn)
        insert_departments(conn)
        insert_job_roles(conn)
        insert_payroll_records(conn)
        insert_leave_requests(conn)
        insert_benefits_packages(conn)
        insert_employee_skills(conn)
        insert_performance_reviews(conn)
        insert_timesheets(conn)
        insert_training_sessions(conn)
        insert_employment_contracts(conn)

        # Finance Domain
        insert_gl_accounts(conn)
        insert_journal_entries(conn)
        insert_tax_records(conn)
        insert_budget_allocations(conn)
        insert_invoices(conn)
        insert_expense_reports(conn)
        insert_bank_transactions(conn)
        insert_purchase_orders(conn)
        insert_depreciation_schedules(conn)
        insert_fiscal_periods(conn)
        insert_currency_rates(conn)

        # Logistics Domain
        insert_warehouses(conn)
        insert_vehicles(conn)
        insert_delivery_routes(conn)
        insert_fuel_logs(conn)
        insert_maintenance_records(conn)
        insert_shipping_containers(conn)
        insert_freight_carriers(conn)
        insert_port_records(conn)
        insert_customs_declarations(conn)
        insert_cargo_manifests(conn)
        insert_driver_logs(conn)

        # CRM Domain
        insert_leads(conn)
        insert_campaigns(conn)
        insert_email_logs(conn)
        insert_sms_logs(conn)
        insert_survey_responses(conn)
        insert_marketing_lists(conn)
        insert_sales_pipelines(conn)
        insert_customer_feedback(conn)
        insert_webinar_attendees(conn)
        insert_competitor_trackers(conn)
        insert_referral_programs(conn)

        # IT Domain
        insert_audit_logs(conn)
        insert_error_logs(conn)
        insert_system_configs(conn)
        insert_api_keys(conn)
        insert_scheduled_jobs(conn)
        insert_user_sessions(conn)
        insert_server_metrics(conn)
        insert_backup_schedules(conn)
        insert_security_policies(conn)
        insert_network_nodes(conn)
        insert_access_tokens(conn)
        insert_ip_whitelists(conn)

        # CMS Domain
        insert_articles(conn)
        insert_tags(conn)
        insert_media_files(conn)
        insert_comments(conn)
        insert_page_views(conn)
        insert_newsletters(conn)
        insert_faq_items(conn)
        insert_site_menus(conn)
        insert_seo_metadata(conn)
        insert_content_templates(conn)
        insert_poll_questions(conn)
        insert_banner_ads(conn)

        # Education Domain
        insert_courses(conn)
        insert_enrollments(conn)
        insert_certificates(conn)
        insert_instructors(conn)
        insert_quiz_results(conn)
        insert_student_grades(conn)
        insert_academic_terms(conn)
        insert_classrooms(conn)
        insert_textbooks(conn)
        insert_tuition_fees(conn)
        insert_alumni_records(conn)
        insert_degree_programs(conn)

        total_inserted = 100 * ROWS_PER_TABLE
        print(f"\n[DONE] Total rows inserted: {total_inserted:,}")

    except Exception as e:
        print(f"\n[CRITICAL ERROR] Script aborted due to failure: {e}")
    finally:
        if conn:
            conn.close()
            print("[OK] Database connection closed.")


if __name__ == "__main__":
    main()
