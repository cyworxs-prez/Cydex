#!/usr/bin/env python3
"""Apply config/homelab.env to every file that carries a site value.

    python3 tools/localize.py            # show what would change (default, read-only)
    python3 tools/localize.py --apply    # rewrite the files, then re-check
    python3 tools/localize.py --check    # exit 1 if any file still holds a value that
                                         # differs from config/homelab.env

Why this exists: Wazuh rules, Zeek config, agent config, hunting scripts, host-side
defaults and the map all carry addresses / VLANs / guest IDs as literals, because the
programs that read them have no shared config. This tool keeps them in sync with one file.

How it works: it knows the values currently in the files (the fictional reference
values on first run, then whatever it last applied - stored in config/localized.env)
and replaces each one with your value. Matching is anchored to specific forms
(full addresses, /24 prefixes, `VLAN 110`, `tap200i1`, `CT 201`...), never bare numbers.

After pulling upstream changes, localize the files that came in from upstream with
    python3 tools/localize.py --apply --from-reference path/to/file ...
(--check lists them.)

Scope: everything except docs/, tools/, config/*.example, LICENSE/NOTICE, images and
dependency trees. Add --include-docs to rewrite the docs too.
"""
import argparse, ipaddress, os, re, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
CONF = os.path.join(ROOT, 'config', 'homelab.env')
STATE = os.path.join(ROOT, 'config', 'localized.env')
SEGS = ('TRUSTED', 'IOT', 'MGMT', 'LAB', 'DIRECT')
HOSTS = ('PVE_HOST', 'FW_MGMT_IP', 'WAZUH_IP', 'SCANNER_IP', 'NETALERTX_IP', 'GUAC_IP',
         'ZEEK_IP', 'PENTEST_IP')
IDS = ('FW_VMID', 'WAZUH_CTID', 'GREENBONE_CTID', 'NETALERTX_CTID', 'KALI_VMID',
       'GUAC_CTID', 'ZEEK_CTID')

REFERENCE = {
    'TRUSTED_NET': '10.10.110.0/24', 'TRUSTED_VLAN': '110',
    'IOT_NET': '10.10.120.0/24', 'IOT_VLAN': '120',
    'MGMT_NET': '10.10.130.0/24', 'MGMT_VLAN': '130',
    'LAB_NET': '10.10.140.0/24', 'LAB_VLAN': '140',
    'DIRECT_NET': '10.10.150.0/24', 'DIRECT_VLAN': '150',
    'INTERNAL_SUPERNET': '10.10.0.0/16',
    'PVE_HOST': '10.10.130.10', 'FW_MGMT_IP': '10.10.130.1', 'WAZUH_IP': '10.10.140.11',
    'SCANNER_IP': '10.10.140.12', 'NETALERTX_IP': '10.10.140.13', 'GUAC_IP': '10.10.140.20',
    'ZEEK_IP': '10.10.140.21', 'PENTEST_IP': '10.10.140.24',
    'FW_VMID': '200', 'WAZUH_CTID': '201', 'GREENBONE_CTID': '202', 'NETALERTX_CTID': '203',
    'KALI_VMID': '204', 'GUAC_CTID': '205', 'ZEEK_CTID': '206',
    'FW_TRUNK_NETIF': '1', 'ZEEK_CAPTURE_NETIF': '1',
}
SKIP_DIRS = {'.git', 'node_modules', 'tools'}
SKIP_FILES = {'LICENSE', 'NOTICE', 'README.md', 'SECURITY.md', 'package-lock.json', 'requirements-freeze.txt'}
SKIP_EXT = ('.png', '.jpg', '.jpeg', '.gif', '.pdf', '.ndjson')


