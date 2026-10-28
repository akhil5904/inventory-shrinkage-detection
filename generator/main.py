"""
Inventory Shrinkage Synthetic Data Generator
=============================================
Run via:  python scripts/generate.py [--scale 0.01]
Seed:     20261022  (fully deterministic)
"""

from __future__ import annotations

import json
import math
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from faker import Faker

from generator import config, ids

# ─── helpers ─────────────────────────────────────────────────────────────────

_US_STATES = [
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
    "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
    "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
    "VA","WA","WV","WI","WY",
]

_REGION_STATES = {
    "Northeast": ["ME","VT","NH","MA","RI","CT","NY","NJ","PA"],
    "Southeast": ["MD","DE","VA","WV","KY","NC","SC","TN","GA","FL","AL","MS","AR","LA"],
    "Midwest":   ["OH","IN","IL","MI","WI","MN","IA","MO","ND","SD","NE","KS"],
    "Southwest": ["TX","OK","NM","AZ"],
    "West":      ["CO","WY","MT","ID","WA","OR","CA","NV","UT","AK","HI"],
}

_TOTAL_DAYS = (
    date.fromisoformat(config.END_DATE_STR) - date.fromisoformat(config.START_DATE_STR)
).days + 1

# ─── Section 1: Master / parent tables ───────────────────────────────────────

def generate_stores(rng: np.random.Generator, fake: Faker) -> pd.DataFrame:
    n = config.N_STORES
    # Guarantee every region appears at least once even at small scale
    n_regions = len(config.STORE_REGIONS)
    if n >= n_regions:
        extras = list(rng.choice(config.STORE_REGIONS, n - n_regions))
        all_regions = np.array(list(config.STORE_REGIONS) + extras)
        rng.shuffle(all_regions)
        regions = all_regions
    else:
        regions = rng.choice(config.STORE_REGIONS, n)
    formats = rng.choice(
        config.STORE_FORMATS, n, p=config.STORE_FORMAT_WEIGHTS
    )
    statuses = rng.choice(
        config.STORE_STATUSES, n, p=config.STORE_STATUS_WEIGHTS
    )

    rows = []
    for i in range(n):
        region = regions[i]
        state  = rng.choice(_REGION_STATES[region])
        city   = fake.city()
        opened = date(
            int(rng.integers(2010, 2026)),
            int(rng.integers(1, 13)),
            int(rng.integers(1, 29)),
        )
        rows.append({
            "store_id":    ids.store_id(i + 1),
            "name":        f"{city} {formats[i].title()} #{i+1:03d}",
            "city":        city,
            "state":       state,
            "region":      region,
            "format":      formats[i],
            "opened_date": opened.isoformat(),
            "status":      statuses[i],
            "timezone":    config.US_TIMEZONES[region],
        })
    return pd.DataFrame(rows)


def generate_skus(rng: np.random.Generator, fake: Faker) -> pd.DataFrame:
    n     = config.N_SKUS
    cats  = list(config.SKU_CATEGORIES.keys())
    cat_w = [config.SKU_CATEGORIES[c]["weight"] for c in cats]
    chosen_cats = rng.choice(cats, n, p=cat_w)

    rows = []
    for i, cat in enumerate(chosen_cats):
        cfg = config.SKU_CATEGORIES[cat]
        sub = rng.choice(cfg["subcategories"])
        cost  = round(float(rng.uniform(cfg["price_lo"], cfg["price_hi"])), 2)
        price = round(cost / (1 - cfg["margin"]), 2)
        rows.append({
            "sku_id":                  ids.sku_id(i + 1),
            "name":                    f"{sub} {fake.word().title()} {i+1}",
            "category":                cat,
            "subcategory":             sub,
            "unit_cost":               cost,
            "unit_price":              price,
            "weight_kg":               round(float(rng.uniform(0.05, 10.0)), 3),
            "is_high_value":           cfg["is_high_value"],
            "requires_age_verification": cfg.get("age_verify", False),
            "shelf_life_days":         cfg["shelf_life_days"],
            "status":                  rng.choice(["active", "discontinued", "seasonal"],
                                                   p=[0.88, 0.07, 0.05]),
        })
    return pd.DataFrame(rows)


def generate_employees(stores: pd.DataFrame, rng: np.random.Generator,
                       fake: Faker) -> pd.DataFrame:
    rows = []
    emp_counter = 1
    for _, store in stores.iterrows():
        n_emp = int(rng.integers(30, 81))
        roles = rng.choice(
            config.EMPLOYEE_ROLES, n_emp, p=config.EMPLOYEE_ROLE_WEIGHTS
        )
        statuses = rng.choice(
            config.EMPLOYEE_STATUSES, n_emp, p=config.EMPLOYEE_STATUS_WEIGHTS
        )
        for j in range(n_emp):
            hire = date(
                int(rng.integers(2015, 2027)),
                int(rng.integers(1, 13)),
                int(rng.integers(1, 29)),
            )
            rows.append({
                "employee_id": ids.employee_id(emp_counter),
                "store_id":    store["store_id"],
                "first_name":  fake.first_name(),
                "last_name":   fake.last_name(),
                "role":        roles[j],
                "hire_date":   hire.isoformat(),
                "status":      statuses[j],
            })
            emp_counter += 1
    return pd.DataFrame(rows)


