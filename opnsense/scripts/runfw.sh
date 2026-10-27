#!/bin/sh
# Run a local shell script ON the OPNsense firewall over SSH.
# Expects an ssh_config Host alias "opnsense-fw" (see docs/setup/02-opnsense.md).
#
#   ./runfw.sh <local-script.sh>
#
# OPNsense's root shell is csh and nested quoting through ssh breaks in
# creative ways. Transferring the script and running it by path with /bin/sh
# sidesteps the whole problem.
set -e
[ -f "$1" ] || { echo "usage: $0 <local-script.sh>"; exit 2; }
BASE=$(basename "$1")
scp -q -o ConnectTimeout=15 -o BatchMode=yes "$1" opnsense-fw:/tmp/"$BASE"
ssh -o ConnectTimeout=30 -o BatchMode=yes opnsense-fw /bin/sh /tmp/"$BASE"
