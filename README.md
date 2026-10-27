# homelab-soc

A segmented home network with a working blue-team stack on one Proxmox host:
OPNsense firewall/IDS, Wazuh SIEM, a Zeek sensor fed by a SPAN mirror, threat-intel
matching, vulnerability scanning, phone paging, self-healing watchdogs, and an
AI-operations layer (MCP servers + an agent policy) that lets an LLM agent run read-only
health checks and hunts safely.

The tooling was built and run on a real home network, then generalised: every address,
ID and device in this repo belongs to a **fictional reference network**.

![Topology](docs/img/topology.png)

## What you get

| Layer | Component | What it does |
|---|---|---|
| Hypervisor | Proxmox VE 9 | Single node. VLAN-aware bridge carries the trunk to the firewall VM |
| Edge | OPNsense (VM) | Routing between 5 VLANs, Kea DHCP, Unbound + DNSBL, forced DNS for IoT, Suricata (IDS mode) |
| Segmentation | 5 VLANs | TRUSTED / IoT / MGMT / LAB / DIRECT (VPN-free) - see [architecture](docs/architecture.md) |
| SIEM | Wazuh all-in-one (LXC) | Agents, OPNsense filterlog + Suricata EVE, ~100 custom rules, dashboards |
| Network sensor | Zeek (LXC) | Full-trunk SPAN via `tc mirred`, JSON logs, Intel framework (~20k daily IOCs) |
| Detection content | Wazuh rules | Segmentation violations, Zeek intel, Sigma->Wazuh, YARA, collector health |
| Paging | ntfy | Wazuh level >= 10 -> phone |
| Vuln mgmt | Greenbone (LXC) | Scans ranked by CISA KEV + FIRST EPSS |
| Self-healing | systemd on the host | Firewall-VM liveness watchdog, span re-apply hookscript, monit on OPNsense |
| Backup | vzdump -> LUKS drive | Weekly, checksummed, read-back verified, pages on failure |
| AI ops | MCP + `AGENTS.md` | OPNsense / Proxmox / Wazuh MCP servers, a patched MCP, an agent safety policy |
| Docs | Live network map | Isometric map rebuilt from `map/model.js`, served from the host |

## Design rules that shaped it

1. **Verify by reading back.** An API that returns `saved` may have saved nothing. Every
   write in this repo is followed by a read.
2. **Quiet is not the same as healthy.** Every collector has a heartbeat or a
   silence-detection rule, so "no alerts" and "sensor dead" look different.
3. **Runtime state must be persistent.** Anything that has to survive a reboot is a systemd
   unit or hookscript that checks it actually applied.
4. **Credentials never touch the repo.** `op://` references, resolved at launch by `op run`.

The full list: [docs/lessons-learned.md](docs/lessons-learned.md).

## Setup

Follow in order. Each guide lists what to do, where, and how to verify it.

| # | Guide | Result |
|---|---|---|
| - | **[Configure for your network](docs/configure.md)** | **Your values everywhere; where every setting lives; pre-automation checks** |
| 0 | [Prerequisites](docs/setup/00-prerequisites.md) | Hardware, accounts, workstation tools |
| 1 | [Proxmox host](docs/setup/01-proxmox.md) | VLAN-aware bridge, guests created |
| 2 | [OPNsense + VLANs](docs/setup/02-opnsense.md) | Routing, DHCP, firewall ladder, forced DNS, DNSBL, Suricata |
| 3 | [Wi-Fi / switch](docs/setup/03-switching-wifi.md) | SSIDs mapped to VLANs, trunk ports |
| 4 | [Wazuh](docs/setup/04-wazuh.md) | SIEM, agents, custom rules, ntfy paging, dashboards |
| 5 | [Zeek sensor](docs/setup/05-zeek.md) | SPAN mirror, Intel feeds, hunting scripts |
| 6 | [Self-healing + backup](docs/setup/06-resilience.md) | Watchdog, span hookscript, monit, weekly encrypted backup |
| 7 | [Vulnerability scanning](docs/setup/07-greenbone.md) | Greenbone + KEV/EPSS ranking |
| 8 | [AI operations](docs/setup/08-ai-ops.md) | MCP servers, MCP patch, agent policy, scheduled read-only reviews |
| 9 | [Network map](docs/setup/09-network-map.md) | Isometric map served from the host |

Reference: [architecture](docs/architecture.md) · [detection catalog](docs/detection-catalog.md) ·
[lessons learned](docs/lessons-learned.md) · [runbooks](docs/runbooks/)

## Repo layout

```
config/        *.env.example - copy to *.env (git-ignored) and edit
proxmox/       host-side: watchdog, span mirror unit + hookscript, backup, helpers
opnsense/      API helper, read-only verification scripts, monit setup, Wazuh agent config
wazuh/         rules, decoders, ntfy integration, YARA, Sigma converter, dashboards
zeek/          sensor config, Intel framework + feed updater, hunting scripts
greenbone/     KEV/EPSS prioritisation
ai-ops/        MCP launchers/installers, OPNsense MCP patch, AGENTS.md policy, hunting skill
map/           isometric network map (isoflow) + layout/render checks
docs/          setup guides, architecture, lessons learned, runbooks
tools/         localize.py - apply your values; check.sh / export-release.sh - release gate
```

## Adapting it

Everything ships set to a fictional reference layout (`10.10.{110,120,130,140,150}.0/24`,
firewall VM 200, Wazuh CT 201, Zeek CT 206). **Start with [docs/configure.md](docs/configure.md):**
fill in `config/homelab.env`, run `python3 tools/localize.py --apply` to write your values
into the rules, sensor config, scripts and map, then set the host-side, credential and
schedule settings it lists.

## Status and scope

A personal lab, shared as a reference. It is not a product and carries no support
promise. Read every script before running it: several write to live systems, and
[`ai-ops/AGENTS.md`](ai-ops/AGENTS.md) lists which.

## License

MIT - see [LICENSE](LICENSE), with these exceptions (details in [NOTICE](NOTICE)):

- `wazuh/rules/sigma_zeek_rules.xml` is generated from [SigmaHQ](https://github.com/SigmaHQ/sigma)
  rules and is covered by the Detection Rule License (DRL) 1.1; each rule carries its
  Sigma ID and source file.
- `ai-ops/skills/zeek-hunting-homelab/` is adapted from an Apache-2.0 skill
  (mukul975/anthropic-cybersecurity-skills) and keeps its own LICENSE.
- Third-party tools (Wazuh, Zeek, OPNsense, isoflow, the MCP servers) are under their own
  licenses and are not vendored here.