def generate_shifts(employees: pd.DataFrame, rng: np.random.Generator,
                    target: int = 200_000) -> pd.DataFrame:
    """Generate roughly `target` shifts, spread over all employees."""
    emp_ids   = employees["employee_id"].values
    store_map = dict(zip(employees["employee_id"], employees["store_id"]))
    role_map  = dict(zip(employees["employee_id"], employees["role"]))

    n     = min(target, len(emp_ids) * _TOTAL_DAYS)
    idx   = rng.integers(0, len(emp_ids), n)
    eids  = emp_ids[idx]
    days  = rng.integers(0, _TOTAL_DAYS, n)
    starts= rng.integers(6, 18, n)         # shift start hour 06–17
    durs  = rng.integers(4, 10, n)         # shift duration 4–9 h

    shift_dates = np.array(
        [date.fromisoformat(config.START_DATE_STR) + timedelta(days=int(d)) for d in days],
        dtype=object
    )
    start_times = [f"{h:02d}:00" for h in starts]
    end_times   = [f"{min(h+d, 23):02d}:00" for h, d in zip(starts, durs)]

    df = pd.DataFrame({
        "shift_id":   [ids.shift_id(i + 1) for i in range(n)],
        "store_id":   [store_map[e] for e in eids],
        "employee_id":eids,
        "shift_date": [d.isoformat() for d in shift_dates],
        "start_time": start_times,
        "end_time":   end_times,
        "role":       [role_map[e] for e in eids],
    })
    # deduplicate same employee same day (keep first)
    df = df.drop_duplicates(subset=["employee_id", "shift_date"]).reset_index(drop=True)
    df["shift_id"] = [ids.shift_id(i + 1) for i in range(len(df))]
    return df


def generate_promotions(skus: pd.DataFrame, stores: pd.DataFrame,
                        rng: np.random.Generator) -> pd.DataFrame:
    n = int(2000 * config.SCALE)
    sku_ids   = skus[skus["status"] == "active"]["sku_id"].values
    store_ids = stores["store_id"].values
    start_day = rng.integers(0, _TOTAL_DAYS - 30, n)
    dur       = rng.integers(7, 61, n)
    discount  = rng.uniform(5.0, 60.0, n).round(1)

    start_date_base = date.fromisoformat(config.START_DATE_STR)
    rows = []
    for i in range(n):
        s = start_date_base + timedelta(days=int(start_day[i]))
        e = s + timedelta(days=int(dur[i]))
        if e > date.fromisoformat(config.END_DATE_STR):
            e = date.fromisoformat(config.END_DATE_STR)
        status = "expired" if e < date.today() else "active"
        rows.append({
            "promo_id":     ids.promotion_id(i + 1),
            "sku_id":       rng.choice(sku_ids),
            "store_id":     rng.choice(store_ids),
            "promo_type":   rng.choice(config.PROMOTION_TYPES),
            "discount_pct": round(float(discount[i]), 1),
            "start_date":   s.isoformat(),
            "end_date":     e.isoformat(),
            "status":       status,
        })
    return pd.DataFrame(rows)


# ─── Section 2: Store-SKU mapping ────────────────────────────────────────────

def build_store_sku_map(stores: pd.DataFrame, skus: pd.DataFrame,
                        rng: np.random.Generator) -> pd.DataFrame:
    """Each store carries a random subset of 300-800 SKUs."""
    all_sku_ids = skus["sku_id"].values
    sku_cost    = dict(zip(skus["sku_id"], skus["unit_cost"]))
    sku_price   = dict(zip(skus["sku_id"], skus["unit_price"]))

    rows = []
    for _, store in stores.iterrows():
        n_skus = int(rng.integers(300, 801))
        chosen = rng.choice(all_sku_ids, min(n_skus, len(all_sku_ids)), replace=False)
        for s in chosen:
            rows.append({
                "store_id":  store["store_id"],
                "sku_id":    s,
                "unit_cost": sku_cost[s],
                "unit_price":sku_price[s],
            })
    return pd.DataFrame(rows)


# ─── Section 3: Inventory movements ──────────────────────────────────────────

def _random_timestamps(n: int, rng: np.random.Generator,
                       start: date, end: date) -> List[str]:
    total_secs = int((datetime.combine(end, datetime.max.time()) -
                      datetime.combine(start, datetime.min.time())).total_seconds())
    offsets    = rng.integers(0, total_secs, n)
    base_ts    = datetime.combine(start, datetime.min.time())
    return [(base_ts + timedelta(seconds=int(o))).strftime("%Y-%m-%dT%H:%M:%S")
            for o in offsets]


def generate_opening_balances(
    store_sku: pd.DataFrame,
    employees: pd.DataFrame,
    shifts: pd.DataFrame,
    rng: np.random.Generator,
    mov_counter_start: int = 1,
) -> Tuple[pd.DataFrame, int]:
    n = len(store_sku)
    qtys = rng.integers(50, 501, n)

    # pick a random employee + shift per row for receipt authorisation
    all_emp = employees["employee_id"].values
    emp_idx = rng.integers(0, len(all_emp), n)
    emp_sel = all_emp[emp_idx]

    start = date.fromisoformat(config.START_DATE_STR)

    rows = []
    for i, (_, row) in enumerate(store_sku.iterrows()):
        mov_num = mov_counter_start + i
        qty     = int(qtys[i])
        cost    = round(float(row["unit_cost"]), 2)
        rows.append({
            "movement_id":   ids.movement_id(mov_num),
            "store_id":      row["store_id"],
            "sku_id":        row["sku_id"],
            "movement_type": "receipt",
            "quantity":      qty,
            "unit_cost":     cost,
            "total_value":   round(qty * cost, 2),
            "shift_id":      None,
            "employee_id":   emp_sel[i],
            "timestamp":     datetime.combine(start, datetime.min.time()).strftime("%Y-%m-%dT%H:%M:%S"),
            "reason":        "opening_balance",
            "reference_id":  None,
            "is_anomaly":    False,
            "anomaly_type":  None,
        })
    return pd.DataFrame(rows), mov_counter_start + n


