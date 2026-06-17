"""
Generate simulated pharma commercial analytics data for POC 3.

Produces a DuckDB file with 9 raw tables covering all 5 metric divergence
scenarios: rebate netting, chargeback timing, sell-through vs ship-in,
returns date allocation, market share denominator.

All rebate/chargeback amounts are calculated from actual gross revenue
(not approximations) so deductions stay within realistic bounds.
"""

import duckdb
import random
from datetime import date
from pathlib import Path

random.seed(42)

DB_PATH = Path(__file__).parent.parent / "pharma_metrics.duckdb"

BRANDS = [
    {"brand_id": "BR001", "brand_name": "Cardivex",  "therapeutic_class": "cardiovascular", "sub_class": "statin"},
    {"brand_id": "BR002", "brand_name": "Oncovance", "therapeutic_class": "oncology",       "sub_class": "taxane"},
    {"brand_id": "BR003", "brand_name": "Respira",   "therapeutic_class": "respiratory",    "sub_class": "inhaled_corticosteroid"},
    {"brand_id": "BR004", "brand_name": "Neuroplex", "therapeutic_class": "neurology",      "sub_class": "anticonvulsant"},
    {"brand_id": "BR005", "brand_name": "Immunex",   "therapeutic_class": "immunology",     "sub_class": "anti_tnf"},
]

COUNTRIES = [
    {"country_id": "US"}, {"country_id": "UK"},
    {"country_id": "DE"}, {"country_id": "JP"},
]

MARKET_MOLECULES = [
    ("atorvastatin-x",   "cardiovascular", "statin",                  True),
    ("rosuva-gen",        "cardiovascular", "statin",                  False),
    ("simva-gen",         "cardiovascular", "statin",                  False),
    ("ezetimibe-brand",   "cardiovascular", "cholesterol_abs",         True),
    ("paclitab-3",        "oncology",       "taxane",                  True),
    ("docetax-gen",       "oncology",       "taxane",                  False),
    ("cabaz-brand",       "oncology",       "taxane",                  True),
    ("imatinib-gen",      "oncology",       "tki",                     False),
    ("flutico-b2",        "respiratory",    "inhaled_corticosteroid",  True),
    ("budesonide-gen",    "respiratory",    "inhaled_corticosteroid",  False),
    ("salmeterol-brand",  "respiratory",    "laba",                    True),
    ("gabap-er",          "neurology",      "anticonvulsant",          True),
    ("pregabalin-gen",    "neurology",      "anticonvulsant",          False),
    ("lamotrig-gen",      "neurology",      "anticonvulsant",          False),
    ("adalim-biosim",     "immunology",     "anti_tnf",                True),
    ("infliximab-biosim", "immunology",     "anti_tnf",                True),
    ("etanercept-gen",    "immunology",     "anti_tnf",                False),
    ("ustekinumab-brand", "immunology",     "il12_23",                 True),
]

# Per brand: net_price, and rebate/deduction pcts (applied to actual gross revenue)
# Kept realistic: total deductions (govt + commercial + chargeback) stay under 55%
BRAND_CONFIG = {
    "BR001": {"net_price": 45.0,   "govt_pct": 0.18, "comm_pct": 0.07, "cback_pct": 0.03, "sample_pct": 0.06},
    "BR002": {"net_price": 380.0,  "govt_pct": 0.15, "comm_pct": 0.05, "cback_pct": 0.02, "sample_pct": 0.02},
    "BR003": {"net_price": 95.0,   "govt_pct": 0.22, "comm_pct": 0.09, "cback_pct": 0.04, "sample_pct": 0.04},
    "BR004": {"net_price": 120.0,  "govt_pct": 0.20, "comm_pct": 0.08, "cback_pct": 0.04, "sample_pct": 0.05},
    "BR005": {"net_price": 2200.0, "govt_pct": 0.25, "comm_pct": 0.12, "cback_pct": 0.02, "sample_pct": 0.01},
}

