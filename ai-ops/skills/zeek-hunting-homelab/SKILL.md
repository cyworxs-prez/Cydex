---
name: zeek-hunting-homelab
description: Hunt for network anomalies in this homelab's Zeek sensor (CT206) - C2 beaconing, DNS tunnelling, data exfiltration, rare TLS and lateral movement - using the actual access path, log format and topology of this deployment. Also covers sensor health, since a Zeek finding is only as good as the capture behind it. Use when investigating suspicious network behaviour, doing retrospective incident analysis on Zeek logs, writing custom .zeek detections, or checking whether the sensor is actually seeing traffic.
domain: cybersecurity
subdomain: network-security
tags:
- network-security
- zeek
- threat-hunting
- anomaly-detection
- homelab
version: '2.0-homelab'
license: Apache-2.0
adapted_from: mukul975/anthropic-cybersecurity-skills - detecting-network-anomalies-with-zeek (author mahipal, Apache-2.0)
nist_csf:
- DE.CM-01
- DE.AE-02
- ID.AM-03
mitre_attack:
- T1071
- T1048
- T1572
- T1046
---

# Zeek hunting in this homelab

## When to use

Investigating suspicious network behaviour, retrospective incident analysis over Zeek
logs, writing a custom detection, or answering "is the sensor actually seeing traffic?"

**Not** for inline blocking (that is OPNsense/Suricata) or host telemetry (that is the
Wazuh agents).

## The four things that make this deployment different

The upstream skill assumes Zeek runs on the machine you are typing on, writes TSV logs,
and ships to Elastic. **All four assumptions are false here.** Getting these wrong wastes
a session:

1. **Zeek is in CT206 on pve. You are not on that host.** Every command needs the
   `pct exec` hop. There is no direct SSH to CT206 from a workstation.
2. **`/opt/zeek/bin` is NOT on `$PATH` under `pct exec`.** `zeek`, `zeekctl` and
   `zeek-cut` all exist - they just are not found. `command -v zeek-cut` returns nothing
   and looks exactly like "not installed". It is not. Always use absolute paths.
3. **Logs are JSON, not TSV.** So **`zeek-cut` is useless here** regardless of PATH - it
   parses the `#fields` header of TSV logs, which JSON logs do not have. Every
   `zeek-cut` recipe you find online must be rewritten. **`jq` is also not installed** in
   CT206. Use `python3`, which is.
4. **Alerts go to Wazuh, not Elastic/Filebeat.** Do not set up a Filebeat pipeline; the
   agent already ships these logs.

## Access path

```bash
# From a workstation: hop through pve. CT206 has no direct SSH from VLAN 110.
ssh root@10.10.130.10
pct exec 206 -- <command>

# One-liner form used throughout this skill:
ssh root@10.10.130.10 'pct exec 206 -- python3 - <<PY
...
PY'
```

| Fact | Value |
|---|---|
| Zeek host | CT206, `10.10.140.21` (LAB/SOC VLAN 140) |
| Zeek version | 8.2.2, standalone (not clustered) |
| Binaries | `/opt/zeek/bin/{zeek,zeekctl,zeek-cut}` - **absolute paths required** |
| Logs | `/opt/zeek/logs/current/*.log` - **JSON lines** |
| Rotated | `/opt/zeek/logs/YYYY-MM-DD/*.log.gz` |
| Site config | `/opt/zeek/share/zeek/site/local.zeek` |
| Capture iface | `eth1` (promisc), fed by a tc mirror - see Sensor health |
| Resources | **2 cores / 2 GB** - keep queries streaming, never load a whole log into RAM |

## Log inventory and real field names

Field names below are read from the live logs, not from documentation.

