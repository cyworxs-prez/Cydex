# Security

## What this repo is

A **fictional reference** build. Addresses (`10.10.x.0/24`), VLAN IDs (110-150), guest
IDs (200-206), SSIDs (`<...-ssid>` placeholders) and device categories are examples,
not a description of any real network. Public addresses in samples come from the RFC
5737 documentation ranges; the only other public addresses are well-known public DNS
resolvers listed in the DoH-hunting code.

## Release process

1. Keep your private pattern list **outside** the repo - one fixed string per line:
   your real names, domains, public and private addresses, SSIDs, hostnames, device
   brands and models, vault/item IDs. Default location:
   `~/.config/cydex/private-patterns.txt` (or set `$CYDEX_PRIVATE_PATTERNS`).
2. Commit, then run `tools/export-release.sh`. It builds the release from committed
   files with `git archive` (no `.git`, no ignored files, no filesystem metadata) in a
   directory outside the repo, and runs `tools/check.sh` on that export.
3. Read the export yourself, including every image. Distribute the generated tarball
   or push the clean history - **never zip or copy the working folder**.

## What `tools/check.sh` checks

- Every file in the scanned tree: tracked, untracked and ignored.
- Every Git object, reachable or dangling, when a `.git` is present; fails on any
  unreachable objects.
- Files that must not ship: env files, keys, archives, bytecode, backups, OS metadata.
- Secret-shaped strings, MAC addresses, non-documentation public IPv4 addresses.
- Your private pattern list (the gate fails if the list is missing).
- Images: each must be listed in `tools/reviewed-images.sha256` after a visual review,
  and PNGs may not carry metadata chunks.

## What it cannot check

Context. A scanner cannot tell that a comment describes a real incident, that a
combination of details is identifying, or what an image shows. A passing run is
necessary, not sufficient - a person must review the export.

## Reporting

Open an issue for a problem in the code (for example a script that could leak a
credential). Do not include secrets or your own network details.

## Using it safely

Several scripts write to live systems (firewall, hypervisor, SIEM); `ai-ops/AGENTS.md`
lists them. Read every script before running it, snapshot first, and test on one host.
