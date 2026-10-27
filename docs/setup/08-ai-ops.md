# 8. AI operations (MCP + agent policy)

An LLM agent (Claude Desktop / Claude Code or any MCP client) can query the firewall,
hypervisor and SIEM directly. That is useful for health checks and hunts, and dangerous
without boundaries. This layer is both halves.

## 8.1 The policy first: `ai-ops/AGENTS.md`

Put it at the root of whatever directory the agent works from. It sets:

- **Read-only by default.** Never run a script because its name sounds safe - read it.
- **Approval list** - firewall, switch, hypervisor, SIEM, sensor, scanner, DNS, VPN and
  host changes all need explicit operator approval; approval for one system does not
  extend to another.
- **Network-change gate** - target, live state, break-glass path, backup, impact,
  rollback trigger, canary, post-checks.
- **Unattended work is read-only only.** Prompt instructions are not a sufficient
  boundary for write-capable automation.
- **Secrets** never printed, logged, committed or placed in argv.

## 8.2 MCP servers

| Server | Package | Purpose | Setup |
|---|---|---|---|
| `opnsense` | `@richard-stovall/opnsense-mcp-server` (npm) | Firewall, DHCP, DNS, IDS | `npm i -g @richard-stovall/opnsense-mcp-server`, then **patch it** (8.3). Launcher: `ai-ops/mcp/opnsense/run-opnsense-mcp.sh` |
| `proxmox-plus` | `proxmox-mcp-plus` (PyPI) | VM/CT lifecycle, guest command execution (allow-listed), job queue | `ai-ops/mcp/proxmox-plus/install.sh` |
| `proxmox-api` | `ry-ops/proxmox-mcp-server` | Full PVE API incl. **`get_node_rrddata`** (historical CPU/memory - use it instead of point-in-time samples) | Clone upstream; launch under `op run` |
| `wazuh` | `gbrigandi/mcp-server-wazuh` | Agents, rules, alerts, manager logs | `ai-ops/mcp/wazuh/setup-wazuh-mcp.sh` (macOS arm64 + 1Password), or download the release binary for your platform into `ai-ops/mcp/wazuh/mcp-server-wazuh` and fill `config/wazuh.env` by hand |

Both launchers read their credentials from `config/opnsense.env` / `config/wazuh.env`
(see [configure.md §3.1](../configure.md#31-credentials-on-the-workstation)):
`op://` references are resolved at launch by `op run`; plain values are exported
directly (keep the file `chmod 600`). For headless use on macOS, a 1Password
**service-account token** in the login Keychain (`security add-generic-password -a
"$(id -un)" -s op-service-account -w <token>`) lets `op` resolve references with the
desktop app locked.

MCP client config is then just the launcher path, e.g.:

```json
"opnsense": { "command": "/path/to/cydex/ai-ops/mcp/opnsense/run-opnsense-mcp.sh" },
"wazuh":    { "command": "/path/to/cydex/ai-ops/mcp/wazuh/run-wazuh-mcp.sh" }
```

Least privilege: the Wazuh MCP uses the indexer's read-only `readall` user for alert
search; the Proxmox MCP's guest command policy is an allow-list (see
`config.template.json`).

## 8.3 The OPNsense MCP patch - silent write failure

The dispatcher posted `{"data": {...}}` verbatim, one level too deep. OPNsense found no
matching key, wrote nothing, and still returned `{"result":"saved"}`.

```bash
node ai-ops/mcp/opnsense/patch-opnsense-mcp.js        # idempotent, backs up index.js, self-tests 7 cases
python3 ai-ops/mcp/opnsense/test-mcp-fix.py           # live proof: flips ids.LogPayload 0->1, reads back, restores
```

`npm update` reverts the patch - re-run it after every update. Details:
`ai-ops/mcp/opnsense/PATCH-NOTES.md`. Regardless of the patch: **read back every write.**
Separately, `kea_manage dhcpv4Set` on the `general` node was observed returning `saved`
and discarding the change; edit `config.xml` for that one.

## 8.4 Hunting skill

`ai-ops/skills/zeek-hunting-homelab/` is a packaged skill (SKILL.md + `scripts/zeek-hunt.sh`)
that teaches an agent this sensor's access path, log format, topology and exclusions.

## 8.5 Scheduled read-only review (pattern)

A weekly unattended run works well if it is **read-only**: check MCP launchers start,
pull Wazuh/Zeek/watchdog/backup health, run the hunts, write a dated report. Give the
prompt its own copy of the access paths and known-benign baseline - each run starts with
no memory. Its most likely failure is the workstation being on an isolated segment (e.g.
DIRECT), where every SSH to MGMT times out: detect that first and report it instead of
retrying.
