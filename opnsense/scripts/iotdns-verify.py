#!/usr/bin/env python3
import json
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', 'scripts'))
from opn_api import call as _api_call  # credentials: see config/opnsense.env.example
def call(path, body=None, t=90):
    try: return _api_call(path, body, timeout=t)
    except Exception as ex: return {'ERR': str(ex)[:150]}
def sel(n):
    if not isinstance(n,dict): return n
    return ','.join(k for k,v in n.items() if isinstance(v,dict) and v.get('selected'))

print("="*70); print("A. UNBOUND — logging + DNSBL"); print("="*70)
u=call('/api/unbound/settings/get')
if 'ERR' in u: print(" ERR",u['ERR'])
else:
    g=u['unbound']['general']; adv=u['unbound'].get('advanced',{})
    print(" general: enabled=%s port=%s" % (g.get('enabled'), g.get('port')))
    for k in ('logqueries','logreplies','logservfail','loglocalactions','extendedstatistics','logverbosity'):
        v=g.get(k, adv.get(k))
        print("   %-20s = %s" % (k, sel(v) if isinstance(v,dict) else v))
    d=u['unbound'].get('dnsbl',{})
    print(" dnsbl:")
    for k,v in d.items():
        print("   %-20s = %s" % (k, (sel(v) if isinstance(v,dict) else v))[:150])

print(); print("="*70); print("B. LIVE pf STATES for IOT hosts"); print("="*70)
for ep,label in [('/api/diagnostics/firewall/query_states','query_states'),
                 ('/api/diagnostics/firewall/pf_states','pf_states')]:
    r=call(ep, {"current":1,"rowCount":500,"searchPhrase":""})
    if 'ERR' in r: print(" %-14s -> %s" % (label, r['ERR'])); continue
    rows=r.get('rows') or []
    print(" %-14s -> %d rows (total %s)" % (label, len(rows), r.get('total')))
    if rows: print("   sample keys:", list(rows[0].keys()))
    dns=[x for x in rows if ':53' in json.dumps(x) and '10.10.120.' in json.dumps(x)]
    print("   IOT-and-:53 states: %d" % len(dns))
    for x in dns[:12]:
        print("    ", json.dumps(x)[:190])
    break

print(); print("="*70); print("C. NAT rdr rules"); print("="*70)
for ep in ['/api/firewall/source_nat/search_rule','/api/firewall/one_to_one/search_rule']:
    r=call(ep,{"current":1,"rowCount":100})
    print(" %s -> %s" % (ep.split('/')[-2], (r.get('total') if 'ERR' not in r else r['ERR'])))
print(" (classic port-forward lives in config.xml, not the MVC API — checking filter rules instead)")

print(); print("="*70); print("D. FILTER RULES touching 53 / 853 / IOT"); print("="*70)
r=call('/api/firewall/filter/search_rule',{"current":1,"rowCount":300})
if 'ERR' in r: print(" ERR",r['ERR'])
else:
    rows=r.get('rows') or []
    print(" total rules in MVC filter: %d" % len(rows))
    for x in rows:
        blob=json.dumps(x)
        if '853' in blob or '"53"' in blob or 'IOT' in blob or '10.10.120' in blob:
            print("   seq=%-5s %-6s %-40s %s" % (x.get('sequence'), x.get('action'),
                  (x.get('description') or '')[:40], x.get('destination_port') or ''))
