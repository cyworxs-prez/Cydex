# Runbook - add a VPN-free segment (DIRECT)

Adds a VLAN whose clients egress straight out the ISP while TRUSTED stays on the VPN.
Uses the fictional reference values; substitute your own.

Standing rule for every network change: inspect current state -> state the rollback ->
smallest reversible change -> **read the result back** -> test intended *and* negative
paths -> write a dated change record.

## Why

Some services refuse datacenter/VPN source addresses and fail at the application layer:
an HTTP 403 from a CDN, or a stream reset after TCP and TLS both succeed (`curl` exit 92).
DNS is clean and the port is open, so it does not look like a network fault. A segment
without a VPN gateway avoids it.

A segment egresses via the ISP simply by **not** setting a gateway on its internet rule.

## Plan

| | |
|---|---|
| VLAN | 150, parent `vtnet1` |
| OPNsense | new interface `DIRECT`, `10.10.150.1/24` |
| Kea | new subnet, pool `.100-.199`, router/DNS/NTP = `.1` |
| SSID | `<vpn-free-ssid>` -> controller network `DIRECT` (VLAN-only, DHCP off) |
| Egress | default gateway (ISP) |
| Posture | isolated - blocked to every internal segment and to the firewall itself |

## Firewall ladder (DIRECT)

| Seq | Action | Proto | Source | Destination | Note |
|---|---|---|---|---|---|
| 10 | pass | TCP/UDP | 10.10.150.0/24 | (self):53 | DNS to firewall |
| 11 | pass | UDP | any | any:67 | DHCP |
| 12 | pass | UDP | 10.10.150.0/24 | any:123 | NTP |
| 13 | pass | ICMP | 10.10.150.0/24 | 10.10.150.1 | diagnostics |
| 19 | block, no log | any | 10.10.150.0/24 | 10.10.150.255 | same-subnet broadcast |
| 20-23 | block + log | any | 10.10.150.0/24 | each internal /24 | one rule per segment |
| 24 | block + log | any | 10.10.150.0/24 | (self) | firewall admin |
| 25 | block + log | TCP/UDP | 10.10.150.0/24 | any:853 | DoT/DoQ |
| 40 | pass | any | 10.10.150.0/24 | **NOT** RFC1918 | **no gateway** - this is the whole mechanism |

The invert flag on seq 40 is load-bearing. Check the flag, never the alias name.

## Procedure

```
0  qm snapshot 200 pre-direct                # never qm stop
   cp /conf/config.xml /conf/config.xml.bak-pre-direct
1  VLAN 150 on vtnet1                         # API: interfaces vlanSettingsAddItem
2  assign the interface, 10.10.150.1/24       # no API: config.xml edit, then
                                              #   configctl interface reconfigure <if>
3  Kea: append the subnet, add the interface  # VERIFY existing subnet IDs unchanged
4  Unbound: add the interface to active_interface, reconfigure
5  firewall ladder above, then: configctl filter reload
6  controller: VLAN-only network DIRECT/150
6b hypervisor: allow the VLAN on vmbr1        # MANDATORY
   bridge vlan add vid 150 dev nic1
   # persist: add 150 to bridge-vids in /etc/network/interfaces
   # do NOT ifreload - it can bounce vmbr1 (management + firewall trunk)
7  SSID, set by hand in the controller        # automation never handles passphrases
8  Zeek: add the subnet to networks.cfg, zeekctl deploy
9  Suricata: add the interface + HOME_NET
   configctl template reload OPNsense/IDS, THEN restart
```

## Verify

```
# from a client on the new SSID
curl https://api.ipify.org          # ISP address, not the VPN address
ping 10.10.110.1; ping 10.10.130.10 # must FAIL
dig @10.10.150.1 example.com        # resolves

# regression - the VPN path is untouched
curl https://api.ipify.org          # from TRUSTED: still the VPN address

# sensors / firewall
bridge vlan show dev nic1                     # on the hypervisor: 150 present
ps auxww | grep suricata                      # lists the new vlan interface
pfctl -sn | grep vlan05                       # NAT uses (vlan05:network), not a literal subnet
```

## Rollback

Additive throughout. To undo: disable the interface's rules, disable the interface,
delete the controller network and SSID.

**Do not delete the Kea subnet casually.** Subnet IDs are positional; deleting one
renumbers the rest and every DHCP client re-addresses. Disable it instead.

## Notes

- **"No switch changes" is not "no L2 changes".** Ports using an all-VLANs profile pick
  up the new network automatically, but the hypervisor bridge allow-list does not. Symptom
  when it is missed: clients associate, get no lease, and report "DNS not resolving" while
  `netstat -I vlanNN` on OPNsense shows zero input packets.
- **Read every write back.** Some settings-node writes through the API return `saved` and
  change nothing; fall back to a `config.xml` edit for those.
- **Suricata needs a template reload** - editing `config.xml` alone does not regenerate
  `suricata.yaml` or the interface list.
- `pfctl -sn | grep 10.10.150` returns nothing because hybrid outbound NAT uses interface
  macros. Grep for the interface.
- ARP-based discovery tools cannot see across a router; point them only at segments they
  have L2 presence on, or blocked-flow alerts will flood.
