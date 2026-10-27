<div align="center">
  <img src="docs/img/logo.svg" alt="Cydex logo" width="140"/>
</div>

<h1 align="center">Cydex</h1>

<p align="center"><strong>A segmented home network with a working blue-team stack on one Proxmox host - firewall/IDS, SIEM, network sensor, threat intel, paging, self-healing, encrypted backups, and an AI-operations layer with guardrails.</strong></p>

<p align="center">
  <img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue">
  <img alt="Proxmox VE 9" src="https://img.shields.io/badge/Proxmox_VE-9-E57000">
  <img alt="OPNsense" src="https://img.shields.io/badge/OPNsense-firewall%20%2B%20IDS-D94F00">
  <img alt="Wazuh 4.14" src="https://img.shields.io/badge/Wazuh-4.14-3595F9">
  <img alt="Zeek" src="https://img.shields.io/badge/Zeek-sensor-4B5563">
  <img alt="MCP" src="https://img.shields.io/badge/MCP-OPNsense%20%7C%20Proxmox%20%7C%20Wazuh-7C3AED">
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> |
  <a href="docs/configure.md">Configure</a> |
  <a href="#components">Components</a> |
  <a href="#safety-model">Safety</a> |
  <a href="#documentation">Docs</a> |
  <a href="docs/detection-catalog.md">Detections</a> |
  <a href="docs/lessons-learned.md">Lessons</a>
</p>

[![Architecture: segments route through OPNsense; a SPAN mirror feeds Zeek; agents and syslog feed Wazuh, which pages via ntfy; host jobs report to Wazuh; MCP servers give an AI agent read-first access](docs/img/architecture.svg)](docs/img/architecture.svg)

