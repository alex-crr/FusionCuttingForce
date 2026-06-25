"""Cutting Force Estimator - Fusion 360 add-in entry point.

Adds a button to the Manufacture workspace that opens an interactive palette:
pick the material there and the report recomputes live. Operations are grouped
by Setup; the heaviest op per setup is starred for fixture sizing; ae/ap that
are not specified in the op (finish/cleanup over stock-to-leave) are flagged.

This is the ONLY Fusion-coupled module. Pure model = cutting_force.py,
payload shaping = report.py, drawing = palette/report.html.

Units: the Fusion API returns LENGTHS in centimetres; length params are *10 -> mm.
CAMParameters uses itemByName (not itemById). op.parameters holds everything.
"""
import importlib
import json
import os
import traceback

import adsk.core
import adsk.cam

# Qualified imports (cf.X, not `from cf import X`) so importlib.reload in run()
# actually refreshes these during development -- a `from x import y` binding
# would keep pointing at the stale function after a reload.
import cutting_force as cf
import materials
import report

PARAM_IDS = {
    "diameter": ["tool_diameter"],
    "flutes":   ["tool_numberOfFlutes"],
    "fz":       ["tool_feedPerTooth"],
    "rpm":      ["tool_spindleSpeed"],
}
CM_TO_MM = 10.0

# Radial (ae) / axial (ap) engagement ids per operation strategy.
ENGAGE = {
    "adaptive":          (["optimalLoad"], ["maximumStepdown"]),
    "adaptive2d":        (["optimalLoad"], ["maximumStepdown"]),
    "pocket2d":          (["stepover", "maximumStepover"], ["maximumStepdown"]),
    "face":              (["stepover"], ["maximumStepdown"]),
    "contour2d":         (["maximumStepover", "stepover"], ["maximumStepdown"]),
}
ENGAGE_DEFAULT = (["stepover", "optimalLoad", "maximumStepover", "tool_stepover"],
                  ["maximumStepdown", "stepdown", "tool_stepdown"])

CMD_ID = "cuttingForceEstimatorCmd"
PALETTE_ID = "cuttingForcePalette"
PANEL_ID = "cuttingForcePanel"
TAB_ID = "MillingTab"          # native Manufacture > Milling tab (always visible);
WORKSPACE_ID = "CAMEnvironment"  # a self-made tab is created hidden (isVisible=False)
_ADDIN_DIR = os.path.dirname(os.path.abspath(__file__))

_handlers = []


# --- CAM reading ------------------------------------------------------------
def _read(params, ids):
    """First id that resolves via itemByName (CAMParameters has no itemById)."""
    if params is None:
        return None
    for pid in ids:
        try:
            p = params.itemByName(pid)
            if p is not None:
                return p.value.value
        except Exception:
            continue
    return None


def _is_milling(op):
    v = _read(getattr(op, "parameters", None), ["tool_isMill"])
    return bool(v) if v is not None else True


def _inputs_for(op, mat):
    """Return (CutInputs, ae_estimated, ap_estimated). Lengths cm -> mm."""
    p = getattr(op, "parameters", None)

    def length(ids):
        v = _read(p, ids)
        return v * CM_TO_MM if v is not None else None

    strat = (getattr(op, "strategy", "") or "").lower()
    ae_ids, ap_ids = ENGAGE.get(strat, ENGAGE_DEFAULT)

    D = length(PARAM_IDS["diameter"])
    z = _read(p, PARAM_IDS["flutes"])
    fz = length(PARAM_IDS["fz"])
    ae = length(ae_ids)
    ap = length(ap_ids)
    rpm = _read(p, PARAM_IDS["rpm"])

    # stickout (cantilever) = protrusion below holder = assembly - holder gauge
    # length (equals tool_bodyLength). Always from the tool; never user-forced.
    asm = length(["tool_assemblyGaugeLength"])
    hold = length(["tool_holderGaugeLength"])
    stickout = (asm - hold) if (asm and hold and asm > hold) \
        else (length(["tool_bodyLength"]) or length(["tool_overallLength"]))

    ap_est = ap is None or ap <= 0
    if ap_est:
        ap = length(["tool_stepdown"])           # tool default as a stand-in
    ae_est = ae is None or strat == "contour2d"  # slot assumption / approx radial
    if ae is None:
        ae = D

    inp = cf.CutInputs(
        diameter_mm=D or 0.0,
        flutes=int(z) if z else 0,
        feed_per_tooth_mm=fz or 0.0,
        radial_depth_mm=ae or 0.0,
        axial_depth_mm=ap or 0.0,
        kc11=mat["kc11"], mc=mat["mc"],
        spindle_rpm=rpm,
        rake_min_deg=mat.get("rake_min"), rake_max_deg=mat.get("rake_max"),
        stickout_mm=stickout,
    )
    return inp, ae_est, ap_est


def _theme(app):
    try:
        if app.preferences.generalPreferences.userInterfaceTheme == \
                adsk.core.UserInterfaceThemes.DarkUITheme:
            return "dark"
    except Exception:
        pass
    return "light"


