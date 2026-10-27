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
git clone <your fork> && cd cydex
cp config/homelab.env.example config/homelab.env
```

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

It records what it applied in `config/localized.env`. **Commit that file in your fork** -
it is how a later run knows which values to replace when you change `homelab.env`.

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
| MCP client | server entries pointing at the launchers | [08-ai-ops.md](setup/08-ai-ops.md) |

### 3.4 Schedules

| Job | Runs on | Default | Change in |
|---|---|---|---|
| Firewall watchdog | Proxmox host | every 60 s, from 10 min after boot | `proxmox/watchdog/opnsense-watchdog.timer` |
| Weekly backup | Proxmox host | Sun 03:00 (+ up to 10 min) | `proxmox/backup/homelab-backup.timer` |
| Zeek Intel refresh | Zeek CT | daily 04:17 (+ up to 15 min) | `zeek/intel/zeek-intel-update.timer` |
| YARA scan | each Linux host with an agent | daily 03:30 (cron) | `wazuh/yara/deploy_yara.sh` |
| Span re-apply | Proxmox host | host boot + every firewall-VM start | event-driven, nothing to set |

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

### 3.6 Content you should edit

- **Map** (`map/model.js`): `localize.py` updates addresses, IDs and VLAN labels, but the
  device categories, names and layout are examples. Edit them for your network, then
  `npm run check && npm run render-check` ([09-network-map.md](setup/09-network-map.md)).
- **Agent policy** (`ai-ops/AGENTS.md`): adjust the approval list to the systems you run.
- **Scanner exceptions**: if you add another authorized scanner, add its address to
  `suppress_scanner.xml` / `local_rules.xml` beside `SCANNER_IP`.

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
| **Every Linux host with a Wazuh agent** | SSH / `pct enter` | `wazuh/yara/deploy_yara.sh` |

To get files onto a host or CT: `scp` to the Proxmox host, then `pct push <ctid> <src> <dst>`.
`run-on-ct.sh` runs one local script inside a CT without copying it by hand.

---

## 5. Before enabling any automation

Nothing in this repo enables a timer or an automatic action for you. Turn each one on
only after its check passes - every one of these can act on, or page about, a live system.

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
