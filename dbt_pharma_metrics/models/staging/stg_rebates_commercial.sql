with source as (
    select * from raw_rebates_commercial
)

select
    rebate_id,
    sale_id,
    brand_id,
    country_id,
    rebate_month,
    commercial_rebate_amount,
    commercial_rebate_pct_applied
from source
