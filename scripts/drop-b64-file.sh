#!/usr/bin/env bash
# Overwrite one template file from stdin or a base64 file. Does not run generate:templates.
#   printf '%s' "$B64" | bash scripts/drop-b64-file.sh templates/2.10_施工日志.docx
#   bash scripts/drop-b64-file.sh templates/2.10_施工日志.docx /tmp/part.b64
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
dest="$ROOT/${1:?usage: drop-b64-file.sh <relative-path> [b64-file]}"
src="${2:-}"
mkdir -p "$(dirname "$dest")"
if [[ -n "$src" ]]; then
  base64 -d "$src" > "$dest"
else
  base64 -d > "$dest"
fi
echo "wrote $dest ($(wc -c < "$dest") bytes)"
