#!/usr/bin/env python3
"""DoH exposure hunt for the IOT VLAN, using the data sources that still work
(Zeek is currently dark - the tc mirror did not survive the reboot)."""
import json,os,base64,ssl,urllib.request,socket,re
from collections import Counter
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', 'scripts'))
from opn_api import call as _api_call, sel  # credentials: see config/opnsense.env.example
def call(path, body=None, t=90):
    try: return _api_call(path, body, timeout=t)
    except Exception as ex: return {'ERR': str(ex)[:150]}

DOH_HOSTS = re.compile(r'(dns\.google|cloudflare-dns|one\.one\.one\.one|mozilla\.cloudflare-dns|'
    r'dns\.quad9\.net|dns9?\.quad9|nextdns\.io|adguard-dns|dns\.adguard|doh\.opendns|'
    r'doh\.cleanbrowsing|dns\.sb|doh\.mullvad|controld\.com|freedns\.controld|dns\.nextdns|'
    r'chrome\.cloudflare-dns|security\.cloudflare-dns|family\.cloudflare-dns|'
    r'dot\.|doh\.|dns-query)', re.I)

print("="*74)
print("1. DoH BOOTSTRAP LOOKUPS  (a device using DoH must first resolve its endpoint)")
print("="*74)
d=call('/api/diagnostics/log/core/resolver',{"rowCount":5000,"current":1})
rows=sorted([r for r in (d.get('rows') or []) if r.get('timestamp')], key=lambda r:r['timestamp'])
print("  resolver log lines: %d   window: %s .. %s" %
      (len(rows), rows[0]['timestamp'][11:19] if rows else '-', rows[-1]['timestamp'][11:19] if rows else '-'))
hits=[r for r in rows if DOH_HOSTS.search(r.get('line') or '')]
print("  DoH-endpoint lookups: %d" % len(hits))
for r in hits[-20:]:
    print("   ", r['timestamp'][11:19], (r.get('line') or '').strip()[:120])
# who asked
askers=Counter()
for r in hits:
    m=re.search(r'(192\.168\.\d+\.\d+)', r.get('line') or '')
    if m: askers[m.group(1)]+=1
if askers:
    print("  requesters:")
    for ip,n in askers.most_common(10): print("    %-16s %d" % (ip,n))

print()
print("="*74)
print("2. IOT -> :443  destinations (who are they actually talking to?)")
print("="*74)
srows=[]; page=1
while True:
    r=call('/api/diagnostics/firewall/query_states',{"current":page,"rowCount":1000,"searchPhrase":""})
    if 'ERR' in r: print("  state ERR", r['ERR']); break
    b=r.get('rows') or []; srows+=b
    if len(srows)>=int(r.get('total') or 0) or not b: break
    page+=1
iot443=[x for x in srows if (x.get('src_addr') or '').startswith('10.10.120.') and str(x.get('dst_port'))=='443']
dests=Counter(x.get('dst_addr') for x in iot443)
print("  states: %d   distinct destinations: %d" % (len(iot443), len(dests)))
KNOWN_DOH={'8.8.8.8','8.8.4.4','1.1.1.1','1.0.0.1','9.9.9.9','149.112.112.112',
 '208.67.222.222','208.67.220.220','94.140.14.14','94.140.15.15','45.90.28.0','45.90.30.0',
 '76.76.2.0','76.76.10.0','185.228.168.9','45.11.45.11','76.76.19.19','193.110.81.0','185.253.5.0'}
print("  %-17s %-6s %s" % ("dest","states","reverse dns"))
for ip,n in dests.most_common(30):
    try: host=socket.gethostbyaddr(ip)[0]
    except Exception: host='-'
    flag=''
    if ip in KNOWN_DOH: flag='  <<< KNOWN DoH RESOLVER IP'
    elif DOH_HOSTS.search(host): flag='  <<< DoH-LOOKING HOSTNAME'
    print("  %-17s %-6d %s%s" % (ip, n, host[:52], flag))

print()
print("="*74)
print("3. IOT devices talking to hardcoded resolver IPs on ANY port")
print("="*74)
hard=[x for x in srows if (x.get('src_addr') or '').startswith('10.10.120.')
      and (x.get('dst_addr') in KNOWN_DOH or x.get('nat_addr') in KNOWN_DOH)]
print("  states: %d" % len(hard))
c=Counter((x.get('src_addr'), x.get('nat_addr') or x.get('dst_addr'), str(x.get('dst_port'))) for x in hard)
for (s,dst,pt),n in c.most_common(20):
    print("    %-16s -> %-16s :%-5s  %d  %s" % (s,dst,pt,n,
          "(intercepted by rdr)" if pt=='53' else "<<< NOT port 53 - not covered by the redirect"))
