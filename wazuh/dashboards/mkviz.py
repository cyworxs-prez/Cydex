#!/usr/bin/env python3
"""Generate OpenSearch Dashboards saved objects (NDJSON) for the SOC hunt panels."""
import json

IDX = "wazuh-alerts-*"
REF = [{"name": "kibanaSavedObjectMeta.searchSourceJSON.index",
        "type": "index-pattern", "id": IDX}]

def search_src(query):
    return json.dumps({"query": {"query": query, "language": "kuery"},
                       "filter": [],
                       "indexRefName": "kibanaSavedObjectMeta.searchSourceJSON.index"})

def viz(vid, title, vis_state, query, desc=""):
    return {"id": vid, "type": "visualization",
            "attributes": {"title": title, "visState": json.dumps(vis_state),
                           "uiStateJSON": "{}", "description": desc, "version": 1,
                           "kibanaSavedObjectMeta": {"searchSourceJSON": search_src(query)}},
            "references": REF}

def count_metric(cid="1", label="Count"):
    return {"id": cid, "enabled": True, "type": "count", "schema": "metric",
            "params": {"customLabel": label}}

def terms(aid, field, size, label):
    return {"id": aid, "enabled": True, "type": "terms", "schema": "bucket",
            "params": {"field": field, "orderBy": "1", "order": "desc", "size": size,
                       "otherBucket": False, "otherBucketLabel": "Other",
                       "missingBucket": False, "missingBucketLabel": "Missing",
                       "customLabel": label}}

def table(title, fields, query, size=20):
    aggs = [count_metric()]
    for i, (f, lbl) in enumerate(fields, start=2):
        aggs.append(terms(str(i), f, size, lbl))
    return {"title": title, "type": "table", "aggs": aggs,
            "params": {"perPage": 10, "showPartialRows": False,
                       "showMetricsAtAllLevels": False, "showTotal": False,
                       "totalFunc": "sum", "percentageCol": ""}}

def timeline(title):
    return {"title": title, "type": "histogram",
            "aggs": [count_metric(),
                     {"id": "2", "enabled": True, "type": "date_histogram", "schema": "segment",
                      "params": {"field": "timestamp", "timeRange": {"from": "now-24h", "to": "now"},
                                 "useNormalizedOpenSearchInterval": True, "interval": "auto",
                                 "drop_partials": False, "min_doc_count": 1,
                                 "extended_bounds": {}, "customLabel": "Time"}}],
            "params": {"type": "histogram", "grid": {"categoryLines": False},
                       "categoryAxes": [{"id": "CategoryAxis-1", "type": "category", "position": "bottom",
                                         "show": True, "style": {}, "scale": {"type": "linear"},
                                         "labels": {"show": True, "filter": True, "truncate": 100},
                                         "title": {}}],
                       "valueAxes": [{"id": "ValueAxis-1", "name": "LeftAxis-1", "type": "value",
                                      "position": "left", "show": True, "style": {},
                                      "scale": {"type": "linear", "mode": "normal"},
                                      "labels": {"show": True, "rotate": 0, "filter": False, "truncate": 100},
                                      "title": {"text": "Count"}}],
                       "seriesParams": [{"show": True, "type": "histogram", "mode": "stacked",
                                         "data": {"label": "Count", "id": "1"},
                                         "valueAxis": "ValueAxis-1", "drawLinesBetweenPoints": True,
                                         "lineWidth": 2, "showCircles": True}],
                       "addTooltip": True, "addLegend": False, "legendPosition": "right",
                       "times": [], "addTimeMarker": False, "labels": {"show": False}, "thresholdLine":
                       {"show": False, "value": 10, "width": 1, "style": "full", "color": "#E7664C"}}}

def pie(title, field, label, size=12):
    return {"title": title, "type": "pie",
            "aggs": [count_metric(), terms("2", field, size, label)],
            "params": {"type": "pie", "addTooltip": True, "addLegend": True,
                       "legendPosition": "right", "isDonut": True,
                       "labels": {"show": True, "values": True, "last_level": True, "truncate": 100}}}

objs = []

# --- Zeek ---
objs.append(viz("hunt-zeek-timeline", "Hunt / Zeek - Activity Over Time",
                timeline("Zeek Activity Over Time"), "rule.groups:zeek",
                "Zeek network-metadata detections over time"))
objs.append(viz("hunt-zeek-top", "Hunt / Zeek - Top Detections",
                table("Zeek Detections", [("rule.description", "Detection"),
                                          ("agent.name", "Sensor")], "rule.groups:zeek"),
                "rule.groups:zeek", "Zeek notices, weird events, TLS issues"))

