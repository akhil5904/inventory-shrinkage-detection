#!/usr/bin/env python
"""
Standalone validation script — reads generated CSV files and runs all checks.

Usage:
  python scripts/validate.py
  python scripts/validate.py --data-dir path/to/data
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from generator import config


def load_tables(data_dir: Path) -> dict:
    csv_dir = data_dir / "csv"
    tables  = {}
    for name in [
        "stores", "skus", "employees", "shifts", "promotions",
        "store_sku_map", "inventory_movements", "cycle_counts", "returns",
        "shrinkage_alerts", "investigations", "ground_truth",
    ]:
        path = csv_dir / f"{name}.csv"
        if path.exists():
            try:
                tables[name] = pd.read_csv(path, low_memory=False)
                print(f"  Loaded {name}: {len(tables[name])} rows")
            except Exception as e:
                tables[name] = pd.DataFrame()
                print(f"  Empty/unreadable {name}: {e}")
        else:
            print(f"  MISSING: {path}")
    return tables


def run_checks(tables: dict) -> dict:
    results = {}

    def check(label, passed, detail=""):
        status = "PASS" if passed else f"FAIL{(' – ' + detail) if detail else ''}"
        results[label] = status
        icon = "✓" if passed else "✗"
        print(f"  {icon} {label}: {status}")

    movements    = tables.get("inventory_movements", pd.DataFrame())
    stores       = tables.get("stores",              pd.DataFrame())
    skus         = tables.get("skus",                pd.DataFrame())
    employees    = tables.get("employees",           pd.DataFrame())
    cycle_counts = tables.get("cycle_counts",        pd.DataFrame())
    alerts       = tables.get("shrinkage_alerts",    pd.DataFrame())
    invs         = tables.get("investigations",      pd.DataFrame())
    ground_truth = tables.get("ground_truth",        pd.DataFrame())

    print("\n── Primary-key uniqueness ──────────────────────")
    pk_map = {
        "stores":              "store_id",
        "skus":                "sku_id",
        "employees":           "employee_id",
        "shifts":              "shift_id",
        "promotions":          "promo_id",
        "inventory_movements": "movement_id",
        "cycle_counts":        "count_id",
        "returns":             "return_id",
        "shrinkage_alerts":    "alert_id",
        "investigations":      "inv_id",
    }
    for name, pk in pk_map.items():
        df = tables.get(name, pd.DataFrame())
        if df.empty or pk not in df.columns:
            continue
        dupes = df[pk].duplicated().sum()
        check(f"{name}.{pk}", dupes == 0, f"{dupes} duplicates")

    print("\n── Foreign-key integrity (non-anomaly rows) ────")
    if not movements.empty and not stores.empty:
        valid_stores = set(stores["store_id"])
        clean_mov = movements[movements["is_anomaly"].astype(str) != "True"]
        bad = (~clean_mov["store_id"].isin(valid_stores)).sum()
        check("movements.store_id ∈ stores", bad == 0, f"{bad} bad FK")

    if not movements.empty and not skus.empty:
        valid_skus = set(skus["sku_id"])
        bad = (~movements["sku_id"].isin(valid_skus)).sum()
        check("movements.sku_id ∈ skus", bad == 0, f"{bad} bad FK")

    if not movements.empty and not employees.empty:
        valid_emp = set(employees["employee_id"])
        bad = (~movements["employee_id"].isin(valid_emp)).sum()
        check("movements.employee_id ∈ employees", bad == 0, f"{bad} bad FK")

    if not alerts.empty and not cycle_counts.empty:
        valid_cnt = set(cycle_counts["count_id"]) | {None, float("nan")}
        bad = alerts["count_id"].dropna()
        bad = (~bad.isin(valid_cnt)).sum()
        check("alerts.count_id ∈ cycle_counts", bad == 0, f"{bad} bad FK")

    if not invs.empty and not alerts.empty:
        valid_alerts = set(alerts["alert_id"])
        bad = (~invs["alert_id"].isin(valid_alerts)).sum()
        check("investigations.alert_id ∈ alerts", bad == 0, f"{bad} bad FK")

    returns_df = tables.get("returns", pd.DataFrame())
    if not returns_df.empty and not movements.empty:
        sales_ids = set(movements[movements["movement_type"] == "sale"]["movement_id"])
        linked = returns_df["original_movement_id"].dropna()
        bad = (~linked.isin(sales_ids)).sum()
        check("returns.original_movement_id ∈ sale movements", bad == 0, f"{bad} bad FK")

    print("\n── Derived-value correctness ────────────────────")
    if not movements.empty:
        computed = (movements["quantity"].abs() * movements["unit_cost"]).round(2)
        mismatch = (computed - movements["total_value"].astype(float)).abs() > 0.02
        check("movements.total_value = |qty| × cost", mismatch.sum() == 0,
              f"{mismatch.sum()} wrong")

    if not cycle_counts.empty:
        computed = cycle_counts["actual_qty"] - cycle_counts["expected_qty"]
        bad = (computed != cycle_counts["variance"]).sum()
        check("cycle_counts.variance = actual − expected", bad == 0, f"{bad} wrong")

    print("\n── Enum / allowed-values checks ─────────────────")
    valid_mv = {"receipt","sale","transfer_in","transfer_out","adjustment","return","shrinkage"}
    if not movements.empty:
        bad = (~movements["movement_type"].isin(valid_mv)).sum()
        check("movements.movement_type enum", bad == 0, f"{bad} bad values")

    valid_roles = {"cashier","stocker","manager","security","analyst"}
    if not employees.empty:
        bad = (~employees["role"].isin(valid_roles)).sum()
        check("employees.role enum", bad == 0, f"{bad} bad values")

    valid_sev = {"low","medium","high","critical"}
    if not alerts.empty:
        bad = (~alerts["severity"].isin(valid_sev)).sum()
        check("alerts.severity enum", bad == 0, f"{bad} bad values")

    print("\n── Lifecycle transitions ────────────────────────")
    if not invs.empty and "closed_date" in invs.columns and "opened_date" in invs.columns:
        closed = invs.dropna(subset=["closed_date"])
        bad = (closed["closed_date"] < closed["opened_date"]).sum()
        check("investigations.closed_date >= opened_date", bad == 0, f"{bad} violations")

    print("\n── Date ordering ────────────────────────────────")
    start_ts = config.START_DATE_STR + "T00:00:00"
    end_ts   = config.END_DATE_STR   + "T23:59:59"
    if not movements.empty:
        bad = ((movements["timestamp"] < start_ts) |
               (movements["timestamp"] > end_ts)).sum()
        check("movements.timestamp within window", bad == 0, f"{bad} out of range")

    print("\n── Adjustment reason policy ─────────────────────")
    if not movements.empty:
        adj = movements[movements["movement_type"] == "adjustment"]
        null_reason = adj["reason"].isna().sum()
        ec2_count   = null_reason
        expected_ec2 = config.N_EC_ADJUSTMENT_NO_REASON
        check(
            f"adjustments with null reason = {expected_ec2} (EC-002)",
            ec2_count == expected_ec2,
            f"found {ec2_count}"
        )

    print("\n── Stock equation reconciliation ────────────────")
    if not movements.empty:
        # Per store-SKU: sum(signed quantities) = on-hand balance (must be >= 0)
        balances = (
            movements.groupby(["store_id", "sku_id"])["quantity"]
            .sum()
            .reset_index(name="balance")
        )
        n_pairs    = len(balances)
        n_negative = (balances["balance"] < 0).sum()
        n_positive = (balances["balance"] >= 0).sum()
        check(
            "stock equation: all store-SKU balances ≥ 0",
            n_negative == 0,
            f"{n_negative}/{n_pairs} pairs have negative on-hand balance"
        )
        results["store_sku_pairs_checked"] = n_pairs
        results["store_sku_negative_balances"] = int(n_negative)
        results["store_sku_positive_balances"] = int(n_positive)
        if n_negative == 0:
            print(f"     All {n_pairs:,} store-SKU pairs reconcile to non-negative balance.")

        # Aggregate net: report but never fail (data-volume metric)
        total_in  = movements.loc[movements["quantity"] > 0, "quantity"].sum()
        total_out = movements.loc[movements["quantity"] < 0, "quantity"].abs().sum()
        net       = int(total_in) - int(total_out)
        results["net_inventory_balance"] = int(net)
        print(f"  ✓ net global balance: {net:+,}")

    print("\n── Alert reasons evidence-based ─────────────────")
    if not alerts.empty and not cycle_counts.empty:
        # Every alert linked to a count_id must reference a count with threshold-breaking variance
        alerts_with_cnt = alerts.dropna(subset=["count_id"])
        if not alerts_with_cnt.empty:
            cnt_lookup = cycle_counts.set_index("count_id")[["variance_value","variance_pct"]].to_dict("index")
            orphan = alerts_with_cnt["count_id"].apply(
                lambda cid: cid not in cnt_lookup
            ).sum()
            check("alerts.count_id all reference valid cycle counts", orphan == 0,
                  f"{orphan} alerts reference missing count_ids")
            # Check that referenced counts actually crossed a threshold
            def crossed(cid):
                c = cnt_lookup.get(cid, {})
                return (c.get("variance_value", 0) > config.VARIANCE_VALUE_THRESHOLD or
                        abs(c.get("variance_pct", 0)) > config.VARIANCE_PCT_THRESHOLD * 100)
            not_crossed = alerts_with_cnt["count_id"].apply(lambda c: not crossed(c)).sum()
            check("alert-triggering counts crossed threshold", not_crossed == 0,
                  f"{not_crossed} alerts reference counts that did not cross a threshold")
    elif alerts.empty:
        print("  ⚠  No alerts to validate (too few cycle counts at this scale).")

    print("\n── Benign explanations represented ──────────────")
    if not movements.empty:
        benign_types = {"receipt", "return", "adjustment"}
        benign_count = movements[movements["movement_type"].isin(benign_types)].shape[0]
        anomaly_count= movements[movements["is_anomaly"].astype(str).str.lower().isin(["true","1"])].shape[0]
        legit_damage = movements[movements["reason"].isin(
            ["damaged_goods","expired_product","receiving_error"])].shape[0]
        check("benign movements present (returns/adjustments/receipts)",
              benign_count > 0, f"{benign_count} benign records")
        check("legitimate damage/expiry reasons present",
              legit_damage > 0, f"{legit_damage} legitimate damage records")
        results["benign_movement_count"]  = int(benign_count)
        results["anomaly_movement_count"] = int(anomaly_count)
        results["legitimate_damage_count"]= int(legit_damage)
        print(f"     Benign movements: {benign_count:,}  |  "
              f"Anomalies: {anomaly_count:,}  |  "
              f"Legitimate damage/expiry: {legit_damage:,}")

    print("\n── Ground-truth anomaly counts ──────────────────")
    if not ground_truth.empty:
        ec_counts = ground_truth.groupby("anomaly_type").size().to_dict()
        print(f"   {ec_counts}")
        # At small scale, some edge-case types cannot be injected
        # (e.g. EC-001 needs ≥2 stores; EC-003 is bounded by cycle-count count).
        # Validate that each type that WAS injected is correctly labelled,
        # and that totals do not EXCEED the configured maximums.
        max_expected = {
            "wrong_store_reference":    config.N_EC_WRONG_STORE,
            "adjustment_missing_reason":config.N_EC_ADJUSTMENT_NO_REASON,
            "count_precedes_movement":  config.N_EC_COUNT_PRECEDES_MOVEMENT,
            "transfer_double_shrinkage":config.N_EC_TRANSFER_DOUBLE_SHRINKAGE,
        }
        for ec_type, max_n in max_expected.items():
            actual_n = ec_counts.get(ec_type, 0)
            check(
                f"ground_truth.{ec_type} count ≤ {max_n}",
                actual_n <= max_n,
                f"got {actual_n} > {max_n}"
            )
        # EC-002 (null-reason adjustments) must always be exactly as configured
        # because it doesn't depend on store/count availability.
        actual_ec2 = ec_counts.get("adjustment_missing_reason", 0)
        check(
            f"ground_truth.adjustment_missing_reason = {config.N_EC_ADJUSTMENT_NO_REASON} (EC-002)",
            actual_ec2 == config.N_EC_ADJUSTMENT_NO_REASON,
            f"expected {config.N_EC_ADJUSTMENT_NO_REASON}, got {actual_ec2}"
        )
        # Confirm every ground_truth row has a non-empty entity_id
        missing_ids = ground_truth["entity_id"].isna().sum()
        check("ground_truth.entity_id all populated", missing_ids == 0,
              f"{missing_ids} rows missing entity_id")

    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args()

    data_dir = Path(args.data_dir) if args.data_dir else config.DATA_DIR
    print(f"Validating data in: {data_dir}\n")

    print("Loading tables …")
    tables = load_tables(data_dir)

    results = run_checks(tables)

    fails = {k: v for k, v in results.items() if "FAIL" in str(v)}
    passes = len(results) - len(fails)
    print(f"\n{'='*50}")
    print(f"Results: {passes} passed, {len(fails)} failed")
    if fails:
        print("Failures:")
        for k, v in fails.items():
            print(f"  {k}: {v}")
        sys.exit(1)
    else:
        print("All checks passed.")


if __name__ == "__main__":
    main()
