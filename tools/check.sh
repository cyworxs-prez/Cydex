#!/usr/bin/env bash
# Release gate. Read-only. Exit non-zero on any failure.
#
#   tools/check.sh [DIR]      DIR defaults to the repo root. Run it on the EXPORT
#                             (tools/export-release.sh does this for you), because
#                             the export is what you actually distribute.
#
# Scans EVERY file under DIR - tracked, untracked and ignored - plus every Git
# object (reachable or dangling) if DIR contains .git. Images cannot be text-scanned,
# so each image must be listed in tools/reviewed-images.sha256 after a visual review.
#
# Private patterns (your real names, addresses, SSIDs, device brands...) live
# OUTSIDE the repo: $HOMELAB_PRIVATE_PATTERNS, default
# ~/.config/homelab-soc/private-patterns.txt, one fixed string per line. The gate
# fails if that file is missing - a scan without it proves very little.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DIR="$(cd "${1:-$HERE/..}" && pwd)"
PRIV="${HOMELAB_PRIVATE_PATTERNS:-$HOME/.config/homelab-soc/private-patterns.txt}"
fail=0
sha() { if command -v sha256sum >/dev/null; then sha256sum "$1"; else shasum -a 256 "$1"; fi; }
note() { printf '  %-6s %s\n' "$1" "$2"; }
bad()  { note FAIL "$1"; fail=1; }

TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
# every regular file, excluding dependency trees and the git store (scanned separately)
( cd "$DIR" && find . -type f -not -path './.git/*' -not -path '*/node_modules/*' | sed 's#^\./##' | sort ) > "$TMP/files"

