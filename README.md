# Inventory Shrinkage Synthetic Data Generator

Detect unusual inventory loss by comparing receipts, sales, transfers, adjustments,
returns and counts.

## Business Context

Retail shrinkage costs the industry an estimated 1–2 % of revenue annually.  
This project generates a fully-labelled synthetic dataset that mirrors real  
retail inventory workflows so that anomaly-detection models, dashboards, and  
audit workflows can be built and evaluated end-to-end.

## Entities

| Entity | ID format | Description |
|--------|-----------|-------------|
| Store | `STORE-000001` | Physical retail location |
| SKU | `SKU-000001` | Stock-keeping unit (product) |
| EmployeeRole | `EMP-000001` | Employee + role at a store |
| Shift | `SHF-2026-000001` | Work period for an employee |
| Promotion | `PRM-2026-000001` | Price promotion on a SKU |
| InventoryMovement | `MOV-2026-00000001` | Any stock-level event |
| CycleCount | `CNT-2026-000001` | Physical inventory count |
| Return | `RET-2026-000001` | Customer/vendor return |
| ShrinkageAlert | `SHR-2026-000001` | Auto-generated loss alert |
| Investigation | `INV-2026-000001` | Formal investigation of an alert |

## Data Volumes (full scale)

| Table | Rows |
|-------|------|
| stores | 100 |
| skus | 5 000 |
| employees | ~5 500 |
| shifts | ~200 000 |
| promotions | ~2 000 |
| inventory_movements | ~1 000 000 |
| cycle_counts | 20 000 |
| returns | ~20 000 |
| shrinkage_alerts | varies |
| investigations | varies |
| ground_truth | ~38 labelled anomalies |

## Injected Edge Cases

| Code | Type | Count |
|------|------|-------|
| EC-001 | Movement references wrong store | 10 |
| EC-002 | Adjustment with null reason | 15 |
| EC-003 | Cycle count timestamp before last movement | 8 |
| EC-004 | Transfer double-counted as shrinkage | 5 |

Ground-truth labels are exported to `data/csv/ground_truth.csv` and  
**never** leak into the main feature tables.

## Setup & Run

### Prerequisites

| Requirement | Version | Check |
|-------------|---------|-------|
| Python | 3.10 or later (3.12 recommended) | `python --version` |
| pip | bundled with Python | `pip --version` |
| Git | any recent version | `git --version` |

> **Windows users:** If Python is not on your PATH after installation, run  
> `winget install Python.Python.3.12` from an elevated terminal and restart your shell.

---

### Step 1 — Clone the repository

```bash
git clone https://github.com/<your-username>/inventory-shrinkage-detector.git
cd inventory-shrinkage-detector
```

---

### Step 2 — Create a virtual environment (recommended)

```bash
# macOS / Linux
python -m venv .venv
source .venv/bin/activate

# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1

# Windows (Command Prompt)
python -m venv .venv
.venv\Scripts\activate.bat
```

---

### Step 3 — Install dependencies

```bash
pip install -r requirements.txt
```

This installs: `numpy`, `pandas`, `faker`, `pyyaml`, `tqdm`, `pytest`,
`streamlit`, and `plotly`.

---

### Step 4 — Generate the dataset

**Starter dataset** (~10 000 movements, finishes in under 1 minute — good for a first look):

```bash
python scripts/generate.py --scale 0.01
```

**Full dataset** (~1 million movements, takes 10–20 minutes):

```bash
python scripts/generate.py
```

Both commands write output to `data/csv/`, `data/json/`, `data/sql/` and print
a progress log:

```
[1/10] Stores … 100 stores
[2/10] SKUs … 5000 SKUs
[3/10] Employees … 5482 employees
...
[10/10] Exporting …
Done in 743.2 s
```

---

### Step 5 — Validate the generated data

```bash
python scripts/validate.py
```

Runs 40+ checks (PK uniqueness, FK integrity, stock equation, alert evidence,
lifecycle transitions, etc.) and prints a PASS/FAIL summary:

```
Results: 44 passed, 0 failed
All checks passed.
```

---

### Step 6 — Launch the actor-based dashboard

```bash
streamlit run scripts/dashboard.py
```

Opens at **http://localhost:8501** with four tabs — one per primary actor:

| Tab | Actor | Key metrics |
|-----|-------|-------------|
| 1 | **Customer** | Returns experience, refund stats, active promotions |
| 2 | **Store / Warehouse Operator** | Movement breakdown, cycle count variances, open alerts |
| 3 | **Merchandising / Analyst** | Sales by category, shrinkage ratio, top-loss SKUs |
| 4 | **Operations Manager** | Investigation status, severity KPIs, ground-truth anomaly labels |

Use the **Store** dropdown in the sidebar to filter all tabs to a single store.

> The dashboard reads from `data/csv/`. Generate data first (Step 4) before launching.

---

### Step 7 — Run the test suite

```bash
# Full suite — runs at 5 % scale, completes in ~30 seconds
pytest tests/ -v

# One test class only
pytest tests/test_data_quality.py::TestDerivedValues -v

# Fast smoke test (1 % scale)
pytest tests/test_data_quality.py::TestReproducibility -v
```

Expected output: **49 passed**.

---

### Step 8 — Prove reproducibility

```bash
python scripts/reproduce.py --scale 0.01
```

Runs the generator twice with the same seed and compares SHA-256 checksums of
all CSV files. Every file must match byte-for-byte:

```
Run 1 complete (12 files)
Run 2 complete (12 files)
Comparing checksums …
  ✓ stores.csv
  ✓ inventory_movements.csv
  ...
All 12 files are byte-identical across two runs.
```

---

### Output Layout

