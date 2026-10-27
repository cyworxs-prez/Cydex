#!/usr/bin/env python3
"""
Build "Cydex - SOC": one unified view over everything the homelab reports.

Design notes
------------
Firewall blocks typically outnumber every other signal by an order of magnitude. If they
share panels with the rest, a single SSH brute force is invisible next to nine
thousand port scans. So every cross-cutting panel excludes rule.groups:firewall_block
and the firewall gets its own contained section near the bottom.

Existing visualizations are referenced rather than duplicated, so edits to them
propagate to both this dashboard and the older focused ones.
"""
import json
import ssl
import urllib.request

BASE = "https://127.0.0.1:9200"
CERTS = "/etc/wazuh-indexer/certs"
INDEX = "wazuh-alerts-*"
# Standing vulnerability exposure. This index pattern has NO time field, so panels
# built on it ignore the dashboard's 24h window and always show current posture.
# The alerts stream only carries NEWLY detected CVEs, which is why long-lived hosts
# could look clean there despite carrying hundreds of open findings.
VULN_INDEX = "wazuh-states-vulnerabilities-*"
DASH_ID = "cydex-soc"

# The noise floor. Everything "cross-cutting" filters it out.
NOFW = "not rule.groups:firewall_block"

ctx = ssl.create_default_context(cafile=f"{CERTS}/root-ca.pem")
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
ctx.load_cert_chain(f"{CERTS}/admin.pem", f"{CERTS}/admin-key.pem")


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
        return json.load(resp)


def save_vis(vid, title, description, vis_state, index=INDEX):
    query = vis_state.pop("_query", "")
    doc = {
        "visualization": {
            "title": title,
            "visState": json.dumps(vis_state),
            "uiStateJSON": "{}",
            "description": description,
            "kibanaSavedObjectMeta": {"searchSourceJSON": json.dumps({
                "index": index,
                "query": {"query": query, "language": "kuery"},
                "filter": [],
            })},
        },
        "type": "visualization",
        "references": [{
            "name": "kibanaSavedObjectMeta.searchSourceJSON.index",
            "type": "index-pattern", "id": index,
        }],
        "migrationVersion": {"visualization": "7.10.0"},
    }
    call("PUT", f"/.kibana/_doc/visualization:{vid}?refresh=wait_for", doc)
    return vid


COUNT = {"id": "1", "enabled": True, "type": "count", "schema": "metric", "params": {}}


def terms(agg_id, field, size, schema, order_by="1"):
    return {"id": agg_id, "enabled": True, "type": "terms", "schema": schema,
            "params": {"field": field, "orderBy": order_by, "order": "desc",
                       "size": size, "otherBucket": False, "missingBucket": False}}


def metric_vis(vid, title, query, description, font=48, index=INDEX):
    state = {
        "title": title, "type": "metric", "aggs": [COUNT],
        "params": {"addTooltip": True, "addLegend": False, "type": "metric",
                   "metric": {"percentageMode": False, "useRanges": False,
                              "colorSchema": "Green to Red", "metricColorMode": "None",
                              "colorsRange": [{"from": 0, "to": 100000}],
                              "labels": {"show": True}, "invertColors": False,
                              "style": {"bgFill": "#000", "bgColor": False,
                                        "labelColor": False, "subText": "",
                                        "fontSize": font}}},
    }
    state["_query"] = query
    return save_vis(vid, title, description, state, index)


def table_vis(vid, title, query, buckets, description, per_page=10, index=INDEX):
    """buckets: list of (field, size) - two entries gives a two-axis breakdown."""
    aggs = [COUNT]
    for i, (field, size) in enumerate(buckets):
        aggs.append(terms(str(i + 2), field, size, "bucket"))
    state = {
        "title": title, "type": "table", "aggs": aggs,
        "params": {"perPage": per_page, "showPartialRows": False,
                   "showMetricsAtAllLevels": False, "showTotal": True,
                   "totalFunc": "sum", "percentageCol": ""},
    }
    state["_query"] = query
    return save_vis(vid, title, description, state, index)


def pie_vis(vid, title, query, field, size, description, index=INDEX):
    state = {
        "title": title, "type": "pie",
        "aggs": [COUNT, terms("2", field, size, "segment")],
        "params": {"type": "pie", "addTooltip": True, "addLegend": True,
                   "legendPosition": "right", "isDonut": True,
                   "labels": {"show": False, "values": True, "last_level": True,
                              "truncate": 100}},
    }
    state["_query"] = query
    return save_vis(vid, title, description, state, index)


