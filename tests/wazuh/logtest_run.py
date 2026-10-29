#!/usr/bin/env python3
"""Replay sample events through Wazuh's logtest engine and check which rule fires.

Runs INSIDE a wazuh-manager container (talks to the logtest unix socket).
    logtest_run.py cases.json

Each case:
  name      label shown in the report
  log       the raw event (syslog line, or one JSON object as a string)
  format    "syslog" (default) or "json"
  location  log source path (default "cydex-test"); rules with <location> need the real one
  repeat    send the event N times in one session (frequency/correlation rules); default 1
  rule      expected rule id on the LAST event
  level     expected level (optional; checked when given)

Exit 0 only if every case matches.
"""
import json
import socket
import struct
import sys

SOCK = "/var/ossec/queue/sockets/logtest"


def call(payload):
    data = json.dumps(payload).encode()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.connect(SOCK)
        s.sendall(struct.pack("<I", len(data)) + data)
        size = struct.unpack("<I", _recv(s, 4))[0]
        return json.loads(_recv(s, size))


def _recv(s, n):
    buf = b""
    while len(buf) < n:
        chunk = s.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("logtest socket closed")
        buf += chunk
    return buf


def process(event, fmt, location, token=None):
    params = {"event": event, "log_format": fmt, "location": location}
    if token:
        params["token"] = token
    r = call({"version": 1, "origin": {"name": "cydex-tests", "module": "api"},
              "command": "log_processing", "parameters": params})
    if r.get("error"):
        raise RuntimeError(f"logtest error {r.get('error')}: {r.get('message')}")
    return r["data"]


def main(path):
    cases = json.load(open(path))
    failed = 0
    for c in cases:
        fmt = c.get("format", "syslog")
        loc = c.get("location", "cydex-test")
        token, out = None, {}
        for _ in range(int(c.get("repeat", 1))):
            data = process(c["log"], fmt, loc, token)
            token = data.get("token", token)
            out = data.get("output", {})
        rule = out.get("rule", {})
        got_id, got_lvl = str(rule.get("id", "-")), rule.get("level")
        ok = got_id == str(c["rule"]) and ("level" not in c or got_lvl == c["level"])
        exp = f"{c['rule']}" + (f"/L{c['level']}" if "level" in c else "")
        print(f"{'PASS' if ok else 'FAIL'}  {c['name']:<58} expected {exp:<10} got {got_id}/L{got_lvl}")
        if not ok:
            failed += 1
            print(f"      decoder={out.get('decoder', {}).get('name')}  "
                  f"fields={json.dumps({k: v for k, v in out.items() if k in ('srcip', 'dstip', 'data', 'program_name')})[:300]}")
    print(f"\n{len(cases) - failed}/{len(cases)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
