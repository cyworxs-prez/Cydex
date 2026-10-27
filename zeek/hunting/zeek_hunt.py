#!/usr/bin/env python3
"""Read-only Zeek hunt: beaconing, rare destinations, DNS anomalies, TLS posture."""
import json, glob, math, collections, ipaddress, os

def load(name, cap=200000):
    rows=[]
    for p in [f"/opt/zeek/logs/current/{name}.log"]:
        if not os.path.exists(p): continue
        with open(p, errors="replace") as fh:
            for line in fh:
                line=line.strip()
                if not line.startswith("{"): continue
                try: rows.append(json.loads(line))
                except: pass
                if len(rows)>=cap: break
    return rows

def priv(ip):
    try: return ipaddress.ip_address(ip).is_private or ipaddress.ip_address(ip).is_link_local or ipaddress.ip_address(ip).is_multicast
    except: return True

conn=load("conn"); dns=load("dns"); ssl=load("ssl"); http=load("http")
print(f"records: conn={len(conn)} dns={len(dns)} ssl={len(ssl)} http={len(http)}")

# ---------- external destinations ----------
ext=collections.Counter(); extbytes=collections.Counter()
pairs=collections.defaultdict(list)
for c in conn:
    d=c.get("id.resp_h"); s=c.get("id.orig_h")
    if not d or priv(d): continue
    ext[d]+=1
    extbytes[d]+=(c.get("orig_ip_bytes",0) or 0)+(c.get("resp_ip_bytes",0) or 0)
    pairs[(s,d,c.get("id.resp_p"))].append(c.get("ts",0))

print("\n--- TOP EXTERNAL DESTINATIONS (by conn count) ---")
for ip,n in ext.most_common(12):
    print(f"  {n:>5} conns  {extbytes[ip]/1024:>9.1f} KB  {ip}")

# ---------- beaconing: regular intervals ----------
print("\n--- BEACONING CANDIDATES (>=6 conns, low interval jitter) ---")
found=0
for (s,d,p),ts in pairs.items():
    if len(ts)<6: continue
    ts=sorted(ts); iv=[b-a for a,b in zip(ts,ts[1:]) if b-a>0]
    if len(iv)<5: continue
    m=sum(iv)/len(iv)
    if m<=0: continue
    sd=math.sqrt(sum((x-m)**2 for x in iv)/len(iv))
    cv=sd/m                      # coefficient of variation; low => regular
    if cv<0.35 and m>5:
        print(f"  {s} -> {d}:{p}  n={len(ts)} mean={m:.0f}s jitter(cv)={cv:.2f}")
        found+=1
if not found: print("  none detected in current window")

# ---------- DNS anomalies ----------
def entropy(s):
    if not s: return 0
    c=collections.Counter(s); n=len(s)
    return -sum((v/n)*math.log2(v/n) for v in c.values())

print("\n--- DNS: high-entropy / long labels (possible DGA or tunneling) ---")
seen=set(); hits=0
for r in dns:
    qq=r.get("query","") or ""
    if not qq or qq in seen: continue
    seen.add(qq)
    lbl=qq.split(".")[0]
    if len(lbl)>=18 and entropy(lbl)>3.6:
        print(f"  H={entropy(lbl):.2f} len={len(lbl):<3} {qq[:88]}")
        hits+=1
    if hits>=12: break
if not hits: print("  none")

print("\n--- DNS: external resolvers contacted (should be OPNsense only) ---")
res=collections.Counter()
for r in dns:
    d=r.get("id.resp_h")
    if d: res[d]+=1
for ip,n in res.most_common(8):
    tag="  <-- EXTERNAL" if not priv(ip) else ""
    print(f"  {n:>6}  {ip}{tag}")

print("\n--- DNS: NXDOMAIN ratio (DGA indicator) ---")
rc=collections.Counter(r.get("rcode_name") for r in dns)
tot=sum(rc.values()) or 1
for k,v in rc.most_common(5):
    print(f"  {v:>6} ({100*v/tot:>5.1f}%)  {k}")

# ---------- TLS ----------
print("\n--- TLS: server names by client (top) ---")
sni=collections.Counter((s.get("id.orig_h"), s.get("server_name")) for s in ssl if s.get("server_name"))
for (o,n),c in sni.most_common(10):
    print(f"  {c:>4}  {o:<16} {n[:60]}")

print("\n--- TLS: validation status ---")
vs=collections.Counter(s.get("validation_status") for s in ssl)
for k,v in vs.most_common(6): print(f"  {v:>5}  {k}")

print("\n--- TLS: JA3 fingerprints (client) ---")
ja3=collections.Counter(s.get("ja3") for s in ssl if s.get("ja3"))
print(f"  distinct JA3: {len(ja3)}")
for k,v in ja3.most_common(5): print(f"  {v:>5}  {k}")

# ---------- plaintext HTTP ----------
print("\n--- HTTP (plaintext) hosts ---")
hh=collections.Counter((h.get("id.orig_h"), h.get("host")) for h in http if h.get("host"))
for (o,host),c in hh.most_common(10):
    print(f"  {c:>4}  {o:<16} {host[:60]}")

# ---------- cross-VLAN ----------
print("\n--- CROSS-SEGMENT FLOWS (internal -> internal, different /24) ---")
xs=collections.Counter()
for c in conn:
    s,d=c.get("id.orig_h"),c.get("id.resp_h")
    if not s or not d or not priv(s) or not priv(d): continue
    try:
        if ipaddress.ip_address(s).version!=4 or ipaddress.ip_address(d).version!=4: continue
    except: continue
    a=".".join(s.split(".")[:3]); b=".".join(d.split(".")[:3])
    if a!=b and not d.endswith(".255"):
        xs[(a,b,c.get("id.resp_p"))]+=1
for (a,b,p),n in xs.most_common(12):
    print(f"  {n:>5}  {a}.0/24 -> {b}.0/24 : {p}")