def timeline_vis(vid, title, query, description, axis_label, split_field=None,
                 split_size=8):
    aggs = [COUNT, {"id": "2", "enabled": True, "type": "date_histogram",
                    "schema": "segment",
                    "params": {"field": "@timestamp", "interval": "auto",
                               "min_doc_count": 1}}]
    if split_field:
        aggs.append(terms("3", split_field, split_size, "group"))
    state = {
        "title": title, "type": "histogram", "aggs": aggs,
        "params": {"type": "histogram", "addTooltip": True,
                   "addLegend": bool(split_field), "legendPosition": "right",
                   "categoryAxes": [{"id": "CategoryAxis-1", "type": "category",
                                     "position": "bottom", "show": True,
                                     "scale": {"type": "linear"},
                                     "labels": {"show": True}, "title": {}}],
                   "valueAxes": [{"id": "ValueAxis-1", "name": "LeftAxis-1",
                                  "type": "value", "position": "left", "show": True,
                                  "scale": {"type": "linear", "mode": "normal"},
                                  "labels": {"show": True},
                                  "title": {"text": axis_label}}],
                   "seriesParams": [{"show": True, "type": "histogram",
                                     "mode": "stacked",
                                     "data": {"label": axis_label, "id": "1"},
                                     "valueAxis": "ValueAxis-1"}]},
    }
    state["_query"] = query
    return save_vis(vid, title, description, state)


# ---------------------------------------------------------------- headline row
metric_vis("soc-tile-vuln-crit", "Critical Vulnerabilities",
           "vulnerability.severity:Critical",
           "Open Critical CVEs across all agents. Standing exposure, not time-filtered.",
           index=VULN_INDEX)
metric_vis("soc-tile-vuln-high", "High Vulnerabilities",
           "vulnerability.severity:High",
           "Open High CVEs across all agents. Standing exposure, not time-filtered.",
           index=VULN_INDEX)
metric_vis("soc-tile-auth-fail", "Failed Authentications",
           "rule.groups:authentication_failed or rule.groups:invalid_login",
           "Rejected logins across every agent.")
metric_vis("soc-tile-auth-ok", "Successful Authentications",
           "rule.groups:authentication_success", "Accepted logins across every agent.")
metric_vis("soc-tile-ids", "IDS Alerts",
           "rule.groups:suricata and data.event_type:alert",
           "Suricata signature hits from the OPNsense agent.")
metric_vis("soc-tile-fw", "Firewall Blocks", "rule.groups:firewall_block",
           "External sources dropped at the OPNsense edge.")

# ------------------------------------------------------------------ the signal
timeline_vis("soc-signal-timeline", "Security events over time (firewall excluded)",
             NOFW, "Everything except the firewall noise floor, split by category.",
             "Events", split_field="rule.groups", split_size=8)
pie_vis("soc-level-dist", "Alert severity distribution", NOFW, "rule.level", 12,
        "Wazuh rule levels. 10+ is what pages you via ntfy.")

# -------------------------------------------------------------------- ATT&CK
pie_vis("soc-mitre-tactic", "MITRE ATT&CK tactics", NOFW, "rule.mitre.tactic", 12,
        "Adversary objectives observed, firewall noise excluded.")
table_vis("soc-mitre-tech", "MITRE ATT&CK techniques", NOFW,
          [("rule.mitre.technique", 15)], "Specific techniques mapped by Wazuh rules.")
table_vis("soc-top-rules", "Top rules firing (firewall excluded)", NOFW,
          [("rule.description", 15)], "What is actually generating volume.")

# ------------------------------------------------------------------- identity
timeline_vis("soc-auth-timeline", "Authentication activity over time",
             "rule.groups:authentication_success or rule.groups:authentication_failed "
             "or rule.groups:invalid_login",
             "Accepted vs rejected logins over time.", "Logins",
             split_field="rule.groups", split_size=6)
table_vis("soc-auth-accounts", "Accounts targeted",
          "rule.groups:authentication_success or rule.groups:authentication_failed "
          "or rule.groups:invalid_login",
          [("data.dstuser", 10)], "Which local accounts logins are aimed at.")
table_vis("soc-auth-sources", "Authentication source IPs",
          "rule.groups:authentication_success or rule.groups:authentication_failed "
          "or rule.groups:invalid_login",
          [("data.srcip", 10)], "Where logins are coming from.")

# ------------------------------------------------------------- vulnerabilities
pie_vis("soc-vuln-sev", "Open vulnerabilities by severity", "",
        "vulnerability.severity", 6,
        "Current exposure across every agent. Ignores the dashboard time range.",
        index=VULN_INDEX)
table_vis("soc-vuln-host", "Exposure by host", "",
          [("agent.name", 8), ("vulnerability.severity", 5)],
          "Which host carries which severity of risk.",
          per_page=12, index=VULN_INDEX)
table_vis("soc-vuln-cve", "Top CVEs", "",
          [("vulnerability.id", 15)], "Most prevalent open CVEs.",
          per_page=12, index=VULN_INDEX)
table_vis("soc-vuln-pkg", "Most vulnerable packages", "",
          [("package.name", 15)], "Packages carrying the most open findings.",
          per_page=12, index=VULN_INDEX)

# ------------------------------------------------------- compliance & posture
table_vis("soc-sca", "CIS benchmark checks", "rule.groups:sca",
          [("data.sca.policy", 8)], "Security Configuration Assessment results.")
