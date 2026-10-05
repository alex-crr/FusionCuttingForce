"""Assemble the Autodesk App Store .bundle from the dev source tree.

Run:    python packaging/build_bundle.py
Output: dist/ADSK.Courrieu.CuttingForce.bundle/  (PackageContents.xml + Contents/)

The repo root stays the dev add-in (loads from Fusion's API/AddIns). This script
just copies the runtime files into the .bundle layout the App Store expects, so
the dev layout isn't disturbed. See the fusion-addin-publishing skill for rules.

Bump "version" in FusionCuttingForce.manifest per submission (ProductCode is
derived from it; UpgradeCode stays constant forever).
"""
import json
import os
import shutil
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")

# Single source of truth: bump "version" in the manifest for every submission.
with open(os.path.join(ROOT, "FusionCuttingForce.manifest"), encoding="utf-8") as _f:
    VERSION = json.load(_f)["version"]

APP_NAME = "Cutting Force"
MODULE = "FusionCuttingForce"
AUTHOR = "Alexandre Courrieu"
EMAIL = "alexandre@courrieu.com"
COMPANY = "Alexandre Courrieu"
URL = "https://github.com/alex-crr/FusionCuttingForce"
DESCRIPTION = "Estimate milling cutting forces per CAM operation (Kienzle model)."

UPGRADE_CODE = "{25842b42-b696-4da4-9cd3-139b871571a6}"          # STABLE forever
_NS = uuid.UUID("91097034-2799-4864-ad66-1a82ca4ad0c3")
PRODUCT_CODE = "{%s}" % uuid.uuid5(_NS, VERSION)                 # per-version

BUNDLE = "ADSK.Courrieu.CuttingForce.bundle"

# Runtime files copied into Contents/ (dev/test/tooling files are excluded).
CONTENTS = [
    "FusionCuttingForce.py", "FusionCuttingForce.manifest",
    "cutting_force.py", "materials.py", "materials.json", "report.py",
    "palette/report.html",
    "resources/16x16.png", "resources/32x32.png", "resources/64x64.png",
]

PACKAGE_CONTENTS = f"""<?xml version="1.0" encoding="utf-8"?>
<ApplicationPackage SchemaVersion="1.0" AutodeskProduct="Fusion360"
    Name="{APP_NAME}" Description="{DESCRIPTION}"
    Author="{AUTHOR}" AppVersion="{VERSION}"
    ProductCode="{PRODUCT_CODE}" UpgradeCode="{UPGRADE_CODE}">
  <CompanyDetails Name="{COMPANY}" Url="{URL}" Email="{EMAIL}"/>
  <Components Description="Fusion 360 Add-in">
    <RuntimeRequirements OS="Win64" Platform="Fusion360" SeriesMin="" SeriesMax=""/>
    <ComponentEntry AppName="{MODULE}" ModuleName="./Contents/{MODULE}.py"
        AppType="addin" Version="{VERSION}" LoadOnFusionStartup="True"/>
  </Components>
</ApplicationPackage>
"""


def build():
    out = os.path.join(DIST, BUNDLE)
    if os.path.exists(out):
        shutil.rmtree(out)
    contents = os.path.join(out, "Contents")
    os.makedirs(contents)
    with open(os.path.join(out, "PackageContents.xml"), "w", encoding="utf-8") as f:
        f.write(PACKAGE_CONTENTS)
    for rel in CONTENTS:
        src = os.path.join(ROOT, *rel.split("/"))
        dst = os.path.join(contents, *rel.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
    print("built:", out)
    print("version:", VERSION, "| ProductCode:", PRODUCT_CODE)


if __name__ == "__main__":
    build()
