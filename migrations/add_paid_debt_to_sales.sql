-- =============================================
-- Migration: Add paid and debt columns to sales table
-- Date: 2026-03-10
-- Description: Adds paid and debt tracking for partial payments
-- =============================================

-- Add paid column (amount customer paid)
ALTER TABLE sales 
ADD COLUMN IF NOT EXISTS paid NUMERIC(14,2) NOT NULL DEFAULT 0;

-- Add debt column (remaining balance)
ALTER TABLE sales 
ADD COLUMN IF NOT EXISTS debt NUMERIC(14,2) NOT NULL DEFAULT 0;

-- Update existing records: set paid = total, debt = 0 (assume all old sales were fully paid)
UPDATE sales 
SET paid = total, debt = 0 
WHERE paid IS NULL OR paid = 0;

-- Add check constraint: paid cannot exceed total
ALTER TABLE sales 
ADD CONSTRAINT chk_sales_paid_not_exceed_total 
CHECK (paid <= total);

-- Add check constraint: debt must equal total - paid
ALTER TABLE sales 
ADD CONSTRAINT chk_sales_debt_equals_balance 
CHECK (debt = (total - paid));

-- Create index for querying debts
CREATE INDEX IF NOT EXISTS idx_sales_debt ON sales(debt) WHERE debt > 0;

SELECT 'Migration completed: paid and debt columns added to sales table' AS status;
