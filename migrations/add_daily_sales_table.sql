-- Add daily_sales table for simplified cash sales tracking
CREATE TABLE IF NOT EXISTS daily_sales (
    id           SERIAL PRIMARY KEY,
    date         DATE NOT NULL,
    total_amount NUMERIC(14, 2) NOT NULL,
    cash_paid    NUMERIC(14, 2) NOT NULL,
    debt         NUMERIC(14, 2) NOT NULL DEFAULT 0,
    note         VARCHAR(255),
    customer_name  VARCHAR(100),
    customer_phone VARCHAR(30),
    recorded_by  INTEGER NOT NULL REFERENCES users(id),
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_daily_sales_date        ON daily_sales(date);
CREATE INDEX IF NOT EXISTS idx_daily_sales_recorded_by ON daily_sales(recorded_by);
