#!/usr/bin/env python3
"""Read-only Zeek hunt: DNS resolver bypass, bad certs, per-host port drill-down,
long-lived external connections. Run inside the Zeek sensor.

Usage: zeek_dns_tls_hunt.py [HOST PORT]   # optional drill-down on one host:port
"""
import json, collections, os, ipaddress, sys
HOST = sys.argv[1] if len(sys.argv) > 2 else None
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else None

def load(n):
    p=f"/opt/zeek/logs/current/{n}.log"; r=[]
    if os.path.exists(p):
        for line in open(p, errors="replace"):
            line=line.strip()
            if line.startswith("{"):
                try: r.append(json.loads(line))
                except: pass
    return r

dns=load("dns"); ssl=load("ssl"); conn=load("conn")
EXT_RES={"8.8.8.8","8.8.4.4","1.1.1.1","1.0.0.1","9.9.9.9","208.67.222.222"}

print("=== DNS BYPASS: internal hosts querying EXTERNAL resolvers ===")
by=collections.Counter(); samples=collections.defaultdict(set)
for r in dns:
    d=r.get("id.resp_h"); s=r.get("id.orig_h")
    if d in EXT_RES and s:
        by[(s,d)]+=1
        if len(samples[s])<4 and r.get("query"): samples[s].add(r["query"][:52])
for (s,d),n in by.most_common(20):
    print(f"  {n:>5}  {s:<16} -> {d}")
print("\n  sample queries per bypassing host:")
for s,q in samples.items():
    print(f"   {s:<16} {'; '.join(sorted(q))[:100]}")

print("\n=== SELF-SIGNED / INVALID CERT DETAIL ===")
for s in ssl:
    v=(s.get("validation_status") or "")
    if "self signed" in v or "expired" in v or "revoked" in v:
        print(f"  {s.get('id.orig_h')} -> {s.get('id.resp_h')}:{s.get('id.resp_p')} "
              f"sni={s.get('server_name')} status={v}")

if HOST:
  print(f"\n=== PORT-{PORT} DETAIL (host {HOST}) ===")
  tot_o=tot_r=0; n=0; dst=set()
  for c in conn:
    if c.get("id.orig_h")==HOST and c.get("id.resp_p")==PORT:
        n+=1; tot_o+=c.get("orig_ip_bytes",0) or 0; tot_r+=c.get("resp_ip_bytes",0) or 0
        dst.add(c.get("id.resp_h")); st=c.get("conn_state")
  print(f"  conns={n} dst={sorted(dst)} orig_bytes={tot_o} resp_bytes={tot_r}")
  states=collections.Counter(c.get("conn_state") for c in conn
          if c.get("id.orig_h")==HOST and c.get("id.resp_p")==PORT)
  print(f"  conn_states={dict(states)}")
  print(f"  all destinations contacted by {HOST}:")
  d2=collections.Counter(c.get("id.resp_h") for c in conn if c.get("id.orig_h")==HOST)
  for ip,c in d2.most_common(8): print(f"    {c:>4}  {ip}")

print("\n=== LONGEST-LIVED EXTERNAL CONNECTIONS ===")
def priv(ip):
    try: return ipaddress.ip_address(ip).is_private or ipaddress.ip_address(ip).is_multicast or ipaddress.ip_address(ip).is_link_local
    except: return True
longs=[c for c in conn if c.get("duration") and not priv(c.get("id.resp_h",""))]
for c in sorted(longs, key=lambda x: -x["duration"])[:8]:
    print(f"  {c['duration']:>8.0f}s  {c.get('id.orig_h')} -> {c.get('id.resp_h')}:{c.get('id.resp_p')} "
          f"tx={c.get('orig_ip_bytes',0)} rx={c.get('resp_ip_bytes',0)}")
