-- =============================================
-- SPESHO Products Management System
-- PostgreSQL Schema with Indexes
-- =============================================

-- Enable UUID extension (optional)
-- CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Drop tables if they exist (for re-initialization)
DROP TABLE IF EXISTS sales CASCADE;
DROP TABLE IF EXISTS stock_movements CASCADE;
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- =============================================
-- USERS TABLE
-- =============================================
CREATE TABLE users (
    id          SERIAL PRIMARY KEY,
    username    VARCHAR(80) UNIQUE NOT NULL,
    password_hash VARCHAR(256) NOT NULL,
    role        VARCHAR(20) NOT NULL CHECK (role IN ('manager', 'salesperson')),
    full_name   VARCHAR(120),
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_role ON users(role);

-- =============================================
-- PRODUCTS TABLE
-- =============================================
CREATE TABLE products (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(120) UNIQUE NOT NULL,
    unit_price  NUMERIC(12,2) NOT NULL,
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_products_name ON products(name);
CREATE INDEX idx_products_is_active ON products(is_active);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_products_updated_at
    BEFORE UPDATE ON products
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- STOCK MOVEMENTS TABLE
-- =============================================
CREATE TABLE stock_movements (
    id              SERIAL PRIMARY KEY,
    product_id      INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    quantity_in     NUMERIC(12,2) DEFAULT 0,
    quantity_out    NUMERIC(12,2) DEFAULT 0,
    unit_price      NUMERIC(12,2),
    note            VARCHAR(255),
    movement_type   VARCHAR(10) NOT NULL CHECK (movement_type IN ('in', 'out')),
    created_by      INTEGER REFERENCES users(id),
    date            DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Critical indexes per SRS requirement
CREATE INDEX idx_stock_movements_product_id ON stock_movements(product_id);
CREATE INDEX idx_stock_movements_date ON stock_movements(date);
CREATE INDEX idx_stock_movements_created_by ON stock_movements(created_by);
CREATE INDEX idx_stock_movements_type ON stock_movements(movement_type);
CREATE INDEX idx_stock_movements_product_date ON stock_movements(product_id, date);

-- =============================================
-- SALES TABLE
-- =============================================
CREATE TABLE sales (
    id          SERIAL PRIMARY KEY,
    product_id  INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    quantity    NUMERIC(12,2) NOT NULL,
    price       NUMERIC(12,2) NOT NULL,
    discount    NUMERIC(12,2) DEFAULT 0,
    total       NUMERIC(14,2) NOT NULL,
    paid        NUMERIC(14,2) NOT NULL DEFAULT 0,
    debt        NUMERIC(14,2) NOT NULL DEFAULT 0,
    note        VARCHAR(255),
    sold_by     INTEGER NOT NULL REFERENCES users(id),
    date        DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_sales_paid_not_exceed_total CHECK (paid <= total),
    CONSTRAINT chk_sales_debt_equals_balance CHECK (debt = (total - paid))
);

-- Critical indexes per SRS requirement
CREATE INDEX idx_sales_product_id ON sales(product_id);
CREATE INDEX idx_sales_date ON sales(date);
CREATE INDEX idx_sales_sold_by ON sales(sold_by);
CREATE INDEX idx_sales_product_date ON sales(product_id, date);

-- =============================================
-- STORED PROCEDURE: Get Current Stock Balance
-- =============================================
CREATE OR REPLACE FUNCTION get_stock_balance(p_product_id INTEGER)
RETURNS NUMERIC AS $$
DECLARE
    v_balance NUMERIC;
BEGIN
    SELECT COALESCE(SUM(quantity_in), 0) - COALESCE(SUM(quantity_out), 0)
    INTO v_balance
    FROM stock_movements
    WHERE product_id = p_product_id;
    RETURN COALESCE(v_balance, 0);
END;
$$ LANGUAGE plpgsql;

-- =============================================
-- STORED PROCEDURE: Dashboard Summary
-- =============================================
CREATE OR REPLACE FUNCTION get_dashboard_summary(p_date DATE DEFAULT CURRENT_DATE)
RETURNS TABLE (
    today_sales     NUMERIC,
    month_sales     NUMERIC,
    month_discounts NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        COALESCE((SELECT SUM(total) FROM sales WHERE date = p_date), 0) AS today_sales,
        COALESCE((SELECT SUM(total) FROM sales
                  WHERE EXTRACT(MONTH FROM date) = EXTRACT(MONTH FROM p_date)
                    AND EXTRACT(YEAR FROM date) = EXTRACT(YEAR FROM p_date)), 0) AS month_sales,
        COALESCE((SELECT SUM(discount) FROM sales
                  WHERE EXTRACT(MONTH FROM date) = EXTRACT(MONTH FROM p_date)
                    AND EXTRACT(YEAR FROM date) = EXTRACT(YEAR FROM p_date)), 0) AS month_discounts;
END;
$$ LANGUAGE plpgsql;

-- =============================================
-- DEFAULT SEED DATA
-- Password: admin123 (bcrypt hashed)
-- =============================================
-- NOTE: Run 'flask seed' after migration for proper bcrypt hashing.
-- This is just a placeholder for reference.
-- INSERT INTO users (username, password_hash, role, full_name)
-- VALUES ('admin', '<bcrypt_hash>', 'manager', 'System Admin');

SELECT 'Schema created successfully' AS status;
