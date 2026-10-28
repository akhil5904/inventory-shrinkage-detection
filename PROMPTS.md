# Claude Prompt History

This file documents every Claude prompt used to build this project, in order.
Anyone can reproduce the full project by sending these prompts to **Claude Sonnet 4.6** (or later)
inside **Claude Code** with a Python 3.12 environment available.

---

## Prompt 1 — Initial project generation

```
Build a working end-to-end solution for the following business problem:

**Business Context / Problem**
Detect unusual inventory loss by comparing receipts, sales, transfers,
adjustments, returns and counts.

**Objective and Scope**
Build a working solution for this end-to-end workflow: Detect unusual inventory
loss by comparing receipts, sales, transfers, adjustments, returns and counts.
The solution should expose key decisions and exceptions, preserve traceability,
and produce measurable outputs. Medium complexity means multiple related
entities, conditional rules, at least one exception path and meaningful
evaluation metrics.

**Primary Actors / Systems**
Customer, store/warehouse operator, merchandising/e-commerce analyst and
operations manager

**Business Workflow and Rules**
1. Generate/reference master data first: Store, SKU, InventoryMovement,
   CycleCount, EmployeeRole.
2. Generate dependent transaction/event records using valid parent IDs.
3. Apply business logic: Create store/SKU opening balances; generate sales and
   movement events; create cycle counts and variances; link movements to
   authorized users/roles and shifts; inject selected patterns such as repeated
   adjustments or unexplained losses; create alerts with ground-truth labels.
4. Persist state changes as explicit records/events where relevant; do not
   overwrite history.
5. Generate outcomes and ground-truth labels from documented rules, not
   independent random assignment.

**Entities and Relationships**
Core entities: Store, SKU, InventoryMovement, CycleCount, EmployeeRole, Shift,
Promotion, Return, ShrinkageAlert, Investigation. Define a primary key for
every entity and foreign keys for every relationship. Document cardinality
(1:1, 1:N, N:M), optional relationships, effective dates and lifecycle states.
Use bridge tables for many-to-many relationships; retain event history for
state changes; validate all joins. For deliberate anomaly cases, keep an
issue_type/ground_truth label rather than silently corrupting unrelated rows.

**ID / Nomenclature Conventions**
STORE-000001; SKU-000001; MOV-2026-00000001; CNT-2026-000001;
SHR-2026-000001; INV-2026-000001.

**Synthetic Data Generation Instructions (Granular)**
Step 1 — Write a data dictionary for all 10 entities. For each field specify
type, required/optional, allowed values, units, uniqueness and validation rule.
Step 2 — Create parent/master tables first, then child and event tables.
Step 3 — Apply deterministic IDs: STORE-000001; SKU-000001; MOV-2026-00000001;
CNT-2026-000001; SHR-2026-000001; INV-2026-000001. Keep counters zero-padded,
IDs immutable, referenced IDs consistent across files.
Step 4 — Generate baseline volume: 100 stores, 5,000 SKUs, 1 million movements
and 20,000 cycle counts. Fixed seed 20261022. Parameterize scale so starter
and full datasets use the same generator.
Step 5 — Inject labelled edge cases after valid baseline:
  - Movement refers to wrong store
  - Adjustment lacks reason
  - Count timestamp precedes stock movements incorrectly
  - Transfer counted as shrinkage at both ends
Step 6 — Calculate derived values (totals, balances, scores, statuses, dates)
from source records rather than generating them independently.
Step 7 — Produce a separate ground_truth.csv/json for known anomalies and
expected decisions; never leak it into input features.
Step 8 — Run validation: primary-key uniqueness, foreign-key integrity, allowed
enums, date ordering, arithmetic reconciliation, lifecycle transitions and
duplicate checks.
Step 9 — Export CSV/JSON/SQL seed data plus README, schema/data dictionary,
generator command, fixed seed, source manifest and validation summary.
Step 10 — Regenerate twice with the same seed and compare row counts/checksums
to demonstrate reproducibility.

**Suggested Volume**
100 stores, 5,000 SKUs, 1 million movements, 20,000 cycle counts.
Include legitimate damage/returns and planted anomalies.

**Required Edge Cases**
Movement refers to wrong store; adjustment lacks reason; count timestamp
precedes stock movements incorrectly; transfer counted as shrinkage at both
ends.

**Validation Rules / Acceptance Criteria**
Stock equation reconciles; alert reasons are evidence-based; planted patterns
can be evaluated; benign explanations are represented.

**Technology Stack**
Python 3.12, numpy (vectorized generation), pandas, faker, pyyaml, tqdm.
Use numpy.random.default_rng(20261022) and Faker.seed(20261022).

Create a local git repository at C:\chasquee\repos\inventory-shrinkage-detector
and develop all code exactly as described above.
```

---

## Prompt 2 — Run the generator locally

```
Please run the generator locally so I can see it produce data.
Use scale=0.01 first for a quick smoke test, then scale=1.0 for the full
dataset.
```

---

## Prompt 3 — Actor-based interactive dashboard

```
I have four primary actors for my application:
  1. Customer
  2. Store / Warehouse Operator
  3. Merchandising / E-commerce Analyst
  4. Operations Manager

Build an interactive dashboard (Streamlit + Plotly) with one tab per actor
so I can view the generated data from each actor's perspective.

Each tab should show the metrics and charts most relevant to that actor:
- Customer: returns experience, refund stats, active promotions.
- Store/Warehouse Operator: movement breakdown, cycle count variances,
  open alerts.
- Merchandising/Analyst: sales by category, shrinkage ratio, top-loss SKUs.
- Operations Manager: investigation status, severity KPIs, store-level alerts,
  ground-truth anomaly summary.

Include a sidebar store filter that applies across all tabs.
Save as scripts/dashboard.py. Run with: streamlit run scripts/dashboard.py
```

