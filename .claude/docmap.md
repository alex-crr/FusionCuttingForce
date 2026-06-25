# Docmap — FusionCuttingForce

Fusion 360 add-in: estimate milling cutting forces per CAM operation, emit HTML report.

## Data flow
button (icon: resources/) → ExecuteHandler → `_show_palette` (loads palette/report.html, docked).
Page fires `ready`/`recompute` (material only) → `HTMLHandler` → `build_full_payload(app, mat_key)`
(EVERY setup's ops via `_inputs_for` → `cf.estimate` → `report.setup_payload`, worst op flagged,
theme detected) → `sendInfoToHTML('render', json)` → JS draws collapsible `<details>` per setup.

## Modules
- **cutting_force.py** — pure model, no Fusion deps.
  - `CutInputs` / `CutResult` (dataclasses); module consts `REFERENCE_RAKE_DEG`, `RAKE_FORCE_SLOPE`.
  - `estimate(CutInputs)->CutResult`: immersion→engagement φ→mean chip hm→Kienzle kc→Ft/Fr/Fa/3D resultant/peak/power/torque/MRR/deflection + rake band (`band_lo`,`band_hi` scale all forces). Deflection = cantilever `F_bend·L³/3EI`, `d_eff=0.8D`, `EFFECTIVE_DIA_FACTOR`.
  - `__main__`: self-check.
- **materials.json** — DATA. Edit to add materials: key→{name,kc11,mc,rake_min,rake_max}. `_`-prefixed keys ignored.
- **materials.py** — loader. `_load()` validates/skips bad entries; exposes `MATERIALS`, `DEFAULT_KEY`, `get(key)`. `__main__` self-check.
- **report.py** — pure payload builder. `op_payload`, `setup_payload(name, rows)->dict` (rows=[(name,CutInputs,CutResult,ae_est,ap_est)]; marks worst=max resultant). Values as rake-band `[lo,hi]`. `__main__` self-check.
- **palette/report.html** — the UI: shell + inline CSS (CSS-vars + `body.dark` for Fusion theme) + JS. Bridge: `window.fusionJavaScriptHandler.handle('render',json)` receives; `adsk.fusionSendData('ready'|'recompute', {material})` sends. Material dropdown + Refresh. Each setup is a collapsible `<details open>` (summary shows op count + ★ heaviest); ≈ marks estimated ae/ap; legend.
- **generate_icon.py** — `python generate_icon.py` → resources/{16,32,64}x16.png (force-arrow-into-workpiece). **resources/** = button icon folder passed to `addButtonDefinition`.
- **FusionCuttingForce.py** — ONLY Fusion-coupled file. Qualified imports (`cf`) + `importlib.reload` in `run()` so pure-module edits load on Stop→Run (editing THIS file needs Fusion restart).
  - `PARAM_IDS` + `ENGAGE` (per-strategy ae/ap ids) + `ENGAGE_DEFAULT`. `CM_TO_MM`: API returns lengths in cm. `_read` uses **itemByName** (CAMParameters has no itemById); `op.parameters` holds everything.
  - `_inputs_for(op,mat)->(CutInputs,ae_est,ap_est)`; stickout always = assemblyGauge−holderGauge (no user override). `_theme(app)`, `build_full_payload`, `_show_palette`, `HTMLHandler`.
  - `CreatedHandler`/`ExecuteHandler` (button→palette, no dialog), `run`/`stop`, `_build_ui`.
  - UI: panel `cuttingForcePanel` added to the **native `MillingTab`** of `CAMEnvironment` (a self-made tab loads hidden); cmd `cuttingForceEstimatorCmd`, palette `cuttingForcePalette`. `stop` removes the panel, never the native tab.
- **FusionCuttingForce.manifest** — add-in metadata; `runOnStartup: true`, valid-GUID `id`.
  Install: register the folder once via Add-Ins "+" (or junction into API/AddIns). Loaded direct from Projets.
- **test_cutting_force.py** — extra checks (`python test_cutting_force.py`).

## Run / test
`python cutting_force.py` · `python report.py` · `python test_cutting_force.py` (no Fusion needed).

## Risk / calibration knobs
- `PARAM_IDS` ae/ap ids vary by op type+version — verify in Fusion text-command window.
- `materials.py` kc11 = literature start; scale to measured spindle load.
- UI tab/panel placement: creates own tab; retarget to existing CAM tab id if desired.
