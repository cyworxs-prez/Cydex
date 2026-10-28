# Configure it for your network

Everything in this repo ships set to a **fictional reference network**. This page turns
it into yours. Do it once, before any setup guide, and again whenever your addressing,
IDs or credentials change.

The short version:

1. Fill in `config/homelab.env` and run `tools/localize.py --apply` (§1-2). That covers
   every address, VLAN and guest ID **inside the repo**.
2. Set the things that `homelab.env` cannot reach - credentials, host-side settings,
   device configuration, schedules and thresholds (§3).
3. Install each component in its setup guide, from the place listed in §4.
4. Before you enable any timer or automatic action, pass its check in §5.

---

## 0. Decide what you are building

You do not need every component. Each one is independent except where noted.

| Component | Needs | Skip it and... |
|---|---|---|
| Proxmox + OPNsense + VLANs | - | (the base; required) |
| Wazuh SIEM | base | no alerting; the rules, paging and dashboards do nothing |
| Zeek sensor + span mirror | base, Wazuh for alerts | no network IDS logs or IOC matching |
| Watchdog, backup, monit | base, Wazuh for paging | no self-healing / no backups |
| Greenbone | Wazuh (for scanner demotion) | no vulnerability ranking |
| NetAlertX, Guacamole, Kali | - | nothing else depends on them |
| AI ops (MCP servers) | the systems they talk to | no agent access |
| Network map | - | no map |

Keep the guest IDs and addresses of components you skip in `homelab.env` anyway; the
values must be unique and valid even if unused.

---

## 1. Fill in the worksheet

```bash
git clone https://github.com/cyworxs-prez/Cydex.git cydex
cd cydex
umask 077
test -f config/homelab.env || cp config/homelab.env.example config/homelab.env
chmod 600 config/homelab.env
# Open config/homelab.env in your editor and save your values before continuing.
```

If you downloaded an archive, extract it and open its root directory instead of cloning.
Run the remaining commands from that directory on your admin workstation.

Keep this deployment copy private. Localization writes real addresses into tracked rules,
scripts and map data, even though `homelab.env` itself is ignored. A public fork should
retain the fictional reference values. Do not push localized changes to it.

Edit `config/homelab.env`. Every variable:

| Variable | What it is | Reference value | Must be |
|---|---|---|---|
| `TRUSTED_NET` / `_VLAN` | Admin workstation segment | 10.10.110.0/24, 110 | a /24; VLAN 2-4094 |
| `IOT_NET` / `_VLAN` | IoT segment | 10.10.120.0/24, 120 | a /24 |
| `MGMT_NET` / `_VLAN` | Hypervisor, switch, APs | 10.10.130.0/24, 130 | a /24 |
| `LAB_NET` / `_VLAN` | SOC guests | 10.10.140.0/24, 140 | a /24 |
| `DIRECT_NET` / `_VLAN` | VPN-free segment | 10.10.150.0/24, 150 | a /24 |
| `INTERNAL_SUPERNET` | One CIDR containing all five segments | 10.10.0.0/16 | contains every `_NET` |
| `PVE_HOST` | Proxmox host address | 10.10.130.10 | inside `MGMT_NET` |
| `FW_MGMT_IP` | OPNsense address on MGMT | 10.10.130.1 | |
| `WAZUH_IP` `SCANNER_IP` `NETALERTX_IP` `GUAC_IP` `ZEEK_IP` `PENTEST_IP` | LAB guest addresses | .11 .12 .13 .20 .21 .24 | |
| `FW_VMID` `WAZUH_CTID` `GREENBONE_CTID` `NETALERTX_CTID` `KALI_VMID` `GUAC_CTID` `ZEEK_CTID` | Proxmox guest IDs | 200-206 | unique, >= 100 |
| `FW_TRUNK_NETIF` | Firewall VM NIC index on the trunk (`net1` -> `1`) | 1 | |
| `ZEEK_CAPTURE_NETIF` | Zeek CT NIC index used for capture (`net1` -> `1`) | 1 | |
| `PVE_SSH` | How the workstation reaches the host | root@10.10.130.10 | key-based SSH works |
| `MAP_BIND` / `MAP_PORT` | Map web server bind address / port | 10.10.130.10 / 8088 | a MGMT address |
| `OP_VAULT` | 1Password vault name (if you use 1Password) | Homelab | no `&` in the name |

