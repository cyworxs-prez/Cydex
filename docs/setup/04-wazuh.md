# 4. Wazuh SIEM

Reference: Wazuh 4.14 all-in-one in an unprivileged Debian LXC (CT 201, 10.10.140.11).

## 4.1 Install

1. In CT 201: run the official installation assistant (`wazuh-install.sh -a`).
2. Keep `/root/wazuh-install-files.tar` - it holds the generated passwords. Never copy it
   off the box in plaintext; `ai-ops/mcp/wazuh/setup-wazuh-mcp.sh` reads it over ssh,
   verifies the credentials live, and moves them into 1Password.
3. Watch disk: the indexer grows fast once firewall blocks are flowing. Set index
   retention (ISM) before you need it.

## 4.2 Agents

| Host | What it ships |
|---|---|
| OPNsense | Suricata EVE JSON, system log (see [02-opnsense.md](02-opnsense.md#29-wazuh-agent-on-opnsense)) |
| Zeek CT | `/opt/zeek/logs/current/{conn,dns,http,ssl,ssh,notice,weird,dhcp,files,x509,software,capture_loss,intel}.log` as JSON |
| Proxmox host | journald - carries the watchdog, span hookscript and backup messages |
| Other CTs / workstation | defaults |

OPNsense filterlog also arrives via syslog to the manager on :514 (decoded by
`opnsense_decoders.xml`).

## 4.3 Rules and decoders

```bash
# from the repo, via the Proxmox host
ssh root@10.10.130.10 'mkdir -p /tmp/rules /tmp/decoders'
scp wazuh/rules/*.xml    root@10.10.130.10:/tmp/rules/
scp wazuh/decoders/*.xml root@10.10.130.10:/tmp/decoders/
ssh root@10.10.130.10 '
  for f in /tmp/rules/*.xml;    do pct push 201 "$f" /var/ossec/etc/rules/$(basename "$f"); done
  for f in /tmp/decoders/*.xml; do pct push 201 "$f" /var/ossec/etc/decoders/$(basename "$f"); done
  pct exec 201 -- sh -c "chown wazuh:wazuh /var/ossec/etc/rules/*.xml /var/ossec/etc/decoders/*.xml"
  pct exec 201 -- /var/ossec/bin/wazuh-analysisd -t && pct exec 201 -- systemctl restart wazuh-manager'
```

- **Always `wazuh-analysisd -t` before restarting.** A bad rule file stops the manager.
- Edit the subnets in `segmentation_rules.xml`, and the scanner IP in
  `suppress_scanner.xml` / `local_rules.xml`, if your addressing differs.
- `zz_audit_tuning.xml` must sort **last**: Wazuh loads rule files alphabetically and
  silently ignores a child whose parent is defined in a later file.
- `wazuh/scripts/sync-rules.sh` pulls deployed rule files back into the repo so the two
  cannot drift. Review with `git diff`.

What each file does: [detection-catalog.md](../detection-catalog.md).

### Rule-writing traps (all hit in practice)

| Trap | Do instead |
|---|---|
| `<srcip>`/`<dstip>` reject `\|`, commas, and mishandle `!` negation | One plain CIDR per element; suppress with level-0 children, not negation |
| `protocol`/`dstport` are static fields | `<protocol>`/`<dstport>` elements, not `<field name=...>` |
| OS_Regex has no `{n}` | `type="pcre2"` |
| Matching a logger tag loosely pages twice (logger + systemd stdout) and catches systemd unit chatter | Anchor on `<program_name>^tag$</program_name>` |
| `wazuh-logtest` cannot satisfy `<location>` | Prove location-gated rules in production (`alerts.log`) |
| A frequency aggregator that is in its own counted group counts itself | Omit the counted group from the aggregator |

## 4.4 Paging (ntfy)

1. Copy `wazuh/integrations/custom-ntfy` to `/var/ossec/integrations/custom-ntfy`
   (`root:wazuh`, `750`).
2. Add `wazuh/integrations/ossec-integration.xml` inside `<ossec_config>` in
   `/var/ossec/etc/ossec.conf` with your topic URL. Treat the topic as a secret.
3. Restart the manager. Verify with `wazuh/scripts/check-ntfy.sh` (run inside CT 201):
   script present + executable, integratord running, sends in `integrations.log`.
4. Prove the chain end to end: trigger a level-10 rule and confirm the phone gets it.
   "Configured" is not "working".

Level policy: 3 = context, 6-8 = suspicious/notify, **10 = page**, 12-14 = confirmed-bad /
sensor dead.

## 4.5 YARA host scanning

Run `wazuh/yara/deploy_yara.sh` as root on each Linux host with a Wazuh agent. It installs
yara + the YARA-Forge core set, **test-compiles before deploying**, installs a JSON-lines
scan wrapper, registers the log with the agent and adds a nightly cron. `yara_rules.xml`
alerts on matches and emits a daily heartbeat - a clean scan and a dead scanner otherwise
look identical.

## 4.6 Sigma -> Wazuh (Zeek)

```bash
git clone https://github.com/SigmaHQ/sigma
python3 wazuh/sigma/sigma2wazuh.py sigma/rules/network/zeek wazuh/rules/sigma_zeek_rules.xml 100800
```

Faithful-or-skip: anything Wazuh cannot express exactly (negation, cross-field OR beyond a
small fan-out, aggregations) is skipped and reported, never approximated.

## 4.7 Dashboards

Run inside CT 201 (they use the indexer admin certs on the box):

| Script | Builds |
|---|---|
| `wazuh/dashboards/build_soc.py` | "Homelab - SOC" - one view over everything; firewall blocks contained in their own section so they do not drown other signal |
| `wazuh/dashboards/add_ids_panels.py` | Suricata panels on the threat-map dashboard |
| `wazuh/dashboards/eve_repoint.py` | Moves IDS panels onto EVE fields + GeoIP |
| `wazuh/dashboards/mkviz.py` | Regenerates `hunt-dashboard.ndjson` (import via Dashboards Management > Saved objects) |

## Verify

```bash
pct exec 201 -- /var/ossec/bin/agent_control -l          # every agent Active
pct exec 201 -- /var/ossec/bin/wazuh-analysisd -t         # rules compile
pct exec 201 -- tail -5 /var/ossec/logs/integrations.log  # ntfy sends
```
