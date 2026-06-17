"""
Pharma Metrics Governance Dashboard
POC 3 — Metrics Layer

Shows how 5 brand teams produce 5 different revenue numbers from the same raw data,
and how a governed dbt metrics layer eliminates the divergence.
"""

import duckdb
import pandas as pd
import streamlit as st
from pathlib import Path
import subprocess, sys, os

DB_PATH = Path(__file__).parent / "pharma_metrics.duckdb"

st.set_page_config(
    page_title="Pharma Metrics Governance",
    page_icon="💊",
    layout="wide",
)

# ── Bootstrap: generate data + run dbt if the DB doesn't exist ──────────────
if not DB_PATH.exists():
    with st.spinner("First run: generating data and running dbt models (takes ~30 seconds)…"):
        venv_python = Path(__file__).parent / ".venv" / "bin" / "python"
        python = str(venv_python) if venv_python.exists() else sys.executable

        subprocess.run([python, "scripts/01_generate_pharma_data.py"], check=True,
                       cwd=str(Path(__file__).parent))
        subprocess.run(
            [python, "-m", "dbt", "seed", "--profiles-dir", ".."],
            check=True, cwd=str(Path(__file__).parent / "dbt_pharma_metrics")
        )
        subprocess.run(
            [python, "-m", "dbt", "run", "--profiles-dir", ".."],
            check=True, cwd=str(Path(__file__).parent / "dbt_pharma_metrics")
        )

@st.cache_resource
def get_conn():
    return duckdb.connect(str(DB_PATH), read_only=True)

con = get_conn()

# ── Sidebar ──────────────────────────────────────────────────────────────────
st.sidebar.title("Pharma Metrics Governance")
st.sidebar.markdown("""
**5 brand teams. 5 different revenue numbers. Same raw data.**

Select a divergence scenario to see the problem — and how a governed dbt metrics
layer produces one consistent number.
""")

SCENARIOS = {
    "Scenario 1 — Rebate Netting": "rebate_netting",
    "Scenario 2 — Chargeback Timing": "chargeback_timing",
    "Scenario 3 — Sell-Through vs Ship-In (Units)": "sellthrough_vs_shipin",
    "Scenario 4 — Returns Date Allocation": "returns_allocation",
    "Scenario 5 — Market Share Denominator": "market_share_denominator",
}

scenario_label = st.sidebar.selectbox("Choose divergence scenario", list(SCENARIOS.keys()))
scenario_key   = SCENARIOS[scenario_label]

brands_all = con.execute(
    "SELECT DISTINCT brand_name FROM main_facts.fct_brand_revenue ORDER BY brand_name"
).df()["brand_name"].tolist()
selected_brands = st.sidebar.multiselect("Filter brands", brands_all, default=brands_all)

brand_filter = "', '".join(selected_brands) if selected_brands else "''"

# ── Header ────────────────────────────────────────────────────────────────────
st.title("Pharma Commercial Metrics Governance")
st.caption("POC 3 · dbt Metrics Layer · 5 brands · 4 countries · 12 months")

# ── Context intro ─────────────────────────────────────────────────────────────
with st.expander("What is this? — Context and overview", expanded=True):
    st.markdown("""
#### The Issue
In pharma commercial analytics, a single month's revenue involves gross sales, government rebates,
commercial rebates, distributor chargebacks, product returns, and free samples.
Each of these has timing and scope decisions that different teams answer differently —
in their own spreadsheet or reporting tool.

The result: the same brand's net revenue looks different in every QBR slide,
even though everyone is reading from the same source data.

| Decision | Team A might say… | Team B might say… |
|---|---|---|
| Which rebates to deduct? | Gross revenue only | Govt + commercial + chargebacks |
| When to count a chargeback? | Estimate it in the sale month | Deduct it when the invoice arrives |
| Which units to report? | Units shipped to distributor | Units sold to pharmacy |
| When to book a return? | The original sale month | The month the return is received |
| What counts as "the market"? | All drugs in the therapeutic class | Same sub-class drugs only |

---

#### The Solution
A **governed dbt metrics layer** encodes every decision once — in SQL, in version control,
agreed with Finance and Medical Affairs:

- **`fct_brand_revenue`** — one fact table where all 5 decisions are locked in as governed rules
- **`metrics.yml`** — formal MetricFlow definitions; the written contract for what each metric means
- **`rpt_governed_revenue`** — the single output table every reporting tool connects to and reads from
- **GL reconciliation test** — automatically checks that governed net revenue ties to Finance's general ledger within 2%

---

#### The 5 Scenarios in this demo

| # | Scenario | What it shows |
|---|---|---|
| **1 — Rebate Netting** | 4 teams deduct different sets of rebates → net revenue varies by 35–40% for the same brand/month |
| **2 — Chargeback Timing** | Chargebacks estimated in sale month vs. deducted when received → net revenue swings 15–20% |
| **3 — Sell-Through vs Ship-In** | Units shipped to distributor vs. units sold to pharmacy → opposite demand trends when inventory builds |
| **4 — Returns Date Allocation** | Return deducted from original sale month vs. the return receipt month → period-close numbers diverge |
| **5 — Market Share Denominator** | 3 different definitions of "the market" → same brand reads 3–4 percentage points apart |

*Select a scenario from the sidebar to see the divergence — and the governed number that resolves it.*
    """)

