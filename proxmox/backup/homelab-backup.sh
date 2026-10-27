#!/bin/bash
# homelab-backup.sh — encrypted vzdump of every guest to a LUKS backup drive.
# Settings: /etc/default/homelab-backup (see homelab-backup.default).
# Encryption comes from the LUKS layer underneath, not from vzdump (vzdump to a
# directory storage has no native encryption; that is a PBS feature).
#
# Safe to re-run. Refuses to start if the drive is locked, unmounted, or short
# on space.
set -euo pipefail

[ -f /etc/default/homelab-backup ] && . /etc/default/homelab-backup
STORAGE="${STORAGE:-bulk-storage}"      # Proxmox directory storage on the LUKS volume
MNT="${MNT:-/mnt/bulk-storage}"
MAPNAME="${MAPNAME:-backup-crypt}"
LUKS_DEV="${LUKS_DEV:-/dev/disk/by-id/REPLACE-part1}"
ABORT_GIB="${ABORT_GIB:-100}"           # measure your own ratio; zstd vzdump ran ~4x here
GREENBONE_VMID="${GREENBONE_VMID:-202}" # thinned harder - mostly re-downloadable feed data
GUESTS="${*:-${GUESTS:-200 201 202 203 204 205 206}}"   # override: homelab-backup.sh <id> <id> ...
LOG="/var/log/homelab-backup-$(date +%Y%m%d-%H%M%S).log"

say() { printf '\n\033[1m%s\033[0m\n' "$*" | tee -a "$LOG"; }
die() { printf '\n!! %s\n' "$*" | tee -a "$LOG" >&2; exit 1; }

LOCK=/var/lock/homelab-backup.lock
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "!! another homelab-backup.sh is already running (lock: $LOCK)." >&2
  echo "   Two concurrent runs share vzdump's /mnt/vzsnap0 and will corrupt each other." >&2
  exit 1
fi

say "Pre-flight"
[ -e "/dev/mapper/$MAPNAME" ] || die "LUKS volume not open. Run: cryptsetup open $LUKS_DEV $MAPNAME"
mountpoint -q "$MNT" || die "$MNT not mounted. Run: mount $MNT"

# encryption actually in effect?
cryptsetup status "$MAPNAME" | grep -q 'type:.*LUKS' || die "$MAPNAME is not a LUKS device"
echo "  LUKS active: $(cryptsetup status $MAPNAME | awk '/cipher:/{print $2}')" | tee -a "$LOG"

FREE_GIB=$(df -BG --output=avail "$MNT" | tail -1 | tr -dc '0-9')
echo "  free on target: ${FREE_GIB} GiB (abort threshold ${ABORT_GIB} GiB)" | tee -a "$LOG"
[ "$FREE_GIB" -ge "$ABORT_GIB" ] || die "only ${FREE_GIB} GiB free — below the ${ABORT_GIB} GiB abort threshold"

POOL=$(lvs --noheadings -o data_percent pve/data | tr -d ' ')
echo "  thin pool: ${POOL}% used" | tee -a "$LOG"

say "Backing up: $GUESTS"
echo "  mode=snapshot  compress=zstd  storage=$STORAGE" | tee -a "$LOG"

START=$(date +%s)
FAILED=""
for id in $GUESTS; do
  echo "" | tee -a "$LOG"
  echo "--- $id ---" | tee -a "$LOG"
  if vzdump "$id" --storage "$STORAGE" --mode snapshot --compress zstd \
        --notes-template '{{guestname}} {{node}} weekly' 2>&1 | tail -6 | tee -a "$LOG"; then
    echo "  OK" | tee -a "$LOG"
  else
    echo "  FAILED" | tee -a "$LOG"
    FAILED="$FAILED $id"
  fi
done
ELAPSED=$(( $(date +%s) - START ))

# Greenbone is thinned harder than everything else: it is the largest guest, and
# almost all of it is re-downloadable vulnerability feed data and container
# layers, not irreplaceable state. Keep 2, not the 3 the storage policy gives
# everyone else.
#
# The explicit zeros are load-bearing. Unspecified keep-* options inherit from
# the storage config, so `--keep-last 2` ALONE silently keeps 5 of 6 (measured
# in practice). Zero every other dimension or this does nothing.
#
# Runs BEFORE the catalog step so SHA256SUMS is built from what survives, rather
# than listing archives this prune is about to delete.
if [ -z "${GUESTS##*$GREENBONE_VMID*}" ]; then
  say "Thinning Greenbone ($GREENBONE_VMID) to keep-last=2"
  pvesm prune-backups "$STORAGE" --vmid "$GREENBONE_VMID" \
    --keep-last 2 --keep-hourly 0 --keep-daily 0 \
    --keep-weekly 0 --keep-monthly 0 --keep-yearly 0 2>&1 | tee -a "$LOG" || \
    echo "  WARN: $GREENBONE_VMID prune failed; it will just keep 3 like the others" | tee -a "$LOG"
