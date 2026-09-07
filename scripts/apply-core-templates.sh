#!/usr/bin/env bash
# Decode concatenated base64 at /tmp/core.b64 and extract into templates/.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -s /tmp/core.b64 ]]; then
  echo "missing or empty /tmp/core.b64" >&2
  exit 1
fi

base64 -d /tmp/core.b64 > /tmp/core-templates.zip
python3 - <<'PY'
import zipfile, pathlib, shutil, os
root = pathlib.Path("templates")
root.mkdir(exist_ok=True)
zf = zipfile.ZipFile("/tmp/core-templates.zip")
# Extract to a staging dir so a zip-root folder can be flattened.
stage = pathlib.Path("/tmp/core-templates-extract")
if stage.exists():
    shutil.rmtree(stage)
stage.mkdir()
zf.extractall(stage)
entries = [p for p in stage.iterdir() if p.name != "__MACOSX"]
src = stage
if len(entries) == 1 and entries[0].is_dir():
    src = entries[0]
for path in src.rglob("*"):
    if path.is_dir() or path.name.startswith("."):
        continue
    rel = path.relative_to(src)
    dest = root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)
    print("extracted", dest)
PY

ls templates
test -f templates/manifest.json
test -f templates/7.2_软硬件清单.docx
echo "core templates applied"
node scripts/inspect-docx.mjs templates/7.2_软硬件清单.docx | head -80