table_vis("soc-rootcheck", "Policy monitoring findings", "rule.groups:rootcheck",
          [("data.title", 12)],
          "Rootcheck puts the actual finding in data.title; rule.description is the "
          "same generic string for every hit, which collapsed this to one row.")
table_vis("soc-pci", "PCI DSS requirements triggered", NOFW,
          [("rule.pci_dss", 12)], "Regulatory mapping Wazuh attaches to firing rules.")

# ----------------------------------------------------------------------- hosts
timeline_vis("soc-agent-timeline", "Events by host over time", NOFW,
             "Per-agent event volume, firewall noise excluded.", "Events",
             split_field="agent.name", split_size=8)
table_vis("soc-agent-table", "Top event hosts", NOFW,
          [("agent.name", 10)], "Which agents are the loudest.", per_page=8)

# ------------------------------------------------- network / the noise floor
table_vis("soc-country-port", "Source country to targeted port",
          "rule.groups:firewall_block",
          [("GeoLocation.country_name", 10), ("data.dstport", 6)],
          "Which countries are probing which ports. Stands in for the Sankey.",
          per_page=15)

# ------------------------------------------------------------------- assemble
PANELS = [
    # (visualization id, x, y, w, h)
    ("soc-tile-vuln-crit",   0,   0,  8,  8),
    ("soc-tile-vuln-high",   8,   0,  8,  8),
    ("soc-tile-auth-fail",  16,   0,  8,  8),
    ("soc-tile-auth-ok",    24,   0,  8,  8),
    ("soc-tile-ids",        32,   0,  8,  8),
    ("soc-tile-fw",         40,   0,  8,  8),

    ("soc-signal-timeline",  0,   8, 32, 15),
    ("soc-level-dist",      32,   8, 16, 15),

    ("soc-mitre-tactic",     0,  23, 16, 15),
    ("soc-mitre-tech",      16,  23, 16, 15),
    ("soc-top-rules",       32,  23, 16, 15),

    ("soc-auth-timeline",    0,  38, 24, 15),
    ("soc-auth-accounts",   24,  38, 12, 15),
    ("soc-auth-sources",    36,  38, 12, 15),

    ("soc-vuln-sev",         0,  53, 12, 15),
    ("soc-vuln-host",       12,  53, 12, 15),
    ("soc-vuln-cve",        24,  53, 12, 15),
    ("soc-vuln-pkg",        36,  53, 12, 15),

    ("soc-sca",              0,  68, 16, 15),
    ("soc-rootcheck",       16,  68, 16, 15),
    ("soc-pci",             32,  68, 16, 15),

    ("soc-agent-timeline",   0,  83, 24, 15),
    ("soc-agent-table",     24,  83, 24, 15),

    ("omega-net-geomap",     0,  98, 24, 18),
    ("soc-country-port",    24,  98, 24, 18),

    ("omega-net-timeline",   0, 116, 24, 15),
    ("omega-net-sources",   24, 116, 12, 15),
    ("omega-net-ports",     36, 116, 12, 15),

    ("omega-ids-timeline",   0, 131, 16, 15),
    ("omega-ids-signatures",16, 131, 16, 15),
    ("omega-ids-classification", 32, 131, 16, 15),
]

panels_json, references = [], []
for i, (vid, x, y, w, h) in enumerate(PANELS):
    panels_json.append({
        "version": "2.13.0",
        "gridData": {"x": x, "y": y, "w": w, "h": h, "i": str(i + 1)},
        "panelIndex": str(i + 1),
        "embeddableConfig": {},
        "panelRefName": f"panel_{i}",
    })
    references.append({"name": f"panel_{i}", "type": "visualization", "id": vid})

dashboard = {
    "dashboard": {
        "title": "Cydex - SOC",
        "description": (
            "Unified view of everything the homelab reports: vulnerabilities, "
            "identity, ATT&CK coverage, compliance posture, per-host volume, the "
            "firewall noise floor and Suricata IDS. Cross-cutting panels exclude "
            "rule.groups:firewall_block so edge drops do not bury the "
            "events that need a human."
        ),
        "panelsJSON": json.dumps(panels_json),
        "optionsJSON": json.dumps({"hidePanelTitles": False, "useMargins": True}),
        "version": 1,
        "timeRestore": True,
        "timeTo": "now",
        "timeFrom": "now-24h",
        "refreshInterval": {"pause": False, "value": 60000},
        "kibanaSavedObjectMeta": {"searchSourceJSON": json.dumps(
            {"query": {"query": "", "language": "kuery"}, "filter": []})},
    },
    "type": "dashboard",
    "references": references,
    "migrationVersion": {"dashboard": "7.9.3"},
}

call("PUT", f"/.kibana/_doc/dashboard:{DASH_ID}?refresh=wait_for", dashboard)
print(f"built dashboard:{DASH_ID} with {len(PANELS)} panels")