Every address, ID and device in this repo belongs to a **fictional reference network**.
[`tools/localize.py`](docs/configure.md#2-localize-the-repo) rewrites them to yours in one step.

## Why this exists

Most homelab security guides stop at "install Wazuh". This one covers what happens after:
sensors that silently go blind, APIs that report `saved` and change nothing, backups
nobody has restored, and alerts that drown in broadcast noise.

- **Every control is checked, not assumed** - each collector has a heartbeat or a
  silence-detection rule, so "no alerts" and "sensor dead" look different.
- **Every write is read back** - including the patched OPNsense MCP server, whose upstream
  version reports success for writes it discards.
- **Automation is earned** - nothing enables itself; each timer has a check to pass first.

## What makes it different

| Priority | How the repo handles it |
| --- | --- |
| Detection that pages for the right things | ~100 custom Wazuh rules: segmentation violations, Zeek IOC matches by confidence, Sigma-converted Zeek rules, YARA, and collector health - tuned around one paging threshold |
| Sensors that stay honest | SPAN mirror re-applied at boot and on VM restart, verified, and alerted on; capture-loss *and* total-blindness detection |
| Self-healing with limits | Firewall watchdog needs three independent probes to fail, with cooldown and a daily cap; monit restarts Suricata only on runaway memory |
| Backups you can trust | Weekly encrypted vzdump, checksums recorded once, every archive re-read, failure pages with the reason |
| AI access with guardrails | MCP servers for OPNsense, Proxmox and Wazuh, plus an agent policy (`AGENTS.md`): read-first, approval list, change gate |
| One config file | `config/homelab.env` + `tools/localize.py` set addresses, VLANs and guest IDs everywhere |
| Safe to publish | `tools/check.sh` and `tools/export-release.sh` gate releases: secrets, private patterns, git objects, images |

## Quick Start

1. **Check prerequisites** - one x86 host with 2 NICs (8+ cores, 24 GB+ to run everything),
   a managed switch, multi-SSID APs. [Details](docs/setup/00-prerequisites.md).
2. **Make it yours**
   ```bash
   git clone <your fork> && cd cydex
   cp config/homelab.env.example config/homelab.env     # your subnets, VLANs, IPs, guest IDs
   python3 tools/localize.py --apply                    # writes them into rules, configs, scripts, map
   python3 tools/localize.py --check                    # OK - every file matches
   ```
   Then set the credentials, host-side files and schedules listed in
   [docs/configure.md](docs/configure.md).
3. **Build the base** - [Proxmox](docs/setup/01-proxmox.md) -> [OPNsense + VLANs](docs/setup/02-opnsense.md) -> [switch / Wi-Fi](docs/setup/03-switching-wifi.md).
4. **Add the SOC** - [Wazuh](docs/setup/04-wazuh.md) -> [Zeek](docs/setup/05-zeek.md) -> [self-healing + backup](docs/setup/06-resilience.md) -> [Greenbone](docs/setup/07-greenbone.md).
5. **Turn on automation only after its check passes** - [configure.md §5](docs/configure.md#5-before-enabling-any-automation).
6. **Optional** - [AI operations](docs/setup/08-ai-ops.md), [network map](docs/setup/09-network-map.md).

## Components

### Edge and segmentation

| Component | Built on | What this repo adds | Guide |
| --- | --- | --- | --- |
| Hypervisor | [Proxmox VE](https://www.proxmox.com/en/proxmox-virtual-environment) | VLAN-aware bridge layout, guest plan, helper scripts that run code in guests without quoting bugs | [01](docs/setup/01-proxmox.md) |
| Firewall / router | [OPNsense](https://github.com/opnsense/core) ![stars](https://img.shields.io/github/stars/opnsense/core?style=flat) | Per-segment rule ladder, forced DNS for IoT, DoT/DoQ block, VPN egress for one segment only | [02](docs/setup/02-opnsense.md) |
| IDS | [Suricata](https://github.com/OISF/suricata) ![stars](https://img.shields.io/github/stars/OISF/suricata?style=flat) | Memory-safe settings (Hyperscan + Low profile), monit restart, EVE to Wazuh | [02](docs/setup/02-opnsense.md#26-suricata-ids) |
| Wi-Fi / switching | any 802.1Q gear | SSID-to-VLAN plan, the two-trunk rule for adding VLANs | [03](docs/setup/03-switching-wifi.md) |

### Detection and response

| Component | Built on | What this repo adds | Guide |
| --- | --- | --- | --- |
| SIEM | [Wazuh](https://github.com/wazuh/wazuh) ![stars](https://img.shields.io/github/stars/wazuh/wazuh?style=flat) | ~100 rules in 13 files, OPNsense + Suricata decoders, dashboards | [04](docs/setup/04-wazuh.md) · [catalog](docs/detection-catalog.md) |
| Network sensor | [Zeek](https://github.com/zeek/zeek) ![stars](https://img.shields.io/github/stars/zeek/zeek?style=flat) | Verified SPAN mirror, daily Intel feeds (abuse.ch + Tor) with a sanity floor, hunting scripts | [05](docs/setup/05-zeek.md) |
| Detection content | [SigmaHQ](https://github.com/SigmaHQ/sigma) ![stars](https://img.shields.io/github/stars/SigmaHQ/sigma?style=flat) · [YARA-Forge](https://github.com/YARAHQ/yara-forge) | Faithful-or-skip Sigma -> Wazuh converter; YARA deploy with test-compile and heartbeat | [04](docs/setup/04-wazuh.md#46-sigma---wazuh-zeek) |
| Paging | [ntfy](https://github.com/binwiederhier/ntfy) ![stars](https://img.shields.io/github/stars/binwiederhier/ntfy?style=flat) | Wazuh integration script, level-based priority | [04](docs/setup/04-wazuh.md#44-paging-ntfy) |
| Vulnerability scanning | [Greenbone Community](https://github.com/greenbone) | Findings ranked by CISA KEV + FIRST EPSS; scanner noise demoted, not paged | [07](docs/setup/07-greenbone.md) |

### Resilience

| Component | What it does | Guide |
| --- | --- | --- |
| Firewall watchdog | Recovers a hung firewall VM - three independent probes, cooldown, daily cap, hourly heartbeat | [06](docs/setup/06-resilience.md#61-firewall-vm-liveness-watchdog-proxmox-host) |
| Span keeper | Re-applies and verifies the Zeek mirror at boot and after every firewall-VM start | [05](docs/setup/05-zeek.md#52-feed-it-the-span-mirror-proxmox-host) |
| Weekly backup | Encrypted vzdump, checksum catalog, full read-back, pages on failure | [06](docs/setup/06-resilience.md#64-weekly-encrypted-backup) |

### AI operations

| Component | Built on | What this repo adds | Guide |
| --- | --- | --- | --- |
| OPNsense MCP | [opnsense-mcp-server](https://github.com/Pixelworlds/opnsense-mcp-server) ![stars](https://img.shields.io/github/stars/Pixelworlds/opnsense-mcp-server?style=flat) | Patch for silent write failures + live read-back test; launcher with 1Password or plain env | [08](docs/setup/08-ai-ops.md#83-the-opnsense-mcp-patch---silent-write-failure) |
| Proxmox MCP | [ProxmoxMCP-Plus](https://github.com/RekklesNA/ProxmoxMCP-Plus) ![stars](https://img.shields.io/github/stars/RekklesNA/ProxmoxMCP-Plus?style=flat) · [proxmox-mcp-server](https://github.com/ry-ops/proxmox-mcp-server) | Pinned install, credentials from 1Password, command allow-list | [08](docs/setup/08-ai-ops.md#82-mcp-servers) |
| Wazuh MCP | [mcp-server-wazuh](https://github.com/gbrigandi/mcp-server-wazuh) ![stars](https://img.shields.io/github/stars/gbrigandi/mcp-server-wazuh?style=flat) | Setup that verifies credentials live before storing them; read-only indexer user | [08](docs/setup/08-ai-ops.md#82-mcp-servers) |
| Agent policy | - | `AGENTS.md`: read-first default, approval list, network-change gate, secrets handling | [08](docs/setup/08-ai-ops.md#81-the-policy-first-ai-opsagentsmd) |
| Hunting skill | adapted from [anthropic-cybersecurity-skills](https://github.com/mukul975/anthropic-cybersecurity-skills) | Zeek hunting workflow for this sensor layout | [skill](ai-ops/skills/zeek-hunting-homelab/SKILL.md) |

### Documentation map

| Component | Built on | What this repo adds | Guide |
| --- | --- | --- | --- |
| Network map | [isoflow](https://github.com/markmanx/isoflow) ![stars](https://img.shields.io/github/stars/markmanx/isoflow?style=flat) | Four views, pinch/wheel zoom patch, layout and render collision checks, served from the host | [09](docs/setup/09-network-map.md) |

## Screenshots

<p align="center"><small>Topology view</small></p>

![Topology view of the fictional reference network](docs/img/topology.png)

<p align="center"><small>Security controls view</small></p>

![Security controls view](docs/img/controls.png)

## Safety model

This repo touches firewalls, hypervisors and SIEMs. It is built so nothing acts on its own
and nothing leaks by accident.

- **Read before run.** Several scripts write to live systems; `ai-ops/AGENTS.md` lists them.
  Snapshot first and test on one host.
- **No automation enables itself.** Each timer and automatic action has a check to pass first
  ([configure.md §5](docs/configure.md#5-before-enabling-any-automation)).
- **Agents are read-first.** The agent policy requires explicit approval for any change to
  the firewall, switch, hypervisor, SIEM, sensor or DNS; unattended runs stay read-only.
- **Credentials never touch the repo.** `op://` references resolved at launch, or plain
  values in git-ignored, `chmod 600` env files.
- **Releases are gated.** `tools/export-release.sh` builds from committed files only and runs
  `tools/check.sh` against the exact archive. See [SECURITY.md](SECURITY.md).

## Documentation

| If you need to... | Start here |
| --- | --- |
| Make the repo match your network | [Configure for your network](docs/configure.md) |
| Understand the segments, hosts and data flows | [Architecture](docs/architecture.md) |
| Build it step by step | [Setup guides 00-09](docs/setup/) |
| Know what each Wazuh rule does and what pages | [Detection catalog](docs/detection-catalog.md) |
| Avoid the failures this design is built around | [Lessons learned](docs/lessons-learned.md) |
| Add a VPN-free segment | [Runbook](docs/runbooks/vpn-free-segment.md) |
| Resize the firewall VM safely | [Runbook](docs/runbooks/firewall-vm-memory.md) |
| Give an AI agent access safely | [AI operations](docs/setup/08-ai-ops.md) · [AGENTS.md](ai-ops/AGENTS.md) |
| Publish your own fork without leaking your network | [SECURITY.md](SECURITY.md) |

## Repo layout

```
config/    homelab.env (your values) + credential env examples
tools/     localize.py (apply your values) · check.sh / export-release.sh (release gate)
proxmox/   host side: watchdog, span keeper, backup, guest helpers
opnsense/  API helper, read-only verification scripts, monit setup, Wazuh agent config
wazuh/     rules, decoders, ntfy integration, YARA, Sigma converter, dashboards
zeek/      sensor config, Intel feeds + updater, hunting scripts
greenbone/ KEV/EPSS prioritisation
ai-ops/    MCP launchers and installers, OPNsense MCP patch, AGENTS.md, hunting skill
map/       isometric network map + layout/render checks
docs/      configure, architecture, setup guides, detection catalog, lessons, runbooks
```

## Status

A personal lab shared as a reference - not a product, no support promise. Read every
script before running it.

## License

MIT - see [LICENSE](LICENSE), with these exceptions (details in [NOTICE](NOTICE)):

- `wazuh/rules/sigma_zeek_rules.xml` is generated from [SigmaHQ](https://github.com/SigmaHQ/sigma)
  rules and is covered by the Detection Rule License (DRL) 1.1; each rule carries its
  Sigma ID and source file.
- `ai-ops/skills/zeek-hunting-homelab/` is adapted from an Apache-2.0 skill
  (mukul975/anthropic-cybersecurity-skills) and keeps its own LICENSE.

Built on, not bundled:

| Project | License |
| --- | --- |
| Proxmox VE | AGPL-3.0 |
| OPNsense | BSD-2-Clause |
| Suricata | GPL-2.0 |
| Wazuh | GPL-2.0 / AGPL-3.0 (engine) |
| Zeek | BSD-3-Clause |
| Greenbone Community Edition | AGPL-3.0 / GPL-2.0 |
| NetAlertX | GPL-3.0 |
| Apache Guacamole | Apache-2.0 |
| ntfy | Apache-2.0 / GPL-2.0 |
| opnsense-mcp-server · ProxmoxMCP-Plus · proxmox-mcp-server · mcp-server-wazuh · isoflow | MIT |
