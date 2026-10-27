#!/usr/bin/env python3
"""Pull real hostnames per VLAN so the map can show individual hosts."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collections import defaultdict
from opn_api import call

SEG = [('10.10.110.', 'TRUSTED'), ('10.10.120.', 'IOT'),
       ('10.10.130.', 'MGMT'), ('10.10.140.', 'LAB'), ('10.10.150.', 'DIRECT')]


def seg_of(ip):
    for pre, name in SEG:
        if ip.startswith(pre):
            return name
    return 'OTHER'


leases = {}
for ep in ('/api/kea/leases4/search', '/api/dhcpv4/leases/searchLease'):
    try:
        d = call(ep, {'current': 1, 'rowCount': 500})
        rows = d.get('rows') or []
        if rows:
            print("### leases from %s: %d" % (ep, len(rows)))
            for r in rows:
                ip = r.get('address') or r.get('ip') or ''
                if not ip:
                    continue
                leases[ip] = {
                    'hostname': (r.get('hostname') or r.get('client-hostname') or '').strip(),
                    'mac': (r.get('hwaddr') or r.get('mac') or '').lower(),
                    'state': r.get('state', ''),
                }
            break
    except Exception as e:
        print("  %s -> %s" % (ep, str(e)[:70]))

arp = call('/api/diagnostics/interface/search_arp', {'current': 1, 'rowCount': 2000}).get('rows') or []
for a in arp:
    ip = a.get('ip', '')
    e = leases.setdefault(ip, {'hostname': '', 'mac': '', 'state': ''})
    e.setdefault('mfg', '')
    e['mfg'] = a.get('manufacturer') or ''
    if not e.get('mac'):
        e['mac'] = (a.get('mac') or '').lower()
    if not e.get('hostname'):
        e['hostname'] = (a.get('hostname') or '').strip()

by = defaultdict(list)
for ip, e in leases.items():
    by[seg_of(ip)].append((ip, e))


def ipkey(t):
    try:
        return tuple(int(p) for p in t[0].split('.'))
    except Exception:
        return (0, 0, 0, 0)


for s in ('TRUSTED', 'IOT', 'MGMT', 'LAB', 'DIRECT'):
    rows = sorted(by.get(s, []), key=ipkey)
    named = [r for r in rows if r[1].get('hostname')]
    print("\n### %s — %d hosts (%d with a hostname)" % (s, len(rows), len(named)))
    for ip, e in rows:
        h = e.get('hostname') or ''
        m = (e.get('mfg') or '')[:26]
        print("   %-16s %-26s %s" % (ip, h[:26], m))
