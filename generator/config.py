from pathlib import Path

# ── Reproducibility ───────────────────────────────────────────
SEED = 20261022

# ── Scale (set SCALE < 1.0 for a fast "starter" run) ─────────
SCALE = 1.0

# ── Volume targets (full scale) ───────────────────────────────
N_STORES        = 100
N_SKUS          = 5_000
TARGET_MOVEMENTS = 1_000_000
N_CYCLE_COUNTS  = 20_000

# ── Date window ───────────────────────────────────────────────
START_DATE_STR = "2026-01-01"
END_DATE_STR   = "2026-10-27"

# ── Directories ───────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent.parent
DATA_DIR   = BASE_DIR / "data"
SCHEMA_DIR = BASE_DIR / "schema"

# ── Store characteristics ─────────────────────────────────────
STORE_FORMATS         = ["grocery", "convenience", "warehouse", "specialty"]
STORE_FORMAT_WEIGHTS  = [0.40, 0.30, 0.15, 0.15]
STORE_STATUSES        = ["active", "closed", "remodeling"]
STORE_STATUS_WEIGHTS  = [0.90, 0.05, 0.05]
STORE_REGIONS         = ["Northeast", "Southeast", "Midwest", "Southwest", "West"]

US_TIMEZONES = {
    "Northeast": "America/New_York",
    "Southeast": "America/New_York",
    "Midwest":   "America/Chicago",
    "Southwest": "America/Denver",
    "West":      "America/Los_Angeles",
}

# ── SKU categories ────────────────────────────────────────────
SKU_CATEGORIES = {
    "Food & Beverage": {
        "subcategories":   ["Dairy", "Bakery", "Produce", "Meat", "Frozen", "Beverages"],
        "weight":          0.30,
        "price_lo":        0.50,
        "price_hi":        25.00,
        "margin":          0.35,
        "is_high_value":   False,
        "age_verify":      False,
        "shelf_life_days": 21,
    },
    "Health & Beauty": {
        "subcategories":   ["Skincare", "Hair Care", "Vitamins", "OTC Medicine"],
        "weight":          0.20,
        "price_lo":        3.00,
        "price_hi":        80.00,
        "margin":          0.45,
        "is_high_value":   False,
        "age_verify":      False,
        "shelf_life_days": 730,
    },
    "Electronics": {
        "subcategories":   ["Mobile Accessories", "Computing", "Audio", "Gaming"],
        "weight":          0.15,
        "price_lo":        10.00,
        "price_hi":        500.00,
        "margin":          0.25,
        "is_high_value":   True,
        "age_verify":      False,
        "shelf_life_days": None,
    },
    "Home & Garden": {
        "subcategories":   ["Cleaning", "Kitchen", "Garden", "Tools"],
        "weight":          0.15,
        "price_lo":        2.00,
        "price_hi":        100.00,
        "margin":          0.40,
        "is_high_value":   False,
        "age_verify":      False,
        "shelf_life_days": None,
    },
    "Apparel": {
        "subcategories":   ["Men", "Women", "Children", "Footwear"],
        "weight":          0.10,
        "price_lo":        5.00,
        "price_hi":        200.00,
        "margin":          0.55,
        "is_high_value":   False,
        "age_verify":      False,
        "shelf_life_days": None,
    },
    "Sporting Goods": {
        "subcategories":   ["Fitness", "Outdoor", "Team Sports"],
        "weight":          0.10,
        "price_lo":        5.00,
        "price_hi":        300.00,
        "margin":          0.40,
        "is_high_value":   False,
        "age_verify":      False,
        "shelf_life_days": None,
    },
}

# ── Employee roles ────────────────────────────────────────────
EMPLOYEE_ROLES         = ["cashier", "stocker", "manager", "security", "analyst"]
EMPLOYEE_ROLE_WEIGHTS  = [0.40, 0.30, 0.10, 0.10, 0.10]
EMPLOYEE_STATUSES      = ["active", "terminated", "on_leave"]
EMPLOYEE_STATUS_WEIGHTS= [0.85, 0.10, 0.05]

# ── Movement sub-types ────────────────────────────────────────
ADJUSTMENT_REASONS = [
    "damaged_goods", "expired_product", "receiving_error",
    "system_reconciliation", "vendor_shortage", "miscounting",
]
SHRINKAGE_TYPES = [
    "shoplifting", "employee_theft", "vendor_fraud",
    "administrative_error", "unknown_loss",
]
RETURN_REASONS = [
    "defective", "wrong_item", "changed_mind",
    "damaged_in_transit", "expired", "duplicate_order",
]
ITEM_CONDITIONS  = ["new", "opened", "damaged", "expired"]
CONDITION_WEIGHTS= [0.55, 0.25, 0.15, 0.05]

PROMOTION_TYPES = ["bogo", "percent_off", "buy_x_get_y", "clearance", "seasonal"]

# ── Alert / investigation ─────────────────────────────────────
ALERT_TYPES        = ["cycle_count_variance", "consecutive_adjustments",
                      "high_value_shrinkage", "transfer_mismatch"]
ALERT_SEVERITIES   = ["low", "medium", "high", "critical"]
ALERT_STATUSES     = ["open", "under_investigation", "resolved", "false_positive"]

INVESTIGATION_FINDINGS   = ["confirmed_theft", "administrative_error", "system_error",
                             "vendor_issue", "unresolved", "false_positive"]
INVESTIGATION_RESOLUTIONS= ["disciplinary_action", "process_improvement", "vendor_claim",
                             "system_fix", "closed_no_action", "police_report"]

# ── Thresholds ────────────────────────────────────────────────
VARIANCE_PCT_THRESHOLD   = 0.05   # 5 %
VARIANCE_VALUE_THRESHOLD = 500.00 # USD

# ── Edge-case injection counts ────────────────────────────────
N_EC_WRONG_STORE                = 10
N_EC_ADJUSTMENT_NO_REASON       = 15
N_EC_COUNT_PRECEDES_MOVEMENT    =  8
N_EC_TRANSFER_DOUBLE_SHRINKAGE  =  5
