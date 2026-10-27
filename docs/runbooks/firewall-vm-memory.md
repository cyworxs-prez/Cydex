# Runbook — bump OPNsense (VM200) 6 GB -> 10 GB

**Downtime: 60-90 seconds. Internet, DNS, DHCP and all inter-VLAN routing stop during this.**
Do it when you can tolerate that. Everything comes back on its own (`onboot: 1`).

Check host headroom first: `free -g` on the Proxmox host. Leave at least 2-3 GB for the host itself.

---

## Option A — Proxmox web UI

1. Open the Proxmox UI -> left tree -> **pve** -> **200 (opnsense)**
2. **Snapshots** -> **Take Snapshot**
   - Name: `pre-mem-bump`
   - Leave "Include RAM" unchecked
   - Click **Take Snapshot**, wait for it to finish
3. **Hardware** -> double-click **Memory**
   - Set to `10240` (MiB)
   - **OK**
   - It will now show under **Pending Changes** — this is expected, memory cannot change on a running VM
4. Top right -> **Shutdown** (the dropdown next to it)
   - Use **Shutdown**, NOT **Stop**. Stop is a hard power cut and risks filesystem damage on OPNsense.
5. Wait until Status shows **stopped** (up to ~2 min)
6. Top right -> **Start**
7. Wait ~60s, then confirm you have internet on a client

## Option B — pve shell (fastest, recommended)

```bash
qm snapshot 200 pre-mem-bump --description "before 6->10GB"
qm set 200 --memory 10240
qm reboot 200 --timeout 120
qm config 200 | grep -E '^memory'   # should print: memory: 10240
```

`qm reboot` does a graceful ACPI shutdown, waits, then starts the VM again — and its own
help text says **"Applies pending changes."** (Proxmox VE 9.)
One command, and there is no window where the VM is left stopped because you forgot to
start it.

Equivalent long form if you prefer to watch each step:
```bash
qm shutdown 200 --timeout 120
qm status 200                      # repeat until it says: status: stopped
qm start 200
```

---

## Verify afterwards

From the pve shell:
```bash
qm config 200 | grep memory        # memory: 10240
```
In the OPNsense UI: **Lobby -> Dashboard**, the memory gauge total should read ~10 GB
(it reports slightly less than 10240 — around 10.1 GB — that is normal).

## If it does not come back

1. `qm start 200` (in case shutdown left it stopped)
2. If it starts but there is no network, open the **Console** in the Proxmox UI and check
   OPNsense booted to its menu
3. Roll back memory only: `qm set 200 --memory 6144 && qm shutdown 200 --timeout 120 && qm start 200`
4. Full rollback to the snapshot: `qm rollback 200 pre-mem-bump`

## The trap: which "reboot" actually works

| Action | QEMU process | Picks up new memory? |
|---|---|---|
| `qm reboot 200` (or GUI **Reboot**) | exits and relaunches | **YES** |
| `qm shutdown 200` then `qm start 200` | exits and relaunches | **YES** |
| Reboot from *inside* OPNsense (its UI, or `reboot` at its shell) | **keeps running** | **NO** |
| `qm reset 200` | **keeps running** | **NO** |
| `qm stop 200` then `qm start 200` | exits and relaunches | yes, but hard power cut — don't |

The VM's hardware is read once, when the QEMU process is launched. A reboot *inside* the
guest is a soft reset within that same process, so OPNsense comes back still holding 6 GB
and the change sits as "pending" forever. Same for `qm reset` — that is a QEMU
system_reset, the process never exits.

## Do not

- Do not use `qm stop 200` — per its own help text, "the qemu process will exit immediately.
  This is akin to pulling the power plug of a running computer and may damage the" guest
- Do not reboot from inside OPNsense and expect the memory change to apply
- Do not go above 12288 — the host needs headroom for the other guests
