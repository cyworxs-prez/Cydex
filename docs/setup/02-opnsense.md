# 2. OPNsense + VLANs

## 2.1 Install and assign

1. Install OPNsense on VM 200. `vtnet0` = WAN (`vmbr0`), `vtnet1` = LAN trunk (`vmbr1`).
2. Install the **qemu-guest-agent** plugin (System > Firmware > Plugins) and enable it.
   Required by the watchdog and by `runfw-via-pve.sh`.
3. Interfaces > Other Types > VLAN: create VLANs 110/120/130/140/150 with parent `vtnet1`.
   OPNsense names them by **creation order** (`vlan01`...), not VLAN ID - write the
   mapping down; logs use these names.
4. Assign each VLAN, static `10.10.<vlan>.1/24`, descriptions TRUSTED/IOT/MGMT/LAB/DIRECT.
5. Leave `vtnet1` (the parent, usually `lan`) **assigned, with no IP**. Unassigning the
   parent reconfigures every VLAN on it.

## 2.2 DHCP (Kea) and DNS (Unbound)

- One Kea subnet per VLAN, pool `.100-.199`, router/DNS/NTP = the VLAN gateway.
- Reservations for the SOC hosts and the switch/APs.
- **Never delete a Kea subnet.** Subnet IDs are positional; deleting one renumbers the
  rest, Kea stops honouring reservations on renewal and every client re-addresses.
  Disable instead.
- Unbound: listen on all VLAN interfaces, enable **query logging**, enable DNSBL
  (for example Hagezi Normal + ThreatFox IOC).

## 2.3 Firewall rule ladder

Same order on every internal interface. All rules `quick`, first match wins.

| Seq | Action | Proto | Source | Destination | Note |
|---|---|---|---|---|---|
| 10 | pass | TCP/UDP | net | (self):53 | DNS to firewall |
| 11 | pass | UDP | any | any:67 | DHCP |
| 12 | pass | UDP | net | any:123 | NTP |
| 13 | pass | ICMP | net | (self) | diagnostics |
| 19 | block, **no log** | any | net | `<net>.255` | same-subnet broadcast - see below |
| 20-23 | block + log | any | net | each other internal /24 | one rule per segment |
| 24 | block + log | any | net | (self) | firewall admin |
| 25 | block + log | TCP/UDP | net | any:853 | DoT/DoQ (IoT, DIRECT) |
| 40 | pass | any | net | **NOT** RFC1918 alias | internet. Gateway: `VPN_GW` on TRUSTED, **empty** elsewhere |

Notes:

- **Seq 19 matters.** A `pass -> NOT RFC1918` rule leaves same-subnet broadcasts to the
  default deny, which logs. A single device's discovery broadcast can become the
  majority of SIEM volume. Never `pass` the whole `/24` to itself: it contains the firewall's own IP
  and would override seq 24.
- Seq 40 `destination_not=1` is load-bearing; check the invert flag, not the alias name.
- TRUSTED gets the exceptions it needs (admin access to MGMT/LAB) above seq 20.

## 2.4 IoT DNS enforcement

1. Firewall > NAT > Port Forward on IOT: TCP/UDP dst `!(self)` port 53 -> `127.0.0.1:53`.
2. Seq 25 block on 853 (DoT/DoQ).
3. Verify (all read-only):
   - `opnsense/scripts/iotdns-verify.py` - Unbound logging + DNSBL, live pf states for IoT
     hosts, NAT rdr rules, filter rules touching 53/853.
   - `opnsense/scripts/dnsbl-check.py` - resolver log blocklist lines and DNSBL status.
   - `opnsense/scripts/doh-hunt.py` - DoH bootstrap lookups, IoT :443 destinations, IoT
     devices talking to hard-coded resolver IPs.

## 2.5 VPN egress for TRUSTED (optional)

1. VPN > WireGuard: tunnel to your provider, assign as an interface (`wg0`), gateway `VPN_GW`.
2. TRUSTED seq 40: set gateway `VPN_GW`. Nothing else.
3. Outbound NAT (hybrid): add a rule for TRUSTED out `wg0`.
4. Verify from a TRUSTED client: `curl https://api.ipify.org` returns the VPN IP; from
   any other VLAN it returns your ISP IP.

The VPN-free DIRECT segment is a full worked example: [runbooks/vpn-free-segment.md](../runbooks/vpn-free-segment.md).

## 2.6 Suricata (IDS)

Services > Intrusion Detection > Administration:

| Setting | Value | Why |
|---|---|---|
| Mode | IDS (not IPS) | Detection without inline failure risk |
| Interfaces | the VLANs + WAN, **not** the parent trunk | Parent + children = every packet inspected twice, every alert duplicated |
| Pattern matcher | **Hyperscan** | Aho-Corasick + the default profile can exhaust firewall memory during a rule reload. Hyperscan + Low uses several times less with the same rulesets |
| Detect profile | Low | as above |
| Home networks | all five /24s | |
| EVE JSON | on | Shipped to Wazuh |

Cutting rulesets does **not** fix memory - the MPM/profile pair does.

After editing interfaces in `config.xml` directly: `configctl template reload OPNsense/IDS`,
then restart, then confirm the process lists `--pcap=vlanNN`.

## 2.7 API access

1. System > Access > Users: create a user for automation, assign only the privileges you
   need; create an API key.
2. Store key + secret in 1Password; reference them from `config/opnsense.env`.
3. Test (read-only): `python3 opnsense/scripts/opn_api.py` - prints the endpoint and
   uptime, never the secret.

Optional SSH alias for `opnsense/scripts/runfw.sh` (`~/.ssh/config`, **above** any `Host *`
block - ssh_config is first-match-wins):

```
Host opnsense-fw
  HostName 10.10.130.1
  User root
  IdentityFile ~/.ssh/opnsense_key
  IdentitiesOnly yes
```

OPNsense's root shell is csh: never inline scripts over ssh, transfer and run them by path
(both helper scripts do this).

## 2.8 Monit: restart Suricata on runaway memory

```bash
python3 opnsense/monit/monit-suricata-restart.py      # WRITES to OPNsense
```

Creates a monit *process* service for Suricata with two tests (memory > 3500 MB for 3
cycles, process missing) and monit's native `restart` action, then reads everything back.
OPNsense rejects spaces in a test path, so `exec`-with-arguments is not an option.

Monit does not page by itself. Either configure its mail alerts or rely on the Wazuh agent
seeing the restart in the system log.

## 2.9 Wazuh agent on OPNsense

Install the `os-wazuh-agent` plugin, point it at `10.10.140.11`, and make sure it ships
`/var/log/suricata/eve.json` (JSON) and the system log. Reference settings:
`opnsense/wazuh-agent/ossec.conf` - syscheck/rootcheck off to keep the agent cheap on the
box everything depends on.

## Verify

```bash
python3 opnsense/scripts/host-inventory.py   # leases per VLAN
python3 opnsense/scripts/iotdns-verify.py
printf 'pfctl -sr | wc -l\nps ax | grep -c "[s]uricata"\n' > /tmp/fwcheck.sh
opnsense/scripts/runfw-via-pve.sh /tmp/fwcheck.sh
```
