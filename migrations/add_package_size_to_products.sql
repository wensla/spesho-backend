-- Add package_size column to products table
ALTER TABLE products ADD COLUMN IF NOT EXISTS package_size INTEGER NOT NULL DEFAULT 5;
