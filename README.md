# Fusion Cutting Force Estimator

A Fusion 360 add-in that estimates **milling cutting forces** per operation from
the tool and cut parameters already in your CAM setup, and generates an HTML
report. Forces use the **Kienzle specific-cutting-force model** — defensible,
transparent, and shown step-by-step in the report.

## Install

1. Copy the `FusionCuttingForce` folder to your Fusion add-ins directory:
   - Windows: `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\`
   - macOS: `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/`
2. Fusion → **Utilities → Add-Ins → Scripts and Add-Ins** → select
   *FusionCuttingForce* → **Run** (tick *Run on Startup* to keep it).
3. Switch to the **Manufacture** workspace → a **Cutting Force** tab/panel
   appears with the **Cutting Force** button.

## Use

1. Generate your milling toolpaths as usual.
2. (Optional) select specific operations in the browser.
3. Click **Cutting Force**, pick the **material**, choose scope, OK.
4. An HTML report opens in your browser with per-operation forces and the math.

## How the calculation works

Metric units. Per operation:

| Step | Formula |
|------|---------|
| Radial immersion | `ar = ae / D` |
| Engagement angle | `φ = acos(1 − 2·ar)` |
| Mean chip thickness | `hm = 2·ar·fz/φ · sin(κr)` |
| Specific cutting force (Kienzle) | `kc = kc1.1 · hm^(−mc)` |
| Tangential force | `Ft = kc · ae · ap · fz · z / (π·D)` |
| Radial / axial | `Fr = 0.4·Ft`, `Fa = 0.3·Ft` (empirical ratios) |
| Resultant (3D) | `Fres = √(Ft² + Fr² + Fa²)` |
| Peak tooth force | one tooth at `h_max = fz·sin(min(φ,90°))·sin(κr)` |
| Cutting power / torque | `Pc = Ft·vc/60`, `M = Ft·(D/2)/1000` |
| Tool deflection | `δ = F_bend·L³/(3·E·I)`, `F_bend=√(Ft²+Fr²)`, `I=π(0.8D)⁴/64` |
| Rake band | each force × `[1 − (γ − γ_ref)·0.01]` over the rake range |

Deflection uses tool stickout `L` (set the override for the real value — it
scales with `L³`), carbide `E=600 GPa`, and an effective diameter `0.8·D`.

`Ft` needs no spindle speed — it's an exact rearrangement of the power route
`Pc = kc·MRR / (60·10⁶)`. Spindle speed only adds power and torque.

**Why ranges, not single numbers?** Fusion stores no rake or helix angle, so
rather than guess one value the report spans each material's *typical rake
range* — forces come out as `Ft: 220–240 N`, honest about the unknown. `kc1.1`,
`mc` and the rake range come from `materials.json` — literature starting points;
treat `kc1.1` as a calibration knob if measured spindle load disagrees. The model
is quasi-static (no wear, runout, chatter); Fr/Fa ratios are coarse until helix
is modelled.

## Adding materials

Edit `materials.json` — one block per material (a bad entry is skipped, not fatal):

```json
"al7075": { "name": "Aluminium 7075-T6", "kc11": 850, "mc": 0.23,
            "rake_min": 12, "rake_max": 20 }
```

## Files

| File | Role |
|------|------|
| `cutting_force.py` | Pure model (no Fusion deps). `python cutting_force.py` self-tests. |
| `materials.json` | Material data — edit this to add materials. |
| `materials.py` | Loader/validator for `materials.json`. |
| `report.py` | HTML report builder (pure). |
| `FusionCuttingForce.py` | Fusion glue: button, dialog, reads operations. |
| `FusionCuttingForce.manifest` | Add-in metadata. |
| `test_cutting_force.py` | Extra checks; run with `python test_cutting_force.py`. |

## CAM parameter IDs & units (verified against a live Fusion tool)

Tool-side IDs and units are confirmed by reading a real tool through the API:
`tool_diameter`, `tool_numberOfFlutes`, `tool_feedPerTooth`, `tool_spindleSpeed`,
`tool_overallLength`. **The API returns lengths in centimetres** (internal
units), so the glue multiplies length parameters by 10 to get mm — see
`LENGTH_KEYS` in `FusionCuttingForce.py`. `vc`/`vf` are deliberately *not* read;
the model derives them from rpm + geometry.

The **operation-level** `ae`/`ap` IDs differ by toolpath strategy and are not yet
confirmed (verification doc had no toolpath). `PARAM_IDS` tries the common ids and
falls back to the confirmed tool-level `tool_stepover`/`tool_stepdown`. With one
real toolpath, dump its parameter ids and prepend the correct one.

## Toward a public release

- [ ] Confirm operation-level `ae`/`ap` ids across strategies (2D/3D adaptive, contour, face).
- [ ] In-app palette report instead of browser (nicer, no temp file).
- [ ] Tool material (carbide/HSS) -> deflection modulus, from the tool or dialog.
- [ ] Helix angle -> proper axial force and per-tooth ripple.
- [ ] Material calibration table validated against measured cuts.
- [ ] Icons + Fusion App Store packaging.