# ── Scenario descriptions ─────────────────────────────────────────────────────
DESCRIPTIONS = {
    "rebate_netting": (
        "**What breaks:** Each brand team uses a different set of deductions in their reporting — "
        "Team A reports gross revenue with no deductions; Team D deducts government rebates, commercial rebates, *and* chargebacks. "
        "Same brand, same month: four different net revenue numbers in four different QBR slides.",
        "**The fix:** The metric definition — which deductions count — is encoded once in the MetricFlow semantic model (`metrics.yml`). "
        "Governed net revenue is pre-calculated in `rpt_governed_revenue`, the single source of truth. "
        "Reporting tools connect to this table and SUM the pre-calculated column directly. "
        "No team can apply a different deduction set without changing the dbt model.",
        "s1_variance_pct", "Net revenue variance across 4 team methods",
    ),
    "chargeback_timing": (
        "**What breaks:** Distributors submit chargebacks 1–2 months after the original sale. "
        "Finance accrues the estimated amount in the sale month (accrual basis); "
        "commercial ops deducts only when the invoice is received (cash basis). "
        "The resulting **net revenue** for the same brand and month swings 15–20% depending on which method is used.",
        "**The fix:** Governed rule = accrual basis, aligned with how Finance closes periods. "
        "The GL reconciliation dbt test (`assert_net_revenue_reconciles_with_gl`) validates that "
        "**net revenue** — the total after all deductions including chargebacks — ties to the Finance GL within 2%. "
        "Governed values are pre-calculated in `rpt_governed_revenue`, the source of truth.",
        "s2_variance_pct", "Net revenue variance (accrual vs cash basis)",
    ),
    "sellthrough_vs_shipin": (
        "**What breaks (unit metrics):** Commercial ops reports units *shipped to distributor* (ship-in). "
        "Market access reports units *sold by distributor to pharmacy* (sell-through). "
        "When distributors build inventory, ship-in trends up while sell-through lags — "
        "the same product shows opposite growth signals in two teams' reports.",
        "**The fix:** Governed rule = ship-in units for revenue recognition (aligns with the invoice and GL); "
        "sell-through units for demand reporting. "
        "Both columns are pre-calculated in `fct_brand_revenue` with explicit labels — "
        "the choice is documented in the metric definitions, not implicit in each team's report.",
        "s3_variance_pct", "Unit variance % (ship-in vs sell-through)",
    ),
    "returns_allocation": (
        "**What breaks:** A product returned in March for a December sale — does it reduce December net revenue or March? "
        "Finance reopens December (booking month); commercial ops takes the hit in March (return month). "
        "Period-close numbers, trend lines, and sales rep bonus calculations all diverge.",
        "**The fix:** Governed rule = returns reduce net revenue in the original booking month, consistent with GL period-close. "
        "Encoded once in `fct_brand_revenue`, pre-calculated in `rpt_governed_revenue` — the source of truth. "
        "No team can apply a different date rule without a dbt model change.",
        "s4_variance_pct", "Net revenue variance (booking vs return month)",
    ),
    "market_share_denominator": (
        "**What breaks:** The denominator of market share — what counts as 'the market' — differs by team: "
        "global brand uses total therapeutic class (all molecules including generics); "
        "regional commercial uses branded-only; medical affairs uses same sub-class only. "
        "Same brand, same month: three different market share figures.",
        "**The fix:** Governed denominator = sub-class total (branded + generic), agreed with Medical Affairs "
        "and encoded in `dim_market_class`. The definition is in the MetricFlow semantic model. "
        "Governed values in `rpt_governed_revenue` are the source of truth — "
        "the denominator choice is explicit, documented, and testable.",
        "s5_market_share_spread_pp", "Market share spread across 3 denominator methods (pp)",
    ),
}

