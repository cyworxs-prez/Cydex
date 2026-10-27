#!/usr/bin/env python3
"""Monit process-level watch on Suricata with native restart. Writes to OPNsense.
OPNsense rejects spaces in test.path, so exec-with-args is impossible.
Instead: define Suricata as a monit PROCESS service with start/stop programs,
and use monit's own RESTART action on a process-memory test. This targets the
actual failure mode (Suricata runaway) instead of a whole-system proxy metric."""
import json,os,base64,ssl,urllib.request,sys

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', 'scripts'))
from opn_api import call as _api_call, sel  # credentials: see config/opnsense.env.example
def call(path, body=None, t=90):
    try: return _api_call(path, body, timeout=t)
    except Exception as ex: return {'ERR': str(ex)[:150]}


def sel(n):
    if not isinstance(n,dict): return n
    return ','.join(k for k,v in n.items() if isinstance(v,dict) and v.get('selected'))

TESTS = [
    ("SuricataMemRunaway", "ProcessResource",
     "total memory usage is greater than 3500 MB for 3 cycles", "restart", ""),
    ("SuricataDown", "Existence", "does not exist", "restart", ""),
]

cfg = call('/api/monit/settings/get')
if 'ERR' in cfg: print("FATAL:", cfg['ERR']); sys.exit(1)
monit = cfg['monit']
tests_by_name = {t['name']:(u,t) for u,t in (monit.get('test') or {}).items()}
svc_by_name   = {s['name']:(u,s) for u,s in (monit.get('service') or {}).items()}

print("=== 1. tests ===")
uuids={}
for name,typ,cond,action,path in TESTS:
    if name in tests_by_name:
        u,t = tests_by_name[name]
        if (sel(t.get('action')), t.get('condition'))==(action,cond):
            print("  %-20s already correct" % name); uuids[name]=u; continue
        r=call('/api/monit/settings/setTest/'+u,
               {'test':{'name':name,'type':typ,'condition':cond,'action':action,'path':path}})
        print("  %-20s updated -> %s" % (name,r)); uuids[name]=u
    else:
        r=call('/api/monit/settings/addTest',
               {'test':{'name':name,'type':typ,'condition':cond,'action':action,'path':path}})
        if r.get('uuid'): print("  %-20s ADDED %s" % (name,r['uuid'])); uuids[name]=r['uuid']
        else: print("  %-20s FAILED %s" % (name,str(r)[:220]))

if len(uuids)!=len(TESTS):
    print("\nnot all tests created - stopping before touching services"); sys.exit(1)

print("\n=== 2. Suricata process service ===")
svc = {
    'enabled':'1', 'name':'Suricata', 'description':'IDS engine - restart on runaway memory',
    'type':'process',
    'pidfile':'/var/run/suricata.pid',
    'start':'/usr/local/sbin/configctl ids start',
    'stop':'/usr/local/sbin/configctl ids stop',
    'timeout':'300', 'starttimeout':'120',
    'tests':','.join(uuids[n] for n,_,_,_,_ in TESTS),
}
if 'Suricata' in svc_by_name:
    u,_=svc_by_name['Suricata']
    r=call('/api/monit/settings/setService/'+u, {'service':svc}); print("  updated ->",r); svc_uuid=u
else:
    r=call('/api/monit/settings/addService', {'service':svc})
    print("  added ->",r); svc_uuid=r.get('uuid')
if not svc_uuid: print("  could not create service"); sys.exit(1)

print("\n=== 3. reconfigure (this validates the generated monitrc) ===")
r=call('/api/monit/service/reconfigure', {})
print("  ",r)
if r.get('template')!='OK' or r.get('status')!='OK':
    print("  CONTROL FILE DID NOT VALIDATE - the service is saved but monit may not be running it")

print("\n=== 4. verify by read-back ===")
m2=call('/api/monit/settings/get')['monit']
s2=m2['service'][svc_uuid]
print("  name=%s enabled=%s type=%s" % (s2['name'], s2['enabled'], sel(s2['type'])))
print("  pidfile=%s" % s2.get('pidfile'))
print("  start  =%s" % s2.get('start'))
print("  stop   =%s" % s2.get('stop'))
att={u for u,v in s2['tests'].items() if isinstance(v,dict) and v.get('selected')}
for name,typ,cond,action,path in TESTS:
    u=uuids[name]; t=m2['test'].get(u)
    print("  test %-20s attached=%-5s action=%-8s cond=%s" %
          (name, u in att, sel(t.get('action')), t.get('condition')))

print("\n=== 5. live monit view ===")
st=call('/api/monit/status/get')
for s in (st.get('status',{}).get('service') or []):
    nm=s.get('name')
    if nm in ('Suricata','OPNsense.internal'):
        sysinfo=s.get('system') or {}
        mem=(sysinfo.get('memory') or s.get('memory') or {})
        print("  %-22s status=%s monitor=%s mem=%s%%" %
              (nm, s.get('status'), s.get('monitor'), mem.get('percent','?')))
