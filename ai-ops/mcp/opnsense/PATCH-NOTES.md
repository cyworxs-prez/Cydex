# OPNsense MCP — silent write failure (local patch)

Package: `@richard-stovall/opnsense-mcp-server` **0.5.3**
File: `$(npm root -g)/@richard-stovall/opnsense-mcp-server/index.js`
Function: `callModularTool`

## The bug

Every write through the MCP returned `{"result":"saved"}` and changed nothing.

The dispatcher passed the entire params object straight through as the HTTP body:

```js
return await method.call(moduleObj, callParams);   // callParams = {data:{ids:{...}}}
```

and the client does:

```js
async settingsSet(data, config) {
    return this.http.post(`/api/ids/settings/set`, data, config);
}
```

So the posted body was `{"data":{"ids":{...}}}` — one level too deep. OPNsense's
`setBase` looks for a top-level `ids` key, finds nothing, writes nothing, and still
returns `saved`. The tool schema advertises a `data` wrapper property that the
dispatcher never unwraps.

**This is the worst kind of API bug: it reports success on failure.** The only way to
catch it is to read the value back after every write.

## The fix

Unwrap a body that consists *solely* of a single `data` or `item` key. Deliberately
narrow so nothing that already worked changes:

| input | result |
|---|---|
| `{data:{ids:{...}}}` | `{ids:{...}}` — was broken, now works |
| `{item:{test:{...}}}` | `{test:{...}}` — was broken, now works |
| `{test:{...}}` | unchanged — already worked |
| `{searchPhrase, rowCount}` | unchanged — already worked |
| `{uuid}` | unchanged — already worked (uuid passthrough) |
| `{data:{...}, rowCount:5}` | unchanged — >1 key, ambiguous, left alone |
| `{data:"str"}` / `{data:[...]}` | unchanged — not an object |

7/7 logic cases pass.

## Verification

Drove the patched server over real JSON-RPC stdio, independent of Claude Desktop:

```
LogPayload before   : '0'
writing LogPayload  : '1' via {data:{ids:{general:{...}}}}
settingsSet returned: {'result': 'saved'}
LogPayload after    : '1'
>>> RESULT: WRITE WORKS - BUG FIXED
restored to         : '0' (matches original)
```

## Backups

The patcher writes `index.js.bak-prewrapfix` beside the original on first run.

## Reapply after an npm update

`npm update` overwrites `index.js` and silently reverts both fixes. The patcher is
idempotent — safe to run any time:

```bash
node ai-ops/mcp/opnsense/patch-opnsense-mcp.js
python3 ai-ops/mcp/opnsense/test-mcp-fix.py     # end-to-end proof
```

The patcher applies **two** fixes to the stock 0.5.3 dispatcher: the wrapper unwrap
above, and a `uuid` path-parameter passthrough (without it, `set*/<uuid>`-style calls such
as `settingsToggleRuleset` lose their uuid). It recognises both the stock code and a copy
that already has the uuid fix, and refuses to touch anything else. Tested against a fresh
`npm i @richard-stovall/opnsense-mcp-server@0.5.3`.

## Standing practice regardless

Keep reading writes back. Both fixes are local patches to a third-party package; the
upstream bug still exists and an update can restore it at any time. The failure mode
is silent, so read-back is the only reliable detector.
