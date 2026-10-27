#!/usr/bin/env python3
"""
Add Suricata IDS panels to the Homelab - Network Threat Map dashboard.

Clones the existing firewall-block visualizations (so the tile_map / histogram
schemas are guaranteed to match this OpenSearch Dashboards version) and re-points
them at the IDS alert stream produced by rules 100200-100210.

Read-only against the home lab from the dashboard's perspective; this only writes
saved objects in the .kibana index on the Wazuh indexer.
"""
import json
import ssl
import urllib.request

BASE = "https://127.0.0.1:9200"
CERTS = "/etc/wazuh-indexer/certs"
IDS_QUERY = "rule.groups:network_ids"

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


def get_vis(vid):
    return call("GET", f"/.kibana/_doc/visualization:{vid}")["_source"]


def put_doc(doc_id, source):
    return call("PUT", f"/.kibana/_doc/{doc_id}?refresh=wait_for", source)


def retarget(src_id, new_id, title, description, mutate_visstate=None):
    """Clone a visualization, set a new title and point it at the IDS query."""
    doc = get_vis(src_id)
    vis = doc["visualization"]

    state = json.loads(vis["visState"])
    state["title"] = title
    if mutate_visstate:
        mutate_visstate(state)
    vis["visState"] = json.dumps(state)
    vis["title"] = title
    vis["description"] = description

    search = json.loads(vis["kibanaSavedObjectMeta"]["searchSourceJSON"])
    search["query"] = {"query": IDS_QUERY, "language": "kuery"}
    vis["kibanaSavedObjectMeta"]["searchSourceJSON"] = json.dumps(search)

    doc.pop("updated_at", None)
    put_doc(f"visualization:{new_id}", doc)
    return new_id


def set_terms_field(field, size=15):
    def _mutate(state):
        for agg in state["aggs"]:
            if agg["type"] == "terms":
                agg["params"]["field"] = field
                agg["params"]["size"] = size
    return _mutate


def set_axis_title(text):
    def _mutate(state):
        for axis in state["params"].get("valueAxes", []):
            axis["title"] = {"text": text}
        for series in state["params"].get("seriesParams", []):
            series["data"]["label"] = text
    return _mutate


new_panels = [
    (retarget("omega-net-timeline", "omega-ids-timeline",
              "IDS alerts over time",
              "Suricata alerts forwarded from OPNsense (rules 100200-100210).",
              set_axis_title("IDS alerts")),
     {"x": 0, "y": 59, "w": 24, "h": 14}),

    (retarget("omega-net-sources", "omega-ids-signatures",
              "Top IDS signatures",
              "Which Suricata rules are actually firing.",
              set_terms_field("data.signature", 15)),
     {"x": 24, "y": 59, "w": 24, "h": 14}),

    (retarget("omega-net-sources", "omega-ids-sources",
              "Top IDS source IPs",
              "Hosts triggering Suricata signatures, attacker side.",
              set_terms_field("data.srcip", 15)),
     {"x": 0, "y": 73, "w": 16, "h": 14}),

    (retarget("omega-net-sources", "omega-ids-classification",
              "IDS alerts by classification",
              "Suricata classtype breakdown.",
              set_terms_field("data.classification", 10)),
     {"x": 16, "y": 73, "w": 16, "h": 14}),

    (retarget("omega-net-geomap", "omega-ids-geomap",
              "IDS alerts - geographic origin",
              "GeoIP of Suricata alert sources. Private RFC1918 addresses do not "
              "geolocate and are absent by design.",
              None),
     {"x": 32, "y": 73, "w": 16, "h": 14}),
]

# --- splice the new panels into the dashboard -------------------------------
dash_doc = call("GET", "/.kibana/_doc/dashboard:omega-network-threat-map")["_source"]
dash = dash_doc["dashboard"]
panels = json.loads(dash["panelsJSON"])
refs = dash_doc["references"]

existing = {r["id"] for r in refs}
next_panel = max(int(p["panelIndex"]) for p in panels) + 1
next_ref = len(refs)

for vis_id, grid in new_panels:
    if vis_id in existing:
        print(f"skip (already on dashboard): {vis_id}")
        continue
    grid = dict(grid, i=str(next_panel))
    panels.append({
        "version": "2.13.0",
        "gridData": grid,
        "panelIndex": str(next_panel),
        "embeddableConfig": {},
        "panelRefName": f"panel_{next_ref}",
    })
    refs.append({"name": f"panel_{next_ref}", "type": "visualization", "id": vis_id})
    next_panel += 1
    next_ref += 1

dash["panelsJSON"] = json.dumps(panels)
dash["description"] = (
    "External firewall blocks (rule 100030) plus Suricata IDS alerts from OPNsense "
    "(rules 100200-100210), both GeoIP-enriched."
)
dash_doc["references"] = refs
dash_doc.pop("updated_at", None)
put_doc("dashboard:omega-network-threat-map", dash_doc)

print("panels on dashboard:", len(panels))
for r in refs:
    print(" ", r["name"], "->", r["id"])
