-- ============================================================
-- Migration Project Database Schema (MySQL Version)
-- Generated for: Python Migration Project
-- Tables: 100 | Target rows: ~1,000,000
-- Domain: E-commerce (dependent) + Mixed (independent)
-- ============================================================

DROP DATABASE IF EXISTS migration_db;
CREATE DATABASE migration_db;
USE migration_db;

-- =============================================
-- SECTION 1: E-COMMERCE DEPENDENT TABLES (20)
-- =============================================

-- Table 1: countries
CREATE TABLE countries (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    iso_code VARCHAR(10) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 2: regions
CREATE TABLE regions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    country_id INT NOT NULL,
    name VARCHAR(100) NOT NULL,
    code VARCHAR(10) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(country_id, code),
    FOREIGN KEY (country_id) REFERENCES countries(id)
) ENGINE=InnoDB;

-- Table 3: addresses
CREATE TABLE addresses (
    id INT AUTO_INCREMENT PRIMARY KEY,
    region_id INT NOT NULL,
    street_address VARCHAR(255) NOT NULL,
    city VARCHAR(100) NOT NULL,
    postal_code VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (region_id) REFERENCES regions(id)
) ENGINE=InnoDB;

-- Table 4: customers
CREATE TABLE customers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    address_id INT NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    phone VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (address_id) REFERENCES addresses(id)
) ENGINE=InnoDB;

-- Table 5: suppliers
CREATE TABLE suppliers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(150) NOT NULL UNIQUE,
    contact_name VARCHAR(100),
    email VARCHAR(150) NOT NULL,
    phone VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 6: products
CREATE TABLE products (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    sku VARCHAR(50) NOT NULL UNIQUE,
    description TEXT,
    price DECIMAL(10, 2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 7: product_categories
CREATE TABLE product_categories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 8: product_variants
CREATE TABLE product_variants (
    id INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT NOT NULL,
    category_id INT NOT NULL,
    sku VARCHAR(50) NOT NULL UNIQUE,
    price_modifier DECIMAL(10, 2) DEFAULT 0.00,
    option_name VARCHAR(50),
    option_value VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(id),
    FOREIGN KEY (category_id) REFERENCES product_categories(id)
) ENGINE=InnoDB;

-- Table 9: inventory
CREATE TABLE inventory (
    id INT AUTO_INCREMENT PRIMARY KEY,
    variant_id INT NOT NULL UNIQUE,
    quantity INT NOT NULL DEFAULT 0,
    warehouse_code VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (variant_id) REFERENCES product_variants(id)
) ENGINE=InnoDB;

-- Table 10: payment_methods
CREATE TABLE payment_methods (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 11: orders
CREATE TABLE orders (
    id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NOT NULL,
    payment_method_id INT NOT NULL,
    order_number VARCHAR(50) NOT NULL UNIQUE,
    total_amount DECIMAL(10, 2) NOT NULL,
    status VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (payment_method_id) REFERENCES payment_methods(id)
) ENGINE=InnoDB;

-- Table 12: order_items
CREATE TABLE order_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    variant_id INT NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(10, 2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(order_id, variant_id),
    FOREIGN KEY (order_id) REFERENCES orders(id),
    FOREIGN KEY (variant_id) REFERENCES product_variants(id)
) ENGINE=InnoDB;

-- Table 13: supplier_products
CREATE TABLE supplier_products (
    id INT AUTO_INCREMENT PRIMARY KEY,
    supplier_id INT NOT NULL,
    product_id INT NOT NULL,
    wholesale_price DECIMAL(10, 2) NOT NULL,
    lead_time_days INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(supplier_id, product_id),
    FOREIGN KEY (supplier_id) REFERENCES suppliers(id),
    FOREIGN KEY (product_id) REFERENCES products(id)
) ENGINE=InnoDB;

-- Table 14: payments
CREATE TABLE payments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    payment_method_id INT NOT NULL,
    transaction_reference VARCHAR(100) NOT NULL UNIQUE,
    amount DECIMAL(10, 2) NOT NULL,
    status VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES orders(id),
    FOREIGN KEY (payment_method_id) REFERENCES payment_methods(id)
) ENGINE=InnoDB;

-- Table 15: coupons
CREATE TABLE coupons (
    id INT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(50) NOT NULL UNIQUE,
    discount_type VARCHAR(20) NOT NULL,
    discount_value DECIMAL(10, 2) NOT NULL,
    expires_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 16: coupon_usage
CREATE TABLE coupon_usage (
    id INT AUTO_INCREMENT PRIMARY KEY,
    coupon_id INT NOT NULL,
    customer_id INT NOT NULL,
    used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(coupon_id, customer_id, used_at),
    FOREIGN KEY (coupon_id) REFERENCES coupons(id),
    FOREIGN KEY (customer_id) REFERENCES customers(id)
) ENGINE=InnoDB;

-- Table 17: shipment_tracking
CREATE TABLE shipment_tracking (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    tracking_number VARCHAR(100) NOT NULL UNIQUE,
    carrier VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL,
    shipped_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES orders(id)
) ENGINE=InnoDB;

-- Table 18: reviews
CREATE TABLE reviews (
    id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NOT NULL,
    product_id INT NOT NULL,
    rating INT NOT NULL,
    review_text TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(customer_id, product_id),
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (product_id) REFERENCES products(id)
) ENGINE=InnoDB;

-- Table 19: carts
CREATE TABLE carts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id)
) ENGINE=InnoDB;

-- Table 20: cart_items
CREATE TABLE cart_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cart_id INT NOT NULL,
    variant_id INT NOT NULL,
    quantity INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(cart_id, variant_id),
    FOREIGN KEY (cart_id) REFERENCES carts(id),
    FOREIGN KEY (variant_id) REFERENCES product_variants(id)
) ENGINE=InnoDB;

