#!/usr/bin/env bash
# Build the distributable from committed files ONLY, outside the source tree, and gate it.
#
#   tools/export-release.sh [OUTDIR]     default OUTDIR: ../cydex-export
#
# Uses `git archive HEAD`: no .git, no ignored or untracked files, no filesystem
# metadata. Produces OUTDIR/cydex/ and OUTDIR/cydex.tar.gz, then runs
# tools/check.sh against the exported copy. Ship the tarball, never the working folder.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/../cydex-export}"
[ -z "$(git -C "$ROOT" status --porcelain)" ] || { echo "commit or stash changes first - the export is built from HEAD"; exit 1; }
case "$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")" in "$ROOT"|"$ROOT"/*) echo "OUTDIR must be outside the repo"; exit 1;; esac
rm -rf "$OUT"; mkdir -p "$OUT/cydex"
git -C "$ROOT" archive --format=tar HEAD | tar -x -C "$OUT/cydex"
"$ROOT/tools/check.sh" "$OUT/cydex"
# No extended attributes, ACLs or macOS metadata (AppleDouble ._ files) in the archive.
export COPYFILE_DISABLE=1
tar --no-xattrs --no-acls --no-mac-metadata -czf "$OUT/cydex.tar.gz" -C "$OUT" cydex 2>/dev/null \
  || tar --no-xattrs --no-acls -czf "$OUT/cydex.tar.gz" -C "$OUT" cydex 2>/dev/null \
  || tar -czf "$OUT/cydex.tar.gz" -C "$OUT" cydex
if tar -tzf "$OUT/cydex.tar.gz" | grep -qE '(^|/)\._'; then echo "FAIL: AppleDouble metadata in archive"; exit 1; fi
echo "export: $OUT/cydex.tar.gz  (commit $(git -C "$ROOT" rev-parse --short HEAD))"