def build_full_payload(app, mat_key):
    """Nested payload: materials list + every setup -> operations, for the palette."""
    keys = list(materials.MATERIALS.keys())
    payload = {
        "materials": [[k, materials.MATERIALS[k]["name"]] for k in keys],
        "material_key": mat_key if mat_key in materials.MATERIALS else materials.DEFAULT_KEY,
        "theme": _theme(app),
        "setups": [],
    }
    cam = app.activeDocument.products.itemByProductType("CAMProductType")
    if cam is None:
        payload["error"] = "No CAM data. Switch to the Manufacture workspace first."
        return payload
    mat = materials.get(payload["material_key"])

    for s in cam.setups:
        try:
            ops = s.allOperations
        except Exception:
            ops = s.operations
        rows = []
        for op in ops:
            if not _is_milling(op):
                continue
            try:
                inp, ae_est, ap_est = _inputs_for(op, mat)
                rows.append((op.name, inp, cf.estimate(inp), ae_est, ap_est))
            except Exception:
                continue
        if rows:
            payload["setups"].append(report.setup_payload(s.name, rows))
    return payload


# --- Palette + bridge -------------------------------------------------------
def _show_palette(ui):
    pal = ui.palettes.itemById(PALETTE_ID)
    if pal:                       # recreate so the webview reloads fresh
        pal.deleteMe()
    url = os.path.join(_ADDIN_DIR, "palette", "report.html").replace("\\", "/")
    pal = ui.palettes.add(PALETTE_ID, "Cutting Force", url, True, True, True, 1040, 580)
    pal.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateRight
    handler = HTMLHandler()
    pal.incomingFromHTML.add(handler)
    _handlers.append(handler)
    pal.isVisible = True


class HTMLHandler(adsk.core.HTMLEventHandler):
    def notify(self, args):
        app = adsk.core.Application.get()
        ui = app.userInterface
        try:
            a = adsk.core.HTMLEventArgs.cast(args)
            pal = ui.palettes.itemById(PALETTE_ID)
            if not pal or a.action not in ("ready", "recompute"):
                return
            if a.data:
                mat_key = json.loads(a.data).get("material") or materials.DEFAULT_KEY
            else:
                mat_key = materials.DEFAULT_KEY
            payload = build_full_payload(app, mat_key)
            pal.sendInfoToHTML("render", json.dumps(payload))
        except Exception:
            ui.messageBox("Cutting Force error:\n" + traceback.format_exc())


# --- Command handlers -------------------------------------------------------
class ExecuteHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        ui = adsk.core.Application.get().userInterface
        try:
            _show_palette(ui)
        except Exception:
            ui.messageBox("Failed:\n" + traceback.format_exc())


class CreatedHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        h = ExecuteHandler()
        args.command.execute.add(h)
        _handlers.append(h)


# --- Add-in lifecycle -------------------------------------------------------
def _build_ui(ui):
    # Icon temporarily off: our PNGs hang Fusion's icon loader on load (FusionScale's
    # work, so it's a PNG-format difference under investigation). Plain button = the
    # known-good state. Re-add the resourceFolder once the icons are fixed + verified.
    cmd_def = ui.commandDefinitions.itemById(CMD_ID) or \
        ui.commandDefinitions.addButtonDefinition(
            CMD_ID, "Cutting Force", "Estimate cutting forces of milling operations")
    h = CreatedHandler()
    cmd_def.commandCreated.add(h)
    _handlers.append(h)

    ws = ui.workspaces.itemById(WORKSPACE_ID)
    tab = ws.toolbarTabs.itemById(TAB_ID)        # existing native Milling tab
    panel = tab.toolbarPanels.itemById(PANEL_ID) or \
        tab.toolbarPanels.add(PANEL_ID, "Cutting Force")
    if not panel.controls.itemById(CMD_ID):
        panel.controls.addCommand(cmd_def)


def run(context):
    ui = None
    try:
        # Pick up edits to the pure modules on Stop->Run without a full Fusion
        # restart. (Editing THIS file still needs a restart.)
        for m in (materials, cf, report):
            try:
                importlib.reload(m)
            except Exception:
                pass
        ui = adsk.core.Application.get().userInterface
        _build_ui(ui)
    except Exception:
        if ui:
            ui.messageBox("Cutting Force start failed:\n" + traceback.format_exc())


def stop(context):
    ui = None
    try:
        ui = adsk.core.Application.get().userInterface
        pal = ui.palettes.itemById(PALETTE_ID)
        if pal:
            pal.deleteMe()
        ws = ui.workspaces.itemById(WORKSPACE_ID)
        tab = ws.toolbarTabs.itemById(TAB_ID)
        if tab:
            panel = tab.toolbarPanels.itemById(PANEL_ID)
            if panel:
                ctrl = panel.controls.itemById(CMD_ID)
                if ctrl:
                    ctrl.deleteMe()
                panel.deleteMe()      # remove only our panel; tab is native
        cmd_def = ui.commandDefinitions.itemById(CMD_ID)
        if cmd_def:
            cmd_def.deleteMe()
        del _handlers[:]
    except Exception:
        if ui:
            ui.messageBox("Cutting Force stop failed:\n" + traceback.format_exc())
