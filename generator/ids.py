"""Deterministic ID builders matching the project nomenclature spec."""

YEAR = 2026


def store_id(n: int) -> str:
    return f"STORE-{n:06d}"


def sku_id(n: int) -> str:
    return f"SKU-{n:06d}"


def employee_id(n: int) -> str:
    return f"EMP-{n:06d}"


def shift_id(n: int, year: int = YEAR) -> str:
    return f"SHF-{year}-{n:06d}"


def promotion_id(n: int, year: int = YEAR) -> str:
    return f"PRM-{year}-{n:06d}"


def movement_id(n: int, year: int = YEAR) -> str:
    return f"MOV-{year}-{n:08d}"


def count_id(n: int, year: int = YEAR) -> str:
    return f"CNT-{year}-{n:06d}"


def return_id(n: int, year: int = YEAR) -> str:
    return f"RET-{year}-{n:06d}"


def shrinkage_id(n: int, year: int = YEAR) -> str:
    return f"SHR-{year}-{n:06d}"


def investigation_id(n: int, year: int = YEAR) -> str:
    return f"INV-{year}-{n:06d}"


def vectorized_movement_ids(start: int, count: int, year: int = YEAR):
    """Return a list of movement IDs [start, start+count)."""
    return [movement_id(i, year) for i in range(start, start + count)]
