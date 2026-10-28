# 0. Prerequisites

## Hardware

Cydex is vendor-neutral. Each role needs a capability, not a brand. The example product
lines are illustrative (alphabetical); none are required, and the repo was not tested
on all of them.

| Role | Must support | Example product lines | Optional MCP server (AI ops) |
|---|---|---|---|
| Hypervisor host | x86-64, VT-x/AMD-V, **2 NICs** (WAN + LAN trunk), 8+ cores, 24 GB+ RAM | any mini PC / small server | Proxmox - [08](08-ai-ops.md#82-mcp-servers) (used here) |
| Router / firewall | Runs as the **OPNsense VM** on the host. The rule ladders, Suricata and the Wazuh agent assume OPNsense | - | OPNsense - [08](08-ai-ops.md#82-mcp-servers) (used here) |
| Managed switch | 802.1Q trunks, per-port native VLAN, enough ports for host + APs + wired devices | Cisco Meraki MS, MikroTik CRS, TP-Link Omada, Ubiquiti UniFi | see below |
| Wi-Fi access points | Multiple SSIDs, each mapped to a VLAN tag; WPA3 | Cisco Meraki MR, MikroTik cAP, TP-Link Omada EAP, Ubiquiti UniFi | see below |
| Backup drive | USB or internal disk, encrypted with LUKS | any | - |
| Phone | Push notifications | any (ntfy app) | - |

**Vendor gateway?** If your switch/AP vendor also sells a gateway (Omada router, UniFi
gateway, Meraki MX), it is **not** the router here: OPNsense routes and filters every
segment. Leave the gateway out, or put it upstream as a plain ISP edge. Its controller
software can still manage the switch and APs.

### Switch / AP controller MCP servers

Only relevant if you use that vendor's switches, APs or gateway. Each one lets an AI agent
read (and, if you let it, change) the controller - networks, WLANs, clients, port
profiles. `ai-ops/AGENTS.md` already requires approval for any controller change.

| Vendor | MCP server | Status in this repo |
|---|---|---|
| Ubiquiti UniFi | [enuno/unifi-mcp-server](https://github.com/enuno/unifi-mcp-server) (PyPI `unifi-mcp-server`) | **Tested.** Launcher + config included - [08](08-ai-ops.md#82-mcp-servers) |
| Cisco Meraki | [CiscoDevNet/cisco-meraki-mcp-official](https://github.com/CiscoDevNet/cisco-meraki-mcp-official) | Not tested |
| TP-Link Omada | [MiguelTVMS/tplink-omada-mcp](https://github.com/MiguelTVMS/tplink-omada-mcp) | Not tested |
| MikroTik | [vesact/mikrotik-mcp](https://github.com/vesact/mikrotik-mcp) | Not tested |

For an untested server: read its code before you run it, launch it read-only first, and
give it the narrowest credential the controller allows. Wrap it the same way as the
others (`ai-ops/mcp/_launch-lib.sh` + a `config/<name>.env`).

Budget RAM: firewall 10 GB, Wazuh 4 GB, Greenbone 4 GB (on demand), Zeek 2 GB, the rest
1-2 GB each, plus 2-3 GB for the host.

## Accounts / services

| Need | Used for |
|---|---|
| ntfy topic (ntfy.sh or self-hosted) | Paging. Use a long random topic name - anyone who knows it can read your alerts |
| Commercial WireGuard VPN (optional) | TRUSTED egress. Skip it and every segment simply egresses via the ISP |
| 1Password (or swap in your own secret store) | Every credential is an `op://` reference resolved at run time |

## Admin workstation tools

| Tool | Why |
|---|---|
| `ssh`, key-based root access to the Proxmox host | Every helper script tunnels through the host |
| `op` (1Password CLI) | Resolves `op://` references |
| Python 3.10+, Node 20+ | Scripts, MCP servers, map build |
| An MCP client (optional) | Claude Desktop / Claude Code etc. for [AI operations](08-ai-ops.md) |

## Repo configuration

Do [configure.md](../configure.md) before any setup step: it creates `config/*.env`,
localizes the repo to your addresses and IDs, and lists every setting that lives
elsewhere. The real `config/*.env` files are git-ignored - keep them that way.

## Addressing

Defaults throughout match the reference layout in [architecture.md](../architecture.md).
Before installing anything, make the repo yours: [configure.md](../configure.md) - fill
`config/homelab.env`, run `tools/localize.py`, and see every other place settings live.
