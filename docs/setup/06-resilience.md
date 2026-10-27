# 6. Self-healing and backup

Every mechanism here logs through `logger -t <tag>` into journald, where the Proxmox
host's Wazuh agent picks it up, and `wazuh/rules/{watchdog,span,backup}_rules.xml` turn it
into alerts. Without those rules the messages land in the archive and stop.

## 6.1 Firewall-VM liveness watchdog (Proxmox host)

```bash
# on the Proxmox host, from a copy of proxmox/watchdog/
bash install.sh
vi /etc/default/opnsense-watchdog                     # VMID, GW
DRY_RUN=1 /usr/local/sbin/opnsense-watchdog.sh        # must log "healthy"/nothing alarming
systemctl enable --now opnsense-watchdog.timer
```

| Behaviour | Detail |
|---|---|
| Probes (every 60s) | Guest agent ping, ICMP to the gateway, TCP 53 - **all three** must fail to count |
| Recovers after | 5 consecutive failures: `qm shutdown --forceStop` then `qm start` (never `qm stop`) |
| Guards | Stands down if the VM is stopped or locked (backup/snapshot); 30-min cooldown; max 3 recoveries/day, then refuses and logs "needs a human" |
| Heartbeat | One info line per ~hour so a dead watchdog is visible |
| Alerts | 100860-100870: probes failing 7 (no page), recovering 10, start-failed / no-return / daily-cap 12 |

Two traps the rules already handle: every message arrives twice (logger + the unit's
stdout), and systemd's own unit lines contain the tag string but carry
`program_name=systemd`. Anchor on the program name.

## 6.2 SPAN re-apply

Covered in [05-zeek.md](05-zeek.md#52-feed-it-the-span-mirror-proxmox-host). Rules
100890-100892.

## 6.3 Monit on OPNsense

Covered in [02-opnsense.md](02-opnsense.md#28-monit-restart-suricata-on-runaway-memory).

## 6.4 Weekly encrypted backup

1. Encrypt the USB drive with LUKS2, open it as `backup-crypt`, make a filesystem, mount it
   at `/mnt/bulk-storage`, and add it as a Proxmox **directory** storage (`bulk-storage`,
   content: backups, retention keep-last=3, keep-monthly=2).
2. Install:
   ```bash
   install -m 750 proxmox/backup/homelab-backup.sh      /usr/local/sbin/
   install -m 644 proxmox/backup/homelab-backup.default /etc/default/homelab-backup   # edit LUKS_DEV
   install -m 644 proxmox/backup/homelab-backup.{service,timer} /etc/systemd/system/
   systemctl daemon-reload && systemctl enable --now homelab-backup.timer
   ```
3. First run by hand: `systemctl start homelab-backup` and read the newest
   `/var/log/homelab-backup-*.log`.

| Behaviour | Detail |
|---|---|
| Pre-flight | Refuses if the LUKS volume is not open, not mounted, or below the free-space floor; single-run lock |
| Backup | `vzdump --mode snapshot --compress zstd` per guest |
| Integrity | SHA256 recorded **once** at creation, catalog pruned in step with retention, every archive re-read and checked |
| Alerts | Outcome logged by `ExecStopPost`; rules 100880-100882 page on failure with the reason |

Encryption is the LUKS layer - vzdump to a directory storage is not itself encrypted.

**Untested backups are not backups.** Periodically restore one guest to a new VMID on an
isolated bridge with networking disabled (a restored LXC duplicates IP, hostname, SSH host
keys and Wazuh agent identity).

## Verify

```bash
systemctl list-timers opnsense-watchdog.timer homelab-backup.timer
journalctl -t opnsense-watchdog -n 3 --no-pager
journalctl -t vm200-span -n 3 --no-pager
```
