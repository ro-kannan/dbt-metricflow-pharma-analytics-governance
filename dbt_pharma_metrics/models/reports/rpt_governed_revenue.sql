-- Clean governed output: one row per brand/country/month.
-- This is what Power BI / Tableau / Streamlit connect to.
-- No business logic here — everything is already calculated in fct_brand_revenue.
-- Teams SUM the pre-calculated columns; no DAX measures or Tableau calculated fields needed.

select
    f.sale_id,
    f.brand_id,
    f.brand_name,
    f.therapeutic_class,
    f.sub_class,
    f.country_id,
    c.country_name,
    c.region,
    f.sale_month,

    -- Revenue metrics
    round(f.gross_revenue, 0)                   as gross_revenue,
    round(f.govt_rebate_amount, 0)              as govt_rebate_deduction,
    round(f.commercial_rebate_amount, 0)        as commercial_rebate_deduction,
    round(f.chargeback_accrued, 0)              as chargeback_deduction,
    round(f.returns_on_booking_month, 0)        as returns_deduction,
    round(f.total_deductions, 0)                as total_deductions,
    round(f.net_revenue, 0)                     as net_revenue,
    round(f.net_revenue_margin_pct, 1)          as net_revenue_margin_pct,

    -- Unit metrics
    f.units_sold                                as units_sold_ship_in,
    f.free_sample_units,
    f.units_sellthrough                         as units_sold_sellthrough,
    f.return_units,

    -- Market share (governed: sub-class denominator)
    f.sub_class_total_units                     as market_denominator_units,
    f.market_share_pct_sub_class                as market_share_pct,
    f.market_share_pct_branded_only

from {{ ref('fct_brand_revenue') }} f
left join {{ ref('dim_countries') }} c on f.country_id = c.country_id
order by f.sale_month, f.brand_id, f.country_id
