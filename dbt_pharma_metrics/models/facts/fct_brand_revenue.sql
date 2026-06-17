-- Canonical fact table: one row per brand/country/month.
-- All metric definitions encoded once here. Every downstream model, dashboard,
-- and ad-hoc query reads from this table — no recalculation elsewhere.
--
-- Governed rules (agreed with Finance and Medical Affairs):
--   net_revenue         = gross - govt_rebate - commercial_rebate - chargeback (accrual basis)
--   units_sold          = paid units shipped (free samples excluded)
--   market_share_pct    = brand units / total sub-class units (branded + generic in same sub-class)
--   returns             = allocated to original booking month (not return receipt month)

with sales as (
    select * from {{ ref('stg_sales') }}
),

rebates_govt as (
    select sale_id, govt_rebate_amount
    from {{ ref('stg_rebates_govt') }}
),

rebates_commercial as (
    select sale_id, commercial_rebate_amount
    from {{ ref('stg_rebates_commercial') }}
),

-- Accrual basis: chargeback recognised in same month as sale
chargebacks as (
    select sale_id, chargeback_accrued
    from {{ ref('stg_chargebacks_accrual') }}
),

-- Returns allocated to original booking month
returns_on_booking_month as (
    select
        sale_id,
        sum(return_value) as total_return_value,
        sum(return_units) as total_return_units
    from {{ ref('stg_returns') }}
    group by sale_id
),

-- Sell-through units (pharmacy demand signal, separate from ship-in revenue)
sellthrough as (
    select sale_id, units_sold_to_pharmacy
    from {{ ref('stg_sellthrough') }}
),

brands as (
    select brand_id, brand_name, therapeutic_class, sub_class
    from {{ ref('dim_brands') }}
),

-- Sub-class market totals per country/month for governed market share denominator
market_sub_class as (
    select
        therapeutic_class,
        molecule_sub_class,
        country_id,
        month,
        sum(total_units) as sub_class_total_units,
        sum(case when is_branded then total_units else 0 end) as branded_only_total_units,
        sum(total_units) as total_class_total_units
    from {{ ref('dim_market_class') }}
    group by therapeutic_class, molecule_sub_class, country_id, month
),

combined as (
    select
        s.sale_id,
        s.brand_id,
        s.country_id,
        s.sale_month,

        -- Units
        s.paid_units_shipped                                                    as units_sold,
        s.free_sample_units_shipped                                             as free_sample_units,
        coalesce(st.units_sold_to_pharmacy, s.paid_units_shipped)               as units_sellthrough,

        -- Revenue (gross)
        s.gross_revenue,
        s.net_price_per_unit,

        -- Deductions
        coalesce(rg.govt_rebate_amount, 0)                                      as govt_rebate_amount,
        coalesce(rc.commercial_rebate_amount, 0)                                as commercial_rebate_amount,
        coalesce(cb.chargeback_accrued, 0)                                      as chargeback_accrued,
        coalesce(ret.total_return_value, 0)                                     as returns_on_booking_month,
        coalesce(ret.total_return_units, 0)                                     as return_units,

        -- Governed net revenue (the single source of truth)
        s.gross_revenue
            - coalesce(rg.govt_rebate_amount, 0)
            - coalesce(rc.commercial_rebate_amount, 0)
            - coalesce(cb.chargeback_accrued, 0)
            - coalesce(ret.total_return_value, 0)                               as net_revenue,

        -- Total deductions for transparency
        coalesce(rg.govt_rebate_amount, 0)
            + coalesce(rc.commercial_rebate_amount, 0)
            + coalesce(cb.chargeback_accrued, 0)
            + coalesce(ret.total_return_value, 0)                               as total_deductions,

        b.brand_name,
        b.therapeutic_class,
        b.sub_class

    from sales s
    left join rebates_govt       rg  on s.sale_id = rg.sale_id
    left join rebates_commercial rc  on s.sale_id = rc.sale_id
    left join chargebacks        cb  on s.sale_id = cb.sale_id
    left join returns_on_booking_month ret on s.sale_id = ret.sale_id
    left join sellthrough        st  on s.sale_id = st.sale_id
    left join brands             b   on s.brand_id = b.brand_id
),

with_market_share as (
    select
        c.*,

        -- Governed market share: brand units / sub-class total (branded + generic)
        coalesce(mkt.sub_class_total_units, 0)                                  as sub_class_total_units,
        coalesce(mkt.branded_only_total_units, 0)                               as branded_only_total_units,

        round(
            c.units_sold::float / nullif(mkt.sub_class_total_units, 0) * 100, 2
        )                                                                        as market_share_pct_sub_class,

        round(
            c.units_sold::float / nullif(mkt.branded_only_total_units, 0) * 100, 2
        )                                                                        as market_share_pct_branded_only,

        -- Gross margin proxy (net revenue / gross revenue)
        round(
            (c.gross_revenue
                - coalesce(c.govt_rebate_amount, 0)
                - coalesce(c.commercial_rebate_amount, 0)
                - coalesce(c.chargeback_accrued, 0)
                - coalesce(c.returns_on_booking_month, 0)
            )::float / nullif(c.gross_revenue, 0) * 100,
        2)                                                                       as net_revenue_margin_pct

    from combined c
    left join market_sub_class mkt
        on  c.therapeutic_class = mkt.therapeutic_class
        and c.sub_class         = mkt.molecule_sub_class
        and c.country_id        = mkt.country_id
        and c.sale_month        = mkt.month
)

select * from with_market_share