def read_env(path):
    out = {}
    if not os.path.exists(path):
        return out
    for line in open(path):
        line = line.split('#', 1)[0].strip()
        if '=' in line:
            k, v = line.split('=', 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def validate(v):
    errs = []
    for k in REFERENCE:
        if k not in v:
            errs.append(f'missing {k}')
    if errs:
        return errs
    nets = {}
    for s in SEGS:
        try:
            n = ipaddress.ip_network(v[f'{s}_NET'])
        except ValueError as e:
            errs.append(f'{s}_NET: {e}'); continue
        if n.prefixlen != 24:
            errs.append(f'{s}_NET must be a /24 (got {n})')
        nets[s] = n
        if not v[f'{s}_VLAN'].isdigit() or not 1 < int(v[f'{s}_VLAN']) < 4095:
            errs.append(f'{s}_VLAN must be 2-4094')
    try:
        sup = ipaddress.ip_network(v['INTERNAL_SUPERNET'])
        for s, n in nets.items():
            if not n.subnet_of(sup):
                errs.append(f'INTERNAL_SUPERNET {sup} does not contain {s}_NET {n}')
    except ValueError as e:
        errs.append(f'INTERNAL_SUPERNET: {e}')
    for h in HOSTS:
        try:
            ipaddress.ip_address(v[h])
        except ValueError:
            errs.append(f'{h} is not an IPv4 address')
    if ipaddress.ip_address(v['PVE_HOST']) not in nets.get('MGMT', ipaddress.ip_network('0.0.0.0/32')):
        errs.append('PVE_HOST should be inside MGMT_NET')
    for k in IDS:
        if not v[k].isdigit() or int(v[k]) < 100:
            errs.append(f'{k} must be a Proxmox ID >= 100')
    if len({v[k] for k in IDS}) != len(IDS):
        errs.append('guest IDs must be unique')
    vlans = [v[f'{s}_VLAN'] for s in SEGS]
    if len(set(vlans)) != len(vlans):
        errs.append('VLAN IDs must be unique')
    return errs


def prefix(net):
    return str(ipaddress.ip_network(net).network_address).rsplit('.', 1)[0] + '.'


def esc(s):
    return s.replace('.', r'\.')


def rules(old, new):
    """(regex, replacement) pairs mapping old -> new. Two-phase via placeholders so a
    new value can never be re-matched as somebody else's old value."""
    pairs = []
    # 1. full host addresses (literal and regex-escaped)
    for h in HOSTS:
        a, b = old[h], new[h]
        pairs.append((r'(?<![\d.])' + re.escape(a) + r'(?![\d])', b))
        pairs.append((re.escape(esc(a)) + r'(?![\d])', esc(b).replace('\\', '\\\\')))
    # 2. supernet and segment CIDRs, then /24 prefixes
    pairs.append((r'(?<![\d.])' + re.escape(old['INTERNAL_SUPERNET']), new['INTERNAL_SUPERNET']))
    for s in SEGS:
        pairs.append((r'(?<![\d.])' + re.escape(old[f'{s}_NET']), new[f'{s}_NET']))
    for s in SEGS:
        a, b = prefix(old[f'{s}_NET']), prefix(new[f'{s}_NET'])
        pairs.append((r'(?<![\d.])' + re.escape(a) + r'(?=\d|[\'"])', b))
        pairs.append((r'(?<![\d.])' + re.escape(a.rstrip('.')) + r"(?=['\"])", b.rstrip('.')))
        pairs.append((re.escape(esc(a)), esc(b).replace('\\', '\\\\')))
    # 3. VLAN IDs, only in VLAN-ish contexts
    ov = [old[f'{s}_VLAN'] for s in SEGS]; nv = [new[f'{s}_VLAN'] for s in SEGS]
    pairs.append((re.escape('bridge-vids 1 ' + ' '.join(ov)), 'bridge-vids 1 ' + ' '.join(nv)))
    pairs.append((re.escape('1,' + ','.join(ov)), '1,' + ','.join(nv)))
    pairs.append((re.escape('/'.join(ov)), '/'.join(nv)))
    for a, b in zip(ov, nv):
        pairs.append((r'\b(VLAN|vlan|Vlan|tag|vid|VID)([ -])' + a + r'\b', r'\g<1>\g<2>' + b))
    # 4. guest IDs, only in Proxmox-ish contexts
    fa, fb = old['FW_VMID'], new['FW_VMID']
    za, zb = old['ZEEK_CTID'], new['ZEEK_CTID']
    pairs.append((r'\btap' + fa + 'i' + old['FW_TRUNK_NETIF'] + r'\b', f"tap{fb}i{new['FW_TRUNK_NETIF']}"))
    pairs.append((r'\bveth' + za + 'i' + old['ZEEK_CAPTURE_NETIF'] + r'\b', f"veth{zb}i{new['ZEEK_CAPTURE_NETIF']}"))
    pairs.append((re.escape(' '.join(old[k] for k in IDS)), ' '.join(new[k] for k in IDS)))
    for k in IDS:
        a, b = old[k], new[k]
        pairs.append((r'\b(VM|CT|ct|vm)( ?)' + a + r'\b', r'\g<1>\g<2>' + b))
        pairs.append((r'(pct (?:exec|push|config|start|stop|enter) |qm (?:guest exec|agent|status|config|set|reboot|shutdown|start|snapshot|rollback|reset|stop) |--vmid "?)' + a + r'\b', r'\g<1>' + b))
        pairs.append((r'\b(' + k + r'|VMID|GREENBONE_VMID)=' + a + r'\b', r'\g<1>=' + b))
        pairs.append((r'(\$\{' + k + r':-)' + a + r'\}', r'\g<1>' + b + '}'))
    pairs.append((r'(\$\{FW_VMID:-|\$\{VMID:-)' + fa + r'\}', r'\g<1>' + fb + '}'))
    pairs.append((r'(\$\{CT:-)' + za + r'\}', r'\g<1>' + zb + '}'))
    pairs.append((r'(\$\{GREENBONE_VMID:-)' + old['GREENBONE_CTID'] + r'\}', r'\g<1>' + new['GREENBONE_CTID'] + '}'))
    pairs.append((r'(GREENBONE_VMID=)' + old['GREENBONE_CTID'] + r'\b', r'\g<1>' + new['GREENBONE_CTID']))
    # 5. Zeek capture interface name inside the CT
    pairs.append((r'(?m)^interface=eth' + old['ZEEK_CAPTURE_NETIF'] + r'$', 'interface=eth' + new['ZEEK_CAPTURE_NETIF']))
    return pairs


def files(include_docs):
    for d, ds, fs in os.walk(ROOT):
        rel = os.path.relpath(d, ROOT)
        ds[:] = [x for x in ds if x not in SKIP_DIRS and not (rel == '.' and x == 'docs' and not include_docs)]
        for f in fs:
            p = os.path.join(d, f)
            r = os.path.relpath(p, ROOT)
            if f in SKIP_FILES or f.endswith(SKIP_EXT) or r.startswith('config/'):
                continue
            yield p, r


def transform(text, pairs):
    """Replace every match with a placeholder holding its final text, so a value that
    was just written can never be matched again by a later pattern."""
    holders = []
    for pat, rep in pairs:
        def _hold(m, rep=rep):
            holders.append(m.expand(rep))
            return f'\x00{len(holders) - 1}\x00'
        text = re.sub(pat, _hold, text)
    return re.sub('\x00(\\d+)\x00', lambda m: holders[int(m.group(1))], text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--include-docs', action='store_true')
    ap.add_argument('--from-reference', nargs='+', metavar='FILE',
                    help='localize these files from the reference values (e.g. files you '
                         'just pulled from upstream), regardless of config/localized.env')
    a = ap.parse_args()

    if not os.path.exists(CONF):
        sys.exit('config/homelab.env not found - cp config/homelab.env.example config/homelab.env and edit it')
    new = {**REFERENCE, **{k: v for k, v in read_env(CONF).items() if k in REFERENCE}}
    errs = validate(new)
    if errs:
        sys.exit('config/homelab.env is invalid:\n  ' + '\n  '.join(errs))
    old = {**REFERENCE, **read_env(STATE)}
    if a.check:
        # Scan for leftovers of BOTH the reference values and the last-applied values,
        # so a file restored from upstream or edited by hand is caught too.
        bad = set()
        newvals = set(new.values())
        for src in (old, REFERENCE):
            # ignore keys whose old value is also a legitimate new value (it would
            # look like a leftover but is yours)
            src = {k: (new[k] if src[k] in newvals else src[k]) for k in REFERENCE}
            if all(src[k] == new[k] for k in REFERENCE):
                continue
            pr = rules(src, new)
            for p, r in files(a.include_docs):
                try:
                    s = open(p, encoding='utf-8').read()
                except (UnicodeDecodeError, OSError):
                    continue
                if transform(s, pr) != s:
                    bad.add(r)
        if bad:
            print('NOT localized - these files still carry values that differ from config/homelab.env:')
            for r in sorted(bad):
                print('  ' + r)
            print('fix: python3 tools/localize.py --apply   (files just pulled from upstream:'
                  ' python3 tools/localize.py --apply --from-reference FILE...)')
            return 1
        print('OK - every file matches config/homelab.env')
        return 0
    changed = {k for k in REFERENCE if old[k] != new[k]}
    if changed:
        print('values that change: ' + ', '.join(f'{k} {old[k]} -> {new[k]}' for k in sorted(changed)))
    # ONE source per run, applied in a single pass - mixing sources could re-map a value
    # that is already yours. Files restored from upstream still carry the reference
    # values: localize those with --from-reference FILE...
    pair_sets = [rules(REFERENCE if a.from_reference else old, new)]
    only = {os.path.normpath(x) for x in a.from_reference or []}
    touched = []
    for p, r in files(a.include_docs):
        if only and os.path.normpath(r) not in only:
            continue
        try:
            s = open(p, encoding='utf-8').read()
        except (UnicodeDecodeError, OSError):
            continue
        t = s
        for pr in pair_sets:
            t = transform(t, pr)
        if t != s:
            n = sum(1 for x, y in zip(s.splitlines(), t.splitlines()) if x != y)
            touched.append((r, n))
            if a.apply:
                open(p, 'w', encoding='utf-8').write(t)
    if not touched:
        print('files already match config/homelab.env - nothing to do')
        if a.apply and changed and not a.from_reference:
            open(STATE, 'w').write(''.join(f'{k}={new[k]}\n' for k in REFERENCE))
        return 0
    for r, n in touched:
        print(f'  {"updated" if a.apply else "would update"} {r} ({n} line(s))')
    if a.apply and a.from_reference:
        print(f'applied reference -> your values to {len(touched)} file(s)')
        return 0
    if a.apply:
        with open(STATE, 'w') as fh:
            fh.write('# Written by tools/localize.py: the values currently applied to the files.\n'
                     '# Do not edit - edit config/homelab.env and re-run localize.py --apply.\n')
            for k in REFERENCE:
                fh.write(f'{k}={new[k]}\n')
        print(f'applied to {len(touched)} file(s); state saved to config/localized.env')
        print('review with: git diff     then re-run the setup step for each component you changed')
        return 0
    print('dry run - nothing written. Re-run with --apply.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
