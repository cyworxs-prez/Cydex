#!/bin/bash
# DoH/DoT indicators for the IOT VLAN from Zeek. Run inside CT206.
L=/opt/zeek/logs/current
DOH='dns\.google|cloudflare-dns|one\.one\.one\.one|quad9|nextdns|adguard|opendns|cleanbrowsing|dns\.sb|mullvad|controld|dns-query|^doh\.|\.doh\.'

echo "== window =="
python3 - <<'PY'
import json,os
p='/opt/zeek/logs/current/conn.log'
ts=[]
for l in open(p):
    try: ts.append(json.loads(l)['ts'])
    except Exception: pass
if ts:
    import datetime as d
    print("  conn.log entries: %d  span: %s .. %s (%.1f min)" % (len(ts),
      d.datetime.fromtimestamp(min(ts)).strftime('%H:%M:%S'),
      d.datetime.fromtimestamp(max(ts)).strftime('%H:%M:%S'), (max(ts)-min(ts))/60))
PY

echo
echo "== 1. IOT TLS SNI matching DoH providers =="
python3 - <<PY
import json,re
pat=re.compile(r'$DOH',re.I)
n=0; tot=0
for l in open('$L/ssl.log'):
    try: r=json.loads(l)
    except Exception: continue
    if not str(r.get('id.orig_h','')).startswith('10.10.120.'): continue
    tot+=1
    sni=r.get('server_name') or ''
    if pat.search(sni):
        n+=1; print("   HIT %s -> %s (%s)" % (r['id.orig_h'], sni, r.get('id.resp_h')))
print("   IOT TLS sessions: %d   DoH-SNI hits: %d" % (tot,n))
PY

echo
echo "== 2. IOT DNS queries for DoH endpoints =="
python3 - <<PY
import json,re
pat=re.compile(r'$DOH',re.I)
n=0; tot=0
for l in open('$L/dns.log'):
    try: r=json.loads(l)
    except Exception: continue
    if not str(r.get('id.orig_h','')).startswith('10.10.120.'): continue
    tot+=1
    q=r.get('query') or ''
    if pat.search(q):
        n+=1; print("   HIT %s asked %s" % (r['id.orig_h'], q))
print("   IOT DNS queries: %d   DoH-name hits: %d" % (tot,n))
PY

echo
echo "== 3. IOT QUIC / HTTP3 (DoH can ride h3) =="
if [ -f "$L/quic.log" ]; then
python3 - <<PY
import json
from collections import Counter
c=Counter()
for l in open('$L/quic.log'):
    try: r=json.loads(l)
    except Exception: continue
    if str(r.get('id.orig_h','')).startswith('10.10.120.'):
        c[(r.get('id.resp_h'), r.get('server_name') or '-')]+=1
print("   IOT QUIC sessions: %d" % sum(c.values()))
for (ip,sni),n in c.most_common(12): print("    %-16s %-42s %d" % (ip, sni[:42], n))
PY
fi

echo
echo "== 4. top IOT SNI overall (what they actually talk to) =="
python3 - <<PY
import json
from collections import Counter
c=Counter()
for l in open('$L/ssl.log'):
    try: r=json.loads(l)
    except Exception: continue
    if str(r.get('id.orig_h','')).startswith('10.10.120.'):
        c[r.get('server_name') or '(no SNI)']+=1
for s,n in c.most_common(15): print("    %-52s %d" % (s[:52], n))
PY
