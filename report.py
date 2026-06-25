"""Builds the JSON payload the palette renders. Pure (no Fusion imports) so it
is unit-testable. The HTML/JS lives in palette/report.html and does the drawing;
Python only ships data via palette.sendInfoToHTML('render', json).
"""
from __future__ import annotations

from cutting_force import CutInputs, CutResult


def _rng(nominal: float, r: CutResult) -> list[float]:
    """A value as [low, high] across the rake band."""
    return [nominal * r.band_lo, nominal * r.band_hi]


def op_payload(name: str, i: CutInputs, r: CutResult,
               ae_est: bool, ap_est: bool) -> dict:
    return {
        "name": name,
        "D": i.diameter_mm, "z": i.flutes, "fz": i.feed_per_tooth_mm,
        "ae": i.radial_depth_mm, "ap": i.axial_depth_mm,
        "rpm": i.spindle_rpm or 0, "stickout": i.stickout_mm or 0,
        "hm": r.mean_chip_mm, "kc": r.specific_force,
        "ft": _rng(r.tangential_N, r), "fr": r.radial_N, "fa": r.axial_N,
        "fres": _rng(r.resultant_N, r), "peak": _rng(r.peak_tooth_N, r),
        "pc": _rng(r.cutting_power_W, r), "torque": _rng(r.torque_Nm, r),
        "defl": _rng(r.deflection_um, r), "mrr": r.mrr_cm3_min,
        "fres_nom": r.resultant_N,          # ranking key for the worst op
        "ae_est": ae_est, "ap_est": ap_est,
        "warnings": r.warnings,
    }


def setup_payload(name: str, rows: list) -> dict:
    """rows = [(op_name, CutInputs, CutResult, ae_est, ap_est), ...].
    Marks the highest-demand op (max resultant force) for fixture sizing."""
    ops = [op_payload(*r) for r in rows]
    worst = max(range(len(ops)), key=lambda k: ops[k]["fres_nom"]) if ops else -1
    return {"name": name, "worst": worst, "ops": ops}


if __name__ == "__main__":
    from cutting_force import estimate
    i = CutInputs(10, 4, 0.05, 10, 2, 850, 0.23, spindle_rpm=8000,
                  rake_min_deg=12, rake_max_deg=20, stickout_mm=40)
    sp = setup_payload("Setup1", [("Slot", i, estimate(i), False, True)])
    assert sp["worst"] == 0 and sp["ops"][0]["ap_est"] is True
    assert len(sp["ops"][0]["ft"]) == 2 and sp["ops"][0]["ft"][0] < sp["ops"][0]["ft"][1]
    print("report payload self-check OK")