---

## Prompt 4 — Acceptance criteria from spec (screenshot 3)

```
Please read and implement the following additional requirements:

**Validation Rules / Acceptance Criteria**
- Stock equation must reconcile: no negative on-hand balances per store-SKU.
  Implement reconcile_stock_equation() that injects correction receipts
  (reason="stock_reconciliation") wherever a store-SKU pair would go negative.
  Call it twice in run(): after combine_movements AND after inject_edge_cases,
  because EC-001/EC-004 can re-introduce negatives.
- Alert reasons must be evidence-based: ShrinkageAlert rows must only be
  created from CycleCount records whose variance_value > $500 OR
  variance_pct > 5%. Validate this in scripts/validate.py.
- Planted patterns can be evaluated: ground_truth.csv must have anomaly_type
  and expected_decision fields for all 4 EC types.
- Benign explanations are represented: legitimate damage/expiry reasons
  (damaged_goods, expired_product, receiving_error) must appear in both
  adjustments and shrinkage.

**Evaluation Focus (a)–(g) — all must be covered by tests**
(a) Realistic distributions — all regions/formats/roles/categories present;
    meaningful variance in cycle counts.
(b) Consistent IDs and valid joins — all FK checks pass; ID format validated
    by regex.
(c) Dependency/lifecycle consistency — every store-SKU starts with a receipt;
    return references original sale; investigation references alert.
(d) Correct derived values — total_value, variance, variance_pct, variance_value
    all derived, not independently generated.
(e) Normal, boundary, failure and exception coverage — 4 edge-case types,
    legitimate damage/returns, high/critical/low severity alerts.
(f) Separate ground truth — ground_truth.csv holds labels; no anomaly_type
    leaks into clean rows.
(g) Fixed-seed reproducibility — seed 20261022; scripts/reproduce.py confirms
    byte-identical CSV output.

**Tests**
Create tests/test_data_quality.py with pytest. Write one test class per
evaluation criterion (a)–(g), 30+ assertions total. Use a session-scoped
fixture that runs the generator at scale=0.05 so the full suite runs in
under 30 seconds. Two reproducibility tests use scale=0.01.

**Public Data Guidance / Lawful Use (add to README)**
All data in this project is fully synthetic — generated programmatically with
Faker (locale en_US) and numpy. No real persons, businesses, or transactions
are represented. No external datasets were incorporated.

Include a table: External data used / Personal data / License / Redistribution.

**Submission requirements**
- Push code to a public GitHub repository.
- Include MIT LICENSE file.
- Evaluation focus checklist (a)–(g) all checked in README.
```

---

## Prompt 5 — Requirement compliance audit

```
Before pushing to GitHub, read the full requirement spec below and audit the
codebase against every requirement bullet. For each item report PASS, PARTIAL
or FAIL with a one-line explanation. Group results by section. At the end,
list all FAIL and PARTIAL items as a prioritized fix list with specific
file:line references.

[Full requirement spec as provided in the project brief]
```

---

## Prompt 6 — Fix all compliance gaps

```
Fix all 4 compliance gaps identified in the audit, then push to GitHub:

P1 — Cardinality not documented:
  Add explicit cardinality labels (1:N, N:M) and a StoreSkuMap entity
  description to schema/data_dictionary.yaml.

P2 — Store-SKU bridge table not exported:
  Add "store_sku_map": store_sku to the tables dict in run() (generator/main.py)
  so it is exported as CSV/JSON/SQL. Update load_tables() in scripts/validate.py
  to include it.

P3 — validate.py missing lifecycle checks:
  Add two checks that were pytest-only:
    - investigations.closed_date >= opened_date
    - returns.original_movement_id ∈ sale movements

P4 — shift_id always None on movements:
  The spec says "link movements to authorized users/roles and shifts."
  In generate_operational_movements(), build a
  (employee_id, shift_date) → shift_id index from the shifts DataFrame
  and populate shift_id on every movement where an employee shift exists
  on that date.

Run pytest tests/ -v after all fixes to confirm 49/49 still pass.
Add pytest>=8.0.0, streamlit>=1.32.0, plotly>=5.20.0 to requirements.txt.
Commit with a descriptive message, then push to a public GitHub repository.
```

---

## Prompt 7 — Include prompt history in the project

```
I also want to include the prompt history in this project, but please write
proper prompt commands so others can reproduce what Claude generated here.
Create a PROMPTS.md file that documents every prompt used, in order, formatted
so anyone can feed them into Claude and reproduce the full project.
```

---

## How to reproduce this project from scratch

1. Open **Claude Code** (CLI or desktop app).
2. Ensure Python 3.12 is installed (`python --version`).
3. Create an empty directory and `cd` into it.
4. Send **Prompt 1** — Claude will scaffold the full repo.
5. Send **Prompt 2** — Claude will run the generator and confirm data.
6. Send **Prompt 3** — Claude will add the Streamlit dashboard.
7. Send **Prompt 4** — Claude will add acceptance-criteria code + tests.
8. Send **Prompt 5** — Claude will audit compliance.
9. Send **Prompt 6** — Claude will fix any gaps and push to GitHub.
10. Send **Prompt 7** — Claude will add this file.

**Expected final state**
- 49/49 pytest tests passing.
- `python scripts/validate.py` reports all checks PASS.
- `python scripts/reproduce.py --scale 0.01` confirms byte-identical output.
- `streamlit run scripts/dashboard.py` opens the actor-based dashboard.
- All data exported to `data/csv/`, `data/json/`, `data/sql/`.
- Public GitHub repository with MIT license.

**Developer:** Akhil Chidella  
**Seed:** 20261022  
**Python:** 3.12  
