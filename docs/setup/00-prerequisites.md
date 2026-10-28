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

### Reference build (what this repo runs on)

One example that meets the table above. Not an endorsement, and not the only option.

| Role | Hardware | Notes |
|---|---|---|
| Hypervisor host | Mini PC, AMD Ryzen 5 3500U (4 cores / 8 threads, Radeon Vega iGPU) ([Amazon](https://www.amazon.com/dp/B0GQTCBV78)) | Proxmox VE 9. Built-in Wi-Fi unused |
| Network ports | 2x 1 GbE, Realtek RTL8111 | NIC0 = WAN, NIC1 = LAN trunk. Guests (including OPNsense) see virtio NICs, so the Realtek chip only matters to the Linux host |
| RAM | 16 GB stock + 8 GB added, DDR4 SO-DIMM (24 GB) | Before the upgrade Proxmox saw only 12.6 GB (iGPU reservation, below); after, ~23 GB |
| Boot / guest storage | 512 GB NVMe (PCIe 3.0, DRAM-less), stock | Holds Proxmox and all guests. DRAM-less drives slow down under sustained writes - fine here, but keep backups off it |
| Backup drive | 1 TB 2.5" HDD (Seagate ST1000LM035) over USB ([enclosure](https://a.co/d/07dxemXj)) | LUKS-encrypted; weekly vzdump target ([06](06-resilience.md#64-weekly-encrypted-backup)) |
| Switch | Ubiquiti UniFi USW Lite 8 PoE | Port 1 = trunk to the host; PoE powers the APs |
| Access points | 2x Ubiquiti UniFi U7 Lite | One SSID per VLAN |
| Router / firewall | OPNsense VM on the host | No hardware gateway |

Lessons from this hardware:

- **Add the RAM before building.** The firewall VM had an out-of-memory outage at 6 GB
  and now runs at 10 GB (Suricata needs the headroom). That, plus Wazuh and the rest,
  only fits after the upgrade. Run a full memtest86+ pass on any added module before you
  trust guests to it: bad non-ECC RAM corrupts guests silently.
- **Shrink the iGPU's memory reservation.** AMD integrated graphics reserve system RAM.
  UEFI: **Advanced -> AMD CBS -> NBIO -> GFX Configuration -> UMA Frame Buffer Size** ->
  minimum (if your firmware shows it). A headless host doesn't need it.
- **A USB HDD is slow but fine for weekly backups.** Size it from measured vzdump output.
  The backup script checks free space first (`ABORT_GIB`).

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
