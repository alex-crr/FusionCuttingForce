"""Extra checks for the model. Run: python test_cutting_force.py
(cutting_force.py and report.py also self-test via their __main__.)"""
from cutting_force import CutInputs, estimate
import materials
import report


def test_slot_vs_finish_force_ordering():
    # Slotting (ae=D) should pull far harder than a light radial finish pass.
    slot = estimate(CutInputs(10, 4, 0.05, 10, 5, 850, 0.23, spindle_rpm=8000))
    fin = estimate(CutInputs(10, 4, 0.05, 0.5, 5, 850, 0.23, spindle_rpm=8000))
    assert slot.tangential_N > fin.tangential_N * 3


def test_thinner_chip_raises_kc():
    # Kienzle: smaller fz -> thinner chip -> higher specific force.
    a = estimate(CutInputs(10, 4, 0.10, 5, 3, 850, 0.23))
    b = estimate(CutInputs(10, 4, 0.02, 5, 3, 850, 0.23))
    assert b.specific_force > a.specific_force


def test_steel_harder_than_alu():
    alu = estimate(CutInputs(10, 4, 0.05, 5, 3, kc11=850, mc=0.23))
    steel = estimate(CutInputs(10, 4, 0.05, 5, 3, kc11=2000, mc=0.26))
    assert steel.tangential_N > 2 * alu.tangential_N


def test_components_and_resultant():
    r = estimate(CutInputs(10, 4, 0.05, 5, 3, kc11=850, mc=0.23))
    assert r.radial_N > 0 and r.axial_N > 0
    # 3D resultant strictly exceeds the largest single component
    assert r.resultant_N > max(r.tangential_N, r.radial_N, r.axial_N)


def test_rake_band_lowers_force_with_more_rake():
    # higher rake range -> band shifts forces down
    low = estimate(CutInputs(10, 4, 0.05, 5, 3, kc11=850, mc=0.23,
                             rake_min_deg=0, rake_max_deg=6))
    high = estimate(CutInputs(10, 4, 0.05, 5, 3, kc11=850, mc=0.23,
                              rake_min_deg=14, rake_max_deg=20))
    assert high.band_hi < low.band_hi
    assert low.band_lo <= low.band_hi and high.band_lo <= high.band_hi


def test_material_db_shape():
    assert materials.DEFAULT_KEY in materials.MATERIALS
    for k, m in materials.MATERIALS.items():
        assert m["kc11"] > 0 and 0 < m["mc"] < 0.4, k
        assert m["rake_min"] <= m["rake_max"], k


def test_payload_groups_and_flags():
    rows = []
    for k, m in materials.MATERIALS.items():
        i = CutInputs(10, 4, 0.05, 5, 3, m["kc11"], m["mc"], spindle_rpm=8000)
        rows.append((k, i, estimate(i), False, False))
    sp = report.setup_payload("S", rows)
    assert len(sp["ops"]) == len(rows)
    assert 0 <= sp["worst"] < len(rows)
    # worst op really is the max resultant
    assert sp["ops"][sp["worst"]]["fres_nom"] == max(o["fres_nom"] for o in sp["ops"])


def test_payload_marks_estimated():
    i = CutInputs(10, 4, 0.05, 5, 3, 850, 0.23, spindle_rpm=8000)
    sp = report.setup_payload("S", [("finish", i, estimate(i), True, True)])
    assert sp["ops"][0]["ae_est"] and sp["ops"][0]["ap_est"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("all tests passed")
