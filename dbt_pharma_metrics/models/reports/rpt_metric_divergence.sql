-- Shows all 5 metric divergence scenarios side-by-side.
-- One row per brand/country/month. Each scenario has a "team calculation" column
-- and the "governed" column — the difference is the problem this POC solves.
--
-- Scenario 1: Rebate netting — how many rebate types are deducted
-- Scenario 2: Chargeback timing — accrual vs cash basis
-- Scenario 3: Sell-through vs ship-in — which unit count drives revenue recognition
-- Scenario 4: Returns date allocation — booking month vs return month
-- Scenario 5: Market share denominator — sub-class vs branded-only vs total class

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

chargebacks_accrual as (
    select sale_id, chargeback_accrued
    from {{ ref('stg_chargebacks_accrual') }}
),

-- Cash basis: chargeback deducted in the month it is received, not when the sale happened
chargebacks_cash as (
    select
        brand_id,
        country_id,
        receipt_month as cash_month,
        sum(chargeback_actual) as chargeback_cash_this_month
    from {{ ref('stg_chargebacks_actual') }}
    group by brand_id, country_id, receipt_month
),

sellthrough as (
    select sale_id, units_sold_to_pharmacy
    from {{ ref('stg_sellthrough') }}
),

-- Returns on booking month (governed)
returns_booking as (
    select sale_id, sum(return_value) as return_value_on_booking_month
    from {{ ref('stg_returns') }}
    group by sale_id
),

-- Returns on return month (what some teams do)
returns_on_return_month as (
    select
        brand_id,
        country_id,
        return_month,
        sum(return_value) as return_value_received_this_month
    from {{ ref('stg_returns') }}
    group by brand_id, country_id, return_month
),

-- Sub-class level: narrowest denominator (e.g. statins only within cardiovascular)
market_sub_class as (
    select
        therapeutic_class,
        sub_class                          as molecule_sub_class,
        country_id,
        month,
        sum(total_units)                   as sub_class_units
    from {{ ref('dim_market_class') }}
    group by therapeutic_class, sub_class, country_id, month
),

-- Therapeutic-class level: widest denominator (all molecules in class, incl. generics)
market_class_totals as (
    select
        therapeutic_class,
        country_id,
        month,
        sum(total_units)                                       as total_class_units,
        sum(case when is_branded then total_units else 0 end)  as branded_only_units
    from {{ ref('dim_market_class') }}
    group by therapeutic_class, country_id, month
),

brands as (
    select brand_id, brand_name, therapeutic_class, sub_class
    from {{ ref('dim_brands') }}
),

-- Governed numbers from the canonical fact
governed as (
    select
        sale_id,
        brand_id,
        country_id,
        sale_month,
        net_revenue                  as governed_net_revenue,
        units_sold                   as governed_units_sold,
        units_sellthrough            as governed_units_sellthrough,
        market_share_pct_sub_class   as governed_market_share_pct,
        market_share_pct_branded_only
    from {{ ref('fct_brand_revenue') }}
),

