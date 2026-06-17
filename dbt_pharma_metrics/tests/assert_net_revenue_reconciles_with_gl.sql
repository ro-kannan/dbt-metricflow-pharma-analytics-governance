-- GL reconciliation test: governed net revenue must tie to finance GL within 2% tolerance.
-- Catches rebate timing lag and accrual estimation errors before they reach reporting.
-- This test reproduces the real incident from the engagement: one brand team's net revenue
-- didn't reconcile with the GL because their rebate timing assumption was wrong.
-- Fails if any brand/country/month exceeds the 2% tolerance.

with governed as (
    select
        brand_id,
        country_id,
        sale_month,
        sum(net_revenue) as governed_net_revenue
    from {{ ref('fct_brand_revenue') }}
    group by brand_id, country_id, sale_month
),

gl as (
    select
        brand_id,
        country_id,
        cast(gl_month as date) as gl_month,
        gl_net_revenue
    from {{ ref('seed_finance_gl') }}
),

comparison as (
    select
        g.brand_id,
        g.country_id,
        g.sale_month,
        g.governed_net_revenue,
        gl.gl_net_revenue,
        abs(g.governed_net_revenue - gl.gl_net_revenue) / nullif(gl.gl_net_revenue, 0) as variance_pct
    from governed g
    inner join gl on g.brand_id = gl.brand_id
                  and g.country_id = gl.country_id
                  and g.sale_month = gl.gl_month
)

-- Return rows that FAIL — dbt tests pass when this query returns 0 rows
select *
from comparison
where variance_pct > 0.02
