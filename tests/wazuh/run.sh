#!/usr/bin/env bash
# Load this repo's decoders and rules into a throwaway Wazuh manager container and
# replay tests/wazuh/cases.json through wazuh-logtest. Needs Docker. Read-only for the repo.
#
#   tests/wazuh/run.sh            # uses WAZUH_IMAGE below
#
# Adding a rule? Add a case to cases.json: a sample event and the rule id it must hit.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
IMAGE="${WAZUH_IMAGE:-wazuh/wazuh-manager:4.14.8@sha256:412f665c77af5497780d29d0d9f069d7a169c5eca45e9a3a47a587d9cfc99b55}"
NAME="cydex-ruletest-$$"
trap 'docker rm -f "$NAME" >/dev/null 2>&1 || true' EXIT

docker create --name "$NAME" "$IMAGE" >/dev/null
for f in "$ROOT"/wazuh/decoders/*.xml; do docker cp "$f" "$NAME:/var/ossec/etc/decoders/"; done
for f in "$ROOT"/wazuh/rules/*.xml;    do docker cp "$f" "$NAME:/var/ossec/etc/rules/"; done
docker cp "$HERE/logtest_run.py" "$NAME:/tmp/logtest_run.py"
docker cp "$HERE/cases.json"     "$NAME:/tmp/cases.json"
docker start "$NAME" >/dev/null

echo "waiting for the logtest engine..."
for _ in $(seq 1 90); do
  docker exec "$NAME" test -S /var/ossec/queue/sockets/logtest 2>/dev/null && break
  sleep 2
done
if ! docker exec "$NAME" test -S /var/ossec/queue/sockets/logtest; then
  echo "logtest never came up - the ruleset probably failed to load:"
  docker exec "$NAME" grep -iE "error|critical" /var/ossec/logs/ossec.log | tail -40 || true
  exit 1
fi
docker exec "$NAME" sh -c 'grep -iE "(rule|decoder).*(error|invalid)|ERROR: .*(rule|decoder)" /var/ossec/logs/ossec.log' && {
  echo "ruleset load errors above"; exit 1; } || true

docker exec "$NAME" /var/ossec/framework/python/bin/python3 /tmp/logtest_run.py /tmp/cases.json
