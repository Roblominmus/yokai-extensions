#!/usr/bin/env bash
# Copy a target extension source's Kotlin files into the harness source set so it
# compiles against our real runtime (instead of the upstream compileOnly stub).
#
# Usage:
#   ./import_source.sh ../../extensions-source/src/en/mangademon
# It finds the inner `.../src/eu/...` package tree and copies it under
# src/main/kotlin/, replacing any previously imported extension.
set -euo pipefail

SRC_DIR="${1:?usage: import_source.sh <path-to-extension-dir> (the folder containing build.gradle + src/)}"
HARNESS_ROOT="$(cd "$(dirname "$0")" && pwd)"
DEST="$HARNESS_ROOT/src/main/kotlin"

if [[ ! -d "$SRC_DIR/src" ]]; then
  echo "error: $SRC_DIR has no src/ subdir (is this an extension module dir?)" >&2
  exit 1
fi

# locate the eu/ package root inside the extension's src/
EU_ROOT="$(find "$SRC_DIR/src" -type d -name eu -maxdepth 4 | head -1)"
if [[ -z "$EU_ROOT" ]]; then
  echo "error: could not find an 'eu/' package root under $SRC_DIR/src" >&2
  exit 1
fi

# Refresh only THIS module's source leaf/leaves (extension/<lang>/<name>), so
# multiple imported sources coexist. Keeps our runtime and other sources intact.
SRC_EXT="$EU_ROOT/kanade/tachiyomi/extension"
mkdir -p "$DEST/eu/kanade/tachiyomi/extension"
for leaf in "$SRC_EXT"/*/*; do
  [ -d "$leaf" ] || continue
  lang="$(basename "$(dirname "$leaf")")"; name="$(basename "$leaf")"
  rm -rf "$DEST/eu/kanade/tachiyomi/extension/$lang/$name"
  mkdir -p "$DEST/eu/kanade/tachiyomi/extension/$lang"
  cp -r "$leaf" "$DEST/eu/kanade/tachiyomi/extension/$lang/"
done

echo "imported source from: $SRC_DIR"
echo "copied .kt files:"
find "$DEST/eu/kanade/tachiyomi/extension" -name '*.kt' -printf '  %p\n'

# surface anything that needs an android.* shim (harness has no Android runtime)
echo ""
echo "android.* imports in the imported source (need shims if any):"
grep -rhoE "^import android\.[a-zA-Z0-9_.]+" "$DEST/eu/kanade/tachiyomi/extension" | sort -u | sed 's/^/  /' || echo "  (none)"