KPI_LABELS = {
    "rebate_netting":           ("Avg net revenue variance (4 methods)", "Max net revenue variance"),
    "chargeback_timing":        ("Avg net revenue variance (accrual vs cash)", "Max net revenue variance"),
    "sellthrough_vs_shipin":    ("Avg unit variance (ship-in vs sell-through)", "Max unit variance"),
    "returns_allocation":       ("Avg net revenue variance (booking vs return month)", "Max net revenue variance"),
    "market_share_denominator": ("Avg market share spread", "Max market share spread"),
}

problem_text, fix_text, variance_col, variance_label = DESCRIPTIONS[scenario_key]

col1, col2 = st.columns(2)
with col1:
    st.error(problem_text)
with col2:
    st.success(fix_text)

st.divider()

# ── KPI strip ─────────────────────────────────────────────────────────────────
kpi_data = con.execute(f"""
    SELECT
        round(avg({variance_col}), 1) as avg_variance,
        round(max({variance_col}), 1) as max_variance,
        count(distinct brand_id)      as brand_count,
        count(distinct country_id)    as country_count
    FROM main_reports.rpt_metric_divergence
    WHERE brand_name IN ('{brand_filter}')
""").df()

k1, k2, k3, k4 = st.columns(4)
avg_label, max_label = KPI_LABELS[scenario_key]
suffix = "pp" if scenario_key == "market_share_denominator" else "%"
k1.metric(avg_label, f"{kpi_data['avg_variance'][0]}{suffix}")
k2.metric(max_label, f"{kpi_data['max_variance'][0]}{suffix}")
k3.metric("Brands", int(kpi_data['brand_count'][0]))
k4.metric("Countries", int(kpi_data['country_count'][0]))

st.divider()

# ── Before / After ────────────────────────────────────────────────────────────
before_tab, after_tab = st.tabs(["Before governance — divergent numbers", "After governance — one number"])

with before_tab:
    if scenario_key == "rebate_netting":
        df = con.execute(f"""
            SELECT brand_name, country_id, strftime(sale_month, '%Y-%m') as month,
                   round(s1_team_a_no_rebates,0)           as "Team A — no deductions (gross revenue)",
                   round(s1_team_b_govt_only,0)            as "Team B — govt rebate deducted",
                   round(s1_team_c_govt_and_commercial,0)  as "Team C — govt + commercial rebate deducted",
                   round(s1_team_d_all_deductions,0)       as "Team D — govt + commercial + chargeback deducted",
                   round(governed_net_revenue,0)            as "Governed net revenue",
                   s1_variance_pct                         as "Variance % (max vs min across 4 methods)"
            FROM main_reports.rpt_metric_divergence
            WHERE brand_name IN ('{brand_filter}')
            ORDER BY sale_month, brand_name, country_id
        """).df()
        st.dataframe(df, use_container_width=True)
        st.caption("All dollar columns are net revenue ($). Variance % = (highest team figure − lowest team figure) / lowest × 100.")

    elif scenario_key == "chargeback_timing":
        df = con.execute(f"""
            SELECT brand_name, country_id, strftime(sale_month, '%Y-%m') as month,
                   round(s2_accrual_basis,0)    as "Net revenue — accrual basis (Finance)",
                   round(s2_cash_basis,0)        as "Net revenue — cash basis (Ops)",
                   round(governed_net_revenue,0) as "Governed net revenue",
                   s2_variance_pct               as "Variance % (accrual vs cash)"
            FROM main_reports.rpt_metric_divergence
            WHERE brand_name IN ('{brand_filter}')
            ORDER BY sale_month, brand_name
        """).df()
        st.dataframe(df, use_container_width=True)
        st.caption("All dollar columns are net revenue ($) after all rebates and chargebacks. Accrual: chargeback estimated and deducted in sale month. Cash: chargeback deducted only when the distributor invoice is received (1–2 months later).")

    elif scenario_key == "sellthrough_vs_shipin":
        df = con.execute(f"""
            SELECT brand_name, country_id, strftime(sale_month, '%Y-%m') as month,
                   s3_ship_in_units      as "Units shipped to distributor (ship-in)",
                   s3_sellthrough_units  as "Units sold to pharmacy (sell-through)",
                   governed_units_sold   as "Governed units (ship-in)",
                   s3_variance_pct       as "Unit variance % (ship-in vs sell-through)"
            FROM main_reports.rpt_metric_divergence
            WHERE brand_name IN ('{brand_filter}')
            ORDER BY sale_month, brand_name
        """).df()
        st.dataframe(df, use_container_width=True)
        st.caption("All columns are unit counts, not revenue. Revenue recognition uses ship-in units (aligns with invoice). Sell-through is the demand signal used by Market Access for forecasting and market share.")

    elif scenario_key == "returns_allocation":
        df = con.execute(f"""
            SELECT brand_name, country_id, strftime(sale_month, '%Y-%m') as month,
                   round(s4_returns_on_booking_month,0) as "Net revenue — return in booking month (Finance)",
                   round(s4_returns_on_return_month,0)  as "Net revenue — return in return month (Ops)",
                   round(governed_net_revenue,0)          as "Governed net revenue",
                   s4_variance_pct                       as "Variance % (booking vs return month)"
            FROM main_reports.rpt_metric_divergence
            WHERE brand_name IN ('{brand_filter}')
            ORDER BY sale_month, brand_name
        """).df()
        st.dataframe(df, use_container_width=True)
        st.caption("All dollar columns are net revenue ($). Variance % = |booking-month net revenue − return-month net revenue| / booking-month × 100.")

    else:  # market share
        df = con.execute(f"""
            SELECT brand_name, country_id, strftime(sale_month, '%Y-%m') as month,
                   s5_market_share_sub_class    as "Market share % — sub-class only (Medical Affairs)",
                   s5_market_share_branded_only as "Market share % — branded molecules only (Regional)",
                   s5_market_share_total_class  as "Market share % — total therapeutic class (Global brand)",
                   governed_market_share_pct    as "Governed market share % (sub-class)",
                   s5_market_share_spread_pp    as "Spread (pp)"
            FROM main_reports.rpt_metric_divergence
            WHERE brand_name IN ('{brand_filter}')
            ORDER BY sale_month, brand_name
        """).df()
        st.dataframe(df, use_container_width=True)
        st.caption("All columns are market share %. Spread (pp) = highest % − lowest % across the 3 denominator definitions.")

