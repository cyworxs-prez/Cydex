# 11. Console gateway (Apache Guacamole)

Reference: Guacamole 1.6.0 in Docker Compose in CT 205, `10.10.140.20`.
UI at `http://10.10.140.20:8080/guacamole/`. **Note the trailing `/guacamole/`.** The
bare `:8080/` is Tomcat, not the app.

Guacamole gives you browser-based SSH, RDP and VNC to lab machines (Kali, test VMs)
without installing clients or opening those ports to your workstation.

## Threat model first

Guacamole is a **jump host**. It stores credentials for every saved connection and
opens sessions from its own IP. Whoever holds a Guacamole admin login can reach
everything Guacamole can reach, from inside LAB. The setup below follows from that:

| Control | Where |
|---|---|
| Reachable from TRUSTED only; never port-forwarded or exposed to the internet | OPNsense (TRUSTED -> LAB already allowed; nothing else is) |
| Reaches **LAB only**. No firewall exceptions from `10.10.140.20` to MGMT or TRUSTED | LAB rule ladder seq 20-23, unchanged. Manage Proxmox and OPNsense from TRUSTED directly, not through Guacamole |
| Default `guacadmin` password changed on first login | [11.3](#113-first-login) |
| TOTP on every account | `TOTP_ENABLED=true` in `.env` |
| Brute-force ban (5 failures -> 5 min) and Wazuh pages before it trips | compose env + rules 100930-100934 |
| guacd and Postgres not published outside the CT | compose file (only `8080` is mapped) |

## 11.1 Create the container (Proxmox host)

Same pattern as [10.1](10-netalertx.md#101-create-the-container-proxmox-host):

```bash
TPL=$(pveam list local | awk '/debian-13-standard/{print $1}' | tail -1)
pct create 205 "$TPL" \
  --hostname guac --cores 2 --memory 2048 --rootfs local-lvm:8 \
  --net0 name=eth0,bridge=vmbr1,tag=140,ip=10.10.140.20/24,gw=10.10.140.1 \
  --nameserver 10.10.140.1 --unprivileged 1 --features nesting=1,keyctl=1 --onboot 1
pct start 205
pct exec 205 -- sh -c 'apt-get update && apt-get install -y docker.io docker-compose && docker compose version'
```

## 11.2 Install

```bash
# from the repo on your workstation
scp lab/guacamole/docker-compose.yml lab/guacamole/.env.example root@10.10.130.10:/tmp/
ssh root@10.10.130.10 'pct exec 205 -- mkdir -p /opt/guac/initdb &&
  pct push 205 /tmp/docker-compose.yml /opt/guac/docker-compose.yml &&
  pct push 205 /tmp/.env.example /opt/guac/.env.example'
```

Inside CT 205 (`pct enter 205`):

```bash
cd /opt/guac
cp .env.example .env && chmod 600 .env
sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(openssl rand -base64 24 | tr -d '/+=')|" .env

# Guacamole does not create its own tables. Generate the schema from the SAME image
# version the compose file runs; Postgres applies it on its first start only.
docker run --rm guacamole/guacamole:1.6.0 /opt/guacamole/bin/initdb.sh --postgresql > initdb/initdb.sql
test -s initdb/initdb.sql && echo schema-ok

docker compose up -d
docker compose logs --tail=30 guacamole      # look for "Server startup in"
```

**Schema only applies to an empty database.** If Postgres started once without
`initdb.sql` (wrong path, empty file), it will never retry. Fix it with
`docker compose down -v` (this deletes the database) and `up -d` again. Do that only
on a fresh install.

## 11.3 First login

1. From TRUSTED, open `http://10.10.140.20:8080/guacamole/`. Log in as `guacadmin` /
   `guacadmin`, the stock default.
2. With TOTP on, you are asked to enroll an authenticator right away. Scan the QR
   code and enter a code.
3. **Change the password from the Preferences page:**
   `http://10.10.140.20:8080/guacamole/#/settings/preferences` -> **Change Password**.

   **Do not use Settings -> Users -> guacadmin.** That form looks right, but saving a new
   password for yourself there fails with *"Permission denied. The password update
   endpoint must be used to change the current user's password."* This is deliberate:
   your own change has to go through the endpoint that asks for your current password.
   Cancel out of that form. Saving it also rewrites the other profile fields.
4. Better still: create a named admin account, log in as it, enroll TOTP, then disable
   `guacadmin` (Settings -> Users -> guacadmin -> **Login disabled**).

**Never edit passwords in Postgres directly.** Guacamole stores a salted hash and a
`password_date`. A hand-written row locks you out with no error. If you are locked out,
recover by creating a new admin through the database and then fixing things in the UI.
That means rebuilding an account, not running one `UPDATE`.

## 11.4 Connections

**Settings** -> **Connections** -> **New connection**. Only add LAB targets, for example:

| Name | Protocol | Host | Notes |
|---|---|---|---|
| kali | SSH | `10.10.140.24` | key auth; paste the private key in the connection, not a password |
| kali-desktop | RDP or VNC | `10.10.140.24` | only if you run a desktop there |

Use the **hostname or IP as seen from CT 205**. guacd opens the session, not your browser.
If a connection hangs at "Connecting", the cause is almost always that guacd can't reach
the target: test from the CT (container traffic leaves with the CT's address, so the firewall sees the same thing):
`timeout 3 bash -c '</dev/tcp/10.10.140.24/22' && echo open`.

Enable **session recording** per connection if you want an audit trail of what was
typed (Connection -> **Screen Recording**). guacd writes the recordings inside **its**
container, so mount a volume on the `guacd` service at the recording path you set, or
they vanish with the container.

## 11.5 Ship its logs to Wazuh

The Guacamole rules ([detection catalog](../detection-catalog.md): 100930-100934) read
Guacamole's log lines from Docker's JSON log files. **Nothing reaches Wazuh until you
do this step**, and the rules sit silent.

1. Install a Wazuh agent in CT 205 and enroll it ([04-wazuh.md](04-wazuh.md#42-agents)).
2. Append `wazuh/agent/guacamole-localfile.xml` inside `<ossec_config>` in the
   agent's `/var/ossec/etc/ossec.conf`, then `systemctl restart wazuh-agent`.

| Rule | Level | Fires on |
|---|---|---|
| 100931 | 5 | one failed login |
| 100932 | 10 (pages) | 3 failures in 5 min - fires **before** the ban |
| 100934 | 10 (pages) | Guacamole's ban tracker blocked an address |
| 100933 | 5 | successful login (who and from where) |

If you change `BAN_MAX_INVALID_ATTEMPTS`, keep it above 100932's `frequency` so Wazuh
still pages before the ban hides further attempts.

## 11.6 Verify

| Check | Expect |
|---|---|
| `curl -s -o /dev/null -w '%{http_code}\n' http://10.10.140.20:8080/guacamole/` from TRUSTED | `200` |
| Same URL from an IoT or DIRECT client | times out (blocked) |
| `ss -ltnp` in CT 205 | `:8080` (docker-proxy) and sshd only; no `4822`, no `5432` |
| `timeout 3 bash -c '</dev/tcp/10.10.130.10/22' && echo open` in CT 205 | no `open` - Guacamole can't reach MGMT |
| Fail 4 logins in a row | 100931 for each, and **100932 pages** |
| Keep going past 5 failures from the same address | 100934 pages; that IP is refused for 5 min, even with the right password |
| `grep -c 'guacamole' /var/ossec/logs/alerts/alerts.json` on the manager | rising after the test |

Backups: CT 205 is in the weekly vzdump set by default. Its state is the Postgres
volume (users, connections, TOTP keys) plus `/opt/guac/.env`. A restore needs both:
the database password in `.env` must match the one the volume was initialised with.

## Upgrades

Bump **both** image tags together (`guacamole/guacd` and `guacamole/guacamole` must be the
same version) and read the release notes for schema upgrade scripts. The init scripts
only run on an empty database, so an upgrade that needs schema changes means applying
the upgrade SQL by hand, after a backup.