# --- Sigma ---
objs.append(viz("hunt-sigma-detections", "Hunt / Sigma - Converted Rule Hits",
                table("Sigma Detections", [("rule.description", "Sigma Rule"),
                                           ("rule.level", "Level")], "rule.groups:sigma"),
                "rule.groups:sigma", "SigmaHQ rules converted to Wazuh"))

# --- YARA ---
objs.append(viz("hunt-yara-matches", "Hunt / YARA - Malware Signature Matches",
                table("YARA Matches", [("data.yara_rule", "YARA Rule"),
                                       ("data.yara_file", "File"),
                                       ("data.yara_host", "Host")], "rule.groups:yara"),
                "rule.groups:yara", "Host-based YARA signature hits (5,029 rules)"))

# --- MITRE ---
objs.append(viz("hunt-mitre-techniques", "Hunt / MITRE ATT&CK - Techniques",
                table("ATT&CK Techniques", [("rule.mitre.technique", "Technique"),
                                            ("rule.mitre.id", "ID")],
                      "rule.mitre.id:*", size=25),
                "rule.mitre.id:*", "Observed ATT&CK techniques"))
objs.append(viz("hunt-mitre-tactics", "Hunt / MITRE ATT&CK - Tactics",
                pie("ATT&CK Tactics", "rule.mitre.tactic", "Tactic"),
                "rule.mitre.id:*", "Distribution of ATT&CK tactics"))

# --- IOC / Threat Intel ---
IOC_Q = ('data.alert.signature:(*ThreatFox* or *URLhaus* or *Feodo* or *DROP* or '
         '*abuse.ch* or *CnC* or *C2* or *Malware* or *Trojan*)')
objs.append(viz("hunt-ioc-hits", "Hunt / IOC - Threat-Intel Signature Hits",
                table("IOC Hits", [("data.alert.signature", "Signature"),
                                   ("data.srcip", "Source"),
                                   ("data.dstip", "Destination")], IOC_Q),
                IOC_Q, "abuse.ch ThreatFox / URLhaus / Feodo / Spamhaus DROP and C2 signatures"))
objs.append(viz("hunt-ioc-categories", "Hunt / IOC - Suricata Alert Categories",
                pie("Alert Categories", "data.alert.category", "Category"),
                "rule.groups:suricata", "Suricata alert category breakdown"))

# --- Segmentation ---
objs.append(viz("hunt-segmentation", "Hunt / Segmentation Violations",
                table("Segmentation Violations", [("rule.description", "Violation"),
                                                  ("data.srcip", "Source"),
                                                  ("data.dstip", "Destination")],
                      "rule.groups:segmentation_violation"),
                "rule.groups:segmentation_violation",
                "Blocked inter-VLAN attempts toward TRUSTED / MGMT / LAB"))

# --- Dashboard ---
panels, refs = [], []
layout = [
    ("hunt-zeek-timeline", 0, 0, 48, 12),
    ("hunt-zeek-top", 0, 12, 24, 15),
    ("hunt-sigma-detections", 24, 12, 24, 15),
    ("hunt-mitre-techniques", 0, 27, 30, 15),
    ("hunt-mitre-tactics", 30, 27, 18, 15),
    ("hunt-yara-matches", 0, 42, 24, 15),
    ("hunt-ioc-hits", 24, 42, 24, 15),
    ("hunt-ioc-categories", 0, 57, 18, 15),
    ("hunt-segmentation", 18, 57, 30, 15),
]
for i, (vid, x, y, w, h) in enumerate(layout, start=1):
    pname = f"panel_{i}"
    panels.append({"version": "2.13.0", "gridData": {"x": x, "y": y, "w": w, "h": h, "i": str(i)},
                   "panelIndex": str(i), "embeddableConfig": {}, "panelRefName": pname})
    refs.append({"name": pname, "type": "visualization", "id": vid})

objs.append({
    "id": "omega-hunt", "type": "dashboard",
    "attributes": {
        "title": "Homelab - Threat Hunting (Zeek / Sigma / YARA / MITRE / IOC)",
        "hits": 0,
        "description": "Network + host hunting surface: Zeek metadata, Sigma detections, YARA matches, ATT&CK coverage, threat-intel IOC hits, segmentation violations.",
        "panelsJSON": json.dumps(panels),
        "optionsJSON": json.dumps({"hidePanelTitles": False, "useMargins": True}),
        "version": 1,
        "timeRestore": False,
        "kibanaSavedObjectMeta": {"searchSourceJSON": json.dumps({"query": {"query": "", "language": "kuery"}, "filter": []})},
    },
    "references": refs})

with open("hunt-dashboard.ndjson", "w") as fh:
    for o in objs:
        fh.write(json.dumps(o) + "\n")
print(f"wrote {len(objs)} saved objects")