| Log | Key fields |
|---|---|
| `conn.log` | `ts uid id.orig_h id.orig_p id.resp_h id.resp_p proto duration orig_bytes resp_bytes conn_state local_orig local_resp missed_bytes history` |
| `dns.log` | `ts uid id.orig_h id.resp_h query qtype_name rcode_name answers` |
| `ssl.log` | `ts uid id.orig_h id.resp_h version cipher server_name resumed established ja3 ja3s` |
| `http.log` | `ts uid id.orig_h id.resp_h method host uri user_agent request_body_len response_body_len` |
| `notice.log` | `ts uid id.orig_h id.resp_h note msg sub src dst` |
| `weird.log` | `ts uid id.orig_h id.resp_h name addl notice peer` |

Also present: `files.log x509.log smtp.log ssh.log ntp.log quic.log mqtt_*.log
known_hosts.log known_services.log known_certs.log software.log tunnel.log
capture_loss.log stats.log analyzer.log`.

Note `mqtt_*` - IoT devices on VLAN 120 speak it, and it is a useful pivot.

## Segment map (from `/opt/zeek/etc/networks.cfg`)

```
10.10.110.0/24   TRUSTED
10.10.120.0/24   IoT
10.10.130.0/24   MGMT
10.10.140.0/24   LAB
10.10.150.0/24   DIRECT
```

Direction matters more than volume in this network. IoT → TRUSTED and anything → MGMT
are the interesting directions; LAB → anywhere is often just Greenbone or Kali.

## Hunting queries

All are streaming (`for line in f`), JSON-aware, and safe on 2 GB. Run via the access
path above. Replace `LOG` with the target file.

### Long-duration connections (possible C2)

```python
import json,collections
out=[]
for line in open('/opt/zeek/logs/current/conn.log',errors='replace'):
    if not line.startswith('{'): continue
    try: o=json.loads(line)
    except Exception: continue
    d=o.get('duration',0) or 0
    if d > 3600:
        out.append((round(d), o['id.orig_h'], o['id.resp_h'], o.get('id.resp_p'), o.get('proto')))
for r in sorted(out, reverse=True)[:20]: print(r)
```

### Beaconing: regular intervals to one destination

The strongest single signal for C2. Low standard deviation of inter-arrival time is the
tell, not connection count.

```python
import json,collections,statistics
t=collections.defaultdict(list)
def noisy(ip):                       # broadcast/multicast discovery beacons perfectly
    return ip.endswith('.255') or ip=='255.255.255.255' or \
           (ip.split('.')[0].isdigit() and 224 <= int(ip.split('.')[0]) <= 239)
SKIP_SRC={'10.10.140.13'}            # NetAlertX status pings: periodic by design
for line in open('/opt/zeek/logs/current/conn.log',errors='replace'):
    if not line.startswith('{'): continue
    try: o=json.loads(line)
    except Exception: continue
    if noisy(o['id.resp_h']) or o['id.orig_h'] in SKIP_SRC: continue
    t[(o['id.orig_h'],o['id.resp_h'],o.get('id.resp_p'))].append(o['ts'])
for k,v in sorted(t.items(), key=lambda x:-len(x[1])):
    if len(v)<8: continue
    v.sort(); gaps=[b-a for a,b in zip(v,v[1:])]
    m=statistics.mean(gaps); s=statistics.pstdev(gaps)
    if m>5 and s/m < 0.15:            # <15% jitter = machine, not human
        print(f"{k}  n={len(v)}  every {m:.0f}s  jitter {100*s/m:.1f}%")
```

**Why the multicast filter matters.** Without it this query is dominated by SSDP
(`239.255.255.250`), subnet broadcast (`x.x.x.255`) and vendor device-discovery
protocols - all of which beacon with near-zero jitter because they are
timers, and none of which are C2. Unfiltered, the top of the list is typically all
broadcast/multicast. A hunt that returns known noise trains you to
ignore it.

