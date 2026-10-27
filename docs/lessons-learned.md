# Lessons learned

Engineering patterns behind the design. Most are **silent failures**: things that
reported healthy while doing nothing.

## Silent failures

| Failure mode | Why it is silent | Countermeasure in this repo |
|---|---|---|
| An API (or MCP server wrapping it) returns `saved` and discards the write | The request body is nested one level too deep; the API still reports success | `ai-ops/mcp/opnsense/patch-opnsense-mcp.js`; **read back every write** |
| The IDS sensor goes blind after a reboot | A `tc` mirror is runtime-only; the sensor process stays up | `zeek-mirror.service` + span hookscript, both self-verifying and alerting |
| A fully blind Zeek reports 0% capture loss | Loss is computed from ACKs for unseen data; no traffic means no ACKs | `span_rules.xml` checks the mirror itself |
| A scanner runs nightly but its alerts never fire | A malformed rule file can stay well-formed XML and pass `analysisd -t` | Daily heartbeat rule, so "no matches" and "not running" differ |
| Tuning rules are ignored | Wazuh loads rule files alphabetically and only warns when a child's parent loads later | `zz_` prefix |
| Watchdog messages never alert | Nothing matches the log tag, so events go to the archive and stop | Dedicated rules per logger tag |
| A self-healing tool restarts a service and tells nobody | Its own alerting has no delivery path | Route the restart through the SIEM, or configure delivery and test it |
| A backup failure pages with no reason | `set -e` exits on the verification command before anything is logged | Explicit checks, reason included in the page |

**Rule:** absence of data is not absence of a problem. Every collector needs a heartbeat.

## Failure patterns worth designing for

| Pattern | Root cause | Lesson |
|---|---|---|
| Suricata exhausts firewall memory during a rule reload | Aho-Corasick MPM + the default detect profile | Hyperscan + Low profile cuts memory by several times with the same rulesets. Reducing rulesets does not |
| Every DHCP client re-addresses after an unrelated cleanup | Kea subnet IDs are positional; deleting one renumbers the rest and reservations stop applying | Ask "what does deleting this **renumber**?", not only "what references this?" |
| A new VLAN carries zero packets | The hypervisor bridge has an explicit VLAN allow-list | Two-trunk rule: switch **and** `bridge vlan add` |
| One chatty device floods the SIEM | `pass -> NOT RFC1918` leaves same-subnet broadcast to the default deny, which logs | Unlogged `<net>.255` block before the cross-segment blocks |

## Operational traps

- **`qm reboot` applies pending VM hardware changes; a reboot from inside the guest or
  `qm reset` does not.** Never `qm stop`: it is a power cut.
- **Proxmox's memory gauge for a FreeBSD VM is meaningless** (QEMU RSS high-water mark).
- **OPNsense names VLAN interfaces by creation order** - `vlan05` is not VLAN 5.
- **OPNsense's root shell is csh.** Transfer scripts and run them by path; base64 the
  payload when it crosses several shells.
- **`ssh_config` is first-match-wins per keyword.** A `Host *` block above a specific host
  overrides it. Put specific hosts first and pin `IdentityFile` + `IdentitiesOnly`.
- **`op whoami` can report "not signed in" under 1Password desktop-app integration even
  when `op` works.** Health-check with `op vault list`. Never truncate `op`'s stderr.
- **A pf state table outlives the traffic that created it.** Use ARP to decide whether a
  segment is still in use.
- **`grep -c` on an address is not a completion test** - it counts comments too.
- **A public fallback resolver on the hypervisor** bypasses DNS filtering and logging.

## Hunting

- JA3 is unreliable against modern browsers (ClientHello extension randomisation). Hunt
  **rare SNI** instead.
- Use `dhcp.log` for identity in retrospective hunts; private MAC addresses rotate.
- Exclude gateway DNS, discovery scanners and known high-volume cloud devices from beacon
  queries, or the top results are all known-good.
- A quiet `intel.log` is not a quiet network - most malicious URLs are HTTPS.

## Process

- **Measure before theorising, and retract explicitly when wrong.**
- **Use historical metrics** (RRD / `get_node_rrddata`) - point-in-time samples hide slow
  trends such as swap growth.
- **Before destructive changes:** snapshot, check what references the target, check what
  deleting it renumbers.
- **Make runtime state persistent** with a unit that verifies it applied.