echo "== packaging hygiene ($DIR)"
case "$PRIV" in "$DIR"/*) bad "private pattern file is inside the scanned tree: $PRIV";; esac
grep -E '(^|/)(private-patterns[^/]*|\.DS_Store|\._[^/]*|.*\.pyc|.*\.bak[^/]*|.*\.orig|.*\.swp|.*\.env|.*\.pem|.*\.key|id_[a-z0-9]+|build_key[^/]*|.*\.tgz|.*\.tar(\.gz)?|.*\.zip|.*\.sqlite3.*|.*\.log)$' "$TMP/files" \
  | grep -v '\.env\.example$' > "$TMP/junk"
[ -s "$TMP/junk" ] && { bad "files that must not ship:"; sed 's/^/           /' "$TMP/junk"; } || note ok "no secrets/bytecode/backups/archives/OS metadata files"
if command -v xattr >/dev/null 2>&1; then
  n=$(cd "$DIR" && xargs -I{} sh -c 'xattr "{}" 2>/dev/null' < "$TMP/files" | grep -vc '^com.apple.provenance$' || true)
  [ "${n:-0}" -gt 0 ] && note warn "$n extended attributes present - export with git archive, not a folder copy" || note ok "no extended attributes"
fi

echo "== syntax"
s=0
while IFS= read -r f; do case "$f" in
  *.sh) bash -n "$DIR/$f" 2>/dev/null || { bad "$f"; s=1; };;
  *.py) python3 -c 'import ast,sys; ast.parse(open(sys.argv[1]).read())' "$DIR/$f" 2>/dev/null || { bad "$f"; s=1; };;
  *.json) python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$DIR/$f" 2>/dev/null || { bad "$f"; s=1; };;
  wazuh/*.xml) python3 -c 'import sys,xml.dom.minidom as m; m.parseString("<r>"+open(sys.argv[1]).read()+"</r>")' "$DIR/$f" 2>/dev/null || { bad "$f"; s=1; };;
esac; done < "$TMP/files"
[ $s = 0 ] && note ok "shell / python / json / wazuh xml"

echo "== images (pixels cannot be text-scanned)"
REV="$DIR/tools/reviewed-images.sha256"
grep -iE '\.(png|jpe?g|gif|webp|svg|bmp|tiff?|ico|pdf)$' "$TMP/files" > "$TMP/imgs" || true
while IFS= read -r f; do
  h=$(sha "$DIR/$f" | cut -d' ' -f1)
  grep -q "^$h  $f$" "$REV" 2>/dev/null || bad "unreviewed image: $f (review it, then: sha256sum $f >> tools/reviewed-images.sha256)"
  python3 - "$DIR/$f" <<'PY' || bad "image carries metadata chunks: $f"
import struct,sys
d=open(sys.argv[1],'rb').read()
if d[:8]!=b'\x89PNG\r\n\x1a\n': sys.exit(0)
i=8
while i<len(d):
    n=struct.unpack('>I',d[i:i+4])[0]; t=d[i+4:i+8]; i+=12+n
    if t not in (b'IHDR',b'PLTE',b'IDAT',b'IEND',b'tRNS'): sys.exit(1)
PY
done < "$TMP/imgs"
[ -s "$TMP/imgs" ] && note info "$(wc -l < "$TMP/imgs") image(s) checked against the review list"

# Build one text corpus: every non-image file + every git object (if any).
corpus() {
  (cd "$DIR" && grep -viE '\.(png|jpe?g|gif|webp|bmp|tiff?|ico|pdf)$' "$TMP/files" | grep -v '^map/package-lock.json$' \
     | while IFS= read -r f; do awk -v F="$f" '{print F":"FNR": "$0}' "$f"; done)
  if [ -d "$DIR/.git" ]; then
    git -C "$DIR" cat-file --batch-all-objects --batch-check='%(objectname) %(objecttype)' \
      | awk '$2=="blob"||$2=="commit"||$2=="tag"{print $1}' \
      | while read -r o; do git -C "$DIR" cat-file -p "$o" | awk -v O="$o" '{print "git-object:"O":"FNR": "$0}'; done
  fi
}
corpus > "$TMP/corpus" 2>/dev/null
if [ -d "$DIR/.git" ]; then
  d=$(git -C "$DIR" fsck --unreachable --no-reflogs 2>/dev/null | grep -c unreachable || true)
  [ "${d:-0}" -gt 0 ] && bad "$d unreachable git objects - do not ship this .git (use tools/export-release.sh)" || note ok "no unreachable git objects"
fi

echo "== secret-shaped strings"
PAT='-----BEGIN [A-Z ]*PRIVATE KEY-----|(api[_-]?key|secret|token|password)["'"'"']?[[:space:]]*[:=][[:space:]]*["'"'"'][A-Za-z0-9+/_-]{16,}|ntfy\.sh/[A-Za-z0-9_-]{8,}|op://[a-z0-9]{26}/|ghp_[A-Za-z0-9]{30,}|github_pat_|xox[abp]-|AKIA[0-9A-Z]{16}|\b([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b'
grep -Ee "$PAT" "$TMP/corpus" | grep -v '^tools/check.sh:' | grep -vF "PAT='-----BEGIN" | grep -v '02:00:00:00:00:01' > "$TMP/hits"
[ -s "$TMP/hits" ] && { bad "secret-shaped strings:"; cut -c1-160 "$TMP/hits"; } || note ok "none"

echo "== public IPv4 addresses (only documentation ranges and known resolvers allowed)"
python3 - "$TMP/corpus" > "$TMP/ips" <<'PY'
import ipaddress, re, sys
ALLOW_NETS = [ipaddress.ip_network(n) for n in ('192.0.2.0/24','198.51.100.0/24','203.0.113.0/24','233.252.0.0/24')]
RESOLVERS = {'1.1.1.1','1.0.0.1','8.8.8.8','8.8.4.4','9.9.9.9','149.112.112.112','208.67.222.222','208.67.220.220',
             '94.140.14.14','94.140.15.15','45.90.28.0','45.90.30.0','76.76.2.0','76.76.10.0','76.76.19.19',
             '185.228.168.9','45.11.45.11','193.110.81.0','185.253.5.0','239.255.255.250','255.255.255.255','0.0.0.0'}
for line in open(sys.argv[1], errors='replace'):
    if line.startswith('tools/check.sh:'): continue
    for m in re.finditer(r'(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])', line):
        s = m.group(1)
        try: a = ipaddress.ip_address(s)
        except ValueError: continue
        if a.is_private or a.is_loopback or a.is_multicast or a.is_link_local or a.is_reserved or a.is_unspecified: continue
        if s in RESOLVERS or any(a in n for n in ALLOW_NETS): continue
        if line.split(':',1)[0].endswith('requirements-freeze.txt'): continue
        print(line.rstrip()[:160])
PY
[ -s "$TMP/ips" ] && { bad "non-documentation public addresses:"; cat "$TMP/ips"; } || note ok "none"

echo "== private patterns ($PRIV)"
if [ ! -s "$PRIV" ]; then
  bad "private pattern file missing - create it outside the repo (see SECURITY.md)"
else
  grep -F -f <(grep -v '^[[:space:]]*\(#\|$\)' "$PRIV") "$TMP/corpus" > "$TMP/priv" || true
  [ -s "$TMP/priv" ] && { bad "private patterns found (values shown so you can fix them; do not paste this output anywhere):"; cut -c1-160 "$TMP/priv"; } \
                      || note ok "none of $(grep -vc '^[[:space:]]*\(#\|$\)' "$PRIV") patterns found"
fi

if command -v gitleaks >/dev/null; then
  gitleaks detect --no-banner --redact --no-git -s "$DIR" >/dev/null 2>&1 && note ok "gitleaks (files)" || bad "gitleaks (files): run gitleaks detect --no-git -v -s $DIR"
  [ -d "$DIR/.git" ] && { gitleaks detect --no-banner --redact -s "$DIR" >/dev/null 2>&1 && note ok "gitleaks (history)" || bad "gitleaks (history)"; }
else note skip "gitleaks not installed"; fi

echo; [ $fail = 0 ] && echo "PASS - automated checks only. Still read the export yourself." || echo "FAIL"
exit $fail