def generate_operational_movements(
    store_sku: pd.DataFrame,
    employees: pd.DataFrame,
    shifts: pd.DataFrame,
    rng: np.random.Generator,
    n_target: int,
    mov_counter_start: int,
) -> Tuple[pd.DataFrame, int]:
    """Generate n_target operational movements (sales, transfers, adjustments, returns, shrinkage)."""
    start_d = date.fromisoformat(config.START_DATE_STR)
    end_d   = date.fromisoformat(config.END_DATE_STR)

    ss_arr     = store_sku.values          # columns: store_id, sku_id, unit_cost, unit_price
    ss_len     = len(ss_arr)
    all_emp    = employees["employee_id"].values
    store_emp  = employees.groupby("store_id")["employee_id"].apply(list).to_dict()

    # Build (employee_id, shift_date) → shift_id index so movements reference their shift
    shift_index: dict = {}
    if not shifts.empty:
        shift_index = dict(zip(
            zip(shifts["employee_id"], shifts["shift_date"]),
            shifts["shift_id"]
        ))

    # type distribution for operational movements
    move_types  = ["sale", "transfer_out", "transfer_in", "adjustment", "return", "shrinkage"]
    move_probs  = [0.60,   0.07,           0.07,          0.10,         0.08,     0.08]

    type_choices  = rng.choice(move_types, n_target, p=move_probs)
    ss_indices    = rng.integers(0, ss_len, n_target)
    timestamps    = _random_timestamps(n_target, rng, start_d, end_d)
    emp_indices   = rng.integers(0, len(all_emp), n_target)
    base_qtys     = rng.integers(1, 16, n_target)

    adj_reason_choices = rng.choice(len(config.ADJUSTMENT_REASONS), n_target)
    shrink_type_choices= rng.choice(len(config.SHRINKAGE_TYPES), n_target)

    # transfer pair reference IDs (for every transfer_out we assign a ref; transfer_in reuses it)
    transfer_ref_pool = {}   # ts → ref string (simple counter)
    transfer_ref_ctr  = 1

    rows = []
    for i in range(n_target):
        mv_type = type_choices[i]
        ss_row  = ss_arr[ss_indices[i]]
        store_id_, sku_id_, unit_cost_, unit_price_ = ss_row
        cost   = float(unit_cost_)
        qty    = int(base_qtys[i])

        # sign convention
        if mv_type in ("sale", "transfer_out", "shrinkage"):
            qty = -qty
        elif mv_type in ("receipt", "transfer_in", "return", "adjustment"):
            if rng.random() < 0.5 and mv_type == "adjustment":
                qty = -qty   # roughly half adjustments are negative

        reason     = None
        reference  = None
        employee_  = all_emp[emp_indices[i]]
        shift_id_  = shift_index.get((employee_, timestamps[i][:10]))

        if mv_type == "adjustment":
            reason = config.ADJUSTMENT_REASONS[int(adj_reason_choices[i])]
        elif mv_type == "shrinkage":
            reason = config.SHRINKAGE_TYPES[int(shrink_type_choices[i])]
        elif mv_type in ("transfer_in", "transfer_out"):
            ref_key   = (store_id_, sku_id_, timestamps[i][:10])
            if mv_type == "transfer_out":
                reference = f"TRF-{transfer_ref_ctr:06d}"
                transfer_ref_pool[ref_key] = reference
                transfer_ref_ctr += 1
            else:
                reference = transfer_ref_pool.pop(ref_key, f"TRF-ORPHAN-{i:06d}")
        elif mv_type == "return":
            reason = rng.choice(config.RETURN_REASONS)

        total_val = round(abs(qty) * cost, 2)
        mov_num   = mov_counter_start + i

        rows.append({
            "movement_id":   ids.movement_id(mov_num),
            "store_id":      store_id_,
            "sku_id":        sku_id_,
            "movement_type": mv_type,
            "quantity":      qty,
            "unit_cost":     round(cost, 2),
            "total_value":   total_val,
            "shift_id":      shift_id_,
            "employee_id":   employee_,
            "timestamp":     timestamps[i],
            "reason":        reason,
            "reference_id":  reference,
            "is_anomaly":    False,
            "anomaly_type":  None,
        })

    return pd.DataFrame(rows), mov_counter_start + n_target