-- =============================================
-- SECTION 2: INDEPENDENT TABLES (80)
-- =============================================

-- Table 21: employees (HR)
CREATE TABLE employees (
    id VARCHAR(36) PRIMARY KEY DEFAULT (UUID()),
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    phone_number VARCHAR(50),
    hire_date DATE NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 22: departments (HR)
CREATE TABLE departments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    dept_name VARCHAR(100) NOT NULL UNIQUE,
    code VARCHAR(10) NOT NULL UNIQUE,
    budget DECIMAL(12, 2) NOT NULL,
    manager_name VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 23: job_roles (HR)
CREATE TABLE job_roles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    min_salary DECIMAL(10, 2) NOT NULL,
    max_salary DECIMAL(10, 2) NOT NULL,
    grade VARCHAR(5) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 24: payroll_records (HR)
CREATE TABLE payroll_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    employee_ref VARCHAR(50) NOT NULL,
    pay_period VARCHAR(20) NOT NULL,
    gross_pay DECIMAL(10, 2) NOT NULL,
    deductions DECIMAL(10, 2) NOT NULL,
    net_pay DECIMAL(10, 2) NOT NULL,
    payment_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 25: leave_requests (HR)
CREATE TABLE leave_requests (
    id INT AUTO_INCREMENT PRIMARY KEY,
    employee_ref VARCHAR(50) NOT NULL,
    leave_type VARCHAR(50) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    status VARCHAR(20) NOT NULL,
    approved_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 26: benefits_packages (HR)
CREATE TABLE benefits_packages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    package_name VARCHAR(100) NOT NULL UNIQUE,
    provider VARCHAR(100) NOT NULL,
    monthly_premium DECIMAL(8, 2) NOT NULL,
    coverage_details TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 27: employee_skills (HR)
CREATE TABLE employee_skills (
    id INT AUTO_INCREMENT PRIMARY KEY,
    employee_ref VARCHAR(50) NOT NULL,
    skill_name VARCHAR(100) NOT NULL,
    proficiency_level VARCHAR(20) NOT NULL,
    years_experience INT NOT NULL,
    certified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 28: performance_reviews (HR)
CREATE TABLE performance_reviews (
    id INT AUTO_INCREMENT PRIMARY KEY,
    employee_ref VARCHAR(50) NOT NULL,
    reviewer_name VARCHAR(100) NOT NULL,
    review_date DATE NOT NULL,
    rating INT NOT NULL,
    achievements TEXT,
    improvement_areas TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 29: timesheets (HR)
CREATE TABLE timesheets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    employee_ref VARCHAR(50) NOT NULL,
    work_date DATE NOT NULL,
    regular_hours DECIMAL(4, 2) NOT NULL,
    overtime_hours DECIMAL(4, 2) NOT NULL,
    description TEXT,
    is_approved BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 30: training_sessions (HR)
CREATE TABLE training_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    topic VARCHAR(150) NOT NULL,
    trainer VARCHAR(100) NOT NULL,
    scheduled_at TIMESTAMP NOT NULL,
    duration_hours INT NOT NULL,
    max_participants INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 31: employment_contracts (HR)
CREATE TABLE employment_contracts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    employee_ref VARCHAR(50) NOT NULL UNIQUE,
    contract_type VARCHAR(50) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE,
    salary_rate DECIMAL(10, 2) NOT NULL,
    terms TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 32: gl_accounts (Finance)
CREATE TABLE gl_accounts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    account_code VARCHAR(20) NOT NULL UNIQUE,
    account_name VARCHAR(100) NOT NULL,
    account_type VARCHAR(50) NOT NULL,
    currency VARCHAR(3) DEFAULT 'USD',
    is_active BOOLEAN DEFAULT TRUE,
    current_balance DECIMAL(15, 2) DEFAULT 0.00,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 33: journal_entries (Finance)
CREATE TABLE journal_entries (
    id INT AUTO_INCREMENT PRIMARY KEY,
    entry_date TIMESTAMP NOT NULL,
    description TEXT NOT NULL,
    source_doc VARCHAR(50),
    created_by VARCHAR(100) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    posted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 34: tax_records (Finance)
CREATE TABLE tax_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tax_period VARCHAR(10) NOT NULL,
    jurisdiction VARCHAR(50) NOT NULL,
    tax_type VARCHAR(50) NOT NULL,
    gross_amount DECIMAL(12, 2) NOT NULL,
    tax_rate DECIMAL(5, 4) NOT NULL,
    tax_amount DECIMAL(12, 2) NOT NULL,
    paid BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 35: budget_allocations (Finance)
CREATE TABLE budget_allocations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    fiscal_year INT NOT NULL,
    department_code VARCHAR(20) NOT NULL,
    allocated_amount DECIMAL(12, 2) NOT NULL,
    spent_amount DECIMAL(12, 2) DEFAULT 0.00,
    notes TEXT,
    approved_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 36: invoices (Finance)
CREATE TABLE invoices (
    id VARCHAR(36) PRIMARY KEY DEFAULT (UUID()),
    invoice_number VARCHAR(50) NOT NULL UNIQUE,
    customer_ref VARCHAR(50) NOT NULL,
    issue_date DATE NOT NULL,
    due_date DATE NOT NULL,
    subtotal DECIMAL(10, 2) NOT NULL,
    tax_amount DECIMAL(10, 2) NOT NULL,
    total_amount DECIMAL(10, 2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 37: expense_reports (Finance)
CREATE TABLE expense_reports (
    id INT AUTO_INCREMENT PRIMARY KEY,
    employee_ref VARCHAR(50) NOT NULL,
    purpose VARCHAR(255) NOT NULL,
    total_claimed DECIMAL(10, 2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    approved_date DATE,
    audited BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 38: bank_transactions (Finance)
CREATE TABLE bank_transactions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    bank_account_no VARCHAR(50) NOT NULL,
    transaction_date TIMESTAMP NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    transaction_type VARCHAR(10) NOT NULL,
    description VARCHAR(255) NOT NULL,
    reference_no VARCHAR(100) UNIQUE,
    reconciled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 39: purchase_orders (Finance)
CREATE TABLE purchase_orders (
    id INT AUTO_INCREMENT PRIMARY KEY,
    po_number VARCHAR(50) NOT NULL UNIQUE,
    vendor_ref VARCHAR(50) NOT NULL,
    order_date DATE NOT NULL,
    expected_delivery DATE,
    total_amount DECIMAL(12, 2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    terms TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 40: depreciation_schedules (Finance)
CREATE TABLE depreciation_schedules (
    id INT AUTO_INCREMENT PRIMARY KEY,
    asset_ref VARCHAR(50) NOT NULL,
    purchase_cost DECIMAL(12, 2) NOT NULL,
    salvage_value DECIMAL(12, 2) NOT NULL,
    useful_life_years INT NOT NULL,
    depreciation_method VARCHAR(50) NOT NULL,
    accumulated_depreciation DECIMAL(12, 2) DEFAULT 0.00,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 41: fiscal_periods (Finance)
CREATE TABLE fiscal_periods (
    id INT AUTO_INCREMENT PRIMARY KEY,
    period_name VARCHAR(20) NOT NULL UNIQUE,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    is_closed BOOLEAN DEFAULT FALSE,
    closed_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 42: currency_rates (Finance)
CREATE TABLE currency_rates (
    id INT AUTO_INCREMENT PRIMARY KEY,
    from_currency VARCHAR(3) NOT NULL,
    to_currency VARCHAR(3) NOT NULL,
    exchange_rate DECIMAL(10, 6) NOT NULL,
    effective_date DATE NOT NULL,
    source_name VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 43: warehouses (Logistics)
CREATE TABLE warehouses (
    id INT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(20) NOT NULL UNIQUE,
    location_name VARCHAR(150) NOT NULL,
    address VARCHAR(255) NOT NULL,
    capacity_cubic_meters DECIMAL(10, 2) NOT NULL,
    manager_name VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 44: vehicles (Logistics)
CREATE TABLE vehicles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    vin VARCHAR(17) NOT NULL UNIQUE,
    license_plate VARCHAR(20) NOT NULL UNIQUE,
    make VARCHAR(50) NOT NULL,
    model VARCHAR(50) NOT NULL,
    year INT NOT NULL,
    fuel_type VARCHAR(20) NOT NULL,
    payload_capacity_lbs INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 45: delivery_routes (Logistics)
CREATE TABLE delivery_routes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    route_code VARCHAR(20) NOT NULL UNIQUE,
    start_location VARCHAR(150) NOT NULL,
    end_location VARCHAR(150) NOT NULL,
    distance_km DECIMAL(8, 2) NOT NULL,
    estimated_duration_hours DECIMAL(5, 2) NOT NULL,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 46: fuel_logs (Logistics)
CREATE TABLE fuel_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    vehicle_ref VARCHAR(50) NOT NULL,
    log_date TIMESTAMP NOT NULL,
    gallons DECIMAL(6, 2) NOT NULL,
    price_per_gallon DECIMAL(4, 2) NOT NULL,
    total_cost DECIMAL(8, 2) NOT NULL,
    odometer_reading INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 47: maintenance_records (Logistics)
CREATE TABLE maintenance_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    vehicle_ref VARCHAR(50) NOT NULL,
    maintenance_date DATE NOT NULL,
    service_type VARCHAR(100) NOT NULL,
    description TEXT,
    cost DECIMAL(8, 2) NOT NULL,
    vendor_name VARCHAR(100),
    next_due_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 48: shipping_containers (Logistics)
CREATE TABLE shipping_containers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    container_no VARCHAR(20) NOT NULL UNIQUE,
    size_feet INT NOT NULL,
    tare_weight_kg INT NOT NULL,
    max_payload_kg INT NOT NULL,
    owner_company VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 49: freight_carriers (Logistics)
CREATE TABLE freight_carriers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    carrier_name VARCHAR(100) NOT NULL UNIQUE,
    scac_code VARCHAR(4) NOT NULL UNIQUE,
    contact_email VARCHAR(100) NOT NULL,
    contact_phone VARCHAR(50),
    rating DECIMAL(3, 2),
    is_preferred BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 50: port_records (Logistics)
CREATE TABLE port_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    port_code VARCHAR(10) NOT NULL UNIQUE,
    port_name VARCHAR(100) NOT NULL,
    country VARCHAR(100) NOT NULL,
    terminal_count INT NOT NULL,
    daily_vessel_capacity INT NOT NULL,
    latitude DECIMAL(9, 6) NOT NULL,
    longitude DECIMAL(9, 6) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 51: customs_declarations (Logistics)
CREATE TABLE customs_declarations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    declaration_ref VARCHAR(50) NOT NULL UNIQUE,
    shipper_name VARCHAR(100) NOT NULL,
    consignee_name VARCHAR(100) NOT NULL,
    declared_value_usd DECIMAL(12, 2) NOT NULL,
    duty_amount_usd DECIMAL(10, 2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    clearance_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 52: cargo_manifests (Logistics)
CREATE TABLE cargo_manifests (
    id INT AUTO_INCREMENT PRIMARY KEY,
    manifest_no VARCHAR(50) NOT NULL UNIQUE,
    vessel_name VARCHAR(100) NOT NULL,
    voyage_number VARCHAR(20) NOT NULL,
    load_port_code VARCHAR(10) NOT NULL,
    discharge_port_code VARCHAR(10) NOT NULL,
    total_weight_tons DECIMAL(10, 2) NOT NULL,
    container_count INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 53: driver_logs (Logistics)
CREATE TABLE driver_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    driver_license VARCHAR(30) NOT NULL UNIQUE,
    driver_name VARCHAR(100) NOT NULL,
    log_date DATE NOT NULL,
    on_duty_hours DECIMAL(4, 2) NOT NULL,
    driving_hours DECIMAL(4, 2) NOT NULL,
    sleeper_berth_hours DECIMAL(4, 2) NOT NULL,
    violation_occurred BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 54: leads (CRM)
CREATE TABLE leads (
    id INT AUTO_INCREMENT PRIMARY KEY,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    phone VARCHAR(50),
    company VARCHAR(100),
    source VARCHAR(50) NOT NULL,
    score INT DEFAULT 0,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 55: campaigns (CRM)
CREATE TABLE campaigns (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    type VARCHAR(50) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    budget DECIMAL(10, 2) NOT NULL,
    actual_cost DECIMAL(10, 2) DEFAULT 0.00,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 56: email_logs (CRM)
CREATE TABLE email_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    campaign_ref VARCHAR(50) NOT NULL,
    recipient_email VARCHAR(100) NOT NULL,
    sent_at TIMESTAMP NOT NULL,
    status VARCHAR(20) NOT NULL,
    opened BOOLEAN DEFAULT FALSE,
    clicked BOOLEAN DEFAULT FALSE,
    bounced BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 57: sms_logs (CRM)
CREATE TABLE sms_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    campaign_ref VARCHAR(50) NOT NULL,
    recipient_phone VARCHAR(50) NOT NULL,
    sent_at TIMESTAMP NOT NULL,
    message_body TEXT NOT NULL,
    status VARCHAR(20) NOT NULL,
    carrier_code VARCHAR(20),
    cost DECIMAL(6, 4) DEFAULT 0.0000,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 58: survey_responses (CRM)
CREATE TABLE survey_responses (
    id INT AUTO_INCREMENT PRIMARY KEY,
    survey_name VARCHAR(100) NOT NULL,
    responder_email VARCHAR(100) NOT NULL,
    question_id INT NOT NULL,
    answer_score INT NOT NULL,
    comments TEXT,
    submitted_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 59: marketing_lists (CRM)
CREATE TABLE marketing_lists (
    id INT AUTO_INCREMENT PRIMARY KEY,
    list_name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    segment_criteria VARCHAR(255),
    is_smart_list BOOLEAN DEFAULT FALSE,
    member_count INT DEFAULT 0,
    last_synced_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 60: sales_pipelines (CRM)
CREATE TABLE sales_pipelines (
    id INT AUTO_INCREMENT PRIMARY KEY,
    pipeline_name VARCHAR(100) NOT NULL UNIQUE,
    stage_name VARCHAR(50) NOT NULL,
    display_order INT NOT NULL,
    probability_pct INT NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 61: customer_feedback (CRM)
CREATE TABLE customer_feedback (
    id INT AUTO_INCREMENT PRIMARY KEY,
    customer_ref VARCHAR(50) NOT NULL,
    feedback_type VARCHAR(20) NOT NULL,
    subject VARCHAR(150) NOT NULL,
    details TEXT NOT NULL,
    severity VARCHAR(10) NOT NULL,
    assigned_to VARCHAR(100),
    resolved BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 62: webinar_attendees (CRM)
CREATE TABLE webinar_attendees (
    id INT AUTO_INCREMENT PRIMARY KEY,
    webinar_id VARCHAR(50) NOT NULL,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    email VARCHAR(100) NOT NULL,
    registered_at TIMESTAMP NOT NULL,
    attended BOOLEAN DEFAULT FALSE,
    duration_minutes INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 63: competitor_trackers (CRM)
CREATE TABLE competitor_trackers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    competitor_name VARCHAR(100) NOT NULL,
    product_name VARCHAR(100) NOT NULL,
    url VARCHAR(255),
    monitored_price DECIMAL(10, 2) NOT NULL,
    availability VARCHAR(20) NOT NULL,
    last_checked_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 64: referral_programs (CRM)
CREATE TABLE referral_programs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    program_name VARCHAR(100) NOT NULL UNIQUE,
    referral_code_prefix VARCHAR(10) NOT NULL,
    reward_type VARCHAR(50) NOT NULL,
    reward_value DECIMAL(10, 2) NOT NULL,
    max_referrals INT DEFAULT 10,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 65: audit_logs (IT)
CREATE TABLE audit_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) NOT NULL,
    action VARCHAR(50) NOT NULL,
    table_name VARCHAR(100) NOT NULL,
    row_id VARCHAR(100),
    old_values JSON,
    new_values JSON,
    ip_address VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 66: error_logs (IT)
CREATE TABLE error_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    app_name VARCHAR(100) NOT NULL,
    error_class VARCHAR(100) NOT NULL,
    error_message TEXT NOT NULL,
    stack_trace TEXT,
    severity VARCHAR(20) NOT NULL,
    is_resolved BOOLEAN DEFAULT FALSE,
    resolved_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 67: system_configs (IT)
CREATE TABLE system_configs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    config_key VARCHAR(100) NOT NULL UNIQUE,
    config_value TEXT NOT NULL,
    data_type VARCHAR(20) NOT NULL,
    category VARCHAR(50) NOT NULL,
    is_encrypted BOOLEAN DEFAULT FALSE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 68: api_keys (IT)
CREATE TABLE api_keys (
    id VARCHAR(36) PRIMARY KEY DEFAULT (UUID()),
    key_name VARCHAR(100) NOT NULL,
    hashed_key VARCHAR(64) NOT NULL UNIQUE,
    scopes TEXT NOT NULL,
    rate_limit_rpm INT DEFAULT 60,
    is_active BOOLEAN DEFAULT TRUE,
    expires_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 69: scheduled_jobs (IT)
CREATE TABLE scheduled_jobs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    job_name VARCHAR(100) NOT NULL UNIQUE,
    job_group VARCHAR(50) NOT NULL,
    cron_expression VARCHAR(50) NOT NULL,
    class_name VARCHAR(255) NOT NULL,
    is_concurrent BOOLEAN DEFAULT FALSE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 70: user_sessions (IT)
CREATE TABLE user_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(100) NOT NULL UNIQUE,
    username VARCHAR(100) NOT NULL,
    ip_address VARCHAR(50) NOT NULL,
    user_agent VARCHAR(255) NOT NULL,
    payload TEXT,
    last_activity TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 71: server_metrics (IT)
CREATE TABLE server_metrics (
    id INT AUTO_INCREMENT PRIMARY KEY,
    server_id VARCHAR(50) NOT NULL,
    cpu_pct DECIMAL(5, 2) NOT NULL,
    ram_pct DECIMAL(5, 2) NOT NULL,
    disk_pct DECIMAL(5, 2) NOT NULL,
    network_in_mb DECIMAL(10, 2) NOT NULL,
    network_out_mb DECIMAL(10, 2) NOT NULL,
    recorded_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 72: backup_schedules (IT)
CREATE TABLE backup_schedules (
    id INT AUTO_INCREMENT PRIMARY KEY,
    backup_name VARCHAR(100) NOT NULL UNIQUE,
    source_path VARCHAR(255) NOT NULL,
    dest_bucket VARCHAR(100) NOT NULL,
    backup_type VARCHAR(10) NOT NULL,
    compression VARCHAR(10) NOT NULL,
    retention_days INT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 73: security_policies (IT)
CREATE TABLE security_policies (
    id INT AUTO_INCREMENT PRIMARY KEY,
    policy_code VARCHAR(50) NOT NULL UNIQUE,
    policy_name VARCHAR(150) NOT NULL,
    description TEXT NOT NULL,
    min_privilege_level VARCHAR(20) NOT NULL,
    enforced BOOLEAN DEFAULT TRUE,
    last_reviewed_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 74: network_nodes (IT)
CREATE TABLE network_nodes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    node_name VARCHAR(100) NOT NULL UNIQUE,
    node_type VARCHAR(50) NOT NULL,
    ip_address VARCHAR(50) NOT NULL UNIQUE,
    mac_address VARCHAR(50) NOT NULL UNIQUE,
    subnet_mask VARCHAR(50) NOT NULL,
    gateway VARCHAR(50) NOT NULL,
    rack_unit INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 75: access_tokens (IT)
CREATE TABLE access_tokens (
    id INT AUTO_INCREMENT PRIMARY KEY,
    jti VARCHAR(100) NOT NULL UNIQUE,
    subject VARCHAR(100) NOT NULL,
    issuer VARCHAR(100) NOT NULL,
    audience VARCHAR(100) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    is_blacklisted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 76: ip_whitelists (IT)
CREATE TABLE ip_whitelists (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cidr_block VARCHAR(50) NOT NULL UNIQUE,
    description VARCHAR(255) NOT NULL,
    environment VARCHAR(20) NOT NULL,
    requested_by VARCHAR(100) NOT NULL,
    approved_by VARCHAR(100) NOT NULL,
    expiry_date TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 77: articles (CMS)
CREATE TABLE articles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(150) NOT NULL,
    slug VARCHAR(150) NOT NULL UNIQUE,
    body TEXT NOT NULL,
    author_name VARCHAR(100) NOT NULL,
    publish_date TIMESTAMP NULL,
    status VARCHAR(20) NOT NULL,
    view_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 78: tags (CMS)
CREATE TABLE tags (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    slug VARCHAR(50) NOT NULL UNIQUE,
    description TEXT,
    color_hex VARCHAR(7) NOT NULL,
    post_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 79: media_files (CMS)
CREATE TABLE media_files (
    id INT AUTO_INCREMENT PRIMARY KEY,
    file_name VARCHAR(255) NOT NULL,
    file_path VARCHAR(255) NOT NULL UNIQUE,
    mime_type VARCHAR(100) NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    dimensions VARCHAR(20),
    caption TEXT,
    uploaded_by VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 80: comments (CMS)
CREATE TABLE comments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    article_ref VARCHAR(150) NOT NULL,
    author_name VARCHAR(100) NOT NULL,
    author_email VARCHAR(100) NOT NULL,
    body TEXT NOT NULL,
    ip_address VARCHAR(50),
    is_approved BOOLEAN DEFAULT FALSE,
    likes INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 81: page_views (CMS)
CREATE TABLE page_views (
    id INT AUTO_INCREMENT PRIMARY KEY,
    page_url VARCHAR(255) NOT NULL,
    referrer_url VARCHAR(255),
    user_agent VARCHAR(255),
    session_id VARCHAR(100),
    load_time_ms INT NOT NULL,
    ip_address VARCHAR(50),
    viewed_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 82: newsletters (CMS)
CREATE TABLE newsletters (
    id INT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(50) NOT NULL UNIQUE,
    title VARCHAR(150) NOT NULL,
    description TEXT,
    schedule_day VARCHAR(20) NOT NULL,
    subscriber_count INT DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 83: faq_items (CMS)
CREATE TABLE faq_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    category VARCHAR(50) NOT NULL,
    sort_order INT DEFAULT 0,
    is_published BOOLEAN DEFAULT TRUE,
    helpful_votes INT DEFAULT 0,
    unhelpful_votes INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 84: site_menus (CMS)
CREATE TABLE site_menus (
    id INT AUTO_INCREMENT PRIMARY KEY,
    menu_name VARCHAR(50) NOT NULL UNIQUE,
    location_code VARCHAR(20) NOT NULL UNIQUE,
    is_hierarchical BOOLEAN DEFAULT FALSE,
    item_count INT DEFAULT 0,
    theme_class VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 85: seo_metadata (CMS)
CREATE TABLE seo_metadata (
    id INT AUTO_INCREMENT PRIMARY KEY,
    path_pattern VARCHAR(255) NOT NULL UNIQUE,
    title_template VARCHAR(255) NOT NULL,
    meta_description TEXT NOT NULL,
    meta_keywords VARCHAR(255),
    og_type VARCHAR(50) DEFAULT 'website',
    robots_txt VARCHAR(50) DEFAULT 'index, follow',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 86: content_templates (CMS)
CREATE TABLE content_templates (
    id INT AUTO_INCREMENT PRIMARY KEY,
    template_name VARCHAR(100) NOT NULL UNIQUE,
    theme_name VARCHAR(50) NOT NULL,
    markup TEXT NOT NULL,
    variables_json JSON,
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 87: poll_questions (CMS)
CREATE TABLE poll_questions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    question TEXT NOT NULL,
    choices_json JSON NOT NULL,
    total_votes INT DEFAULT 0,
    allow_multiple BOOLEAN DEFAULT FALSE,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 88: banner_ads (CMS)
CREATE TABLE banner_ads (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ad_name VARCHAR(100) NOT NULL UNIQUE,
    image_url VARCHAR(255) NOT NULL,
    target_url VARCHAR(255) NOT NULL,
    zone_code VARCHAR(20) NOT NULL,
    impressions INT DEFAULT 0,
    clicks INT DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 89: courses (Education)
CREATE TABLE courses (
    id INT AUTO_INCREMENT PRIMARY KEY,
    course_code VARCHAR(20) NOT NULL UNIQUE,
    title VARCHAR(150) NOT NULL,
    description TEXT,
    credits INT NOT NULL,
    department VARCHAR(100) NOT NULL,
    syllabus_url VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 90: enrollments (Education)
CREATE TABLE enrollments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_ref VARCHAR(50) NOT NULL,
    course_ref VARCHAR(20) NOT NULL,
    enrollment_date DATE NOT NULL,
    status VARCHAR(20) NOT NULL,
    final_grade VARCHAR(2),
    paid BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 91: certificates (Education)
CREATE TABLE certificates (
    id VARCHAR(36) PRIMARY KEY DEFAULT (UUID()),
    certificate_no VARCHAR(50) NOT NULL UNIQUE,
    recipient_name VARCHAR(100) NOT NULL,
    course_title VARCHAR(150) NOT NULL,
    issue_date DATE NOT NULL,
    grade_achieved VARCHAR(10) NOT NULL,
    verification_hash VARCHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 92: instructors (Education)
CREATE TABLE instructors (
    id INT AUTO_INCREMENT PRIMARY KEY,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    office VARCHAR(50),
    biography TEXT,
    department VARCHAR(100) NOT NULL,
    is_tenured BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 93: quiz_results (Education)
CREATE TABLE quiz_results (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_ref VARCHAR(50) NOT NULL,
    quiz_name VARCHAR(100) NOT NULL,
    score DECIMAL(5, 2) NOT NULL,
    max_score DECIMAL(5, 2) NOT NULL,
    time_taken_seconds INT NOT NULL,
    submitted_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 94: student_grades (Education)
CREATE TABLE student_grades (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_ref VARCHAR(50) NOT NULL,
    term_name VARCHAR(20) NOT NULL,
    gpa DECIMAL(3, 2) NOT NULL,
    total_credits INT NOT NULL,
    academic_standing VARCHAR(50) NOT NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 95: academic_terms (Education)
CREATE TABLE academic_terms (
    id INT AUTO_INCREMENT PRIMARY KEY,
    term_name VARCHAR(20) NOT NULL UNIQUE,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    class_days INT NOT NULL,
    exam_start_date DATE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 96: classrooms (Education)
CREATE TABLE classrooms (
    id INT AUTO_INCREMENT PRIMARY KEY,
    building VARCHAR(100) NOT NULL,
    room_number VARCHAR(20) NOT NULL,
    capacity INT NOT NULL,
    has_projector BOOLEAN DEFAULT FALSE,
    has_lab_equipment BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(building, room_number)
) ENGINE=InnoDB;

-- Table 97: textbooks (Education)
CREATE TABLE textbooks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    isbn VARCHAR(20) NOT NULL UNIQUE,
    title VARCHAR(255) NOT NULL,
    author VARCHAR(150) NOT NULL,
    publisher VARCHAR(150) NOT NULL,
    edition INT NOT NULL,
    price DECIMAL(6, 2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 98: tuition_fees (Education)
CREATE TABLE tuition_fees (
    id INT AUTO_INCREMENT PRIMARY KEY,
    fee_code VARCHAR(20) NOT NULL UNIQUE,
    description VARCHAR(255) NOT NULL,
    amount DECIMAL(8, 2) NOT NULL,
    semester VARCHAR(20) NOT NULL,
    due_date DATE NOT NULL,
    is_refundable BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 99: alumni_records (Education)
CREATE TABLE alumni_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_ref VARCHAR(50) NOT NULL UNIQUE,
    graduation_year INT NOT NULL,
    degree_program VARCHAR(100) NOT NULL,
    contact_email VARCHAR(100) NOT NULL,
    donation_total DECIMAL(10, 2) DEFAULT 0.00,
    current_employer VARCHAR(150),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 100: degree_programs (Education)
CREATE TABLE degree_programs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    program_name VARCHAR(100) NOT NULL UNIQUE,
    degree_type VARCHAR(10) NOT NULL,
    minimum_credits INT NOT NULL,
    head_of_program VARCHAR(100) NOT NULL,
    department VARCHAR(100) NOT NULL,
    accreditation_expiry DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- =============================================
-- SECTION 3: INDEXES
-- =============================================

CREATE INDEX idx_regions_country_id ON regions (country_id);
CREATE INDEX idx_addresses_region_id ON addresses (region_id);
CREATE INDEX idx_customers_address_id ON customers (address_id);
CREATE INDEX idx_product_variants_product_id ON product_variants (product_id);
CREATE INDEX idx_product_variants_category_id ON product_variants (category_id);
CREATE INDEX idx_inventory_variant_id ON inventory (variant_id);
CREATE INDEX idx_orders_customer_id ON orders (customer_id);
CREATE INDEX idx_orders_payment_method_id ON orders (payment_method_id);
CREATE INDEX idx_order_items_order_id ON order_items (order_id);
CREATE INDEX idx_order_items_variant_id ON order_items (variant_id);
CREATE INDEX idx_supplier_products_supplier_id ON supplier_products (supplier_id);
CREATE INDEX idx_supplier_products_product_id ON supplier_products (product_id);
CREATE INDEX idx_payments_order_id ON payments (order_id);
CREATE INDEX idx_payments_payment_method_id ON payments (payment_method_id);
CREATE INDEX idx_coupon_usage_coupon_id ON coupon_usage (coupon_id);
CREATE INDEX idx_coupon_usage_customer_id ON coupon_usage (customer_id);
CREATE INDEX idx_shipment_tracking_order_id ON shipment_tracking (order_id);
CREATE INDEX idx_reviews_customer_id ON reviews (customer_id);
CREATE INDEX idx_reviews_product_id ON reviews (product_id);
CREATE INDEX idx_carts_customer_id ON carts (customer_id);
CREATE INDEX idx_cart_items_cart_id ON cart_items (cart_id);
CREATE INDEX idx_cart_items_variant_id ON cart_items (variant_id);
