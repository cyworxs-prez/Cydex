# 10. Device discovery (NetAlertX)

Reference: NetAlertX in Docker in CT 203, `10.10.140.13`, one interface on LAB.
UI on `http://10.10.140.13:20211/`.

NetAlertX keeps an inventory of devices and alerts when a new one appears or a known one
disappears. Here its job is narrow: **know every device on LAB**, the segment where the
SOC lives. It is not the network-wide inventory. That comes from Kea leases on OPNsense
and from Zeek, which see every segment without NetAlertX needing a path into them.

## Design: one interface, LAB only

| Choice | Why |
|---|---|
| One NIC, on LAB | A discovery box with a leg in every VLAN joins them all at layer 2, which undoes the segmentation. Never multihome it. |
| ARP scan of LAB only | ARP does not cross a router. Scanning another segment from LAB sends traffic that the LAB rule ladder blocks (seq 20-23). Every probe is then logged and decoded as a cross-segment block (Wazuh 100840+). |
| Other segments: optional, ICMP only, known devices only | See [10.5](#105-optional-status-for-devices-on-other-segments). It costs a firewall exception and Zeek noise, so it is opt-in. |

What you give up: MAC and vendor identification and new-device detection outside LAB.
If you need that, use a SPAN port with a passive sensor (Zeek already does this) or
DHCP-lease data. Don't widen NetAlertX.

## 10.1 Create the container (Proxmox host)

```bash
# on the Proxmox host - adjust storage and bridge to yours
pveam update && pveam available --section system | grep debian-13   # pick the newest
pveam download local <that-template>                                # once per host
TPL=$(pveam list local | awk '/debian-13-standard/{print $1}' | tail -1)
pct create 203 "$TPL" \
  --hostname netalertx --cores 1 --memory 1024 --rootfs local-lvm:8 \
  --net0 name=eth0,bridge=vmbr1,tag=140,ip=10.10.140.13/24,gw=10.10.140.1 \
  --nameserver 10.10.140.1 --unprivileged 1 --features nesting=1,keyctl=1 --onboot 1
pct start 203
```

`nesting=1,keyctl=1` lets Docker run inside an unprivileged LXC. NetAlertX's ARP scan
works there because the CT has its own network namespace.

Inside the CT (`pct enter 203`), set the timezone, ARP sysctls, and Docker:

```bash
timedatectl set-timezone America/New_York          # your zone; NetAlertX timestamps use it
cat > /etc/sysctl.d/90-netalertx.conf <<'EOF'
# Upstream's compose sets these as container sysctls. Docker refuses net.* sysctls with
# network_mode: host, so set them on the CT instead (stops ARP flux / duplicate replies).
net.ipv4.conf.all.arp_ignore = 1
net.ipv4.conf.all.arp_announce = 2
EOF
sysctl --system >/dev/null
apt-get update && apt-get install -y docker.io docker-compose
docker compose version        # must work (Compose v2); if not, use Docker's own apt repo
```

## 10.2 Install

```bash
# from the repo on your workstation
scp lab/netalertx/docker-compose.yml root@10.10.130.10:/tmp/
ssh root@10.10.130.10 'pct exec 203 -- mkdir -p /opt/netalertx/data &&
  pct push 203 /tmp/docker-compose.yml /opt/netalertx/docker-compose.yml'

# inside CT 203
cd /opt/netalertx && docker compose up -d
docker compose logs -f --tail=50          # wait for the web server to come up, Ctrl-C
```

Pin the image to a digest once it works. The compose file's header has the one-liner.

## 10.3 First login: set a password

New installs have **password protection with the default `123456`**. Change it before
doing anything else:

1. Browse to `http://10.10.140.13:20211/` from TRUSTED. TRUSTED -> LAB is already allowed.
2. **Settings** -> **Set password** (plugin `SETPWD`): set a new password and keep
   `SETPWD_enable_password` on. Save. NetAlertX stores the password as a SHA-256 hash in
   `app.conf`.
3. Log out and back in to prove it.

Port `20212` is the GraphQL API that the UI calls. It is not a second UI, so don't
bookmark it. Don't open either port beyond TRUSTED.

## 10.4 Scan LAB

**Settings** -> **Core** / **ARPSCAN**. Use the UI rather than editing `app.conf`; it
validates the format.

| Setting | Value | Notes |
|---|---|---|
| `SCAN_SUBNETS` | `['10.10.140.0/24 --interface=eth0']` | LAB only. Exactly one entry. |
| `ARPSCAN_RUN` | `schedule` | |
| `ARPSCAN_RUN_SCHD` | `*/5 * * * *` | |
| `TIMEZONE` | your zone | match the CT |

The config lives at `/opt/netalertx/data/config/app.conf` in the CT.

**Re-check `SCAN_SUBNETS` whenever you renumber or retire a segment.** A stale subnet
here keeps sending traffic at a network that no longer exists. That shows up as a
steady stream of blocked flows from `10.10.140.13`, not as an error.

Then mark what you find. Every SOC guest (Wazuh, Greenbone, Zeek, Guacamole, Kali, the
firewall's LAB address) should be named and set to **alert on down**. A new unknown
device on LAB is worth a look; LAB holds your security tooling.

## 10.5 Optional: status for devices on other segments

If you want up/down status for specific devices elsewhere (a printer, an AP), the
`ICMP` plugin pings devices **you add by hand** with their real IP. It does not discover
new ones. It needs a firewall exception, because LAB is blocked from everything else.

1. OPNsense, **LAB** interface rules, **above seq 20**: pass, protocol ICMP (echo
   request only), source `10.10.140.13`, destination an alias holding just those device
   IPs, log off. Never use a whole segment, and never TRUSTED or MGMT.
2. NetAlertX: add each device manually (**Devices** -> add, real IP, a dummy MAC is fine).
   Set `ICMP_RUN` to `schedule` and `ICMP_RUN_SCHD` to `*/5 * * * *`.
3. Tell your hunts about it. Zeek sees the pings as perfectly regular traffic, and the
   beaconing query in the hunting skill will rank them first. That query already skips
   `NETALERTX_IP`. If you rename hosts, keep it updated.

Without step 1, the pings are dropped, logged and decoded as cross-segment blocks.
One scan of a /24 is about 250 Wazuh events every 5 minutes.

**Kea leases (not recommended here).** NetAlertX has a `KEALSS` plugin that imports
leases from Kea's control agent, which would give names and MACs for every segment. The
control agent's API also accepts commands that change leases and the DHCP config, and
its only protection is basic auth over HTTP. Turning it on and opening it to a LAB
container gives that container write access to DHCP on your firewall. If you want
lease data, read it on the firewall side; don't give NetAlertX the API.

## 10.6 Alerts

NetAlertX can publish to ntfy (**Settings** -> **NTFY**: `NTFY_HOST`, `NTFY_TOPIC`,
`NTFY_TOKEN`). Use a **separate topic** from Wazuh's. New-device notices are inventory
events, not security pages, and mixing them trains you to ignore the SIEM topic.

Install a Wazuh agent in the CT as on any other guest ([04-wazuh.md](04-wazuh.md#42-agents)).
It adds the CT to vulnerability detection. The NetAlertX image carries a large package
set, so expect many findings, and keep the image updated.

## 10.7 Verify

| Check | Expect |
|---|---|
| `curl -s -o /dev/null -w '%{http_code}\n' http://10.10.140.13:20211/` from TRUSTED | `302` (redirect to login), never `200` |
| `docker exec netalertx arp-scan --interface=eth0 10.10.140.0/24` | every LAB guest listed |
| Wazuh: `rule.id:100840 AND data.srcip:10.10.140.13`, last 24 h | **zero** hits; any hit means a scan is crossing the ladder |
| Stop a LAB guest for 10 min | NetAlertX marks it down and notifies |

Backups: CT 203 is in the weekly vzdump set by default (`GUESTS` in
`/etc/default/homelab-backup`). All its state is under `/opt/netalertx/data`.