**Known periodic sources.** NetAlertX (`10.10.140.13`) pings the devices you gave it on a
fixed schedule ([10-netalertx.md](../../../docs/setup/10-netalertx.md#105-optional-status-for-devices-on-other-segments)),
so its flows have near-zero jitter. `SKIP_SRC` drops it. Add any other monitoring host
you run, and nothing else: every source you skip is a place C2 could hide.

### DNS tunnelling / DGA

```python
import json,collections,math
q=collections.defaultdict(list)
for line in open('/opt/zeek/logs/current/dns.log',errors='replace'):
    if not line.startswith('{'): continue
    try: o=json.loads(line)
    except Exception: continue
    if o.get('query'): q[o['id.orig_h']].append(o['query'])
def ent(s):
    return -sum((s.count(c)/len(s))*math.log2(s.count(c)/len(s)) for c in set(s)) if s else 0
for src,qs in q.items():
    longs=[x for x in qs if len(x)>50]
    hi=[x for x in qs if ent(x.split('.')[0])>3.5 and len(x.split('.')[0])>12]
    if len(qs)>500 or longs or len(hi)>20:
        print(f"{src}: {len(qs)} queries, {len(longs)} over 50 chars, {len(hi)} high-entropy")
        for x in (longs[:3] or hi[:3]): print("    ", x[:90])
```

### Exfiltration: outbound bytes far exceeding inbound

```python
import json,collections
b=collections.defaultdict(lambda:[0,0])
for line in open('/opt/zeek/logs/current/conn.log',errors='replace'):
    if not line.startswith('{'): continue
    try: o=json.loads(line)
    except Exception: continue
    k=(o['id.orig_h'],o['id.resp_h'])
    b[k][0]+=o.get('orig_bytes',0) or 0; b[k][1]+=o.get('resp_bytes',0) or 0
for k,(up,down) in sorted(b.items(), key=lambda x:-x[1][0])[:20]:
    if up > 10_000_000 and up > down*3:
        print(f"{k[0]} -> {k[1]}  up {up/1e6:.1f} MB  down {down/1e6:.1f} MB")
```

### Rare user agents and rare JA3 (long tail = interesting)

```python
import json,collections
c=collections.Counter(); j=collections.Counter()
for line in open('/opt/zeek/logs/current/http.log',errors='replace'):
    if line.startswith('{'):
        try: c[json.loads(line).get('user_agent','')]+=1
        except Exception: pass
for line in open('/opt/zeek/logs/current/ssl.log',errors='replace'):
    if line.startswith('{'):
        try: j[json.loads(line).get('ja3','')]+=1
        except Exception: pass
print("rare user agents:");  [print(f"  {n:4d}  {u[:80]}") for u,n in c.most_common()[-15:] if u]
print("rare JA3:");          [print(f"  {n:4d}  {x}")      for x,n in j.most_common()[-15:] if x]
```

### Cross-segment connections that succeeded

Blocked attempts are OPNsense's business (Wazuh rules 100840-100850). What Zeek adds is
what actually *completed* across a boundary.

```python
import json
def seg(ip):
    for p,n in (('10.10.110.','TRUSTED'),('10.10.120.','IoT'),
                ('10.10.130.','MGMT'),('10.10.140.','LAB')):
        if ip.startswith(p): return n
    return 'EXT'
for line in open('/opt/zeek/logs/current/conn.log',errors='replace'):
    if not line.startswith('{'): continue
    try: o=json.loads(line)
    except Exception: continue
    a,b=seg(o['id.orig_h']),seg(o['id.resp_h'])
    if a!=b and 'EXT' not in (a,b) and o.get('conn_state')in('SF','S1','RSTO'):
        print(f"{a}->{b}  {o['id.orig_h']}:{o.get('id.orig_p')} -> "
              f"{o['id.resp_h']}:{o.get('id.resp_p')} {o.get('proto')} {o.get('conn_state')}")
```

## Sensor health - check this BEFORE trusting a null result

"I found nothing" and "the sensor saw nothing" look identical in the output. They are not
the same claim. Check capture health first.

```python
import json
r=[json.loads(l) for l in open('/opt/zeek/logs/current/capture_loss.log') if l.startswith('{')]
for o in r[-8:]:
    print(f"{o['ts']:.0f}  loss {o.get('percent_lost',0):6.3f}%  gaps {o.get('gaps')}  acks {o.get('acks')}")
```

**Interpreting it:**

- Establish your own baseline first (a low single-digit percentage is typical for a
  software mirror). Compare against it, not against zero.
- Short bursts can occur without any drop counter in the capture path moving. Treat a
  burst as a sensor-health question before treating it as a finding.

**The failure mode that matters most:** `capture_loss` is computed from TCP ACKs for data
Zeek never saw. A **partially** blind sensor is loud. A **completely** blind sensor sees
no ACKs either, reports **0% loss**, and looks perfect. Loud when degraded, silent when
dead. If loss is suspiciously *low* and traffic volume has dropped, suspect the mirror,
not good luck:

```bash
# on pve, not in CT206 - the mirror is a tc rule on OPNsense's LAN tap
tc filter show dev tap200i1 ingress | grep -c mirred    # expect 1
tc filter show dev tap200i1 egress  | grep -c mirred    # expect 1 (NOT 0, and NOT 2)
```

Both hooks must show exactly 1. `tc filter show dev tap200i1` **without** the direction
keyword shows the root qdisc and reports nothing - that is not evidence the mirror is
missing. Two on the egress hook means a duplicate mirror, which double-delivers every
packet to Zeek and corrupts analysis.

The `zeek-span.pl` hookscript re-applies both after any firewall-VM restart, and Wazuh
rules 100890-100892 page if it cannot.

## Writing a custom detection

There is no `custom-detections` directory yet - create it. Load order matters; anything
not referenced from `local.zeek` silently never runs.

```bash
ssh root@10.10.130.10
pct exec 206 -- mkdir -p /opt/zeek/share/zeek/site/custom-detections
# write the .zeek file, then append to local.zeek:
#   @load ./custom-detections/your-detection.zeek

# ALWAYS syntax-check before deploying - a bad script stops Zeek from starting:
pct exec 206 -- /opt/zeek/bin/zeek -a /opt/zeek/share/zeek/site/local.zeek
pct exec 206 -- systemctl restart zeek     # or: /opt/zeek/bin/zeekctl deploy
```

Verify it actually loaded rather than assuming - a script that fails to load produces no
error at runtime, just silence:

```bash
pct exec 206 -- grep -i "your-detection" /opt/zeek/logs/current/stderr.log
pct exec 206 -- ls -la /opt/zeek/logs/current/notice.log
```

## Feeding findings into Wazuh

Zeek notices already reach Wazuh through the CT206 agent. To make a new notice page:

1. Write the detection so it raises a Zeek `NOTICE` with a distinctive `note` value.
2. Add a Wazuh rule keyed on that note, in the local rules on CT201.
3. Levels: **>= 10 pages** via `custom-ntfy`. Use 3 for context, 7 for suspicious,
   12 for confirmed-bad.
4. **Test with `wazuh-logtest` before trusting it**, then confirm in `alerts.log`.

Existing Zeek-related rules: **100710/100713** (capture loss / SENSOR BLIND, level 12),
**100715/100716**. Do not collide with those IDs.

## Notes on this deployment

- **Intel framework** is configured from `zeek/intel/` in this repo; `intel.log` matches
  are shipped to Wazuh (rules 100900-100909).
- **Logs are JSON but nothing sets `json-streaming`** in `local.zeek` - JSON is coming
  from elsewhere in the config. Do not "fix" this by adding a second JSON writer.
- **2 cores / 2 GB.** Zeek is single-threaded here. Heavy `-r` pcap replays compete with
  live capture; do them when you can tolerate loss, or on a copy elsewhere.

## Reporting format

```markdown
## Zeek finding - <date>

**Sensor health at time of analysis:** capture_loss X.X% (your baseline: X.X%)
**Window analysed:** <start> to <end>, <log files>

### Finding
<what, with the query output that shows it>

### Why this is/is not benign
<direction, segment pair, whether the flow completed, what the host is>

### What would confirm it
<the specific next query or capture - not a guess>
```

Always state sensor health. A finding from a degraded window carries less weight, and a
null result from a blind sensor carries none.
