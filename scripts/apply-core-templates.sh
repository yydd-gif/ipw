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
import json, pathlib, zipfile, zlib
root = pathlib.Path("templates")
root.mkdir(exist_ok=True)
zf = zipfile.ZipFile("/tmp/core-templates.zip")

def crc32(path: pathlib.Path) -> int:
    return zlib.crc32(path.read_bytes()) & 0xFFFFFFFF

def keep_layout_aligned_manifest(path: pathlib.Path) -> bool:
    try:
        data = json.loads(path.read_text())
    except Exception:
        return False
    for tmpl in data.get("templates", []):
        for scalar in tmpl.get("scalars", []):
            if scalar.get("key") == "qs_check" and scalar.get("mode") == "afterLabel":
                return True
    return False

for info in zf.infolist():
    name = pathlib.Path(info.filename).name
    if info.is_dir() or not name or name.startswith(".") or "__MACOSX" in info.filename:
        continue
    dest = root / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = zf.read(info.filename)
    except Exception as exc:
        if dest.exists() and crc32(dest) == (info.CRC & 0xFFFFFFFF):
            print(f"kept existing {dest} (zip member corrupt, CRC matches {info.CRC:08x})")
            continue
        raise SystemExit(f"failed to extract {info.filename}: {exc}") from exc
    if dest.name == "manifest.json" and dest.exists() and keep_layout_aligned_manifest(dest):
        print(f"kept existing {dest} (layout-aligned CellPatch coords)")
        continue
    dest.write_bytes(data)
    print("extracted", dest)
PY

ls templates
test -f templates/manifest.json
test -f templates/7.2_软硬件清单.docx
python3 - <<'PY'
from pathlib import Path
checks = {
    "2.10_施工日志.docx": 9393,
    "7.2_软硬件清单.docx": 12275,
    "6.2_竣工验收报告.docx": 46865,
}
root = Path("templates")
bad = []
for name, expect in checks.items():
    p = root / name
    n = p.stat().st_size if p.exists() else 0
    print(f"size {name}: {n} (expect ≈ {expect})")
    if n < expect * 0.6:
        bad.append(f"{name} still looks like a stub ({n} bytes)")
if bad:
    raise SystemExit("SIZE CHECK FAILED:\n" + "\n".join(bad))
print("size checks ok")
PY
echo "core templates applied"
node scripts/inspect-docx.mjs templates/7.2_软硬件清单.docx | head -80
