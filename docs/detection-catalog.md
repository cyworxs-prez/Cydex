# Detection catalog

Wazuh custom rules in `wazuh/rules/`. Paging threshold is **level 10**.

## Files

| File | IDs | Purpose |
|---|---|---|
| `local_rules.xml` | 100010-100031 | Noise tuning (LXC rootcheck artefacts, port churn), scanner allowlist, surface OPNsense blocks as level-3 alerts, suppress VPN-tunnel ICMP chatter |
| `opnsense_rules.xml` | 100100-100102 | OPNsense filterlog grouping; repeated blocks from one source |
| `suricata_syslog_rules.xml` | 100200-100210 | Suricata alerts (syslog fast.log shape + EVE severity); scanner demoted |
| `zeek_rules.xml` | 100710-100732 | Zeek notices, TLS validation issues, software inventory, **capture-loss sensor health** |
| `suppress_scanner.xml` | 100720-100727 | Authorized-scanner demotion (level 2: searchable, never paged) |
| `sigma_zeek_rules.xml` | 100800-100811 | Generated from SigmaHQ Zeek rules by `sigma2wazuh.py` (DRL 1.1) |
| `yara_rules.xml` | 100820-100824 | YARA matches + daily scan heartbeat |
| `segmentation_rules.xml` | 100840-100851 | Blocked cross-zone flows; escalation by protected destination; sustained-probing aggregator |
| `watchdog_rules.xml` | 100860-100870 | Firewall-VM watchdog lifecycle |
| `backup_rules.xml` | 100880-100882 | Weekly backup outcome |
| `span_rules.xml` | 100890-100892 | SPAN mirror applied / not applied |
| `zeek_intel_rules.xml` | 100900-100909 | Intel framework matches by source confidence; feed updater health |
| `zz_audit_tuning.xml` | 100718-100934 (sparse) | Cross-file tuning; must load **last** (alphabetical) because it extends parents in other files |

Decoders: `opnsense_decoders.xml` (filterlog CSV), `suricata_syslog_decoders.xml`.

## What pages

| Rule | Level | Fires on |
|---|---|---|
| 100843 | 10 | Blocked flow from another segment **into LAB/SOC** - a pivot toward the monitoring stack is one or two packets, so it pages on the first |
| 100845 | 10 | 12 blocked cross-zone attempts from one source in 5 min |
| 100102 | 10 | Burst of firewall blocks from one IP |
| 100203 / 100205 | 10 / 12 | Suricata high-priority / high-severity alert |
| 100802 | 10 | Sigma: Kerberos coercion via DNS SPN spoofing |
| 100901 / 100903 / 100902 | 10 / 12 / 14 | Zeek Intel match: URL feed / botnet C2 / **local** indicator |
| 100821 | 12 | YARA match on a host |
| 100713 / 100735 | 12 | **Sensor degraded/blind** - sustained capture loss / repeated zero-ACK windows |
| 100892 | 12 | **Sensor blind** - SPAN mirror could not be applied |
| 100907 / 100909 | 10 / 12 | Intel refresh aborted / Zeek failed to restart after a refresh |
| 100826 | 10 | YARA scanning stopped reporting on a host |
| 100866 / 100867 | 10 | Firewall VM down + watchdog in cooldown / watchdog force-recovering |
| 100868 / 100869 / 100870 | 12 | Recovery start failed / VM did not return / daily cap hit |
| 100882 | 12 | Weekly backup failed - archives not verified |
| 100932 / 100934 | 10 | Guacamole brute force / lockout tripped |

## Design patterns used throughout

- **Suppress with level-0 children, never by deleting.** Events stay in the archive for
  baselining; only the page goes away.
- **Demote known-benign sources to level 2-3**, not 0, when you want them searchable on
  dashboards.
- **Every collector has a liveness rule** (heartbeat at level 0-3, silence or failure at
  10-12). Quiet must not look like healthy.
- **Blocked ACK-bearing TCP is not a probe** (100844): it is the tail of an established
  flow after state expiry. SYN, bare FIN and NULL still alert.
- **Blocked UDP to ephemeral ports (>= 49152) is app traffic** (100850), not recon.
- **Anchor logger-tag rules on `<program_name>`** so systemd unit chatter and duplicated
  stdout lines never match.
