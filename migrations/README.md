# Database Migrations

## How to Apply Migrations

### For New Installations
Run the `init.sql` file which includes all tables with the latest schema:
```bash
psql -U your_username -d your_database -f migrations/init.sql
```

### For Existing Installations

#### Migration: Add Paid and Debt Tracking (2026-03-10)
This migration adds `paid` and `debt` columns to the `sales` table to track partial payments.

**To apply:**
```bash
psql -U your_username -d your_database -f migrations/add_paid_debt_to_sales.sql
```

**What it does:**
- Adds `paid` column (amount customer paid)
- Adds `debt` column (remaining balance)
- Updates existing records to set `paid = total` and `debt = 0`
- Adds constraints to ensure data integrity
- Creates index for querying debts

**After migration:**
- Backend API now accepts `paid` parameter in POST `/sales/`
- If `paid` is not provided, it defaults to `total` (full payment)
- `debt` is automatically calculated as `total - paid`
- Frontend (Flutter app) now sends `paid` amount from the cash received field

## Migration History

| Date | File | Description |
|------|------|-------------|
| 2026-03-10 | `add_paid_debt_to_sales.sql` | Added paid and debt tracking for partial payments |
