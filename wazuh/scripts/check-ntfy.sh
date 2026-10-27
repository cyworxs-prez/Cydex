#!/bin/sh
# "No paging destination" is a common gap, but ossec.conf may declare an
# ntfy integration at level 10+. Configured is not the same as working - is the
# integration script actually present, executable, and firing? Read-only.
echo "=== integration declared in ossec.conf ==="
grep -A5 "custom-ntfy" /var/ossec/etc/ossec.conf | sed 's/hook_url>.*</hook_url>REDACTED</' | head -8

echo
echo "=== does the integration script exist and is it executable? ==="
ls -la /var/ossec/integrations/custom-ntfy* 2>/dev/null || echo "  NOT PRESENT - integration is declared but dead"

echo
echo "=== has it actually run? (integrator log) ==="
tail -20 /var/ossec/logs/integrations.log 2>/dev/null | cut -c1-140 || echo "  no integrations.log"

echo
echo "=== is wazuh-integratord running? ==="
/var/ossec/bin/wazuh-control status 2>/dev/null | grep -i integrator || echo "  integratord NOT in status list"

echo
echo "=== how many level>=10 alerts in the last 24h could have paged? ==="
grep -a '"level":1[0-9]' /var/ossec/logs/alerts/alerts.json 2>/dev/null | wc -l
