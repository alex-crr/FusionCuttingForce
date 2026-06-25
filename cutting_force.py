"""Milling cutting-force estimation (Kienzle specific-force model).

Pure Python, NO Fusion dependencies -> unit-testable standalone (see __main__).
Metric units throughout.

Pipeline:
    geometry (D, ae, ap, fz, z, kr)
        -> swept engagement angle  phi
        -> mean undeformed chip thickness  hm
        -> specific cutting force  kc = kc1.1 * hm^(-mc)   (Kienzle 1952)
        -> tangential Ft, radial Fr, axial Fa, 3D resultant
        -> cutting power, spindle torque, MRR
        -> rake-angle band: forces scale with a correction factor over the
           material's typical rake range, so outputs are a range, not a
           false-precise point.

Key identity (keeps force valid even with no spindle data):
    Ft = kc * ae * ap * fz * z / (pi * D)
    -- equals the power-route force kc*MRR/(1000*vc); derivation in README.

References:
    Kienzle, O. (1952), specific cutting force kc = kc1.1 * h^(-mc).
    Koenig/Kienzle rake correction ~1% force per degree of rake.
    Sandvik Coromant, "Milling formulas and definitions".
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# Rake correction: kc1.1 table values assume this reference rake; force changes
# ~1% per degree away from it. ponytail: linear approx (real 1-1.5%/deg); the
# whole point of the band is that we don't pretend to know it exactly.
REFERENCE_RAKE_DEG = 6.0
RAKE_FORCE_SLOPE = 0.01

# Deflection: end-mill flutes remove material, so the section bending the tool is
# weaker than a solid bar -> effective diameter ~0.8*D (Harvey/Kennametal rule).
EFFECTIVE_DIA_FACTOR = 0.8


@dataclass
class CutInputs:
    diameter_mm: float          # D  tool diameter
    flutes: int                 # z  number of teeth
    feed_per_tooth_mm: float    # fz
    radial_depth_mm: float      # ae radial engagement (stepover)
    axial_depth_mm: float       # ap axial engagement (stepdown)
    kc11: float                 # kc1.1 material specific cutting force [N/mm^2]
    mc: float                   # Kienzle exponent
    spindle_rpm: float | None = None          # n   (optional)
    cutting_speed_m_min: float | None = None  # vc  (optional; derived from n,D)
    feed_mm_min: float | None = None          # vf  (optional; derived from fz,z,n)
    lead_angle_deg: float = 90.0              # kr  (90 = square end mill)
    radial_ratio: float = 0.4   # Fr/Ft empirical ~0.3-0.5. ponytail: constant;
    axial_ratio: float = 0.3    # Fa/Ft, helix-driven ~0.2-0.4. ponytail: constant
                                # until helix angle is available (not in Fusion).
    rake_min_deg: float | None = None  # typical cutter rake range for this
    rake_max_deg: float | None = None  # material -> force band (None = no band)
    stickout_mm: float | None = None   # tool length out of holder (cantilever L)
    tool_modulus_gpa: float = 600.0    # Young's modulus: carbide ~600, HSS ~210


@dataclass
class CutResult:
    mean_chip_mm: float
    engagement_deg: float
    teeth_in_cut: float
    specific_force: float       # kc at hm, at reference rake [N/mm^2]
    tangential_N: float         # Ft, mean over a revolution -> spindle load
    radial_N: float             # Fr, bending the tool -> deflection
    axial_N: float              # Fa, along the spindle -> thrust / pull-out
    resultant_N: float          # 3D |Ft,Fr,Fa|
    peak_tooth_N: float         # single tooth at max engagement
    cutting_power_W: float       # 0 if no rpm/vc given
    torque_Nm: float
    mrr_cm3_min: float           # 0 if no feed/rpm given
    band_lo: float = 1.0         # multiply any force/power/torque by [band_lo,
    band_hi: float = 1.0         # band_hi] for the rake-range band
    bending_N: float = 0.0       # transverse force bending the tool = |Ft,Fr|
    deflection_um: float = 0.0   # tip deflection [microns]; 0 if no stickout
    warnings: list[str] = field(default_factory=list)


def _rake_factor(rake_deg: float) -> float:
    # less rake -> blunter -> more force; clamp to stay positive
    return max(0.05, 1.0 - (rake_deg - REFERENCE_RAKE_DEG) * RAKE_FORCE_SLOPE)


def estimate(i: CutInputs) -> CutResult:
    warnings: list[str] = []
    D, z, fz = i.diameter_mm, i.flutes, i.feed_per_tooth_mm
    ae, ap = i.radial_depth_mm, i.axial_depth_mm
    kr = math.radians(i.lead_angle_deg)
    sin_kr = math.sin(kr)

    if D <= 0 or z <= 0 or fz <= 0 or ap <= 0 or ae <= 0:
        warnings.append("Missing/zero geometry; result is zero. Check operation parameters.")
        return CutResult(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, warnings=warnings)

    if ae > D:
        warnings.append(f"ae ({ae:.3g}) > D ({D:.3g}); clamped to D (slot).")
        ae = D
    immersion = ae / D  # 0..1

    # swept engagement angle from radial immersion (entry->exit), radians
    phi = math.acos(max(-1.0, min(1.0, 1.0 - 2.0 * immersion)))
    teeth_in_cut = z * phi / (2.0 * math.pi)

    # mean undeformed chip thickness: (1/phi) * integral fz*sin(t) dt over arc,
    # which reduces to 2*(ae/D)*fz/phi, scaled by sin(kr) for non-square tools.
    hm = (2.0 * immersion * fz / phi) * sin_kr

    # Kienzle specific cutting force at the mean chip thickness (reference rake)
    kc = i.kc11 * hm ** (-i.mc)

    # force components
    ft = kc * ae * ap * fz * z / (math.pi * D)   # tangential, rpm-independent
    fr = i.radial_ratio * ft                     # radial (bending)
    fa = i.axial_ratio * ft                      # axial (thrust)
    resultant = math.sqrt(ft * ft + fr * fr + fa * fa)

    # peak: one tooth at its maximum chip thickness within the engaged arc
    h_max = fz * math.sin(min(phi, math.pi / 2.0)) * sin_kr
    peak_tooth = i.kc11 * h_max ** (-i.mc) * h_max * ap

    # tool deflection: cantilever beam under the transverse (bending) force.
    # Axial force is along the axis and does not bend the tool.
    bending = math.sqrt(ft * ft + fr * fr)
    deflection_um = 0.0
    if i.stickout_mm and i.stickout_mm > 0:
        d_eff = EFFECTIVE_DIA_FACTOR * D
        second_moment = math.pi * d_eff ** 4 / 64.0          # I [mm^4]
        e_mod = i.tool_modulus_gpa * 1000.0                  # GPa -> N/mm^2
        deflection_um = (bending * i.stickout_mm ** 3
                         / (3.0 * e_mod * second_moment)) * 1000.0

    # kinematics (optional)
    n, vc, vf = i.spindle_rpm, i.cutting_speed_m_min, i.feed_mm_min
    if vc is None and n is not None:
        vc = math.pi * D * n / 1000.0
    if n is None and vc is not None and vc > 0:
        n = vc * 1000.0 / (math.pi * D)
    if vf is None and n is not None:
        vf = fz * z * n

    pc_W = ft * vc / 60.0 if vc else 0.0           # Pc[W] = Ft*vc[m/min]/60
    torque = ft * (D / 2.0) / 1000.0               # N*m
    mrr = (ae * ap * vf / 1000.0) if vf else 0.0   # cm^3/min

    # rake-angle band: forces are linear in kc, so one factor scales them all.
    band_lo = band_hi = 1.0
    if i.rake_min_deg is not None and i.rake_max_deg is not None:
        lo_rake, hi_rake = sorted((i.rake_min_deg, i.rake_max_deg))
        band_hi = _rake_factor(lo_rake)   # least rake -> most force
        band_lo = _rake_factor(hi_rake)   # most rake  -> least force

    return CutResult(
        mean_chip_mm=hm,
        engagement_deg=math.degrees(phi),
        teeth_in_cut=teeth_in_cut,
        specific_force=kc,
        tangential_N=ft,
        radial_N=fr,
        axial_N=fa,
        resultant_N=resultant,
        peak_tooth_N=peak_tooth,
        cutting_power_W=pc_W,
        torque_Nm=torque,
        mrr_cm3_min=mrr,
        band_lo=band_lo,
        band_hi=band_hi,
        bending_N=bending,
        deflection_um=deflection_um,
        warnings=warnings,
    )


if __name__ == "__main__":
    # Self-check: 10 mm 4-flute slotting Al7075 @ 8000 rpm, fz 0.05, ap 2,
    # rake range 12-20 deg.
    r = estimate(CutInputs(
        diameter_mm=10, flutes=4, feed_per_tooth_mm=0.05,
        radial_depth_mm=10, axial_depth_mm=2,
        kc11=850, mc=0.23, spindle_rpm=8000,
        rake_min_deg=12, rake_max_deg=20, stickout_mm=40,
    ))
    assert abs(r.mean_chip_mm - 0.0318) < 0.002, r.mean_chip_mm
    assert 1800 < r.specific_force < 2200, r.specific_force
    assert 200 < r.tangential_N < 300, r.tangential_N
    assert r.radial_N > 0 and r.axial_N > 0
    assert r.resultant_N > r.tangential_N            # 3D resultant exceeds Ft
    assert 900 < r.cutting_power_W < 1200, r.cutting_power_W
    assert abs(r.mrr_cm3_min - 32.0) < 1.0, r.mrr_cm3_min
    # rake band: 12-20 deg with ref 6 -> factors 0.86..0.94, all below 1
    assert abs(r.band_hi - 0.94) < 1e-9 and abs(r.band_lo - 0.86) < 1e-9, (r.band_lo, r.band_hi)
    assert r.band_lo < r.band_hi <= 1.0
    # deflection: bending force is the transverse resultant, > Ft alone; tip
    # deflection positive and scales with stickout^3.
    assert r.bending_N > r.tangential_N, r.bending_N
    assert r.deflection_um > 0, r.deflection_um
    r_long = estimate(CutInputs(10, 4, 0.05, 10, 2, 850, 0.23, spindle_rpm=8000,
                                stickout_mm=80))
    assert abs(r_long.deflection_um / r.deflection_um - 8.0) < 0.01, "L^3 scaling"

    # Half-immersion check: engagement must be 90 deg at ae = D/2.
    r2 = estimate(CutInputs(10, 4, 0.05, 5, 2, 850, 0.23))
    assert abs(r2.engagement_deg - 90.0) < 1e-6, r2.engagement_deg
    assert r2.cutting_power_W == 0.0, "no rpm -> no power, but force still valid"
    assert r2.tangential_N > 0
    assert r2.band_lo == 1.0 and r2.band_hi == 1.0, "no rake range -> no band"

    print("cutting_force self-check OK")
