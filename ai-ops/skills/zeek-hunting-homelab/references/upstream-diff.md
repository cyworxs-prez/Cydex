# What changed from the upstream skill, and why

Adapted from **mukul975/anthropic-cybersecurity-skills** →
`skills/detecting-network-anomalies-with-zeek` (author: mahipal, Apache-2.0).
Upstream content is good; it is written for a *generic* Zeek deployment. This homelab
violates four of its core assumptions, so most of its commands fail here as written.

## Removed

| Upstream section | Why removed |
|---|---|
| Step 1: Install and Configure Zeek | Zeek is already deployed in its own container. Following this (editing `node.cfg`/`networks.cfg`, `zeekctl deploy`) would disrupt a working sensor. |
| "Disable NIC offloading" | The capture path here is a `tc` mirror onto a veth, not a physical NIC. The offload advice does not transfer, and every drop counter in the real path already reads zero. |
| Filebeat → Elastic SIEM pipeline | Wazuh already ingests these logs via the CT206 agent. Building a second pipeline would duplicate ingestion. |
| Example IPs `10.10.x.x`, `networks.cfg` `10.0.0.0/8` | Wrong network entirely. Replaced with the real VLAN map. |

## Rewritten

- **Every hunting query.** Upstream uses `zeek-cut`, which parses the `#fields` header of
  **TSV** logs. This deployment writes **JSON**, so `zeek-cut` cannot work here at all —
  regardless of PATH. `jq` is not installed either. All queries are now streaming
  `python3`, which is present.
- **Access path.** Upstream assumes you are on the Zeek host. Here everything needs
  `ssh root@10.10.130.10` → `pct exec 206`.
- **Absolute binary paths.** `/opt/zeek/bin` is not on `$PATH` under `pct exec`, so
  `command -v zeek-cut` returns nothing and looks like "not installed". It is installed.
- **`scripts/agent.py` → `scripts/zeek-hunt.sh`.** The upstream Python agent shells out to
  a local `zeek`/`zeekctl`; it cannot work from a workstation. Replaced with a wrapper
  that hops through pve.

## Added

- **Sensor-health section**, because a null result from a blind sensor is not a null
  result. Includes the asymmetry that matters: `capture_loss` is derived from TCP ACKs,
  so a *partially* blind sensor is loud while a *fully* blind one reports 0% and looks
  perfect.
- **The `tc` mirror check**, including that `tc filter show dev tap200i1` without a
  direction keyword reports nothing and is not evidence the mirror is missing.
- **Multicast/broadcast filter on the beacon detector.** Unfiltered, the top candidates
  were SSDP/broadcast/device-discovery traffic. They beacon perfectly because they are
  timers.
- **Known-periodic-source skip (`SKIP_SRC`)** for the NetAlertX host, whose status pings
  would otherwise top the beacon list.

## Verified

Every query was run against a live sensor before shipping.
