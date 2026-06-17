with source as (
    select * from raw_returns
)

select
    return_id,
    sale_id,
    brand_id,
    country_id,
    original_sale_month,
    return_month,
    return_units,
    return_value
from source
