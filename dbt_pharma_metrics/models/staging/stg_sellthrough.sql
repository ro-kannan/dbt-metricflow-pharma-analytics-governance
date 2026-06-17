-- Distributor sell-through: units sold by distributors to pharmacies/hospitals.
-- Diverges from ship-in due to distributor inventory carry — typically lags by 2-6 weeks.
with source as (
    select * from raw_distributor_sellthrough
)

select
    sellthrough_id,
    sale_id,
    brand_id,
    country_id,
    month,
    units_shipped_to_distributor,
    units_sold_to_pharmacy,
    units_in_distributor_inventory,
    units_sold_to_pharmacy::float / nullif(units_shipped_to_distributor, 0) as sellthrough_rate
from source
