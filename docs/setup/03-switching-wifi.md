# 3. Switch and Wi-Fi

Any 802.1Q-capable switch and multi-SSID APs work. If your gear has a controller, it does
not route - OPNsense does.

## 3.1 Networks (controller side)

Create one **VLAN-only** network per segment (VLAN 110/120/130/140/150, controller DHCP
**off** - OPNsense serves DHCP).

## 3.2 Switch ports

| Port role | Profile | Why |
|---|---|---|
| Uplink to the hypervisor (`nic1`) | All VLANs tagged | The trunk |
| AP ports | All VLANs tagged | APs pick up new networks automatically |
| Wired IoT devices | Native VLAN 120 | |
| Out-of-band recovery port | Native VLAN 130 (MGMT) | Physical recovery path if a firewall change locks you out |

## 3.3 SSIDs

| SSID | VLAN | Notes |
|---|---|---|
| `<trusted-ssid>` | 110 | WPA3 where clients support it |
| `<iot-ssid>` | 120 | 2.4 GHz enabled |
| `<vpn-free-ssid>` | 150 | The VPN-free segment |

Set passphrases yourself. Do not hand them to automation.

## 3.4 Adding a VLAN later - the two-trunk rule

A new VLAN needs **both**:

1. The switch/AP side (above), **and**
2. The hypervisor bridge: `bridge vlan add vid <N> dev nic1` + add `<N>` to `bridge-vids`.

Miss step 2 and clients associate, get no DHCP lease, and report "DNS not resolving".
Check with `bridge vlan show dev nic1` and, on OPNsense, `netstat -I vlanNN` (zero input
packets = L2 problem).

## Verify

From a client on each SSID: it gets a lease in the right /24, resolves via the gateway,
and `curl https://api.ipify.org` shows the expected egress address.
