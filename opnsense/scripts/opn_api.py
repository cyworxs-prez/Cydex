#!/usr/bin/env python3
"""Shared OPNsense API helper.

Credentials are never stored in this repo. They are resolved at run time:

Resolution order:
  1. Environment (OPNSENSE_URL / OPNSENSE_API_KEY / OPNSENSE_API_SECRET) -
     e.g. when run under `op run --env-file config/opnsense.env`.
  2. The env file named by $OPNSENSE_ENV_FILE, else <repo>/config/opnsense.env.
     Values may be literal or op:// references (resolved with `op read`).

Never prints or logs a secret value.

Usage:
    from opn_api import call, sel
    data = call('/api/ids/settings/get')
    data = call('/api/ids/settings/set', {'ids': {...}})
"""
import base64, json, os, shutil, ssl, subprocess, time, urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
_OP = shutil.which('op') or '/opt/homebrew/bin/op'
_ctx = ssl._create_unverified_context()


def _op_read(ref, tries=2):
    """Resolve an op:// reference.

    Two things this deliberately does:

    1. NEVER truncate op's stderr - the reason a read failed comes after the
       "could not read secret '<ref>':" prefix.
    2. Retry once - op read failures are often transient.

    op's stderr on a failed read never contains the secret value.
    """
    env = dict(os.environ)
    env['PATH'] = '/opt/homebrew/bin:' + env.get('PATH', '')
    last = ''
    for attempt in range(tries):
        r = subprocess.run([_OP, 'read', ref], capture_output=True, text=True, env=env)
        if r.returncode == 0:
            return r.stdout.strip()
        last = r.stderr.strip()
        if attempt + 1 < tries:
            time.sleep(1.5)
    raise RuntimeError(
        "op read failed for %s after %d attempt(s).\n"
        "  full stderr: %s\n"
        "  NOTE: `op whoami` saying 'account is not signed in' is NORMAL with\n"
        "  1Password desktop-app integration and does NOT mean the vault is\n"
        "  locked. Check with `op vault list` or by reading a reference."
        % (ref, tries, last or '(empty)'))


def _from_envfile(path):
    if not os.path.exists(path):
        return {}
    out = {}
    for line in open(path):
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        v = v.strip()
        # values may be quoted: PROXMOX_X="op://..." or 'op://...'
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
            v = v[1:-1]
        out[k.strip()] = _op_read(v) if v.startswith('op://') else v
    return out


def _creds():
    # 1. already in the environment (running under `op run`)
    if os.environ.get('OPNSENSE_URL') and os.environ.get('OPNSENSE_API_KEY'):
        return (os.environ['OPNSENSE_URL'].rstrip('/'),
                os.environ['OPNSENSE_API_KEY'],
                os.environ['OPNSENSE_API_SECRET'])

    # 2. env file: $OPNSENSE_ENV_FILE, else <repo>/config/opnsense.env
    for cand in (os.environ.get('OPNSENSE_ENV_FILE', ''),
                 os.path.join(_HERE, '..', '..', 'config', 'opnsense.env')):
        if not cand:
            continue
        e = _from_envfile(os.path.abspath(cand))
        if e.get('OPNSENSE_URL') and e.get('OPNSENSE_API_KEY'):
            return (e['OPNSENSE_URL'].rstrip('/'),
                    e['OPNSENSE_API_KEY'], e['OPNSENSE_API_SECRET'])


    raise RuntimeError(
        "No OPNsense credentials found. Expected OPNSENSE_* in the environment, "
        "or config/opnsense.env (see config/opnsense.env.example).")


_URL, _KEY, _SECRET = None, None, None


def _ensure():
    global _URL, _KEY, _SECRET
    if _URL is None:
        _URL, _KEY, _SECRET = _creds()


def call(path, body=None, timeout=90):
    """GET when body is None, POST otherwise. Returns parsed JSON."""
    _ensure()
    req = urllib.request.Request(_URL + path, method='POST' if body is not None else 'GET')
    auth = base64.b64encode((_KEY + ':' + _SECRET).encode()).decode()
    req.add_header('Authorization', 'Basic ' + auth)
    if body is not None:
        req.add_header('Content-Type', 'application/json')
        req.data = json.dumps(body).encode()
    return json.load(urllib.request.urlopen(req, context=_ctx, timeout=timeout))


def sel(node):
    """Collapse an OPNsense dropdown dict to its selected key(s)."""
    if not isinstance(node, dict):
        return node
    return ','.join(k for k, v in node.items() if isinstance(v, dict) and v.get('selected'))


if __name__ == '__main__':
    _ensure()
    print("OPNsense endpoint: %s" % _URL)
    print("key length: %d, secret length: %d (values not shown)" % (len(_KEY), len(_SECRET)))
    d = call('/api/diagnostics/system/systemTime')
    d = d.get('data', d)   # direct API has no 'data' wrapper; the MCP adds one
    print("live check -> uptime %s, %s" % (d.get('uptime'), d.get('datetime')))
