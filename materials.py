"""Material database loader. Reads materials.json (edit THAT to add materials).

JSON over a .py dict so non-coders can add materials without breaking the
add-in: one malformed entry is skipped, not fatal, and no code is executed.

Each entry -> {name, kc11, mc, rake_min, rake_max}. See materials.json header.
"""
import json
import os

_PATH = os.path.join(os.path.dirname(__file__), "materials.json")
DEFAULT_KEY = "al7075"


def _load() -> dict:
    with open(_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    out = {}
    for key, m in raw.items():
        if key.startswith("_"):
            continue  # skip _comment etc.
        try:
            entry = {
                "name": str(m["name"]),
                "kc11": float(m["kc11"]),
                "mc": float(m["mc"]),
                "rake_min": float(m.get("rake_min", 0.0)),
                "rake_max": float(m.get("rake_max", 0.0)),
            }
        except (KeyError, ValueError, TypeError):
            continue  # one bad entry must not break the rest
        if entry["kc11"] <= 0 or not (0.0 < entry["mc"] < 0.5):
            continue
        out[key] = entry
    return out


MATERIALS = _load()
if DEFAULT_KEY not in MATERIALS and MATERIALS:
    DEFAULT_KEY = next(iter(MATERIALS))


def get(key: str) -> dict:
    return MATERIALS.get(key, MATERIALS[DEFAULT_KEY])


if __name__ == "__main__":
    assert MATERIALS, "no materials loaded"
    assert DEFAULT_KEY in MATERIALS
    print(f"materials OK: {len(MATERIALS)} loaded, default={DEFAULT_KEY}")