```
data/
├── csv/
│   ├── stores.csv
│   ├── skus.csv
│   ├── employees.csv
│   ├── shifts.csv
│   ├── promotions.csv
│   ├── store_sku_map.csv        ← M:N bridge table
│   ├── inventory_movements.csv
│   ├── cycle_counts.csv
│   ├── returns.csv
│   ├── shrinkage_alerts.csv
│   ├── investigations.csv
│   └── ground_truth.csv         ← anomaly labels (never join into features)
├── json/                        ← line-delimited JSON (one per entity)
├── sql/                         ← SQL INSERT seed (first 1 000 rows each)
├── source_manifest.json         ← row counts, columns, seed, timestamp
└── validation_summary.json      ← all check results as key:value
```

---

### Troubleshooting

| Symptom | Fix |
|---------|-----|
| `python: command not found` | Use `python3` instead, or add Python to PATH |
| `ModuleNotFoundError: No module named 'faker'` | Run `pip install -r requirements.txt` inside your virtual environment |
| `streamlit: command not found` | Activate your virtual environment first |
| Dashboard shows "No data found" | Generate data first: `python scripts/generate.py --scale 0.01` |
| `pytest` reports import errors | Run from the repo root, not from inside `tests/` |
| Full-scale run is slow | This is expected (~10–20 min for 1 M movements). Use `--scale 0.10` for a 100 K-row dataset in 2–3 min |

## Seed & Reproducibility

Fixed seed: **20261022**  
All random choices use `numpy.random.default_rng(20261022)` and  
`Faker.seed(20261022)`.  Running `scripts/reproduce.py` confirms  
byte-identical CSV output across two independent runs.

## Schema / Data Dictionary

Full field-level documentation, cardinality, validation rules, and  
allowed values are in [`schema/data_dictionary.yaml`](schema/data_dictionary.yaml).

## Business Logic Summary

1. **Opening balances** — each store-SKU pair gets a `receipt` movement on  
   2026-01-01 with 50–500 units.
2. **Sales** (60 % of operational movements) — negative quantity; can't exceed  
   on-hand stock.
3. **Transfers** — paired `transfer_out` / `transfer_in`; same SKU, different stores;  
   linked by `reference_id`.
4. **Adjustments** (10 %) — must carry a `reason`; EC-002 injects 15 null-reason rows.
5. **Returns** (8 %) — reference original `sale` movement_id; within 30-day window.
6. **Shrinkage** (8 %) — legitimate damage/theft/expiry; plus planted anomalies.
7. **Cycle counts** — `expected_qty` derived from movement history; ~5 % have large  
   variance; alerts fired when variance > 5 % OR > $500 value impact.
8. **Investigations** — opened automatically for `high`/`critical` alerts; 70 %  
   closed with a finding.

## Validation Rules / Acceptance Criteria

| Criterion | How it is met |
|-----------|---------------|
| **Stock equation reconciles** | Per-store-SKU sum of signed quantities ≥ 0. `reconcile_stock_equation()` injects correction receipts (`reason=stock_reconciliation`) wherever a pair would go negative. |
| **Alert reasons are evidence-based** | `ShrinkageAlert` rows are only created from `CycleCount` records whose `variance_value > $500` OR `variance_pct > 5 %`. Validated in `scripts/validate.py` and `tests/`. |
| **Planted patterns can be evaluated** | Four EC types in `ground_truth.csv` with `expected_decision` labels. Ground truth is never joined into feature tables. |
| **Benign explanations represented** | ~8 % of movements are legitimate returns; ~10 % are adjustments; damage/expiry reasons (`damaged_goods`, `expired_product`) appear in both adjustments and shrinkage. |

## Evaluation Focus Checklist

- [x] **(a)** Realistic distributions — all regions, formats, roles, categories present; meaningful variance in cycle counts
- [x] **(b)** Consistent IDs and valid joins — all FK checks pass; ID format validated by regex
- [x] **(c)** Dependency/lifecycle consistency — every store-SKU starts with a receipt; return references original sale; investigation references alert
- [x] **(d)** Correct derived values — `total_value`, `variance`, `variance_pct`, `variance_value` all derived, not independently generated
- [x] **(e)** Normal, boundary, failure and exception coverage — 4 edge-case types, legitimate damage/returns, high/critical/low severity alerts
- [x] **(f)** Separate ground truth — `ground_truth.csv` holds labels; no `anomaly_type` leaks into clean rows
- [x] **(g)** Fixed-seed reproducibility — seed `20261022`; `scripts/reproduce.py` confirms byte-identical CSV output

## Tests

```bash
# Run all data-quality tests (uses 5% scale, ~30 seconds)
pytest tests/ -v

# Run a specific test class
pytest tests/test_data_quality.py::TestDerivedValues -v
```

The test suite covers all seven evaluation criteria above with 30+ assertions.

## Public Data Guidance / Lawful Use

All data in this project is **fully synthetic** — generated programmatically with
`Faker` (locale `en_US`) and `numpy`. No real persons, businesses, or transactions
are represented. No external datasets were incorporated.

| Item | Value |
|------|-------|
| External data used | None |
| Personal data | None — all names/locations are fictitious |
| License | MIT (see `LICENSE`) |
| Redistribution | Free to use, share, and modify |

## How This Project Was Built

This project was developed by **Akhil Chidella**.
Every prompt used — from initial scaffolding through compliance fixes — is documented
in [`PROMPTS.md`](PROMPTS.md) so anyone can reproduce the full project by following
the prompts in order.

## Generator Command Reference

```
python scripts/generate.py --scale SCALE
```

| `--scale` | Movements | Approx. time |
|-----------|-----------|--------------|
| 0.01 | ~10 000 | < 1 min |
| 0.10 | ~100 000 | 2–3 min |
| 1.00 | ~1 000 000 | 10–20 min |