fi

say "Checksums + catalog"
cd "$MNT/dump"
CAT="$MNT/dump/CATALOG-$(date +%Y%m%d).txt"
{
  echo "homelab encrypted backup"
  echo "date        : $(date -Is)"
  echo "host        : $(hostname)"
  echo "target      : $STORAGE ($MNT), LUKS2 over ${MAPNAME}"
  echo "encryption  : LUKS at rest; archives themselves are plain vzdump"
  echo "elapsed     : $((ELAPSED/60)) min"
  echo "retention   : keep-last=3, keep-monthly=2"
  echo ""
  printf '%-58s %12s  %s\n' "archive" "size" "sha256"
} > "$CAT"
# Retention prunes archives; this catalog has to be pruned in step with it or
# the read-back below fails on files that were deliberately deleted. That is
# otherwise the read-back fails on the first run after a prune. Surviving
# entries keep their ORIGINAL checksum (written once, at creation) so silent
# bit-rot is still detectable; only vanished files are dropped. sort -u also
# clears the duplicate lines the old append-every-run behaviour accumulated.
if [ -s "$MNT/dump/SHA256SUMS" ]; then
  BEFORE=$(wc -l < "$MNT/dump/SHA256SUMS")
  while read -r sum file; do
    [ -n "$file" ] && [ -e "$MNT/dump/$file" ] && printf '%s  %s\n' "$sum" "$file"
  done < "$MNT/dump/SHA256SUMS" | sort -u > "$MNT/dump/SHA256SUMS.keep"
  mv "$MNT/dump/SHA256SUMS.keep" "$MNT/dump/SHA256SUMS"
  AFTER=$(wc -l < "$MNT/dump/SHA256SUMS")
  [ "$BEFORE" -ne "$AFTER" ] && \
    echo "  catalog reconciled: $BEFORE -> $AFTER entries (pruned archives dropped)" | tee -a "$LOG"
fi

for f in vzdump-*.{vma.zst,tar.zst}; do
  [ -e "$f" ] || continue
  SUM=$(sha256sum "$f" | cut -d' ' -f1)
  printf '%-58s %12s  %s\n' "$f" "$(du -h "$f" | cut -f1)" "$SUM" >> "$CAT"
  # Catalogue on first sight only. Re-appending every week both duplicated
  # entries and would mask rot, by overwriting the creation-time checksum with
  # one recomputed from an already-corrupt file.
  grep -q "  $f\$" "$MNT/dump/SHA256SUMS" 2>/dev/null || echo "$SUM  $f" >> "$MNT/dump/SHA256SUMS"
done
cat "$CAT" | tee -a "$LOG"

say "Verify: re-read every archive and confirm its checksum"
cd "$MNT/dump"
EXPECT=$(wc -l < SHA256SUMS)
# `|| true` is load-bearing: sha256sum -c exits non-zero on any problem, and
# under `set -e` that killed the script HERE — before any of the messages below
# could run - a failure then paged as a bare "status=1" with nothing in the
# log to act on.
VOUT=$(sha256sum -c SHA256SUMS 2>&1) || true; echo "$VOUT" | tee -a "$LOG" >/dev/null
GOT=$(echo "$VOUT" | grep -c ': OK$') || true
if echo "$VOUT" | grep -q 'FAILED open or read'; then
  echo "$VOUT" | grep 'FAILED open or read' | tee -a "$LOG"
  die "CATALOG DRIFT — SHA256SUMS names archives that are not on disk. The backups themselves are fine; the catalog is stale. Reconcile it, do not re-run blindly."
fi
if echo "$VOUT" | grep -q ': FAILED$'; then
  echo "$VOUT" | grep ': FAILED$' | tee -a "$LOG"
  die "CHECKSUM MISMATCH — the drive did not return what was written. Do not trust these backups."
fi
# absence of FAILED is not proof of success: require one OK per archive
if [ "$GOT" -ne "$EXPECT" ] || [ "$EXPECT" -eq 0 ]; then
  die "VERIFICATION DID NOT RUN PROPERLY — expected $EXPECT OK lines, got $GOT. Treat these backups as unverified."
fi
echo "  all $GOT archives verified by read-back" | tee -a "$LOG"

say "Result"
df -h "$MNT" | tail -1 | tee -a "$LOG"
if [ -n "$FAILED" ]; then
  echo "  FAILED guests:$FAILED" | tee -a "$LOG"
  exit 1
fi
echo "  all guests backed up and verified in $((ELAPSED/60)) min" | tee -a "$LOG"
echo "  log: $LOG" | tee -a "$LOG"
echo ""
echo "  REMINDER: periodically restore one guest into an isolated bridge with networking"
echo "  disabled and a new VMID. A restored LXC duplicates IP, hostname, SSH"
echo "  host keys and Wazuh agent identity. Untested backups are not backups."
