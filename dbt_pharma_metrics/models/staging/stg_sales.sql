with source as (
    select * from raw_sales
)

select
    sale_id,
    brand_id,
    country_id,
    sale_month,
    paid_units_shipped,
    free_sample_units_shipped,
    paid_units_shipped + free_sample_units_shipped as total_units_shipped,
    gross_revenue,
    net_price_per_unit
from source