combined as (
    select
        s.sale_id,
        s.brand_id,
        b.brand_name,
        b.therapeutic_class,
        b.sub_class,
        s.country_id,
        s.sale_month,

        -- Raw components
        s.gross_revenue,
        s.paid_units_shipped,
        s.free_sample_units_shipped,
        coalesce(rg.govt_rebate_amount, 0)          as govt_rebate,
        coalesce(rc.commercial_rebate_amount, 0)    as commercial_rebate,
        coalesce(ca.chargeback_accrued, 0)          as chargeback_accrual,
        coalesce(cc.chargeback_cash_this_month, 0)  as chargeback_cash,
        coalesce(st.units_sold_to_pharmacy, s.paid_units_shipped) as sellthrough_units,
        coalesce(rb.return_value_on_booking_month, 0)  as returns_on_booking_month,
        coalesce(rm.return_value_received_this_month, 0) as returns_on_return_month,
        coalesce(msc.sub_class_units, 0)            as sub_class_market_units,
        coalesce(mct.branded_only_units, 0)         as branded_only_market_units,
        coalesce(mct.total_class_units, 0)          as total_class_market_units,

        -- SCENARIO 1: Rebate netting — 4 team methods
        s.gross_revenue                                                             as s1_team_a_no_rebates,
        s.gross_revenue - coalesce(rg.govt_rebate_amount, 0)                       as s1_team_b_govt_only,
        s.gross_revenue - coalesce(rg.govt_rebate_amount, 0)
                        - coalesce(rc.commercial_rebate_amount, 0)                  as s1_team_c_govt_and_commercial,
        s.gross_revenue - coalesce(rg.govt_rebate_amount, 0)
                        - coalesce(rc.commercial_rebate_amount, 0)
                        - coalesce(ca.chargeback_accrued, 0)                        as s1_team_d_all_deductions,

        -- SCENARIO 2: Chargeback timing — accrual vs cash
        -- Accrual: deduct estimated chargeback in the sale month
        s.gross_revenue - coalesce(rg.govt_rebate_amount, 0)
                        - coalesce(rc.commercial_rebate_amount, 0)
                        - coalesce(ca.chargeback_accrued, 0)                        as s2_accrual_basis,
        -- Cash: deduct chargebacks received this month (regardless of which sale they relate to)
        s.gross_revenue - coalesce(rg.govt_rebate_amount, 0)
                        - coalesce(rc.commercial_rebate_amount, 0)
                        - coalesce(cc.chargeback_cash_this_month, 0)                as s2_cash_basis,

        -- SCENARIO 3: Units — ship-in vs sell-through
        s.paid_units_shipped                                                        as s3_ship_in_units,
        coalesce(st.units_sold_to_pharmacy, s.paid_units_shipped)                   as s3_sellthrough_units,

        -- SCENARIO 4: Returns — booking month vs return month
        -- Booking month: return reduces revenue in the original sale month (governed)
        s.gross_revenue - coalesce(rg.govt_rebate_amount, 0)
                        - coalesce(rc.commercial_rebate_amount, 0)
                        - coalesce(ca.chargeback_accrued, 0)
                        - coalesce(rb.return_value_on_booking_month, 0)             as s4_returns_on_booking_month,
        -- Return month: return reduces revenue in the month it is physically returned
        s.gross_revenue - coalesce(rg.govt_rebate_amount, 0)
                        - coalesce(rc.commercial_rebate_amount, 0)
                        - coalesce(ca.chargeback_accrued, 0)
                        - coalesce(rm.return_value_received_this_month, 0)          as s4_returns_on_return_month,

        -- SCENARIO 5: Market share denominator
        round(s.paid_units_shipped::float / nullif(msc.sub_class_units, 0) * 100, 2)     as s5_market_share_sub_class,
        round(s.paid_units_shipped::float / nullif(mct.branded_only_units, 0) * 100, 2)  as s5_market_share_branded_only,
        round(s.paid_units_shipped::float / nullif(mct.total_class_units, 0) * 100, 2)   as s5_market_share_total_class,

        -- Governed values for comparison
        g.governed_net_revenue,
        g.governed_units_sold,
        g.governed_market_share_pct

    from sales s
    left join brands b                  on s.brand_id = b.brand_id
    left join rebates_govt rg           on s.sale_id = rg.sale_id
    left join rebates_commercial rc     on s.sale_id = rc.sale_id
    left join chargebacks_accrual ca    on s.sale_id = ca.sale_id
    left join chargebacks_cash cc       on s.brand_id = cc.brand_id
                                        and s.country_id = cc.country_id
                                        and s.sale_month = cc.cash_month
    left join sellthrough st            on s.sale_id = st.sale_id
    left join returns_booking rb        on s.sale_id = rb.sale_id
    left join returns_on_return_month rm on s.brand_id = rm.brand_id
                                        and s.country_id = rm.country_id
                                        and s.sale_month = rm.return_month
    left join market_sub_class msc      on b.therapeutic_class = msc.therapeutic_class
                                        and b.sub_class = msc.molecule_sub_class
                                        and s.country_id = msc.country_id
                                        and s.sale_month = msc.month
    left join market_class_totals mct   on b.therapeutic_class = mct.therapeutic_class
                                        and s.country_id = mct.country_id
                                        and s.sale_month = mct.month
    left join governed g                on s.sale_id = g.sale_id
)

select
    *,
    -- Scenario 1 variance: max vs min revenue across 4 team methods
    round(
        (greatest(s1_team_a_no_rebates, s1_team_b_govt_only, s1_team_c_govt_and_commercial, s1_team_d_all_deductions)
         - least(s1_team_a_no_rebates, s1_team_b_govt_only, s1_team_c_govt_and_commercial, s1_team_d_all_deductions))
        / nullif(least(s1_team_a_no_rebates, s1_team_b_govt_only, s1_team_c_govt_and_commercial, s1_team_d_all_deductions), 0) * 100,
    1) as s1_variance_pct,

    -- Scenario 2 variance
    round(abs(s2_accrual_basis - s2_cash_basis) / nullif(s2_accrual_basis, 0) * 100, 1) as s2_variance_pct,

    -- Scenario 3 variance
    round(abs(s3_ship_in_units - s3_sellthrough_units)::float / nullif(s3_ship_in_units, 0) * 100, 1) as s3_variance_pct,

    -- Scenario 4 variance
    round(abs(s4_returns_on_booking_month - s4_returns_on_return_month) / nullif(s4_returns_on_booking_month, 0) * 100, 1) as s4_variance_pct,

    -- Scenario 5 variance: market share spread
    round(
        coalesce(greatest(s5_market_share_sub_class, s5_market_share_branded_only, s5_market_share_total_class), 0)
        - coalesce(least(s5_market_share_sub_class, s5_market_share_branded_only, s5_market_share_total_class), 0),
    1) as s5_market_share_spread_pp

from combined
