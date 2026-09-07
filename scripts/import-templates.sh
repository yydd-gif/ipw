#!/usr/bin/env bash
# Import real catalog templates without going through generate:templates.
#
#   bash scripts/import-templates.sh                 # /tmp/core.b64 zip (base64)
#   bash scripts/import-templates.sh --ref <git-ref> # checkout templates/ from a pushed ref
#   bash scripts/import-templates.sh --raw <url> <dest-relative-to-templates>
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
OUT="$ROOT/templates"
mkdir -p "$OUT"

copy_tree() {
  local src="$1"
  find "$src" -type f ! -name '.DS_Store' ! -path '*/__MACOSX/*' | while read -r f; do
    rel="${f#"$src"/}"
    mkdir -p "$OUT/$(dirname "$rel")"
    cp -f "$f" "$OUT/$rel"
    echo "imported $rel"
  done
}

if [[ "${1:-}" == "--ref" ]]; then
  ref="${2:?usage: --ref <git-ref>}"
  git fetch origin "$ref" 2>/dev/null || git fetch origin
  git checkout "$ref" -- templates
  ls "$OUT"
  test -f "$OUT/manifest.json"
  echo "checked out templates/ from $ref"
  exit 0
fi

if [[ "${1:-}" == "--raw" ]]; then
  url="${2:?usage: --raw <url> <dest-filename>}"
  dest="${3:?usage: --raw <url> <dest-filename>}"
  curl -fsSL "$url" -o "$OUT/$dest"
  echo "downloaded $dest"
  ls -l "$OUT/$dest"
  exit 0
fi

if [[ -s /tmp/core.b64 ]]; then
  exec bash "$ROOT/scripts/apply-core-templates.sh"
fi

echo "nothing to import: pass --ref, --raw, or put zip base64 in /tmp/core.b64" >&2
exit 1