def combine_movements(opening: pd.DataFrame, operational: pd.DataFrame) -> pd.DataFrame:
    df = pd.concat([opening, operational], ignore_index=True)
    df.sort_values("timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)
    df["movement_id"] = [ids.movement_id(i + 1) for i in range(len(df))]
    return df


def reconcile_stock_equation(
    movements: pd.DataFrame,
    store_sku: pd.DataFrame,
    employees: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """
    Stock equation: sum(signed quantities per store-SKU) must be >= 0.
    Any pair with a negative balance gets a correction receipt so the
    equation reconciles without altering the rest of the data.
    The correction reason is 'stock_reconciliation' so it is auditable.
    """
    balances = (
        movements.groupby(["store_id", "sku_id"])["quantity"]
        .sum()
        .reset_index(name="balance")
    )
    negative = balances[balances["balance"] < 0].copy()
    if negative.empty:
        return movements

    sku_cost = dict(zip(store_sku["sku_id"], store_sku["unit_cost"]))
    all_emp  = employees["employee_id"].values
    # Use max existing numeric suffix to avoid collisions with gaps left by inject_edge_cases
    max_id   = int(movements["movement_id"].str.extract(r"-(\d+)$")[0].astype(int).max())
    start_n  = max_id + 1
    end_ts   = config.END_DATE_STR + "T23:59:00"

    correction_rows = []
    for i, (_, row) in enumerate(negative.iterrows()):
        correction_qty = int(abs(row["balance"])) + 1   # bring to ≥ 1
        cost = round(float(sku_cost.get(row["sku_id"], 1.0)), 2)
        correction_rows.append({
            "movement_id":   ids.movement_id(start_n + i),
            "store_id":      row["store_id"],
            "sku_id":        row["sku_id"],
            "movement_type": "receipt",
            "quantity":      correction_qty,
            "unit_cost":     cost,
            "total_value":   round(correction_qty * cost, 2),
            "shift_id":      None,
            "employee_id":   rng.choice(all_emp),
            "timestamp":     end_ts,
            "reason":        "stock_reconciliation",
            "reference_id":  None,
            "is_anomaly":    False,
            "anomaly_type":  None,
        })

    corr_df   = pd.DataFrame(correction_rows)
    # Append corrections without renumbering existing IDs — callers (returns, ground_truth)
    # hold references to existing movement_ids that must not change.
    return pd.concat([movements, corr_df], ignore_index=True)


# ─── Section 4: Running balance ──────────────────────────────────────────────

def compute_running_balances(movements: pd.DataFrame) -> pd.DataFrame:
    """Return a DataFrame with store_id, sku_id, balance (current on-hand qty)."""
    df = movements.copy()
    df["ts"] = pd.to_datetime(df["timestamp"])
    df.sort_values(["store_id", "sku_id", "ts"], inplace=True)
    df["cum_qty"] = df.groupby(["store_id", "sku_id"])["quantity"].cumsum()
    last = df.groupby(["store_id", "sku_id"]).last().reset_index()[
        ["store_id", "sku_id", "cum_qty"]
    ]
    last.rename(columns={"cum_qty": "balance"}, inplace=True)
    return last


def compute_balance_at(movements: pd.DataFrame, store_id_: str,
                       sku_id_: str, before_ts: str) -> int:
    mask = (
        (movements["store_id"] == store_id_) &
        (movements["sku_id"]   == sku_id_) &
        (movements["timestamp"] <= before_ts)
    )
    return int(movements.loc[mask, "quantity"].sum())


# ─── Section 5: Cycle counts ─────────────────────────────────────────────────

def generate_cycle_counts(
    store_sku: pd.DataFrame,
    movements: pd.DataFrame,
    employees: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    n = int(config.N_CYCLE_COUNTS * config.SCALE)
    start_d = date.fromisoformat(config.START_DATE_STR)
    end_d   = date.fromisoformat(config.END_DATE_STR)

    # index movements for fast balance lookups
    mov_indexed = movements.set_index(["store_id", "sku_id"])
    sku_cost    = dict(zip(store_sku["sku_id"], store_sku["unit_cost"]))
    all_emp     = employees["employee_id"].values

    ss_arr = store_sku.values
    ss_idx = rng.integers(0, len(ss_arr), n)
    day_offsets = rng.integers(30, _TOTAL_DAYS, n)   # start at least 30 days in
    emp_idx     = rng.integers(0, len(all_emp), n)

    rows = []
    for i in range(n):
        row       = ss_arr[ss_idx[i]]
        store_id_ = row[0]
        sku_id_   = row[1]
        cost      = float(sku_cost.get(sku_id_, row[2]))

        count_date = start_d + timedelta(days=int(day_offsets[i]))
        if count_date > end_d:
            count_date = end_d
        count_ts = datetime.combine(count_date, datetime.min.time()).strftime("%Y-%m-%dT%H:%M:%S")

        # expected = sum of all movements for this store-sku up to count_date
        try:
            grp = mov_indexed.loc[(store_id_, sku_id_)]
            expected = int(grp.loc[grp["timestamp"] <= count_ts, "quantity"].sum())
        except KeyError:
            expected = 0
        expected = max(0, expected)

        # actual: mostly close to expected; ~5 % are anomalous
        if rng.random() < 0.05:
            variance = int(rng.integers(-expected // 4 - 1, expected // 4 + 2))
        else:
            variance = int(rng.integers(-3, 4))
        actual = max(0, expected + variance)
        variance_pct = round((actual - expected) / max(1, expected) * 100, 2)
        variance_val = round(abs(actual - expected) * cost, 2)

        if abs(variance) == 0:
            status = "clean"
        elif abs(variance_pct) <= 2:
            status = "variance_low"
        elif abs(variance_pct) <= config.VARIANCE_PCT_THRESHOLD * 100:
            status = "variance_low"
        else:
            status = "variance_high"
        if variance_val > config.VARIANCE_VALUE_THRESHOLD or abs(variance_pct) > 20:
            status = "anomaly"

        rows.append({
            "count_id":       ids.count_id(i + 1),
            "store_id":       store_id_,
            "sku_id":         sku_id_,
            "counted_by":     all_emp[emp_idx[i]],
            "shift_id":       None,
            "count_datetime": count_ts,
            "expected_qty":   expected,
            "actual_qty":     actual,
            "variance":       actual - expected,
            "variance_pct":   variance_pct,
            "variance_value": variance_val,
            "status":         status,
            "notes":          None,
        })
    return pd.DataFrame(rows)


# ─── Section 6: Returns ───────────────────────────────────────────────────────

def generate_returns(
    movements: pd.DataFrame,
    employees: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    _RET_COLS = ["return_id","store_id","sku_id","original_movement_id","return_date",
                 "quantity","reason","condition","employee_id","refund_amount"]
    sales = movements[movements["movement_type"] == "sale"].copy()
    n     = min(int(20_000 * config.SCALE), len(sales))
    if n == 0:
        return pd.DataFrame(columns=_RET_COLS)

    sampled = sales.sample(n, random_state=int(rng.integers(0, 999_999)),
                           replace=False).reset_index(drop=True)
    all_emp = employees["employee_id"].values
    emp_idx = rng.integers(0, len(all_emp), n)
    qtys    = rng.integers(1, 4, n)
    reasons = rng.choice(config.RETURN_REASONS, n)
    conds   = rng.choice(config.ITEM_CONDITIONS, n, p=config.CONDITION_WEIGHTS)

    rows = []
    for i, (_, sale_row) in enumerate(sampled.iterrows()):
        sale_ts  = pd.to_datetime(sale_row["timestamp"])
        ret_date = (sale_ts + timedelta(days=int(rng.integers(1, 31)))).date()
        end_d    = date.fromisoformat(config.END_DATE_STR)
        if ret_date > end_d:
            ret_date = end_d
        qty = min(int(qtys[i]), abs(int(sale_row["quantity"])))
        rows.append({
            "return_id":            ids.return_id(i + 1),
            "store_id":             sale_row["store_id"],
            "sku_id":               sale_row["sku_id"],
            "original_movement_id": sale_row["movement_id"],
            "return_date":          ret_date.isoformat(),
            "quantity":             qty,
            "reason":               reasons[i],
            "condition":            conds[i],
            "employee_id":          all_emp[emp_idx[i]],
            "refund_amount":        round(qty * float(sale_row["unit_cost"]), 2),
        })
    return pd.DataFrame(rows)


# ─── Section 7: Shrinkage alerts ─────────────────────────────────────────────

def generate_shrinkage_alerts(
    cycle_counts: pd.DataFrame,
    employees: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    alarming = cycle_counts[
        (cycle_counts["variance_value"] > config.VARIANCE_VALUE_THRESHOLD) |
        (cycle_counts["variance_pct"].abs() > config.VARIANCE_PCT_THRESHOLD * 100)
    ].copy()
    _ALERT_COLS = ["alert_id","store_id","sku_id","alert_date","alert_type",
                   "severity","trigger_value","threshold_value","count_id","status","assigned_to"]
    if alarming.empty:
        return pd.DataFrame(columns=_ALERT_COLS)

    all_emp = employees[employees["role"].isin(["manager", "analyst"])]["employee_id"].values
    if len(all_emp) == 0:
        all_emp = employees["employee_id"].values

    rows = []
    for i, (_, row) in enumerate(alarming.iterrows()):
        vv  = float(row["variance_value"])
        vp  = abs(float(row["variance_pct"]))
        if vv > 5_000 or vp > 30:
            sev = "critical"
        elif vv > 1_000 or vp > 15:
            sev = "high"
        elif vv > 500 or vp > 10:
            sev = "medium"
        else:
            sev = "low"

        rows.append({
            "alert_id":       ids.shrinkage_id(i + 1),
            "store_id":       row["store_id"],
            "sku_id":         row["sku_id"],
            "alert_date":     row["count_datetime"][:10],
            "alert_type":     "cycle_count_variance",
            "severity":       sev,
            "trigger_value":  vv,
            "threshold_value":config.VARIANCE_VALUE_THRESHOLD,
            "count_id":       row["count_id"],
            "status":         rng.choice(config.ALERT_STATUSES,
                                         p=[0.30, 0.30, 0.35, 0.05]),
            "assigned_to":    rng.choice(all_emp),
        })
    return pd.DataFrame(rows)


# ─── Section 8: Investigations ────────────────────────────────────────────────

def generate_investigations(
    alerts: pd.DataFrame,
    employees: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    _INV_COLS = ["inv_id","alert_id","store_id","opened_date","closed_date",
                 "assigned_to","finding","resolution","is_confirmed_theft","financial_impact"]
    if alerts.empty:
        return pd.DataFrame(columns=_INV_COLS)

    hi = alerts[alerts["severity"].isin(["high", "critical"])].copy()
    if hi.empty:
        return pd.DataFrame(columns=_INV_COLS)

    all_emp = employees[employees["role"].isin(["manager", "security", "analyst"])
                        ]["employee_id"].values
    if len(all_emp) == 0:
        all_emp = employees["employee_id"].values

    rows = []
    for i, (_, row) in enumerate(hi.iterrows()):
        open_date  = date.fromisoformat(row["alert_date"])
        close_date = None
        finding    = None
        resolution = None
        is_theft   = False
        impact     = round(float(row["trigger_value"]), 2)

        if rng.random() < 0.70:   # 70 % closed
            close_days = int(rng.integers(5, 61))
            close_date = min(
                open_date + timedelta(days=close_days),
                date.fromisoformat(config.END_DATE_STR)
            )
            finding    = rng.choice(config.INVESTIGATION_FINDINGS)
            resolution = rng.choice(config.INVESTIGATION_RESOLUTIONS)
            is_theft   = finding == "confirmed_theft"

        rows.append({
            "inv_id":            ids.investigation_id(i + 1),
            "alert_id":          row["alert_id"],
            "store_id":          row["store_id"],
            "opened_date":       open_date.isoformat(),
            "closed_date":       close_date.isoformat() if close_date else None,
            "assigned_to":       rng.choice(all_emp),
            "finding":           finding,
            "resolution":        resolution,
            "is_confirmed_theft":is_theft,
            "financial_impact":  impact,
        })
    return pd.DataFrame(rows)


# ─── Section 9: Edge-case injection ──────────────────────────────────────────

def inject_edge_cases(
    movements: pd.DataFrame,
    cycle_counts: pd.DataFrame,
    store_sku: pd.DataFrame,
    rng: np.random.Generator,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Returns (movements, cycle_counts, ground_truth).
    Injects 4 types of labelled anomalies from the spec.
    """
    gt_rows: List[dict] = []
    mov_df  = movements.copy()
    cnt_df  = cycle_counts.copy()

    all_store_ids = mov_df["store_id"].unique()
    all_sku_ids   = mov_df["sku_id"].unique()

    # EC-001 – movement references a store that does not own the SKU
    ec1_idx = rng.choice(mov_df.index, config.N_EC_WRONG_STORE, replace=False)
    for idx in ec1_idx:
        original_store = mov_df.at[idx, "store_id"]
        wrong_stores   = [s for s in all_store_ids if s != original_store]
        if not wrong_stores:
            continue
        wrong_store = rng.choice(wrong_stores)
        mov_df.at[idx, "store_id"]   = wrong_store
        mov_df.at[idx, "is_anomaly"] = True
        mov_df.at[idx, "anomaly_type"] = "wrong_store_reference"
        gt_rows.append({
            "anomaly_id":       f"GT-EC001-{idx}",
            "entity_type":      "InventoryMovement",
            "entity_id":        mov_df.at[idx, "movement_id"],
            "anomaly_type":     "wrong_store_reference",
            "description":      f"Movement store changed from {original_store} to {wrong_store}",
            "original_store":   original_store,
            "expected_decision":"flag and reject",
        })

    # EC-002 – adjustment missing reason
    adj_mask = mov_df["movement_type"] == "adjustment"
    adj_idx  = mov_df.index[adj_mask].tolist()
    if len(adj_idx) > config.N_EC_ADJUSTMENT_NO_REASON:
        ec2_idx = rng.choice(adj_idx, config.N_EC_ADJUSTMENT_NO_REASON, replace=False)
        for idx in ec2_idx:
            mov_df.at[idx, "reason"]      = None
            mov_df.at[idx, "is_anomaly"]  = True
            mov_df.at[idx, "anomaly_type"]= "adjustment_missing_reason"
            gt_rows.append({
                "anomaly_id":       f"GT-EC002-{idx}",
                "entity_type":      "InventoryMovement",
                "entity_id":        mov_df.at[idx, "movement_id"],
                "anomaly_type":     "adjustment_missing_reason",
                "description":      "Adjustment movement has null reason",
                "original_store":   mov_df.at[idx, "store_id"],
                "expected_decision":"flag for manual review",
            })

    # EC-003 – cycle count timestamp precedes the last movement for that store-sku
    last_mov_ts = (
        mov_df.groupby(["store_id", "sku_id"])["timestamp"].max().reset_index()
        .rename(columns={"timestamp": "last_mov_ts"})
    )
    cnt_merged = cnt_df.merge(last_mov_ts, on=["store_id", "sku_id"], how="left")
    valid_cnt  = cnt_merged[cnt_merged["last_mov_ts"].notna()].index.tolist()

    n_ec3 = min(config.N_EC_COUNT_PRECEDES_MOVEMENT, len(valid_cnt))
    ec3_idx = rng.choice(valid_cnt, n_ec3, replace=False)
    for idx in ec3_idx:
        store_id_  = cnt_df.at[idx, "store_id"]
        sku_id_    = cnt_df.at[idx, "sku_id"]
        last_ts    = cnt_merged.at[idx, "last_mov_ts"]
        # push count_datetime to BEFORE the last movement
        new_ts = (pd.to_datetime(last_ts) - timedelta(hours=int(rng.integers(1, 25)))
                  ).strftime("%Y-%m-%dT%H:%M:%S")
        cnt_df.at[idx, "count_datetime"] = new_ts
        gt_rows.append({
            "anomaly_id":       f"GT-EC003-{idx}",
            "entity_type":      "CycleCount",
            "entity_id":        cnt_df.at[idx, "count_id"],
            "anomaly_type":     "count_precedes_movement",
            "description":      f"count_datetime {new_ts} precedes last movement {last_ts}",
            "original_store":   store_id_,
            "expected_decision":"flag ordering violation",
        })

    # EC-004 – transfer recorded as shrinkage at both ends
    transfer_outs = mov_df[mov_df["movement_type"] == "transfer_out"].head(
        config.N_EC_TRANSFER_DOUBLE_SHRINKAGE * 2
    )
    for i, (tidx, trow) in enumerate(transfer_outs.iterrows()):
        if i >= config.N_EC_TRANSFER_DOUBLE_SHRINKAGE:
            break
        # duplicate movement as shrinkage on destination store
        new_row = trow.copy()
        new_row["movement_id"]   = ids.movement_id(len(mov_df) + i + 1)
        new_row["movement_type"] = "shrinkage"
        new_row["reason"]        = "unknown_loss"
        new_row["is_anomaly"]    = True
        new_row["anomaly_type"]  = "transfer_double_shrinkage"
        # pick a different store as destination
        other_stores = [s for s in all_store_ids if s != trow["store_id"]]
        if other_stores:
            new_row["store_id"] = rng.choice(other_stores)
        mov_df = pd.concat([mov_df, pd.DataFrame([new_row])], ignore_index=True)

        mov_df.at[tidx, "is_anomaly"]   = True
        mov_df.at[tidx, "anomaly_type"] = "transfer_double_shrinkage"
        gt_rows.append({
            "anomaly_id":       f"GT-EC004-{i}",
            "entity_type":      "InventoryMovement",
            "entity_id":        trow["movement_id"],
            "anomaly_type":     "transfer_double_shrinkage",
            "description":      "Transfer recorded as shrinkage at source; duplicate shrinkage injected at destination",
            "original_store":   trow["store_id"],
            "expected_decision":"reconcile transfer pair; reject duplicate shrinkage",
        })

    ground_truth = pd.DataFrame(gt_rows)
    return mov_df, cnt_df, ground_truth


# ─── Section 10: Export ───────────────────────────────────────────────────────

def export_tables(tables: Dict[str, pd.DataFrame], data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    csv_dir  = data_dir / "csv"
    json_dir = data_dir / "json"
    sql_dir  = data_dir / "sql"
    for d in (csv_dir, json_dir, sql_dir):
        d.mkdir(parents=True, exist_ok=True)

    manifest = {}
    for name, df in tables.items():
        csv_path = csv_dir / f"{name}.csv"
        df.to_csv(csv_path, index=False)
        manifest[name] = {
            "rows":    len(df),
            "columns": list(df.columns),
            "csv":     str(csv_path.relative_to(data_dir)),
        }
        # JSON (write line-delimited for large tables)
        json_path = json_dir / f"{name}.json"
        df.to_json(json_path, orient="records", lines=True, date_format="iso")

        # SQL INSERT seed (first 1000 rows only; full data is in CSV)
        sql_path = sql_dir / f"{name}.sql"
        _write_sql(name, df.head(1_000), sql_path)

    manifest_path = data_dir / "source_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump({"seed": config.SEED, "scale": config.SCALE,
                   "generated_at": datetime.utcnow().isoformat() + "Z",
                   "tables": manifest}, f, indent=2)
    print(f"  Manifest → {manifest_path}")


def _write_sql(table: str, df: pd.DataFrame, path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"-- {table}  (first {len(df)} rows)\n")
        cols = ", ".join(df.columns)
        for _, row in df.iterrows():
            vals = ", ".join(
                "NULL" if (v is None or (isinstance(v, float) and math.isnan(v)))
                else f"'{str(v).replace(chr(39), chr(39)*2)}'"
                for v in row
            )
            f.write(f"INSERT INTO {table} ({cols}) VALUES ({vals});\n")


# ─── Section 11: Validation summary ──────────────────────────────────────────

def validate_and_summarise(tables: Dict[str, pd.DataFrame]) -> dict:
    results: dict = {}

    movements      = tables.get("inventory_movements", pd.DataFrame())
    stores         = tables.get("stores", pd.DataFrame())
    skus           = tables.get("skus", pd.DataFrame())
    employees      = tables.get("employees", pd.DataFrame())
    cycle_counts   = tables.get("cycle_counts", pd.DataFrame())
    alerts         = tables.get("shrinkage_alerts", pd.DataFrame())

    # PK uniqueness
    for name, df in tables.items():
        pk_col = {
            "stores":               "store_id",
            "skus":                 "sku_id",
            "employees":            "employee_id",
            "shifts":               "shift_id",
            "promotions":           "promo_id",
            "inventory_movements":  "movement_id",
            "cycle_counts":         "count_id",
            "returns":              "return_id",
            "shrinkage_alerts":     "alert_id",
            "investigations":       "inv_id",
        }.get(name)
        if pk_col and pk_col in df.columns:
            dupes = df[pk_col].duplicated().sum()
            results[f"{name}.{pk_col}.unique"] = "PASS" if dupes == 0 else f"FAIL ({dupes} dupes)"

    # FK: movements.store_id ∈ stores.store_id
    if not movements.empty and not stores.empty:
        valid_stores = set(stores["store_id"])
        bad = (~movements["store_id"].isin(valid_stores) & ~movements["is_anomaly"]).sum()
        results["movements.store_id.fk"] = "PASS" if bad == 0 else f"FAIL ({bad} bad FKs)"

    # FK: movements.sku_id ∈ skus.sku_id
    if not movements.empty and not skus.empty:
        valid_skus = set(skus["sku_id"])
        bad = (~movements["sku_id"].isin(valid_skus)).sum()
        results["movements.sku_id.fk"] = "PASS" if bad == 0 else f"FAIL ({bad} bad FKs)"

    # Derived: total_value = abs(quantity) * unit_cost
    if not movements.empty:
        computed = (movements["quantity"].abs() * movements["unit_cost"]).round(2)
        mismatch = (computed - movements["total_value"]).abs() > 0.01
        results["movements.total_value.derived"] = (
            "PASS" if mismatch.sum() == 0 else f"FAIL ({mismatch.sum()} mismatches)"
        )

    # Cycle count variance derived correctly
    if not cycle_counts.empty:
        computed_var = cycle_counts["actual_qty"] - cycle_counts["expected_qty"]
        bad = (computed_var != cycle_counts["variance"]).sum()
        results["cycle_counts.variance.derived"] = "PASS" if bad == 0 else f"FAIL ({bad})"

    # Enum checks
    valid_mv_types = {"receipt","sale","transfer_in","transfer_out","adjustment","return","shrinkage"}
    if not movements.empty:
        bad = (~movements["movement_type"].isin(valid_mv_types)).sum()
        results["movements.movement_type.enum"] = "PASS" if bad == 0 else f"FAIL ({bad})"

    # Date ordering: adjustment records should have timestamps within date window
    start_ts = config.START_DATE_STR + "T00:00:00"
    end_ts   = config.END_DATE_STR   + "T23:59:59"
    if not movements.empty:
        bad = ((movements["timestamp"] < start_ts) | (movements["timestamp"] > end_ts)).sum()
        results["movements.timestamp.range"] = "PASS" if bad == 0 else f"FAIL ({bad})"

    # Adjustment missing reason count (should match EC-002 exactly)
    if not movements.empty:
        adj_null = (
            (movements["movement_type"] == "adjustment") &
            movements["reason"].isna()
        ).sum()
        results["adjustments_with_null_reason"] = int(adj_null)

    # Row counts
    for name, df in tables.items():
        results[f"row_count.{name}"] = len(df)

    return results


# ─── Orchestrator ─────────────────────────────────────────────────────────────

def run(scale: float = None) -> Dict[str, pd.DataFrame]:
    if scale is not None:
        config.SCALE = scale

    n_stores   = int(config.N_STORES   * config.SCALE)
    n_skus     = int(config.N_SKUS     * config.SCALE)
    n_moves    = int(config.TARGET_MOVEMENTS * config.SCALE)
    n_counts   = int(config.N_CYCLE_COUNTS   * config.SCALE)

    # Override module constants for this run
    _orig = (config.N_STORES, config.N_SKUS, config.TARGET_MOVEMENTS, config.N_CYCLE_COUNTS)
    config.N_STORES, config.N_SKUS, config.TARGET_MOVEMENTS, config.N_CYCLE_COUNTS = (
        n_stores, n_skus, n_moves, n_counts
    )

    rng  = np.random.default_rng(config.SEED)
    fake = Faker("en_US")
    Faker.seed(config.SEED)

    t0 = time.time()

    print("[1/10] Stores …")
    stores = generate_stores(rng, fake)
    print(f"       {len(stores)} stores")

    print("[2/10] SKUs …")
    skus = generate_skus(rng, fake)
    print(f"       {len(skus)} SKUs")

    print("[3/10] Employees …")
    employees = generate_employees(stores, rng, fake)
    print(f"       {len(employees)} employees")

    print("[4/10] Shifts …")
    target_shifts = int(200_000 * config.SCALE)
    shifts = generate_shifts(employees, rng, target=target_shifts)
    print(f"       {len(shifts)} shifts")

    print("[5/10] Promotions …")
    promotions = generate_promotions(skus, stores, rng)
    print(f"       {len(promotions)} promotions")

    print("[6/10] Store-SKU mapping …")
    store_sku = build_store_sku_map(stores, skus, rng)
    print(f"       {len(store_sku)} store-SKU pairs")

    print("[7/10] Inventory movements …")
    opening, ctr = generate_opening_balances(store_sku, employees, shifts, rng)
    print(f"       Opening balances: {len(opening)}")
    n_ops = max(0, n_moves - len(opening))
    ops, ctr = generate_operational_movements(store_sku, employees, shifts, rng, n_ops, ctr)
    print(f"       Operational: {len(ops)}")
    movements = combine_movements(opening, ops)
    print(f"       Total movements (pre-reconciliation): {len(movements)}")
    movements = reconcile_stock_equation(movements, store_sku, employees, rng)
    neg_fixed = (movements["reason"] == "stock_reconciliation").sum()
    print(f"       Correction receipts added: {neg_fixed}")
    print(f"       Total movements: {len(movements)}")

    print("[8/10] Cycle counts …")
    cycle_counts = generate_cycle_counts(store_sku, movements, employees, rng)
    print(f"       {len(cycle_counts)} cycle counts")

    print("[8b] Returns …")
    returns = generate_returns(movements, employees, rng)
    print(f"       {len(returns)} returns")

    print("[8c] Shrinkage alerts …")
    alerts = generate_shrinkage_alerts(cycle_counts, employees, rng)
    print(f"       {len(alerts)} alerts")

    print("[8d] Investigations …")
    investigations = generate_investigations(alerts, employees, rng)
    print(f"       {len(investigations)} investigations")

    print("[9/10] Injecting edge cases …")
    movements, cycle_counts, ground_truth = inject_edge_cases(
        movements, cycle_counts, store_sku, rng
    )
    print(f"       {len(ground_truth)} labelled anomalies")
    # EC-001 (store_id swap) and EC-004 (extra shrinkage) can re-introduce
    # negative balances, so reconcile once more after injection.
    movements = reconcile_stock_equation(movements, store_sku, employees, rng)

    print("[10/10] Exporting …")
    tables = {
        "stores":              stores,
        "skus":                skus,
        "employees":           employees,
        "shifts":              shifts,
        "promotions":          promotions,
        "store_sku_map":       store_sku,   # M:N bridge table (spec §Entities)
        "inventory_movements": movements,
        "cycle_counts":        cycle_counts,
        "returns":             returns,
        "shrinkage_alerts":    alerts,
        "investigations":      investigations,
        "ground_truth":        ground_truth,
    }
    export_tables(tables, config.DATA_DIR)

    print("\nValidation …")
    results = validate_and_summarise(tables)
    summary_path = config.DATA_DIR / "validation_summary.json"
    with open(summary_path, "w") as f:
        json.dump(results, f, indent=2)
    fails = {k: v for k, v in results.items() if str(v).startswith("FAIL")}
    if fails:
        print("  ⚠ Validation failures:")
        for k, v in fails.items():
            print(f"    {k}: {v}")
    else:
        print("  All validation checks passed.")
    print(f"  Summary → {summary_path}")

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.1f}s")

    # Restore originals
    config.N_STORES, config.N_SKUS, config.TARGET_MOVEMENTS, config.N_CYCLE_COUNTS = _orig

    return tables
