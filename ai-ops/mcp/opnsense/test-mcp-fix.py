#!/usr/bin/env python3
"""End-to-end proof of the OPNsense MCP write fix.
Spawns the PATCHED server over stdio and drives it with real JSON-RPC.
Test: flip ids LogPayload 0->1, read back, restore. Harmless and instantly verifiable."""
import json, os, subprocess, sys, threading, queue

# Drive the same launcher the MCP client uses, so the test exercises the real path
# (credential resolution included).
launcher = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'run-opnsense-mcp.sh')
env = dict(os.environ)

proc = subprocess.Popen([launcher],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL, env=env, text=True, bufsize=1)
q = queue.Queue()
threading.Thread(target=lambda: [q.put(l) for l in proc.stdout], daemon=True).start()

_id = [0]
def rpc(method, params=None, notify=False):
    msg = {"jsonrpc": "2.0", "method": method}
    if params is not None: msg["params"] = params
    if not notify:
        _id[0] += 1; msg["id"] = _id[0]
    proc.stdin.write(json.dumps(msg) + "\n"); proc.stdin.flush()
    if notify: return None
    while True:
        line = q.get(timeout=60)
        try: m = json.loads(line)
        except Exception: continue
        if m.get("id") == _id[0]: return m

def call_tool(name, args):
    r = rpc("tools/call", {"name": name, "arguments": args})
    if "error" in r: return {"MCP_ERROR": r["error"]}
    for c in r.get("result", {}).get("content", []):
        if c.get("type") == "text":
            try: return json.loads(c["text"])
            except Exception: return {"raw": c["text"][:400]}
    return r.get("result")

def get_logpayload():
    d = call_tool("opnsense_ids_manage", {"method": "settingsGet"})
    d = d.get("data", d)
    return d["ids"]["general"]["LogPayload"]

rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                   "clientInfo": {"name": "fixtest", "version": "1"}})
rpc("notifications/initialized", {}, notify=True)

tools = [t["name"] for t in rpc("tools/list", {}).get("result", {}).get("tools", [])]
ids_tool = next((t for t in tools if t.endswith("ids_manage")), None)
print("tools exposed:", len(tools), "| ids tool:", ids_tool)
if not ids_tool: print("FATAL: no ids tool"); proc.kill(); sys.exit(1)

def call_ids(args): return call_tool(ids_tool, args)
def logpayload():
    d = call_ids({"method": "settingsGet"}); d = d.get("data", d)
    return d["ids"]["general"]["LogPayload"]

before = logpayload()
target = "1" if before == "0" else "0"
print("\nLogPayload before   :", repr(before))
print("writing LogPayload  :", repr(target), "via {data:{ids:{general:{...}}}}")

res = call_ids({"method": "settingsSet",
                "params": {"data": {"ids": {"general": {"LogPayload": target}}}}})
print("settingsSet returned:", res)

after = logpayload()
print("LogPayload after    :", repr(after))

ok = (after == target)
print("\n>>> RESULT:", "WRITE WORKS - BUG FIXED" if ok else "STILL BROKEN (write silently ignored)")

# restore
call_ids({"method": "settingsSet", "params": {"data": {"ids": {"general": {"LogPayload": before}}}}})
restored = logpayload()
print("restored to         :", repr(restored), "(matches original)" if restored == before else "!! RESTORE FAILED !!")

proc.kill()
sys.exit(0 if ok and restored == before else 1)