# Base paid units per brand/country — used only for raw_sales generation
BASE_UNITS = {
    ("BR001","US"):12000, ("BR001","UK"):4500, ("BR001","DE"):3800, ("BR001","JP"):5200,
    ("BR002","US"):1800,  ("BR002","UK"):620,  ("BR002","DE"):580,  ("BR002","JP"):810,
    ("BR003","US"):9500,  ("BR003","UK"):3200, ("BR003","DE"):2900, ("BR003","JP"):4100,
    ("BR004","US"):6200,  ("BR004","UK"):2100, ("BR004","DE"):1900, ("BR004","JP"):2700,
    ("BR005","US"):820,   ("BR005","UK"):290,  ("BR005","DE"):260,  ("BR005","JP"):370,
}

MONTHS = [date(2024, m, 1) for m in range(1, 13)]


def generate_all(con: duckdb.DuckDBPyConnection):
    # ── Step 1: raw_sales ──────────────────────────────────────────────────────
    sales_rows = []
    # sale_id → actual gross_revenue (used by all downstream rebate calcs)
    gross_lookup: dict[str, float] = {}

    for b in BRANDS:
        cfg = BRAND_CONFIG[b["brand_id"]]
        for c in COUNTRIES:
            base = BASE_UNITS[(b["brand_id"], c["country_id"])]
            for i, month in enumerate(MONTHS):
                trend = 1.0 + i * 0.004
                paid = max(1, int(base * trend * random.uniform(0.90, 1.10)))
                free = max(0, int(paid * cfg["sample_pct"] * random.uniform(0.8, 1.2)))
                gross = round(paid * cfg["net_price"], 2)
                sid = f"S-{b['brand_id']}-{c['country_id']}-{month.strftime('%Y%m')}"
                gross_lookup[sid] = gross
                sales_rows.append((sid, b["brand_id"], c["country_id"], month, paid, free, gross, cfg["net_price"]))

    con.execute("CREATE TABLE raw_sales AS SELECT * FROM (VALUES " +
        ",\n".join(f"('{r[0]}','{r[1]}','{r[2]}',DATE '{r[3]}',{r[4]},{r[5]},{r[6]},{r[7]})" for r in sales_rows) +
        ") t(sale_id,brand_id,country_id,sale_month,paid_units_shipped,free_sample_units_shipped,gross_revenue,net_price_per_unit)")
    print(f"  raw_sales: {len(sales_rows)} rows")

    # ── Step 2: raw_rebates_govt ──────────────────────────────────────────────
    rows = []
    for b in BRANDS:
        cfg = BRAND_CONFIG[b["brand_id"]]
        for c in COUNTRIES:
            for month in MONTHS:
                sid = f"S-{b['brand_id']}-{c['country_id']}-{month.strftime('%Y%m')}"
                gross = gross_lookup[sid]
                amt = round(gross * cfg["govt_pct"] * random.uniform(0.92, 1.08), 2)
                rows.append((f"RG-{sid}", sid, b["brand_id"], c["country_id"], month, amt, cfg["govt_pct"]))
    con.execute("CREATE TABLE raw_rebates_govt AS SELECT * FROM (VALUES " +
        ",\n".join(f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',DATE '{r[4]}',{r[5]},{r[6]})" for r in rows) +
        ") t(rebate_id,sale_id,brand_id,country_id,rebate_month,govt_rebate_amount,govt_rebate_pct_applied)")
    print(f"  raw_rebates_govt: {len(rows)} rows")

    # ── Step 3: raw_rebates_commercial ───────────────────────────────────────
    rows = []
    for b in BRANDS:
        cfg = BRAND_CONFIG[b["brand_id"]]
        for c in COUNTRIES:
            for month in MONTHS:
                sid = f"S-{b['brand_id']}-{c['country_id']}-{month.strftime('%Y%m')}"
                gross = gross_lookup[sid]
                amt = round(gross * cfg["comm_pct"] * random.uniform(0.88, 1.12), 2)
                rows.append((f"RC-{sid}", sid, b["brand_id"], c["country_id"], month, amt, cfg["comm_pct"]))
    con.execute("CREATE TABLE raw_rebates_commercial AS SELECT * FROM (VALUES " +
        ",\n".join(f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',DATE '{r[4]}',{r[5]},{r[6]})" for r in rows) +
        ") t(rebate_id,sale_id,brand_id,country_id,rebate_month,commercial_rebate_amount,commercial_rebate_pct_applied)")
    print(f"  raw_rebates_commercial: {len(rows)} rows")

    # ── Step 4: raw_chargebacks_accrual + actual ──────────────────────────────
    acc_rows, act_rows = [], []
    for b in BRANDS:
        cfg = BRAND_CONFIG[b["brand_id"]]
        for c in COUNTRIES:
            for i, month in enumerate(MONTHS):
                sid = f"S-{b['brand_id']}-{c['country_id']}-{month.strftime('%Y%m')}"
                gross = gross_lookup[sid]
                accrued = round(gross * cfg["cback_pct"] * random.uniform(0.90, 1.10), 2)
                lag = random.choice([1, 2])
                ri = i + lag
                receipt_month = MONTHS[ri] if ri < len(MONTHS) else date(2025, ri - 11, 1)
                actual = round(accrued * random.uniform(0.85, 1.15), 2)
                acc_rows.append((f"CA-{sid}", sid, b["brand_id"], c["country_id"], month, accrued))
                act_rows.append((f"CR-{sid}", sid, b["brand_id"], c["country_id"], month, receipt_month, actual, round(actual - accrued, 2)))

    con.execute("CREATE TABLE raw_chargebacks_accrual AS SELECT * FROM (VALUES " +
        ",\n".join(f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',DATE '{r[4]}',{r[5]})" for r in acc_rows) +
        ") t(accrual_id,sale_id,brand_id,country_id,sale_month,chargeback_accrued)")
    con.execute("CREATE TABLE raw_chargebacks_actual AS SELECT * FROM (VALUES " +
        ",\n".join(f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',DATE '{r[4]}',DATE '{r[5]}',{r[6]},{r[7]})" for r in act_rows) +
        ") t(receipt_id,sale_id,brand_id,country_id,original_sale_month,receipt_month,chargeback_actual,variance_vs_accrual)")
    print(f"  raw_chargebacks_accrual: {len(acc_rows)} rows")
    print(f"  raw_chargebacks_actual:  {len(act_rows)} rows")

    # ── Step 5: raw_distributor_sellthrough ───────────────────────────────────
    rows = []
    for b in BRANDS:
        for c in COUNTRIES:
            inv = 0
            for i, month in enumerate(MONTHS):
                sid = f"S-{b['brand_id']}-{c['country_id']}-{month.strftime('%Y%m')}"
                # Get actual shipped units from sales_rows
                shipped = next(r[4] for r in sales_rows if r[0] == sid)
                available = shipped + inv
                sold = int(available * random.uniform(0.88, 0.98))
                inv = available - sold
                rows.append((f"ST-{sid}", sid, b["brand_id"], c["country_id"], month, shipped, sold, inv))
    con.execute("CREATE TABLE raw_distributor_sellthrough AS SELECT * FROM (VALUES " +
        ",\n".join(f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',DATE '{r[4]}',{r[5]},{r[6]},{r[7]})" for r in rows) +
        ") t(sellthrough_id,sale_id,brand_id,country_id,month,units_shipped_to_distributor,units_sold_to_pharmacy,units_in_distributor_inventory)")
    print(f"  raw_distributor_sellthrough: {len(rows)} rows")

    # ── Step 6: raw_returns ───────────────────────────────────────────────────
    rows, ret_id = [], 1
    for b in BRANDS:
        cfg = BRAND_CONFIG[b["brand_id"]]
        for c in COUNTRIES:
            for i, month in enumerate(MONTHS):
                if random.random() < 0.35:
                    sid = f"S-{b['brand_id']}-{c['country_id']}-{month.strftime('%Y%m')}"
                    units = next(r[4] for r in sales_rows if r[0] == sid)
                    ret_units = max(1, int(units * random.uniform(0.01, 0.03)))
                    ret_val = round(ret_units * cfg["net_price"], 2)
                    lag = random.choice([1, 2, 3])
                    ri = i + lag
                    ret_month = MONTHS[ri] if ri < len(MONTHS) else date(2025, ri - 11, 1)
                    rows.append((f"RET-{ret_id:04d}", sid, b["brand_id"], c["country_id"], month, ret_month, ret_units, ret_val))
                    ret_id += 1
    con.execute("CREATE TABLE raw_returns AS SELECT * FROM (VALUES " +
        ",\n".join(f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',DATE '{r[4]}',DATE '{r[5]}',{r[6]},{r[7]})" for r in rows) +
        ") t(return_id,sale_id,brand_id,country_id,original_sale_month,return_month,return_units,return_value)")
    print(f"  raw_returns: {len(rows)} rows")

    # ── Step 7: raw_market_units ─────────────────────────────────────────────
    base_mkt = {"cardiovascular":85000,"oncology":12000,"respiratory":65000,"neurology":42000,"immunology":8500}
    rows = []
    for mol, tc, sc, is_branded in MARKET_MOLECULES:
        for c in COUNTRIES:
            for i, month in enumerate(MONTHS):
                units = max(1, int(base_mkt[tc] * random.uniform(0.88, 1.12) * (1 + i * 0.002)))
                rows.append((mol, tc, sc, is_branded, c["country_id"], month, units))
    con.execute("CREATE TABLE raw_market_units AS SELECT * FROM (VALUES " +
        ",\n".join(f"('{r[0]}','{r[1]}','{r[2]}',{str(r[3]).upper()},'{r[4]}',DATE '{r[5]}',{r[6]})" for r in rows) +
        ") t(molecule,therapeutic_class,sub_class,is_branded,country_id,month,total_units)")
    print(f"  raw_market_units: {len(rows)} rows")

    # ── Step 8: raw_finance_gl — placeholder, regenerated after dbt run ──────
    # Populated later from fct_brand_revenue to ensure within-tolerance reconciliation
    rows = []
    for b in BRANDS:
        for c in COUNTRIES:
            for month in MONTHS:
                sid = f"S-{b['brand_id']}-{c['country_id']}-{month.strftime('%Y%m')}"
                gross = gross_lookup[sid]
                rows.append((b["brand_id"], c["country_id"], month, round(gross, 2), 0.0))
    con.execute("CREATE TABLE raw_finance_gl AS SELECT * FROM (VALUES " +
        ",\n".join(f"('{r[0]}','{r[1]}',DATE '{r[2]}',{r[3]},{r[4]})" for r in rows) +
        ") t(brand_id,country_id,gl_month,gl_gross_revenue,gl_net_revenue)")
    print(f"  raw_finance_gl: {len(rows)} rows (placeholder — update after dbt run)")


def main():
    if DB_PATH.exists():
        DB_PATH.unlink()

    print(f"Creating DuckDB: {DB_PATH}")
    con = duckdb.connect(str(DB_PATH))
    print("Generating tables...")
    generate_all(con)

    tables = con.execute("SHOW TABLES").fetchall()
    print(f"\nTables: {[t[0] for t in tables]}")
    for t in tables:
        cnt = con.execute(f"SELECT COUNT(*) FROM {t[0]}").fetchone()[0]
        print(f"  {t[0]}: {cnt} rows")
    con.close()
    print("\nDone. Run dbt seed + run, then regenerate GL seed.")


if __name__ == "__main__":
    main()