### Choosing consistent values

Pick non-overlapping private /24 subnets that do not conflict with your existing LAN,
remote-access VPN or container networks. Reserve static addresses outside DHCP pools.
The subnet octet and VLAN tag need not match. Keep a local console and a configuration
backup before changing the host bridge, firewall gateway or management segment.

For example, a fictional replacement for the reference MGMT segment is:

```ini
MGMT_NET=10.42.30.0/24
MGMT_VLAN=230
FW_MGMT_IP=10.42.30.1
PVE_HOST=10.42.30.10
PVE_SSH=root@10.42.30.10
MAP_BIND=10.42.30.10
```

This is a **partial example, not a complete env file**. If the other four segments are
also inside `10.42.0.0/16`, use that as `INTERNAL_SUPERNET` and move every LAB guest
address into your chosen `LAB_NET`. Do not change only the management rows while
leaving an incompatible supernet. Keep every guest ID and VLAN tag unique.

The examples assume `.1` for segment gateways; account for that in the firewall and
DHCP settings. Physical NIC names (`nic0`, `nic1`), bridge names, SSH keys and wireless
credentials are separate settings. Verify them on your own hardware rather than
assuming the sample names exist. The localization checker is a text-consistency check,
not proof of reachability, non-overlapping networks or a correct firewall policy.

Limits: one /24 per segment, IPv4 only, five segments. Adding a sixth segment means
editing the Wazuh segmentation rules, `zeek/config/networks.cfg` and the map by hand.

---

## 2. Localize the repo

```bash
python3 tools/localize.py            # dry run: validates homelab.env, lists files it would change
python3 tools/localize.py --apply    # writes your values
git diff                             # review every change
python3 tools/localize.py --check    # must say: OK - every file matches config/homelab.env
```

What it rewrites (about 30 files):

| Area | Files | What changes |
|---|---|---|
| Wazuh rules | `wazuh/rules/{segmentation,local,suppress_scanner,suricata_syslog,zz_audit_tuning}_rules.xml` | segment CIDRs, supernet, scanner and pentest host addresses |
| OPNsense Wazuh agent | `opnsense/wazuh-agent/ossec.conf` | manager address |
| Zeek | `zeek/config/networks.cfg`, `zeek/config/node.cfg`, `zeek/hunting/*` | segment CIDRs, capture interface, IoT prefix |
| OPNsense scripts | `opnsense/scripts/*.py`, `runfw-via-pve.sh` | segment prefixes, host/VM defaults |
| Host-side defaults | `proxmox/*/*.default`, `proxmox/watchdog/opnsense-watchdog.sh`, `proxmox/backup/homelab-backup.sh` | VM/CT IDs, gateway address, tap/veth names |
| Workstation helpers | `proxmox/scripts/run-on-ct.sh`, `wazuh/scripts/sync-rules.sh`, `ai-ops/mcp/*` | host address, CT IDs (also read from `homelab.env` at run time) |
| Map | `map/model.js`, `map/model.mjs`, `map/app.jsx`, `map/*.sh` | addresses, VLAN labels, guest IDs |
| Agent skill | `ai-ops/skills/zeek-hunting-homelab/**` | addresses, CT IDs |

What it does **not** touch: `docs/` (they keep describing the reference network - add
`--include-docs` if you want your values there too), `README.md`, `SECURITY.md`,
`config/*.example`, and everything outside the repo (§3).

It records what it applied in `config/localized.env`. Keep this file alongside the
private deployment copy: later runs need it to know which values to replace.
It contains your real network addresses and IDs, and `.gitignore` explicitly permits
tracking it. Commit it only in a private repository with appropriate access; never
commit it or the localized source files to a public fork. Keep a protected backup of
the state file if you do not use private version control.

**Changing a value later:** edit `homelab.env`, `--apply`, review, then redeploy the
affected component (copy the changed rule files to Wazuh, the changed `.default` file
to the host, and so on). Localizing the repo changes nothing on running systems.

**Pulling upstream updates:** files that come in from upstream carry the reference
values again. `--check` lists them; localize just those with
`python3 tools/localize.py --apply --from-reference <file>...`.

---

## 3. Settings that live outside `homelab.env`

