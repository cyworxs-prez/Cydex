# 0. Prerequisites

## Hardware (recommended)

| Item | Notes |
|---|---|
| One x86 host, 2 NICs | 8+ cores / 24 GB+ to run every guest at once. NIC0 = WAN, NIC1 = LAN trunk |
| Managed switch | 802.1Q trunks + per-port VLAN profiles |
| 1-2 Wi-Fi APs | Multiple SSIDs, each mapped to a VLAN |
| USB drive for backups | Encrypted with LUKS. Size it from measured vzdump output, not guesses |
| Phone | For ntfy push notifications |

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
