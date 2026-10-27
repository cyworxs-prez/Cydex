#!/bin/bash
# zeek-hunt.sh - run a hunt against the homelab Zeek sensor (CT206) from anywhere
# that can reach pve. Replaces the upstream agent.py, which assumed Zeek was local.
#
# Usage:  ./zeek-hunt.sh health|beacon|dns|exfil|rare|crossseg|longconn [logdir]
#
# Design notes:
#   - hops via pve; CT206 has no direct SSH
#   - absolute /opt/zeek/bin paths: that dir is NOT on PATH under pct exec
#   - python3, not jq (jq is not installed) and not zeek-cut (logs are JSON, not TSV)
#   - streams line by line; CT206 has 2 GB and a live capture to protect
set -uo pipefail
PVE=${PVE:-root@10.10.130.10}
CT=${CT:-206}
LOGDIR=${2:-/opt/zeek/logs/current}
MODE=${1:-health}

run() { ssh -o BatchMode=yes -o ConnectTimeout=10 "$PVE" "pct exec $CT -- python3 - <<'PYEOF'
$1
PYEOF"; }

case "$MODE" in
health)
  run "
import json
p='$LOGDIR/capture_loss.log'
try: r=[json.loads(l) for l in open(p) if l.startswith('{')]
except FileNotFoundError: print('no capture_loss.log - sensor may never have started'); raise SystemExit
if not r: print('capture_loss.log empty'); raise SystemExit
last=[o.get('percent_lost',0) for o in r[-8:]]
print('last 8 samples (%%): ' + ', '.join('%.2f'%x for x in last))
avg=sum(last)/len(last)
print('mean %.2f%%  (compare with your own baseline)' % avg)
if avg>5: print('DEGRADED - treat findings from this window with caution')
elif avg<0.05: print('SUSPICIOUSLY LOW - a fully blind sensor reports 0%. Check the tc mirror on pve.')
else: print('normal')
"
  echo "--- mirror check (run on pve) ---"
  ssh -o BatchMode=yes "$PVE" 'echo "  ingress mirred: $(tc filter show dev tap200i1 ingress 2>/dev/null | grep -c mirred) (expect 1)"; echo "  egress  mirred: $(tc filter show dev tap200i1 egress 2>/dev/null | grep -c mirred) (expect 1)"'
  ;;
beacon)
  run "
import json,collections,statistics
t=collections.defaultdict(list)
for line in open('$LOGDIR/conn.log',errors='replace'):
    if not line.startswith('{'): continue
    try: o=json.loads(line)
    except Exception: continue
    d=o['id.resp_h']
    if d.endswith('.255') or d=='255.255.255.255' or (d.split('.')[0].isdigit() and 224<=int(d.split('.')[0])<=239): continue
    t[(o['id.orig_h'],o['id.resp_h'],o.get('id.resp_p'))].append(o['ts'])
hits=0
for k,v in sorted(t.items(), key=lambda x:-len(x[1])):
    if len(v)<8: continue
    v.sort(); g=[b-a for a,b in zip(v,v[1:])]
    m=statistics.mean(g); s=statistics.pstdev(g)
    if m>5 and s/m<0.15:
        print('%-46s n=%-5d every %6.0fs  jitter %5.1f%%' % (str(k),len(v),m,100*s/m)); hits+=1
print('no periodic patterns found' if not hits else '%d candidate(s)'%hits)
"
  ;;
dns)
  run "
import json,collections,math
q=collections.defaultdict(list)
for line in open('$LOGDIR/dns.log',errors='replace'):
    if not line.startswith('{'): continue
    try: o=json.loads(line)
    except Exception: continue
    if o.get('query'): q[o['id.orig_h']].append(o['query'])
