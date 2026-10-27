#!/usr/bin/env python3
import json,os,base64,ssl,urllib.request,re
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', 'scripts'))
from opn_api import call as _api_call, sel  # credentials: see config/opnsense.env.example
def call(path, body=None, t=90):
    try: return _api_call(path, body, timeout=t)
    except Exception as ex: return {'ERR': str(ex)[:150]}

print("### resolver log — dnsbl / blocklist / error lines ###")
d=call('/api/diagnostics/log/core/resolver',{"rowCount":4000,"current":1})
rows=sorted([r for r in (d.get('rows') or []) if r.get('timestamp')], key=lambda r:r['timestamp'])
pat=re.compile(r'dnsbl|blocklist|block|error|fail|warn|download|local-zone|local-data',re.I)
hits=[r for r in rows if pat.search(r.get('line') or '')]
print("  matching lines: %d (of %d)" % (len(hits), len(rows)))
for r in hits[-25:]:
    print("   ", r['timestamp'][11:19], (r.get('line') or '').strip()[:125])

print("\n### unbound service status + dnsbl endpoints ###")
for ep,body in [('/api/unbound/service/status',None),
                ('/api/unbound/service/dnsbl',None),
                ('/api/unbound/service/dnsbl',{}),
                ('/api/unbound/service/reconfigure',None)]:
    if ep.endswith('reconfigure'): continue
    r=call(ep,body)
    print("  %-38s %-6s -> %s" % (ep, 'POST' if body is not None else 'GET', json.dumps(r)[:180]))

print("\n### is the blocklist actually in effect? query a known-blocked domain ###")
# unbound's own diagnostics: dump the local zones it has loaded
for ep in ['/api/unbound/diagnostics/dumpcache','/api/unbound/diagnostics/listlocaldata',
           '/api/unbound/diagnostics/listinsecure','/api/unbound/diagnostics/stats']:
    r=call(ep)
    s=json.dumps(r)
    print("  %-42s -> %s" % (ep, (s[:160] if 'ERR' not in r else r['ERR'][:70])))

print("\n### live 853 rule present in pf? ###")
r=call('/api/diagnostics/firewall/list_rule_ids') 
print("  list_rule_ids:", json.dumps(r)[:200])
rl=call('/api/firewall/filter/search_rule',{"current":1,"rowCount":300}).get('rows') or []
for x in rl:
    if '853' in (x.get('description') or ''):
        full=call('/api/firewall/filter/get_rule/'+x['uuid']).get('rule',{})
        def sel(n):
            if not isinstance(n,dict): return n
            return ','.join(k for k,v in n.items() if isinstance(v,dict) and v.get('selected'))
        print("  rule seq=%s enabled=%s action=%s iface=%s proto=%s src=%s dst=%s port=%s log=%s" % (
            full.get('sequence'), full.get('enabled'), sel(full.get('action')),
            sel(full.get('interface')), sel(full.get('protocol')),
            full.get('source_net'), full.get('destination_net'),
            full.get('destination_port'), full.get('log')))
