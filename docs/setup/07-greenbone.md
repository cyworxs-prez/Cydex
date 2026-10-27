# 7. Vulnerability scanning (Greenbone)

Reference: Greenbone Community Edition (docker compose) in CT 202, 10.10.140.12,
started on demand - it needs ~4 GB and should not run alongside heavy jobs (backups,
Suricata reloads, Kali).

## 7.1 Install

1. CT 202: Debian LXC with `nesting=1,keyctl=1`, docker installed.
2. Deploy Greenbone Community Edition with the official compose file.
3. Store the admin password in `/root/.gbpw` (`chmod 600`) - never in a script.

## 7.2 Keep the scanner from paging you

An authenticated scan looks exactly like an attack. `wazuh/rules/suppress_scanner.xml`
and the scanner block in `local_rules.xml` demote alerts **from the scanner IP** to level 2:
still decoded, archived and searchable, never paged. Update the IP there if yours differs.

## 7.3 Rank findings by real-world exploitation

```bash
# inside CT 202, after a scan finishes
python3 vuln_prioritize.py
```

Pulls the latest finished report over the gvmd socket (dockerized `gvm-cli`), joins every
CVE against the **CISA KEV** catalog and **FIRST EPSS** scores, and writes
`/root/vuln-priority.csv` plus a top-25 summary. Order: KEV membership > EPSS > CVSS.

Regenerate before acting on it - a stale CSV is not a remediation list.

## 7.4 Backup note

Greenbone is the largest guest and mostly re-downloadable feed data; the backup script
keeps 2 copies of it instead of 3.
