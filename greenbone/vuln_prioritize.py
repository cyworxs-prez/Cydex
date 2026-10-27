#!/usr/bin/env python3
"""
vuln_prioritize.py  -  Risk-rank Greenbone/GVM findings with CISA KEV + FIRST EPSS.

Pulls the most recent finished report from the local gvmd socket (via the
greenbone-community gvm-tools docker image), extracts every CVE-bearing result,
then joins against:
  - CISA Known Exploited Vulnerabilities (KEV) catalog
  - FIRST EPSS (Exploit Prediction Scoring System) daily scores

Output:
  /root/vuln-priority.csv   full ranked table
  stdout                    top-25 executive summary

Ranking (descending):
  1. KEV membership (actively exploited in the wild)  -> hard top priority
  2. EPSS probability (likelihood of exploitation next 30 days)
  3. CVSS base severity

Auth:
  GMP password read from $GB_PW, else /root/.gbpw (chmod 600), else abort.
  (No password is hard-coded in this file.)
"""
import os, sys, csv, ssl, gzip, json, io, subprocess, urllib.request, xml.etree.ElementTree as ET
from collections import defaultdict

GVMD_VOL = "greenbone-community-edition_gvmd_socket_vol"
GVM_IMG  = "registry.community.greenbone.net/community/gvm-tools"
KEV_URL  = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
EPSS_URL = "https://epss.cyentia.com/epss_scores-current.csv.gz"
OUT_CSV  = "/root/vuln-priority.csv"

def gb_password():
    pw = os.environ.get("GB_PW")
    if pw:
        return pw.strip()
    try:
        with open("/root/.gbpw") as f:
            return f.read().strip()
    except OSError:
        sys.exit("ERROR: no GMP password. Set $GB_PW or create /root/.gbpw (chmod 600).")

def gcli(xml_cmd, pw):
    """Run one GMP command through the dockerized gvm-cli, return stdout XML."""
    cmd = [
        "docker","run","--rm","-i","-v", f"{GVMD_VOL}:/run/gvmd", GVM_IMG,
        "gvm-cli","--gmp-username","admin", f"--gmp-password={pw}",
        "socket","--socketpath","/run/gvmd/gvmd.sock","--xml", xml_cmd,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        sys.exit(f"gvm-cli failed: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout

def latest_report_id(pw):
    xml = gcli('<get_reports filter="rows=100 sort-reverse=date"/>', pw)
    root = ET.fromstring(xml)
    best_id, best_end = None, ""
    for rep in root.findall(".//report[@id]"):
        # the outer <report> wraps an inner <report>; scan_end marks completion
        end = rep.findtext("scan_end") or ""
        rid = rep.get("id")
        if rid and end and end > best_end:
            best_end, best_id = end, rid
    if not best_id:
        sys.exit("No finished reports found in gvmd.")
    return best_id, best_end

def fetch(url):
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "vuln-prioritize/1.0"})
    with urllib.request.urlopen(req, context=ctx, timeout=120) as r:
        return r.read()

def load_kev():
    data = json.loads(fetch(KEV_URL))
    return {v["cveID"].upper(): v for v in data.get("vulnerabilities", [])}

def load_epss():
    raw = gzip.decompress(fetch(EPSS_URL)).decode("utf-8", "replace")
    epss = {}
    for line in raw.splitlines():
        if not line or line.startswith("#") or line.startswith("cve"):
            continue
        parts = line.split(",")
        if len(parts) >= 3:
            epss[parts[0].upper()] = (float(parts[1]), float(parts[2]))  # (epss, percentile)
    return epss

def parse_report(pw, rid):
    xml = gcli(f'<get_reports report_id="{rid}" details="1" '
               f'filter="rows=-1 apply_overrides=1 levels=hml"/>', pw)
    root = ET.fromstring(xml)
    # map: cve -> {hosts:set, cvss:max, name:str}
    findings = defaultdict(lambda: {"hosts": set(), "cvss": 0.0, "name": ""})
    for res in root.findall(".//result"):
        host = res.findtext("host") or (res.find("host").text if res.find("host") is not None else "")
        if host:
            host = host.strip().split("\n")[0]
        nvt = res.find("nvt")
        if nvt is None:
            continue
        name = nvt.findtext("name") or ""
        try:
            cvss = float(res.findtext("severity") or nvt.findtext("cvss_base") or 0)
        except ValueError:
            cvss = 0.0
        for ref in nvt.findall(".//ref"):
            if (ref.get("type") or "").lower() == "cve":
                cve = (ref.get("id") or "").upper()
                if not cve.startswith("CVE-"):
                    continue
                f = findings[cve]
                f["hosts"].add(host)
                f["cvss"] = max(f["cvss"], cvss)
                if not f["name"]:
                    f["name"] = name
    return findings

def main():
    pw = gb_password()
    print("[*] locating latest finished report ...", file=sys.stderr)
    rid, end = latest_report_id(pw)
    print(f"[*] report {rid} (scan_end {end})", file=sys.stderr)
    findings = parse_report(pw, rid)
    print(f"[*] {len(findings)} distinct CVEs across findings", file=sys.stderr)
    print("[*] fetching CISA KEV ...", file=sys.stderr)
    kev = load_kev()
    print(f"[*] KEV catalog: {len(kev)} CVEs", file=sys.stderr)
    print("[*] fetching FIRST EPSS ...", file=sys.stderr)
    epss = load_epss()
    print(f"[*] EPSS scores: {len(epss)} CVEs", file=sys.stderr)

    rows = []
    for cve, f in findings.items():
        e_prob, e_pct = epss.get(cve, (0.0, 0.0))
        in_kev = cve in kev
        kev_due = kev.get(cve, {}).get("dueDate", "")
        # composite priority: KEV dominates, then EPSS, then CVSS
        priority = (1000 if in_kev else 0) + e_prob * 100 + f["cvss"]
        rows.append({
            "cve": cve,
            "in_kev": "YES" if in_kev else "",
            "epss": round(e_prob, 4),
            "epss_pct": round(e_pct, 4),
            "cvss": f["cvss"],
            "hosts": ";".join(sorted(h for h in f["hosts"] if h)),
            "kev_due": kev_due,
            "name": f["name"][:90],
            "priority": round(priority, 3),
        })
    rows.sort(key=lambda r: r["priority"], reverse=True)

    with open(OUT_CSV, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["priority","cve","in_kev","epss","epss_pct",
                                           "cvss","hosts","kev_due","name"])
        w.writeheader()
        for r in rows:
            w.writerow(r)

    kev_hits = [r for r in rows if r["in_kev"]]
    print("\n===== VULN PRIORITY (top 25) =====")
    print(f"report={rid} end={end}  cves={len(rows)}  KEV-hits={len(kev_hits)}  csv={OUT_CSV}\n")
    hdr = f'{"PRI":>7}  {"CVE":<16} {"KEV":<3} {"EPSS":>6} {"CVSS":>4}  HOSTS / NAME'
    print(hdr); print("-"*len(hdr))
    for r in rows[:25]:
        print(f'{r["priority"]:>7} {r["cve"]:<16} {r["in_kev"]:<3} '
              f'{r["epss"]:>6} {r["cvss"]:>4}  {r["hosts"]}  {r["name"]}')
    if kev_hits:
        print(f"\n!! {len(kev_hits)} finding(s) are on the CISA KEV list — patch these first.")

if __name__ == "__main__":
    main()
