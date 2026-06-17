with source as (
    select * from raw_rebates_govt
)

select
    rebate_id,
    sale_id,
    brand_id,
    country_id,
    rebate_month,
    govt_rebate_amount,
    govt_rebate_pct_applied
from source
