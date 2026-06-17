-- Actual chargeback receipts from distributors, arriving 1-2 months after the original sale.
-- Some teams deduct only when received (cash basis), creating a timing divergence.
with source as (
    select * from raw_chargebacks_actual
)

select
    receipt_id,
    sale_id,
    brand_id,
    country_id,
    original_sale_month,
    receipt_month,
    chargeback_actual,
    variance_vs_accrual
from source