with after_tab:
    st.markdown("**One number per brand/country/month — from the governed metrics layer.**")
    st.caption("This is what every team's reporting dashboard shows when connected to `rpt_governed_revenue` — the governed single source of truth.")

    if scenario_key == "market_share_denominator":
        df = con.execute(f"""
            SELECT brand_name, country_id, strftime(sale_month, '%Y-%m') as month,
                   units_sold_ship_in as units_sold,
                   market_denominator_units,
                   market_share_pct   as "Market share % (governed sub-class)"
            FROM main_reports.rpt_governed_revenue
            WHERE brand_name IN ('{brand_filter}')
            ORDER BY sale_month, brand_name, country_id
        """).df()
    else:
        df = con.execute(f"""
            SELECT brand_name, country_id, strftime(sale_month, '%Y-%m') as month,
                   gross_revenue,
                   govt_rebate_deduction, commercial_rebate_deduction,
                   chargeback_deduction, returns_deduction,
                   net_revenue,
                   net_revenue_margin_pct as "Margin %"
            FROM main_reports.rpt_governed_revenue
            WHERE brand_name IN ('{brand_filter}')
            ORDER BY sale_month, brand_name, country_id
        """).df()

    st.dataframe(df, use_container_width=True)

    # Summary by brand
    st.subheader("Annual summary by brand (governed numbers)")
    summary = con.execute(f"""
        SELECT brand_name,
               round(sum(gross_revenue)/1e6, 2)   as "Gross revenue ($M)",
               round(sum(net_revenue)/1e6, 2)     as "Net revenue ($M)",
               round(avg(net_revenue_margin_pct),1) as "Avg margin %",
               sum(units_sold_ship_in)             as "Total units sold",
               round(avg(market_share_pct),1)      as "Avg market share %"
        FROM main_reports.rpt_governed_revenue
        WHERE brand_name IN ('{brand_filter}')
        GROUP BY brand_name ORDER BY brand_name
    """).df()
    st.dataframe(summary, use_container_width=True)

st.divider()

# ── Architecture note ─────────────────────────────────────────────────────────
with st.expander("How this works — architecture"):
    st.markdown("""
**The pattern this demo proves:**

| Layer | What it does |
|---|---|
| Raw tables | Gross sales, rebates, chargebacks, returns, distributor sell-through, market units |
| dbt staging | Clean, typed, one-to-one from source |
| `dim_market_class` | Governs the market share denominator — one agreed definition |
| **`fct_brand_revenue`** | **All 5 metric calculations encoded once. This is the single source of truth.** |
| MetricFlow YAML | Formal metric definitions — in dbt Cloud, reporting tools consume these via the Semantic Layer API |
| `rpt_governed_revenue` | Clean output; reporting tools connect to this and SUM pre-calculated columns — no custom metric calculations needed |
| GL reconciliation test | `assert_net_revenue_reconciles_with_gl.sql` — governed net revenue must tie to finance GL within 2% |

**In production with dbt Cloud**, the Semantic Layer API means reporting tools cannot write a different metric definition —
they query the MetricFlow-defined `net_revenue` metric directly and get back a result set, not a column to recalculate.
    """)