### 3.1 Credentials (on the workstation)

Never in the repo. Each `config/*.env` accepts either `op://` references (resolved by the
1Password CLI at launch) or plain values (then `chmod 600` the file).

| File | Holds | Used by | How to create |
|---|---|---|---|
| `config/opnsense.env` | `OPNSENSE_URL`, `OPNSENSE_API_KEY`, `OPNSENSE_API_SECRET` | `opnsense/scripts/*`, `opnsense/monit/*`, OPNsense MCP | `cp config/opnsense.env.example config/opnsense.env`; API key from OPNsense (System > Access > Users) |
| `config/wazuh.env` | Wazuh API + indexer users/passwords | Wazuh MCP | `ai-ops/mcp/wazuh/setup-wazuh-mcp.sh` writes it (1Password + macOS), or copy the example and fill it in |
| `~/.proxmoxmcp/config.json` | Proxmox API token, SSH key path | Proxmox MCP | `ai-ops/mcp/proxmox-plus/install.sh` (1Password), or fill `config.template.json` by hand |
| `/opt/guac/.env` **on the Guacamole CT** | Postgres password, TOTP and ban settings | Guacamole compose | `cp .env.example .env`, `chmod 600`, generate the password ([11-guacamole.md](setup/11-guacamole.md#112-install)) |

1Password items the examples expect, in vault `OP_VAULT` (rename freely, then update the
references in the files above):

| Item | Fields |
|---|---|
| `opnsense-api` | `username` (API key), `credential` (API secret) |
| `proxmox-api-token` | `token name`, `credential` |
| `proxmox-mcp-ssh-key` | `private key` |
| `wazuh-mcp` | `api_password`, `indexer_password` (created by the setup script) |

The vault name is written into `config/opnsense.env.example` and
`ai-ops/mcp/proxmox-plus/{config.template.json,install.sh}` - change it there too if
yours is not `Homelab`.

**ntfy topic** (paging): set `hook_url` in `wazuh/integrations/ossec-integration.xml`
**on the Wazuh manager only** - never commit your topic. Anyone who knows it can read
your alerts.

### 3.2 Host-side settings (on the Proxmox host)

Each installer (`proxmox/{watchdog,span,backup}/install.sh`) copies its `.default` file to `/etc/default/` **only if none exists**, so
your edits survive re-installs. After `localize.py`, the copies in the repo already
carry your IDs and addresses - review them before installing.

| File on the host | From | Set |
|---|---|---|
| `/etc/default/opnsense-watchdog` | `proxmox/watchdog/opnsense-watchdog.default` | `VMID`, `GW` (an OPNsense address the host reaches directly), `FAIL_THRESHOLD` 5, `COOLDOWN` 1800 s, `MAX_PER_DAY` 3, `HEARTBEAT_EVERY` 60 |
| `/etc/default/zeek-span` | `proxmox/span/zeek-span.default` | `FW_VMID`, `MIRROR_SRC` (`tap<FW_VMID>i<n>`), `MIRROR_DST` (`veth<ZEEK_CTID>i<n>`), `WAIT_SECS` |
| `/etc/default/homelab-backup` | `proxmox/backup/homelab-backup.default` | `LUKS_DEV` (**must** set: `ls -l /dev/disk/by-id/`), `STORAGE`, `MNT`, `MAPNAME`, `ABORT_GIB`, `GUESTS`, `GREENBONE_VMID` |
| `/etc/systemd/system/homelab-backup.service` | `proxmox/backup/` | `RequiresMountsFor=` must equal `MNT` |
| `/etc/network/interfaces` | written by hand ([01-proxmox.md](setup/01-proxmox.md)) | NIC names, `bridge-vids` = your VLANs, MGMT address |
| `/etc/resolv.conf` | by hand | `nameserver <FW_MGMT_IP>` only |
| Proxmox storage | by hand ([06-resilience.md](setup/06-resilience.md)) | LUKS volume + directory storage named `STORAGE` |

Check the interface names before writing `zeek-span`: `ip -br link | grep -E 'tap|veth'`.

### 3.3 Settings in device UIs (not in the repo)

| Where | What | Guide |
|---|---|---|
| OPNsense | VLANs, interface assignment, Kea subnets/reservations, firewall rule ladders, NAT port-forward for IoT DNS, Unbound + blocklists, Suricata, WireGuard, API user, qemu-guest-agent plugin, Wazuh agent plugin | [02-opnsense.md](setup/02-opnsense.md) |
| Switch / AP controller | VLAN-only networks, port profiles, SSIDs and passphrases | [03-switching-wifi.md](setup/03-switching-wifi.md) |
| Wazuh manager `ossec.conf` | ntfy `<integration>`, syslog receiver | [04-wazuh.md](setup/04-wazuh.md) |
| Greenbone | admin password in `/root/.gbpw` (CT only) | [07-greenbone.md](setup/07-greenbone.md) |
| NetAlertX UI | password (default `123456`), `SCAN_SUBNETS` = LAB only, `TIMEZONE`, optional ICMP devices and ntfy topic. Stored in `/opt/netalertx/data/config/app.conf` | [10-netalertx.md](setup/10-netalertx.md) |
| Guacamole UI | change `guacadmin` password (Preferences page), enroll TOTP, named admin, connections | [11-guacamole.md](setup/11-guacamole.md) |
| Guacamole CT Wazuh agent `ossec.conf` | Docker log `<localfile>` from `wazuh/agent/guacamole-localfile.xml` | [11-guacamole.md](setup/11-guacamole.md#115-ship-its-logs-to-wazuh) |
| OPNsense LAB rules (only if you use NetAlertX ICMP) | pass ICMP from `NETALERTX_IP` to an alias of named devices, above seq 20 | [10-netalertx.md](setup/10-netalertx.md#105-optional-status-for-devices-on-other-segments) |
| MCP client | server entries pointing at the launchers | [08-ai-ops.md](setup/08-ai-ops.md) |

### 3.4 Schedules

| Job | Runs on | Default | Change in |
|---|---|---|---|
| Firewall watchdog | Proxmox host | every 60 s, from 10 min after boot | `proxmox/watchdog/opnsense-watchdog.timer` |
| Weekly backup | Proxmox host | Sun 03:00 (+ up to 10 min) | `proxmox/backup/homelab-backup.timer` |
| Zeek Intel refresh | Zeek CT | daily 04:17 (+ up to 15 min) | `zeek/intel/zeek-intel-update.timer` |
| YARA scan | each Linux host with an agent | daily 03:30 (cron) | `wazuh/yara/deploy_yara.sh` |
| Span re-apply | Proxmox host | host boot + every firewall-VM start | event-driven, nothing to set |
| NetAlertX ARP scan / ICMP checks | NetAlertX CT | every 5 min (suggested) | NetAlertX UI: `ARPSCAN_RUN_SCHD`, `ICMP_RUN_SCHD` |

Keep heavy jobs apart: backup, YARA, Intel refresh and Greenbone scans should not overlap.

### 3.5 Thresholds and tuning

| Setting | Default | File |
|---|---|---|
| Wazuh paging level | 10 | `wazuh/integrations/ossec-integration.xml` (`<level>`) |
| Sustained cross-zone probing | 12 blocks / 300 s per source | `wazuh/rules/segmentation_rules.xml` (rule 100845) |
| Suricata restart (monit) | > 3500 MB for 3 cycles, or process missing | `opnsense/monit/monit-suricata-restart.py` (`TESTS`) |
| Intel sanity floor | 500 indicators | `zeek/intel/zeek-intel-update.sh` (`FLOOR`) |
| Intel feeds / exclusions / your own IOCs | abuse.ch + Tor | `zeek/intel/zeek-intel-update.sh`, `domain-exclude.txt`, `local-iocs.dat` (on the CT) |
| YARA scan targets | `/tmp /var/tmp /dev/shm /root /home /usr/local/*` | `wazuh/yara/deploy_yara.sh` (`TARGETS`) |
| Backup free-space floor | 100 GiB | `/etc/default/homelab-backup` (`ABORT_GIB`) |
| Watchdog guards | see §3.2 | `/etc/default/opnsense-watchdog` |
| Proxmox MCP command allow-list | read-mostly | `ai-ops/mcp/proxmox-plus/config.template.json` (`command_policy`) |
| Guacamole brute-force ban | 5 failures -> 300 s | `/opt/guac/.env` (`BAN_*`); keep above rule 100932's `frequency` |
| Guacamole failed-login page | 3 in 300 s | `wazuh/rules/zz_audit_tuning.xml` (rule 100932) |

### 3.6 Content you should edit

- **Map** (`map/model.js`): `localize.py` updates addresses, IDs and VLAN labels, but the
  device categories, names and layout are examples. Edit them for your network, then
  `npm run check && npm run render-check` ([09-network-map.md](setup/09-network-map.md)).
- **Agent policy** (`ai-ops/AGENTS.md`): adjust the approval list to the systems you run.
- **Scanner exceptions**: if you add another authorized scanner, add its address to
  `suppress_scanner.xml` / `local_rules.xml` beside `SCANNER_IP`.
- **Periodic monitoring hosts**: add any host that polls on a timer to `SKIP_SRC` in the
  hunting skill's beacon query (NetAlertX is already there).

---

## 4. Where each command runs

| Place | How you get there | What runs there |
|---|---|---|
| **Workstation** (your clone) | local shell | `tools/*`, `opnsense/scripts/*`, `opnsense/monit/*`, `wazuh/scripts/sync-rules.sh`, `map/*`, `ai-ops/mcp/*`, MCP clients |
| **Proxmox host** | `ssh $PVE_SSH` | `proxmox/watchdog/install.sh`, `proxmox/span/install.sh`, `proxmox/backup/install.sh`, `map/install-map-server.sh`, `qm` / `pct` commands |
| **OPNsense** | `opnsense/scripts/runfw-via-pve.sh <script>` (guest agent) or SSH | read-only diagnostics; configuration is done in its UI or API |
| **Wazuh CT** | `pct enter $WAZUH_CTID` on the host, or `proxmox/scripts/run-on-ct.sh` | rule/decoder install, `wazuh-analysisd -t`, `wazuh/scripts/check-ntfy.sh`, `wazuh/dashboards/*.py` |
| **Zeek CT** | `pct enter $ZEEK_CTID` | `zeek/intel/install.sh`, `zeek/hunting/*`, `zeekctl` |
| **Greenbone CT** | `pct enter $GREENBONE_CTID` | `greenbone/vuln_prioritize.py` |
| **NetAlertX CT** | `pct enter $NETALERTX_CTID` | `docker compose` in `/opt/netalertx` (`lab/netalertx/`) |
| **Guacamole CT** | `pct enter $GUAC_CTID` | `docker compose` in `/opt/guac` (`lab/guacamole/`), schema generation |
| **Every Linux host with a Wazuh agent** | SSH / `pct enter` | `wazuh/yara/deploy_yara.sh` |

To get files onto a host or CT: `scp` to the Proxmox host, then `pct push <ctid> <src> <dst>`.
`run-on-ct.sh` runs one local script inside a CT without copying it by hand.

---

## 5. Before enabling any automation

Some installers perform a check and then enable a timer, cron job or live action in the
same run (see the Enable column). Inspect and configure them before running them.
For separately enabled services, pass the check first. Every entry can act on, or page
about, a live system.

| Automation | Check first | Enable | Proof it works |
|---|---|---|---|
| Firewall watchdog | `DRY_RUN=1 /usr/local/sbin/opnsense-watchdog.sh` logs nothing alarming; `qm agent $FW_VMID ping` succeeds; `GW` answers ping from the host | `systemctl enable --now opnsense-watchdog.timer` | `journalctl -t opnsense-watchdog` shows a heartbeat within ~1 h |
| Span mirror (boot) | `/usr/local/sbin/zeek-span-apply.sh` prints `span re-applied`; Zeek `capture_loss.log` shows `acks > 0` | `systemctl enable zeek-mirror.service` | reboot the host (or wait for the next one) and re-check `acks` |
| Span mirror (VM restart) | same as above | `qm set $FW_VMID --hookscript local:snippets/zeek-span.pl` | `qm reboot $FW_VMID` in a maintenance window, then `journalctl -t zeek-span` |
| Weekly backup | LUKS volume open and mounted; `systemctl start homelab-backup` completes; newest `/var/log/homelab-backup-*.log` ends "verified" | `systemctl enable --now homelab-backup.timer` | **restore one guest** to a new ID on an isolated bridge |
| Zeek Intel refresh | first run in `install.sh` logs `REFRESH OK` (`journalctl -t zeek-intel`) | done by `install.sh` | Wazuh rule 100908 appears daily |
| ntfy paging | integration script present and executable (`check-ntfy.sh`) | restart the Wazuh manager | trigger a level-10 rule and receive it on your phone |
| Wazuh rules | `wazuh-analysisd -t` passes; `localize.py --check` OK | restart the Wazuh manager | `wazuh-logtest` with a sample line; then watch `alerts.log` |
| Monit Suricata restart | `monit-suricata-restart.py` read-back shows both tests attached | done by the script (it writes to OPNsense) | Services > Monit > Status shows Suricata monitored |
| YARA nightly scan | the script's test-compile prints `COMPILE-OK` | done by the script (cron) | Wazuh daily heartbeat rule fires the next morning |
| MCP servers (agent access) | launcher starts by hand; a **read-only** call returns live data | add to the MCP client | put `ai-ops/AGENTS.md` where the agent works **before** first use |
| Scheduled agent runs | everything above, plus the agent policy | your scheduler | keep unattended runs read-only |
| NetAlertX scheduled scans | UI password changed; `SCAN_SUBNETS` holds LAB only; ICMP devices covered by a LAB pass rule | `ARPSCAN_RUN` / `ICMP_RUN` = `schedule` | 24 h later: zero Wazuh 100840 hits with `srcip` = `NETALERTX_IP` |
| Guacamole (before saving any connection) | `guacadmin` password changed and TOTP enrolled; agent `<localfile>` added | add connections | 4 bad logins page 100932 ([11.6](setup/11-guacamole.md#116-verify)) |

---

## 6. Whole-stack verification

Run after the first full install and after any change:

```bash
set -a; . config/homelab.env; set +a                     # load your values into this shell
python3 tools/localize.py --check                        # repo matches homelab.env
ssh "$PVE_SSH" 'bridge vlan show dev nic1'               # every VLAN on the trunk
ssh "$PVE_SSH" 'systemctl list-timers opnsense-watchdog.timer homelab-backup.timer'
ssh "$PVE_SSH" "pct exec $WAZUH_CTID -- /var/ossec/bin/agent_control -l"   # agents Active
ssh "$PVE_SSH" "pct exec $ZEEK_CTID -- tail -1 /opt/zeek/logs/current/capture_loss.log"
python3 opnsense/scripts/opn_api.py                      # API reachable, no secret printed
python3 opnsense/scripts/iotdns-verify.py                # IoT DNS enforcement
```

From one client per SSID: correct /24 lease, DNS via the gateway, expected egress address
(`curl https://api.ipify.org`), and blocked access to segments it should not reach.


## 7. Troubleshooting and keeping your deployment private

| Symptom | Check first |
|---|---|
| Localizer reports a missing config | Run from the extracted/cloned project, create `config/homelab.env` from its example, then edit it |
| Localizer reports invalid values | All five /24s, enclosing supernet, numeric unique VLANs/guest IDs, management host in MGMT; review the worksheet before applying |
| Localizer passes but the network is unchanged | It only edits local files. Copy/install the affected settings on their target hosts and configure the device UIs |
| SSH to Proxmox fails | Workstation segment, management access rules, `PVE_SSH`, route and SSH key; the reference DIRECT segment is isolated |
| Client joins Wi-Fi but has no DHCP/DNS | AP tag, allowed VLANs on both trunks, firewall interface assignment and DHCP scope |
| Zeek runs but logs no traffic | Actual tap/veth names, capture NIC, mirror filters, fresh log timestamps and controlled test traffic |
| Reinstall leaves old values on a host | Installers preserve existing `/etc/default/` files; review and update those files explicitly |
| Map still shows example devices | Localization changes addressing, not the inventory or layout; edit the private `map/model.js` and rebuild |

A successful install is not a deployment test. Use one owned test client per segment,
confirm allowed and blocked paths, verify fresh telemetry and paging, and test restores
on an isolated guest before relying on the system.

`tools/check.sh` checks a **public release**, not a configured private deployment.
Real env files and private-pattern matches are expected to fail its packaging gate.
Do not disable the gate or remove private patterns to make a localized copy pass.
Keep an untouched public reference and export that separately; never publish synced
live rules, credential files, real maps or screenshots without another privacy review.