def ent(s): return -sum((s.count(c)/len(s))*math.log2(s.count(c)/len(s)) for c in set(s)) if s else 0
hits=0
for src,qs in sorted(q.items(), key=lambda x:-len(x[1])):
    longs=[x for x in qs if len(x)>50]
    hi=[x for x in qs if len(x.split('.')[0])>12 and ent(x.split('.')[0])>3.5]
    if len(qs)>500 or longs or len(hi)>20:
        print('%-16s %5d queries  %3d long  %3d high-entropy' % (src,len(qs),len(longs),len(hi)))
        for x in (longs[:2] or hi[:2]): print('      ', x[:90])
        hits+=1
print('nothing anomalous' if not hits else '')
"
  ;;
exfil)
  run "
import json,collections
b=collections.defaultdict(lambda:[0,0])
for line in open('$LOGDIR/conn.log',errors='replace'):
    if not line.startswith('{'): continue
    try: o=json.loads(line)
    except Exception: continue
    k=(o['id.orig_h'],o['id.resp_h'])
    b[k][0]+=o.get('orig_bytes',0) or 0; b[k][1]+=o.get('resp_bytes',0) or 0
hits=0
for k,(up,dn) in sorted(b.items(), key=lambda x:-x[1][0])[:40]:
    if up>10_000_000 and up>dn*3:
        print('%-16s -> %-16s  up %8.1f MB  down %8.1f MB' % (k[0],k[1],up/1e6,dn/1e6)); hits+=1
print('no outbound-heavy transfers' if not hits else '')
"
  ;;
rare)
  run "
import json,collections
c=collections.Counter(); j=collections.Counter()
try:
    for l in open('$LOGDIR/http.log',errors='replace'):
        if l.startswith('{'):
            try: c[json.loads(l).get('user_agent','')]+=1
            except Exception: pass
except FileNotFoundError: pass
try:
    for l in open('$LOGDIR/ssl.log',errors='replace'):
        if l.startswith('{'):
            try: j[json.loads(l).get('ja3','')]+=1
            except Exception: pass
except FileNotFoundError: pass
print('--- rarest user agents ---')
for u,n in [x for x in c.most_common() if x[0]][-12:]: print('  %4d  %s'%(n,u[:80]))
print('--- rarest JA3 ---')
for x,n in [y for y in j.most_common() if y[0]][-12:]: print('  %4d  %s'%(n,x))
"
  ;;
crossseg)
  run "
import json
def seg(ip):
    for p,n in (('10.10.110.','TRUSTED'),('10.10.120.','IoT'),('10.10.130.','MGMT'),('10.10.140.','LAB')):
        if ip.startswith(p): return n
    return 'EXT'
import collections
c=collections.Counter(); ex=collections.defaultdict(list)
for line in open('$LOGDIR/conn.log',errors='replace'):
    if not line.startswith('{'): continue
    try: o=json.loads(line)
    except Exception: continue
    a,b=seg(o['id.orig_h']),seg(o['id.resp_h'])
    if a!=b and 'EXT' not in (a,b) and o.get('conn_state') in ('SF','S1','RSTO'):
        c[(a,b)]+=1
        if len(ex[(a,b)])<3: ex[(a,b)].append('%s:%s -> %s:%s %s'%(o['id.orig_h'],o.get('id.orig_p'),o['id.resp_h'],o.get('id.resp_p'),o.get('proto')))
for k,n in c.most_common():
    print('%s -> %s : %d completed' % (k[0],k[1],n))
    for e in ex[k]: print('     ',e)
print('no completed cross-segment flows' if not c else '')
"
  ;;
longconn)
  run "
import json
out=[]
for line in open('$LOGDIR/conn.log',errors='replace'):
    if not line.startswith('{'): continue
    try: o=json.loads(line)
    except Exception: continue
    d=o.get('duration',0) or 0
    if d>3600: out.append((d,o['id.orig_h'],o['id.resp_h'],o.get('id.resp_p'),o.get('proto')))
for d,a,b,p,pr in sorted(out,reverse=True)[:20]:
    print('%7.0fs  %-16s -> %-16s :%-6s %s'%(d,a,b,p,pr))
print('none over 1h' if not out else '')
"
  ;;
*) echo "usage: $0 health|beacon|dns|exfil|rare|crossseg|longconn [logdir]" >&2; exit 2;;
esac
