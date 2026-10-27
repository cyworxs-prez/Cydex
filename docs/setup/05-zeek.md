# 5. Zeek sensor

Reference: Zeek 9 (from the official OBS packages) in an unprivileged Debian LXC
(CT 206). `eth0` = management on LAB; `eth1` = capture, on the port-less `vmbrspan`
bridge, no IP.

## 5.1 Install and configure

1. Install Zeek from the official package repo into `/opt/zeek`.
2. Copy `zeek/config/node.cfg` (standalone, `interface=eth1`) and
   `zeek/config/networks.cfg` (all five /24s) into `/opt/zeek/etc/`.
3. Copy `zeek/config/local.zeek` to `/opt/zeek/share/zeek/site/local.zeek`. Key lines:
   `@load policy/tuning/json-logs`, `@load misc/capture-loss`, `redef ignore_checksums = T`
   (mirrored traffic has offloaded checksums), `@load ./intel-config`.
4. `/opt/zeek/bin/zeekctl deploy`.

Keep `networks.cfg` complete. A missing segment is labelled external and every
`local_orig` decision for it is silently wrong.

## 5.2 Feed it: the SPAN mirror (Proxmox host)

The firewall's LAN trunk tap is mirrored, ingress + egress, into the sensor's capture veth
with `tc mirred`. That is runtime state, so it is installed twice over:

| Piece | Covers |
|---|---|
| `/usr/local/sbin/zeek-span-apply.sh` | Applies the mirror, verifies exactly one filter per direction, logs as `zeek-span` |
| `zeek-mirror.service` | Runs it at host boot |
| `zeek-span.pl` hookscript | Runs it after every firewall-VM start (the tap is destroyed and recreated) |
| `/etc/default/zeek-span` | `FW_VMID`, `MIRROR_SRC`, `MIRROR_DST` - the only place these are set |

```bash
# on the Proxmox host, from a copy of proxmox/span/
bash install.sh                                   # installs files only
vi /etc/default/zeek-span                         # check the three values
/usr/local/sbin/zeek-span-apply.sh                # must print "span re-applied"
systemctl enable zeek-mirror.service
qm set 200 --hookscript local:snippets/zeek-span.pl
```

Find the interface names with `ip -br link | grep -E 'tap200|veth206'`: the tap index is
the firewall VM's trunk NIC (`net1` -> `i1`), the veth index is the Zeek CT's capture NIC.

Both verify the filter landed and log via `logger`; Wazuh `span_rules.xml` pages if the
span is not applied.

Why both matter: Zeek computes capture loss from ACKs for data it never saw. A **fully**
blind Zeek sees no ACKs either and reports 0% loss - healthy-looking. Only the span check
catches total loss.

## 5.3 Intel framework (IOC matching)

```bash
# copy zeek/intel/ to the sensor, then as root inside CT 206:
cd intel && sh install.sh
```

- Daily timer rebuilds `master.dat` from abuse.ch Feodo, ThreatFox, URLhaus (URLs +
  domains) and the Tor exit list (~20k indicators). A sanity floor keeps yesterday's set if
  the rebuild is implausibly small.
- Hand-curated indicators go in `site/intel/local-iocs.dat` (`meta.source` = `local`,
  alerts at level 14). Never edit `master.dat`.
- `domain-exclude.txt` keeps file-sharing/CDN domains out of the domain feed.
- `Input::REREAD` picks up **added** indicators live but never retires removed ones, so
  the updater restarts Zeek when a refresh drops any. Rule 100909 pages if that restart fails.
- Most malicious URLs are HTTPS. A quiet `intel.log` is not evidence of a quiet network.

## 5.4 Hunting

Run inside CT 206 (read-only):

| Script | Finds |
|---|---|
| `zeek/hunting/zeek_hunt.py` | Beaconing, rare external destinations, DNS anomalies, TLS posture |
| `zeek/hunting/zeek_dns_tls_hunt.py [HOST PORT]` | Hosts using external resolvers, self-signed/expired certs, long-lived external connections, optional host:port drill-down |
| `zeek/hunting/zeek-doh.sh` | DoH/DoT indicators from the IoT VLAN |

For an LLM agent, `ai-ops/skills/zeek-hunting-homelab/` packages the same workflow as a skill.

Hunting notes:

- **Hunt rare SNI, not JA3.** Modern browsers randomise ClientHello extension order, so
  JA3 values barely repeat.
- Exclude internal gateway DNS, the discovery scanner and known high-volume cloud
  devices from beacon queries, or the top results are all known-good.
- Identity for retrospective hunts comes from `dhcp.log`, not current leases. Private MAC
  rotation makes one device look like several IPs.

## Verify

```bash
pct exec 206 -- /opt/zeek/bin/zeekctl status                       # running
pct exec 206 -- tail -2 /opt/zeek/logs/current/capture_loss.log    # acks > 0
tc filter show dev tap200i1 ingress | grep -c mirred               # 1 (on the host)
pct exec 206 -- systemctl list-timers zeek-intel-update.timer
```
