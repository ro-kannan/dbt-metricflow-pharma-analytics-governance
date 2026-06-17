-- Market class dimension governs the denominator for market share calculations.
-- This single table is the governed answer to divergence scenario 5:
-- which molecules count as "the market" depends on whose definition you use.
--
-- Three denominator tiers (agreed with Medical Affairs, encoded here once):
--   sub_class_only   = narrowest — same sub-class (e.g. statins only)
--   branded_class    = intermediate — branded molecules across the therapeutic class
--   total_class      = widest — all molecules including generics in the class
--
-- The governed market share metric uses sub_class_only for brand-vs-brand comparison
-- and total_class for market penetration reporting. Both definitions are explicit here.
with source as (
    select * from raw_market_units
)

select
    molecule,
    therapeutic_class,
    sub_class,
    is_branded,
    country_id,
    month,
    total_units,
    -- Flag which denominator tier each molecule belongs to for each brand's calculation
    true                          as included_in_total_class,
    is_branded                    as included_in_branded_class,
    -- sub_class_only is resolved per brand in fct_brand_revenue using the brand's own sub_class
    sub_class                     as molecule_sub_class
from source
