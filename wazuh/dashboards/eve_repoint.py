#!/usr/bin/env python3
"""
Now that the OPNsense agent ships Suricata EVE JSON (rule 86601), move the IDS
dashboard panels off the flat syslog fields and onto the richer EVE fields, and
teach the ingest pipelines to GeoIP the EVE source address.

  syslog (rules 100200-100210)   ->  EVE (rule 86601)
  data.srcip                     ->  data.src_ip
  data.signature                 ->  data.alert.signature
  data.classification            ->  data.alert.category

The syslog decoder/rules stay installed as a dormant fallback: if the agent ever
stops reporting, those alerts still land, they just no longer feed these panels.
"""
import json
import ssl
import urllib.request

BASE = "https://127.0.0.1:9200"
CERTS = "/etc/wazuh-indexer/certs"
EVE_QUERY = "rule.groups:suricata and data.event_type:alert"
GEO_PROPS = ["city_name", "country_name", "region_name", "location"]

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


# --- 1. GeoIP the EVE source address ---------------------------------------
pipelines = call("GET", "/_ingest/pipeline")
for name, body in pipelines.items():
    if "wazuh" not in name:
        continue
    procs = body["processors"]
    if any(p.get("geoip", {}).get("field") == "data.src_ip" for p in procs):
        print(f"geoip ok    {name}")
        continue
    idx = next(i for i, p in enumerate(procs)
               if p.get("geoip", {}).get("field") == "data.srcip")
    procs.insert(idx + 1, {"geoip": {
        "field": "data.src_ip", "target_field": "GeoLocation",
        "properties": GEO_PROPS, "ignore_missing": True, "ignore_failure": True,
    }})
    call("PUT", f"/_ingest/pipeline/{name}", body)
    print(f"geoip ADDED {name}")


# --- 2. Repoint the IDS visualizations --------------------------------------
FIELD_SWAP = {
    "omega-ids-signatures": "data.alert.signature",
    "omega-ids-sources": "data.src_ip",
    "omega-ids-classification": "data.alert.category",
}

for vid in ["omega-ids-timeline", "omega-ids-signatures", "omega-ids-sources",
            "omega-ids-classification", "omega-ids-geomap"]:
    doc = call("GET", f"/.kibana/_doc/visualization:{vid}")["_source"]
    vis = doc["visualization"]

    state = json.loads(vis["visState"])
    if vid in FIELD_SWAP:
        for agg in state["aggs"]:
            if agg["type"] == "terms":
                agg["params"]["field"] = FIELD_SWAP[vid]
    vis["visState"] = json.dumps(state)

    search = json.loads(vis["kibanaSavedObjectMeta"]["searchSourceJSON"])
    search["query"] = {"query": EVE_QUERY, "language": "kuery"}
    vis["kibanaSavedObjectMeta"]["searchSourceJSON"] = json.dumps(search)

    doc.pop("updated_at", None)
    call("PUT", f"/.kibana/_doc/visualization:{vid}?refresh=wait_for", doc)
    print(f"repointed   {vid} -> {FIELD_SWAP.get(vid, '(query only)')}")
