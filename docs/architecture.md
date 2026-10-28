# Architecture

> **Fictional reference network.** All addresses, VLAN IDs and guest IDs in this repo
> are examples. Replace them with your own (`config/homelab.env`, and the subnets in
> `wazuh/rules/`).

## Segments

| VLAN | Name | Subnet | Gateway | Egress | Purpose |
|---|---|---|---|---|---|
| 110 | TRUSTED | 10.10.110.0/24 | .1 | Commercial VPN (WireGuard) | Admin workstation, laptops |
| 120 | IOT | 10.10.120.0/24 | .1 | ISP | IoT devices. DNS forced to the firewall, DoT/DoQ blocked |
| 130 | MGMT | 10.10.130.0/24 | .1 | ISP | Hypervisor, switch, APs |
| 140 | LAB | 10.10.140.0/24 | .1 | ISP | SOC stack |
| 150 | DIRECT | 10.10.150.0/24 | .1 | ISP (no VPN) | Devices that must not egress via a VPN. Isolated from every other segment |

- **Egress is decided by one setting:** whether the segment's internet rule sets a
  gateway. TRUSTED's rule sets `VPN_GW`; every other segment leaves it empty and goes out
  the ISP. Check egress with `curl https://api.ipify.org` *from the segment*.
- **Why a VPN-free segment:** some services refuse datacenter/VPN source addresses and
  fail at the application layer (an HTTP 403, or a stream reset after TLS completes), so
  it never looks like a network fault. See [runbooks/vpn-free-segment.md](runbooks/vpn-free-segment.md).
- The VPN tunnel is **not** IDS-inspected by design; Suricata sees the VLAN interfaces
  before traffic enters it.

## Hosts

One Proxmox node.

| Guest | ID | Type | Role | IP |
|---|---|---|---|---|
| opnsense | 200 | VM (FreeBSD) | Firewall, router, DHCP, DNS, IDS | .1 on each VLAN |
| wazuh | 201 | LXC | SIEM manager + indexer + dashboard | 10.10.140.11 |
| greenbone | 202 | LXC (docker) | Vulnerability scanner, on demand | 10.10.140.12 |
| netalertx | 203 | LXC | Device discovery, LAB only ([10](setup/10-netalertx.md)) | 10.10.140.13 |
| kali | 204 | VM | Offensive tooling, stopped by default | - |
| guac | 205 | LXC | Apache Guacamole console gateway, reaches LAB only ([11](setup/11-guacamole.md)) | 10.10.140.20 |
| zeek | 206 | LXC | Network sensor | 10.10.140.21 |

The Proxmox host is `10.10.130.10` on MGMT (`vmbr1.130`). Sizing: [00-prerequisites.md](setup/00-prerequisites.md).

![Topology view of the fictional reference network](img/topology.png)

## Layer 2 path

```
client -> AP -> switch -> switch uplink -> hypervisor nic1
       -> vmbr1 (VLAN-aware, explicit bridge-vids allow-list)
       -> tap200i1 -> OPNsense vtnet1 -> vlan01..vlan05
```

- `vmbr1` has an **explicit VLAN allow-list** (`bridge-vids`). A VLAN missing there is
  dropped at the hypervisor silently. Adding a VLAN = switch/AP change **and**
  `bridge vlan add vid <N> dev nic1` + persist in `bridge-vids`.
- `vtnet1` is the parent of every VLAN. It carries no IP address but must stay assigned.

## Telemetry flow

```
                    +-------------------- Wazuh (CT 201) ---------------------+
                    |  manager -> rules -> alerts index -> dashboards          |
                    |                  \-> integratord -> custom-ntfy -> phone |
                    +----^-----------^-------------^--------------^-----------+
                         |           |             |              |
  OPNsense agent --------+           |             |              |
   (Suricata EVE, filterlog)         |             |              |
  Zeek agent (JSON logs, intel.log) -+             |              |
  hypervisor agent (journald: watchdog, span, backup)             |
  other agents --------------------------------------------------+

  OPNsense LAN trunk tap200i1 --tc mirred (ingress+egress)--> veth206i1 -> Zeek
```

- **SPAN:** the whole trunk is mirrored, so a new VLAN is captured as soon as it exists.
  Update `networks.cfg` so `local_orig` stays correct.
- **The mirror is runtime state.** The tap is recreated on every firewall-VM restart.
  `zeek-mirror.service` (host boot) and the span hookscript (VM restart) re-apply it;
  both log, and Wazuh pages if either fails.
- **Paging threshold:** Wazuh level >= 10. Context 3-6, suspicious 7-8, page 10+,
  confirmed-bad or sensor-dead 12-14.

## Security controls

![Security controls view](img/controls.png)

| Control | Where | How it is verified |
|---|---|---|
| Inter-VLAN isolation | OPNsense per-interface rule ladders | Wazuh 100840-100851 on blocked cross-zone flows |
| Forced DNS (IoT) | NAT port-forward 53 -> firewall resolver | pf states; Zeek DNS shows no external resolvers |
| DoT/DoQ block | Block + log 853 from IoT and DIRECT | filterlog hits |
| DNSBL | Unbound blocklists | resolve a known-blocked domain |
| IDS | Suricata, Hyperscan MPM, Low profile, IDS mode | EVE -> Wazuh |
| IOC matching | Zeek Intel framework, daily refresh | 100900-100909; refresh failures page |
| Host malware scan | YARA, nightly | daily heartbeat rule |
| Firewall liveness | hypervisor watchdog (3 independent probes) | hourly heartbeat; recovery pages |
| Sensor liveness | span hookscript + capture-loss rules | 100713 / 100735 (degraded), 100890-100892 (blind) |
| Backups | weekly vzdump to an encrypted drive, checksum read-back | 100880-100882; failure pages |

## Management access

- The admin workstation lives on TRUSTED. MGMT and LAB are reachable from TRUSTED only.
- DIRECT is isolated from MGMT by design: automation run from a device on DIRECT cannot
  reach anything. Detect that and report it rather than retrying.
- Keep a physical out-of-band path (for example, an untagged MGMT switch port) for
  recovering from a bad firewall change.
- `opnsense/scripts/runfw-via-pve.sh` runs read-only scripts on OPNsense through the QEMU
  guest agent - no API key and no SSH to the firewall.

## Clocks

Containers may log UTC while the host and firewall log local time. Convert before correlating.
