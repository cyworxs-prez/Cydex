# 1. Proxmox host

## 1.1 Networking - `/etc/network/interfaces`

```
auto vmbr0                      # WAN - firewall VM only, no host IP
iface vmbr0 inet manual
    bridge-ports nic0
    bridge-stp off
    bridge-fd 0

auto vmbr1                      # LAN trunk - VLAN-aware, EXPLICIT allow-list
iface vmbr1 inet manual
    bridge-ports nic1
    bridge-stp off
    bridge-fd 0
    bridge-vlan-aware yes
    bridge-vids 1 110 120 130 140 150

auto vmbr1.130                   # host management address on MGMT
iface vmbr1.130 inet static
    address 10.10.130.10/24
    gateway 10.10.130.1

auto vmbrspan                   # port-less bridge for the Zeek capture NIC
iface vmbrspan inet manual
    bridge-ports none
    bridge-stp off
    bridge-fd 0
```

| Rule | Why |
|---|---|
| Every VLAN you use must be in `bridge-vids` | A missing VID is dropped silently at the hypervisor - the segment looks configured and carries zero packets |
| Add a VLAN live with `bridge vlan add vid <N> dev nic1`, then persist it in the file | **Never `ifreload -a`** - it can bounce vmbr1, which carries both your management address and the firewall trunk |
| Verify with `bridge vlan show dev nic1` | One command catches the whole class of fault |

Point the host's `/etc/resolv.conf` at the firewall (`nameserver 10.10.130.1`) only.
A public fallback resolver silently bypasses your DNS filtering and logging.

## 1.2 Guests

| ID | Name | Type | vCPU / RAM / disk | NICs |
|---|---|---|---|---|
| 200 | opnsense | VM, OPNsense ISO | 4 / 10 GB / 32 GB | net0 `vmbr0` (WAN), net1 `vmbr1` (trunk, no tag). Enable **QEMU guest agent** |
| 201 | wazuh | LXC Debian, unprivileged, `nesting=1` | 3 / 4 GB / 50 GB+ | `vmbr1` tag 140, 10.10.140.11 |
| 202 | greenbone | LXC Debian, docker (`nesting=1,keyctl=1`) | 2 / 4 GB / 64 GB | `vmbr1` tag 140, .12 |
| 203 | netalertx | LXC | 1 / 1 GB | `vmbr1` tag 140, .13 |
| 204 | kali | VM, onboot=0 | 2 / 4 GB | `vmbr1` tag 140 |
| 205 | guac | LXC | 2 / 2 GB | `vmbr1` tag 140, .20 |
| 206 | zeek | LXC Debian, unprivileged | 2 / 2 GB | net0 `vmbr1` tag 140 .21; **net1 `vmbrspan`, no IP** (capture) |

Set `onboot: 1` on the firewall and Wazuh. Start order: firewall first.

## 1.3 Memory changes on the firewall VM

`qm set 200 --memory <MiB>` then **`qm reboot 200`**. A reboot from inside the guest, or
`qm reset`, does *not* apply pending hardware changes - the QEMU process never exits.
Never `qm stop` (hard power cut). Full procedure: [runbooks/firewall-vm-memory.md](../runbooks/firewall-vm-memory.md).

Ignore the Proxmox memory gauge for the FreeBSD VM: with no balloon stats it falls back to
QEMU RSS, a high-water mark that reads ~100% forever. Use OPNsense's own figure.

## 1.4 Helper scripts (workstation side)

| Script | Does |
|---|---|
| `proxmox/scripts/run-on-ct.sh <ctid> <script>` | Runs a local script inside a container via `pct exec` (base64 transport - no quoting bugs) |
| `opnsense/scripts/runfw-via-pve.sh <script>` | Runs a local script **on OPNsense** via the guest agent. No API key, no SSH to the firewall |

Both read `config/homelab.env`.

## Verify

```bash
bridge vlan show dev nic1          # 1 110 120 130 140 150
qm agent 200 ping && echo agent-ok
pct list
```
