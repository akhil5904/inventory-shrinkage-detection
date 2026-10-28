"""
Data-quality tests for the Inventory Shrinkage generator.

Covers the Evaluation Focus criteria from the project spec:
  (a) realistic distributions and meaningful variation
  (b) consistent IDs and valid joins
  (c) dependency/lifecycle consistency across entities
  (d) correct derived values and reconciliation
  (e) normal, boundary, failure and exception coverage
  (f) separate ground truth (no leak into feature tables)
  (g) fixed-seed reproducibility

Run:
  pytest tests/ -v

For a fast smoke-test, uses scale=0.05 (50K movements).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from generator import config
from generator.main import (
    build_store_sku_map,
    combine_movements,
    generate_cycle_counts,
    generate_employees,
    generate_investigations,
    generate_opening_balances,
    generate_operational_movements,
    generate_promotions,
    generate_returns,
    generate_shifts,
    generate_shrinkage_alerts,
    generate_skus,
    generate_stores,
    inject_edge_cases,
    reconcile_stock_equation,
    run,
)
from generator import ids
from faker import Faker


# ── Fixture: generate a small but complete dataset once per session ────────────
@pytest.fixture(scope="session")
def dataset():
    """Returns all tables from a 5%-scale run (deterministic, seed 20261022)."""
    tables = run(scale=0.05)
    return tables


# ══════════════════════════════════════════════════════════════════════════════
# (a) Realistic distributions and meaningful variation
# ══════════════════════════════════════════════════════════════════════════════

class TestDistributions:

    def test_stores_have_all_regions(self, dataset):
        stores = dataset["stores"]
        assert set(stores["region"]).issuperset({"Northeast", "Southeast", "Midwest"}), \
            "Expected multiple US regions represented"

    def test_stores_have_multiple_formats(self, dataset):
        stores = dataset["stores"]
        assert stores["format"].nunique() >= 2, "Expected at least 2 store formats"

    def test_sku_categories_all_present(self, dataset):
        skus = dataset["skus"]
        assert skus["category"].nunique() == len(config.SKU_CATEGORIES), \
            "All SKU categories should be represented"

    def test_employee_roles_all_present(self, dataset):
        emp = dataset["employees"]
        assert set(emp["role"]).issuperset(set(config.EMPLOYEE_ROLES)), \
            "All employee roles should be present"

    def test_movement_types_all_present(self, dataset):
        mov = dataset["inventory_movements"]
        expected = {"receipt", "sale", "transfer_in", "transfer_out",
                    "adjustment", "return", "shrinkage"}
        assert expected.issubset(set(mov["movement_type"])), \
            "All movement types should appear in the data"

    def test_adjustment_reasons_varied(self, dataset):
        mov  = dataset["inventory_movements"]
        adjs = mov[(mov["movement_type"] == "adjustment") & mov["reason"].notna()]
        assert adjs["reason"].nunique() >= 3, \
            "Adjustments should use at least 3 distinct reasons"

    def test_promotions_multiple_types(self, dataset):
        promos = dataset["promotions"]
        if len(promos) > 0:
            assert promos["promo_type"].nunique() >= 2, \
                "Multiple promotion types expected"

    def test_cycle_counts_have_variance(self, dataset):
        counts = dataset["cycle_counts"]
        if len(counts) > 5:
            assert counts["variance"].std() > 0, "Cycle count variance should not be constant"
            assert (counts["variance"] != 0).any(), "Some cycle counts should show variance"


# ══════════════════════════════════════════════════════════════════════════════
# (b) Consistent IDs and valid joins
# ══════════════════════════════════════════════════════════════════════════════

class TestIDConsistency:

    @pytest.mark.parametrize("table,pk", [
        ("stores",              "store_id"),
        ("skus",                "sku_id"),
        ("employees",           "employee_id"),
        ("shifts",              "shift_id"),
        ("promotions",          "promo_id"),
        ("inventory_movements", "movement_id"),
        ("cycle_counts",        "count_id"),
        ("returns",             "return_id"),
    ])
    def test_primary_key_unique(self, dataset, table, pk):
        df = dataset[table]
        dupes = df[pk].duplicated().sum()
        assert dupes == 0, f"{table}.{pk} has {dupes} duplicate values"

    def test_movement_store_fk(self, dataset):
        mov    = dataset["inventory_movements"]
        stores = dataset["stores"]
        clean  = mov[mov["is_anomaly"].astype(str).str.lower() != "true"]
        valid  = set(stores["store_id"])
        bad    = (~clean["store_id"].isin(valid)).sum()
        assert bad == 0, f"{bad} non-anomaly movements reference unknown store_ids"

    def test_movement_sku_fk(self, dataset):
        mov  = dataset["inventory_movements"]
        skus = dataset["skus"]
        bad  = (~mov["sku_id"].isin(set(skus["sku_id"]))).sum()
        assert bad == 0, f"{bad} movements reference unknown sku_ids"

    def test_movement_employee_fk(self, dataset):
        mov = dataset["inventory_movements"]
        emp = dataset["employees"]
        bad = (~mov["employee_id"].isin(set(emp["employee_id"]))).sum()
        assert bad == 0, f"{bad} movements reference unknown employee_ids"

    def test_return_references_sale(self, dataset):
        returns  = dataset["returns"]
        movements = dataset["inventory_movements"]
        if returns.empty:
            pytest.skip("No returns generated at this scale")
        sales_ids = set(movements[movements["movement_type"] == "sale"]["movement_id"])
        linked = returns["original_movement_id"].dropna()
        bad = (~linked.isin(sales_ids)).sum()
        assert bad == 0, f"{bad} returns reference movement_ids that are not sales"

    def test_store_id_format(self, dataset):
        stores = dataset["stores"]
        pattern = r"^STORE-\d{6}$"
        bad = (~stores["store_id"].str.match(pattern)).sum()
        assert bad == 0, f"{bad} store IDs don't match STORE-NNNNNN format"

    def test_sku_id_format(self, dataset):
        skus = dataset["skus"]
        bad = (~skus["sku_id"].str.match(r"^SKU-\d{6}$")).sum()
        assert bad == 0, f"{bad} SKU IDs have wrong format"

    def test_movement_id_format(self, dataset):
        mov = dataset["inventory_movements"]
        bad = (~mov["movement_id"].str.match(r"^MOV-\d{4}-\d{8}$")).sum()
        assert bad == 0, f"{bad} movement IDs have wrong format"


# ══════════════════════════════════════════════════════════════════════════════
# (c) Dependency and lifecycle consistency
# ══════════════════════════════════════════════════════════════════════════════

class TestLifecycleConsistency:

    def test_opening_balances_are_receipts(self, dataset):
        """The first movement for every store-SKU pair must be a receipt."""
        mov = dataset["inventory_movements"].copy()
        mov["ts"] = pd.to_datetime(mov["timestamp"])
        first = mov.sort_values("ts").groupby(["store_id","sku_id"]).first().reset_index()
        non_receipt = (first["movement_type"] != "receipt").sum()
        assert non_receipt == 0, \
            f"{non_receipt} store-SKU pairs don't start with a receipt movement"

    def test_all_movements_in_date_window(self, dataset):
        mov = dataset["inventory_movements"]
        lo  = config.START_DATE_STR + "T00:00:00"
        hi  = config.END_DATE_STR   + "T23:59:59"
        bad = ((mov["timestamp"] < lo) | (mov["timestamp"] > hi)).sum()
        assert bad == 0, f"{bad} movements fall outside the date window"

    def test_shift_date_in_window(self, dataset):
        shifts = dataset["shifts"]
        lo = config.START_DATE_STR
        hi = config.END_DATE_STR
        bad = ((shifts["shift_date"] < lo) | (shifts["shift_date"] > hi)).sum()
        assert bad == 0, f"{bad} shifts fall outside the date window"

    def test_promotion_end_after_start(self, dataset):
        promos = dataset["promotions"]
        bad = (promos["end_date"] < promos["start_date"]).sum()
        assert bad == 0, f"{bad} promotions have end_date before start_date"

    def test_investigation_closed_after_opened(self, dataset):
        invs = dataset["investigations"]
        closed = invs.dropna(subset=["closed_date"])
        bad = (closed["closed_date"] < closed["opened_date"]).sum()
        assert bad == 0, f"{bad} investigations closed before they were opened"

    def test_return_date_after_epoch(self, dataset):
        rets = dataset["returns"]
        if rets.empty:
            pytest.skip("No returns at this scale")
        bad = (rets["return_date"] < config.START_DATE_STR).sum()
        assert bad == 0, f"{bad} returns predate the simulation start"


# ══════════════════════════════════════════════════════════════════════════════
# (d) Correct derived values and reconciliation
# ══════════════════════════════════════════════════════════════════════════════

class TestDerivedValues:

    def test_total_value_correct(self, dataset):
        """total_value must equal abs(quantity) * unit_cost."""
        mov = dataset["inventory_movements"]
        computed = (mov["quantity"].abs() * mov["unit_cost"]).round(2)
        mismatch = (computed - mov["total_value"].astype(float)).abs() > 0.02
        assert mismatch.sum() == 0, \
            f"{mismatch.sum()} movements have wrong total_value"

    def test_cycle_count_variance_derived(self, dataset):
        """variance must equal actual_qty - expected_qty."""
        cnt = dataset["cycle_counts"]
        computed = cnt["actual_qty"] - cnt["expected_qty"]
        bad = (computed != cnt["variance"]).sum()
        assert bad == 0, f"{bad} cycle counts have wrong variance"

    def test_stock_equation_reconciles(self, dataset):
        """Every store-SKU pair must have non-negative on-hand balance."""
        mov = dataset["inventory_movements"]
        balances = mov.groupby(["store_id","sku_id"])["quantity"].sum()
        neg = (balances < 0).sum()
        assert neg == 0, \
            f"{neg} store-SKU pairs have negative on-hand balance (stock equation fails)"

    def test_unit_price_exceeds_cost(self, dataset):
        skus = dataset["skus"]
        bad = (skus["unit_price"] <= skus["unit_cost"]).sum()
        assert bad == 0, f"{bad} SKUs have unit_price ≤ unit_cost"

    def test_refund_positive(self, dataset):
        rets = dataset["returns"]
        if rets.empty:
            pytest.skip("No returns at this scale")
        bad = (rets["refund_amount"] < 0).sum()
        assert bad == 0, f"{bad} returns have negative refund_amount"


# ══════════════════════════════════════════════════════════════════════════════
# (e) Normal, boundary, failure and exception coverage
# ══════════════════════════════════════════════════════════════════════════════

class TestEdgeCaseCoverage:

    def test_ec002_null_reason_adjustments(self, dataset):
        """EC-002: exactly N_EC_ADJUSTMENT_NO_REASON adjustments have null reason."""
        mov  = dataset["inventory_movements"]
        null = (
            (mov["movement_type"] == "adjustment") & mov["reason"].isna()
        ).sum()
        assert null == config.N_EC_ADJUSTMENT_NO_REASON, \
            f"Expected {config.N_EC_ADJUSTMENT_NO_REASON} null-reason adjustments, got {null}"

    def test_ec001_wrong_store_labelled(self, dataset):
        gt = dataset["ground_truth"]
        ec1 = gt[gt["anomaly_type"] == "wrong_store_reference"]
        assert len(ec1) <= config.N_EC_WRONG_STORE, \
            "More EC-001 anomalies in ground_truth than configured"

    def test_ec003_count_precedes_movement_labelled(self, dataset):
        gt  = dataset["ground_truth"]
        ec3 = gt[gt["anomaly_type"] == "count_precedes_movement"]
        assert len(ec3) <= config.N_EC_COUNT_PRECEDES_MOVEMENT

    def test_ec004_transfer_double_shrinkage_labelled(self, dataset):
        gt  = dataset["ground_truth"]
        ec4 = gt[gt["anomaly_type"] == "transfer_double_shrinkage"]
        assert len(ec4) <= config.N_EC_TRANSFER_DOUBLE_SHRINKAGE

    def test_anomaly_rows_marked_is_anomaly(self, dataset):
        """All movement rows in ground_truth must have is_anomaly=True in movements."""
        gt  = dataset["ground_truth"]
        mov = dataset["inventory_movements"]
        mov_ec_ids = gt[gt["entity_type"] == "InventoryMovement"]["entity_id"].tolist()
        if not mov_ec_ids:
            pytest.skip("No movement-level anomalies at this scale")
        subset = mov[mov["movement_id"].isin(mov_ec_ids)]
        bad = (subset["is_anomaly"].astype(str).str.lower() != "true").sum()
        assert bad == 0, \
            f"{bad} anomaly movements are not flagged with is_anomaly=True"

    def test_legitimate_damage_returns_present(self, dataset):
        """Benign explanations: legitimate damage/expiry must be represented."""
        mov = dataset["inventory_movements"]
        benign = mov["reason"].isin(["damaged_goods","expired_product","receiving_error"])
        assert benign.sum() > 0, \
            "No legitimate damage/expiry records — benign explanations missing"


# ══════════════════════════════════════════════════════════════════════════════
# (f) Separate ground truth — no leak into feature tables
# ══════════════════════════════════════════════════════════════════════════════

class TestGroundTruthSeparation:

    def test_ground_truth_not_empty(self, dataset):
        gt = dataset["ground_truth"]
        assert len(gt) > 0, "Ground truth must contain labelled anomalies"

    def test_ground_truth_has_required_columns(self, dataset):
        gt   = dataset["ground_truth"]
        required = {"anomaly_id","entity_type","entity_id","anomaly_type",
                    "expected_decision","description"}
        missing = required - set(gt.columns)
        assert not missing, f"Ground truth missing columns: {missing}"

    def test_ground_truth_entity_ids_populated(self, dataset):
        gt = dataset["ground_truth"]
        bad = gt["entity_id"].isna().sum()
        assert bad == 0, f"{bad} ground_truth rows have null entity_id"

    def test_no_anomaly_type_column_in_movements_for_clean_rows(self, dataset):
        """Clean (non-anomaly) movement rows must have null anomaly_type."""
        mov   = dataset["inventory_movements"]
        clean = mov[mov["is_anomaly"].astype(str).str.lower() != "true"]
        leak  = clean["anomaly_type"].notna().sum()
        assert leak == 0, \
            f"{leak} non-anomaly movements have a non-null anomaly_type (ground-truth leaked)"

    def test_alert_reasons_are_evidence_based(self, dataset):
        """Every alert with a count_id must reference a count that crossed the threshold."""
        alerts = dataset["shrinkage_alerts"]
        counts = dataset["cycle_counts"]
        if alerts.empty or counts.empty:
            pytest.skip("No alerts at this scale")
        linked = alerts.dropna(subset=["count_id"])
        if linked.empty:
            pytest.skip("No alerts have count_id references")
        cnt_idx = counts.set_index("count_id")[["variance_value","variance_pct"]]
        for _, row in linked.iterrows():
            cid = row["count_id"]
            assert cid in cnt_idx.index, f"Alert references missing count_id {cid}"
            c = cnt_idx.loc[cid]
            triggered = (
                c["variance_value"] > config.VARIANCE_VALUE_THRESHOLD or
                abs(c["variance_pct"]) > config.VARIANCE_PCT_THRESHOLD * 100
            )
            assert triggered, \
                f"Alert {row['alert_id']} references count {cid} that did not cross threshold"


# ══════════════════════════════════════════════════════════════════════════════
# (g) Fixed-seed reproducibility
# ══════════════════════════════════════════════════════════════════════════════

class TestReproducibility:

    def test_two_runs_produce_identical_movement_count(self):
        """Running twice with the same seed produces the same row count."""
        t1 = run(scale=0.01)
        t2 = run(scale=0.01)
        assert len(t1["inventory_movements"]) == len(t2["inventory_movements"]), \
            "Movement count differs between runs — generator is not deterministic"

    def test_two_runs_produce_identical_store_ids(self):
        t1 = run(scale=0.01)
        t2 = run(scale=0.01)
        ids1 = sorted(t1["stores"]["store_id"].tolist())
        ids2 = sorted(t2["stores"]["store_id"].tolist())
        assert ids1 == ids2, "Store IDs differ between runs"

    def test_two_runs_produce_identical_ground_truth(self):
        t1 = run(scale=0.01)
        t2 = run(scale=0.01)
        assert sorted(t1["ground_truth"]["anomaly_id"].tolist()) == \
               sorted(t2["ground_truth"]["anomaly_id"].tolist()), \
               "Ground truth anomaly IDs differ between runs"

    def test_seed_constant_is_correct(self):
        assert config.SEED == 20261022, "Seed must be 20261022 per spec"
