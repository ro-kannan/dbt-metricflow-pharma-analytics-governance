-- Chargeback estimated at time of sale (accrual basis).
-- Finance uses this to recognise the deduction in the same period as the sale.
with source as (
    select * from raw_chargebacks_accrual
)

select
    accrual_id,
    sale_id,
    brand_id,
    country_id,
    sale_month,
    chargeback_accrued
from source
