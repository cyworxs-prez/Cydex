#!/usr/bin/env python3
"""
sigma2wazuh.py - Convert SigmaHQ Zeek rules into Wazuh local rules (XML).

Design principles:
  * FAITHFUL OR SKIP. Any Sigma construct that cannot be expressed exactly in a
    Wazuh rule (negation, cross-field OR beyond a small fan-out, aggregations)
    is SKIPPED and reported -- never silently approximated.
  * Sigma's Zeek field names are CIM-style aliases (c-uri, c-useragent...).
    They are mapped to the real Zeek JSON keys. Any field we cannot map, or
    that contains a dot (Zeek writes literal dotted keys like "id.orig_h",
    which Wazuh's JSON decoder reads as a nested path), causes a skip.
  * Multiple <field> elements in a Wazuh rule are ANDed. A list of values on
    one field is ORed via regex alternation. |all on one field uses PCRE2
    lookaheads. Cross-field OR is expanded into sibling rules (bounded).

Usage: sigma2wazuh.py <sigma_rules_dir> <out.xml> [start_id]
"""
import os, re, sys, glob, yaml

# Sigma Zeek alias -> real Zeek JSON key (dot-free keys only).
FIELD_MAP = {
    "query": "query", "qtype_name": "qtype_name", "answers": "answers",
    "rcode_name": "rcode_name", "Z": "Z", "rejected": "rejected",
    "c-uri": "uri", "uri": "uri",
    "c-useragent": "user_agent", "user_agent": "user_agent",
    "c-host": "host", "host": "host", "method": "method",
    "status_code": "status_code", "resp_mime_types": "resp_mime_types",
    "orig_mime_types": "orig_mime_types",
    "server_name": "server_name", "validation_status": "validation_status",
    "issuer": "issuer", "subject": "subject",
    "certificate.issuer": None, "certificate.subject": None,  # dotted -> skip
    "id.orig_h": None, "id.resp_h": None, "id.resp_p": None, "id.orig_p": None,
}

# Sigma logsource service -> (zeek log file, base rule suffix)
SERVICE_LOG = {
    "dns": "dns.log", "http": "http.log", "x509": "x509.log",
    "ssl": "ssl.log", "conn": "conn.log", "dhcp": "dhcp.log",
    "software": "software.log", "ssh": "ssh.log",
}

LEVEL_MAP = {"critical": 13, "high": 10, "medium": 7, "low": 5, "informational": 3}


def esc(v):
    """Escape a literal for use inside a PCRE2 pattern."""
    return re.escape(str(v))


def build_pattern(modifiers, values):
    """Return a PCRE2 pattern for one field given Sigma modifiers + value(s)."""
    if not isinstance(values, list):
        values = [values]
    vals = [esc(v) for v in values]

    if "all" in modifiers:
        # every value must be present (order-independent) -> lookaheads
        if "contains" in modifiers or not (set(modifiers) & {"startswith", "endswith"}):
            return "(?i)" + "".join(f"(?=.*{v})" for v in vals)
        return None  # all+startswith/endswith is not meaningfully expressible

    if "contains" in modifiers:
        body = "|".join(vals)
        return f"(?i)(?:{body})"
    if "endswith" in modifiers:
        body = "|".join(vals)
        return f"(?i)(?:{body})$"
    if "startswith" in modifiers:
        body = "|".join(vals)
        return f"(?i)^(?:{body})"
    if "re" in modifiers:
        if len(values) != 1:
            return None
        return str(values[0])
    # plain equality
    body = "|".join(vals)
    return f"(?i)^(?:{body})$"


def convert_map(sel_map):
    """One Sigma selection map -> list of (field, pattern) ANDed. None if unsupported."""
    out = []
    for key, values in sel_map.items():
        parts = key.split("|")
        raw_field, modifiers = parts[0], [m.lower() for m in parts[1:]]
        if any(m not in ("contains", "endswith", "startswith", "all", "re") for m in modifiers):
            return None  # unknown modifier (base64, cidr, windash...) -> skip
        if raw_field not in FIELD_MAP or FIELD_MAP[raw_field] is None:
            return None  # unmappable or dotted field -> skip
        field = FIELD_MAP[raw_field]
        if values is None:
            return None
        pat = build_pattern(modifiers, values)
        if pat is None:
            return None
        out.append((field, pat))
    return out or None


def expand_selection(sel):
    """A selection is a map (AND) or list of maps (OR).
    Returns list of OR-branches; each branch is a list of (field, pattern)."""
    if isinstance(sel, dict):
        c = convert_map(sel)
        return [c] if c else None
    if isinstance(sel, list):
        branches = []
        for item in sel:
            if not isinstance(item, dict):
                return None
            c = convert_map(item)
            if not c:
                return None
            branches.append(c)
        return branches or None
    return None


def _resolve_names(token, detection):
    """Resolve a condition token into ALTERNATIVES: a list of AND-groups.
    The term is satisfied if ANY alternative matches (each alternative is a
    list of selection names that must ALL match).
      'name'        -> [[name]]
      '1 of pat*'   -> [[a],[b],[c]]   (OR  - any one)
      'all of pat*' -> [[a,b,c]]       (AND - every one)
      '(a or b)'    -> [[a],[b]]
    """
    t = token.strip()
    m = re.fullmatch(r"\((.*)\)", t, re.S)
    if m:
        inner = m.group(1)
        if re.search(r"\band\b", inner, re.I):
            return None  # AND inside a group -> not decomposable here
        names = [n.strip() for n in re.split(r"\s+or\s+", inner, flags=re.I) if n.strip()]
        if not names or not all(n in detection for n in names):
            return None
        return [[n] for n in names]
    m = re.fullmatch(r"(1|all) of (\S+)", t, re.I)
    if m:
        quant, pat = m.group(1).lower(), m.group(2).replace("*", ".*")
        names = [k for k in detection if k != "condition" and re.fullmatch(pat, k)]
        if not names:
            return None
        return [names] if quant == "all" else [[n] for n in names]
    if re.fullmatch(r"[\w]+", t) and t in detection:
        return [[t]]
    return None


def parse_condition(cond, detection):
    """Return (positive_names, negative_names) or None if not expressible.

    Positive terms are ANDed. Negative terms are ANDed as negations, which is
    exact for `not (a or b)` / `not 1 of x*` since !(a|b) == !a & !b.
    `all of x*` inside a NOT would be !(a&b) == !a|!b -> rejected.
    """
    if not isinstance(cond, str):
        return None
    c = " ".join(cond.split())
    if "|" in c:
        return None  # aggregation
    # split on top-level ' and ' (parentheses only ever wrap OR groups here)
    terms, depth, buf = [], 0, ""
    for tok in re.split(r"(\s+and\s+|\(|\))", c, flags=re.I):
        if tok is None or tok == "":
            continue
        if tok == "(":
            depth += 1; buf += tok
        elif tok == ")":
            depth -= 1; buf += tok
        elif re.fullmatch(r"\s+and\s+", tok, re.I) and depth == 0:
            terms.append(buf.strip()); buf = ""
        else:
            buf += tok
    if buf.strip():
        terms.append(buf.strip())
    if not terms:
        return None

    pos_terms, neg = [], []
    for t in terms:
        m = re.match(r"^not\s+(.*)$", t, re.I)
        negated = bool(m)
        body = m.group(1) if m else t
        if negated and re.match(r"^all of ", body, re.I):
            return None  # !(a&b) is an OR of negations -> not expressible
        alts = _resolve_names(body, detection)
        if not alts:
            return None
        if negated:
            # !(any alternative) == none may match; each alternative must be a
            # single selection so it reduces to an AND of negated fields.
            if any(len(a) != 1 for a in alts):
                return None
            neg.extend(a[0] for a in alts)
        else:
            pos_terms.append(alts)
    if not pos_terms:
        return None  # a pure-negative rule would match nearly everything
    return pos_terms, neg


def merge_same_field(fields):
    """Wazuh ANDs <field> elements, but two <field> tags with the SAME name are
    ambiguous. Merge them into one pattern using lookaheads so the AND is exact."""
    order, by_field = [], {}
    for fname, pat in fields:
        if fname not in by_field:
            by_field[fname] = []; order.append(fname)
        by_field[fname].append(pat)
    out = []
    for fname in order:
        pats = by_field[fname]
        if len(pats) == 1:
            out.append((fname, pats[0])); continue
        looks = []
        for p in pats:
            body = p[4:] if p.startswith("(?i)") else p
            looks.append(f"(?={body})" if body.startswith("^") else f"(?=.*{body})")
        out.append((fname, "(?i)" + "".join(looks)))
    return out


def negated_fields(names, detection):
    """Negated selections must each reduce to exactly ONE field, because
    !(f1 & f2) is an OR of negations and cannot be one Wazuh rule."""
    out = []
    for n in names:
        branches = expand_selection(detection.get(n))
        if not branches or len(branches) != 1 or len(branches[0]) != 1:
            return None
        out.append(branches[0][0])
    return out


def mitre_ids(tags):
    ids = []
    for t in tags or []:
        m = re.fullmatch(r"attack\.(t\d{4}(?:\.\d{3})?)", str(t), re.I)
        if m:
            ids.append(m.group(1).upper())
    return sorted(set(ids))


def xml_escape(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def main():
    src, out_path = sys.argv[1], sys.argv[2]
    next_id = int(sys.argv[3]) if len(sys.argv) > 3 else 100800

    files = sorted(glob.glob(os.path.join(src, "*.yml")))
    services_used, rules_xml, converted, skipped = {}, [], [], []

    # first pass: parse and convert
    parsed = []
    for path in files:
        try:
            doc = yaml.safe_load(open(path))
        except Exception as e:
            skipped.append((os.path.basename(path), f"yaml error: {e}")); continue
        if not isinstance(doc, dict):
            skipped.append((os.path.basename(path), "not a sigma rule")); continue
        name = os.path.basename(path)
        ls = doc.get("logsource", {}) or {}
        svc = ls.get("service")
        if svc not in SERVICE_LOG:
            skipped.append((name, f"logsource service '{svc}' not collected here")); continue
        det = doc.get("detection", {}) or {}
        parsed_cond = parse_condition(det.get("condition"), det)
        if not parsed_cond:
            skipped.append((name, f"condition not expressible: {det.get('condition')!r}")); continue
        sel_names, neg_names = parsed_cond

        neg_fields = negated_fields(neg_names, det)
        if neg_fields is None:
            skipped.append((name, "negated selection spans multiple fields (OR of negations)")); continue

        # Each positive term is a set of alternatives (OR). Each alternative is
        # a set of selections (AND). Each selection may itself fan out (OR).
        # Overall = AND across terms -> cartesian product of all OR-branches.
        combos = [[]]
        bad = None
        for alts in sel_names:
            term_branches = []
            for alt in alts:                     # alternative = AND of selections
                alt_combos = [[]]
                for sn in alt:
                    branches = expand_selection(det.get(sn))
                    if not branches:
                        bad = f"selection '{sn}' uses unmappable field/modifier"; break
                    alt_combos = [c + b for c in alt_combos for b in branches]
                if bad:
                    break
                term_branches.extend(alt_combos)
            if bad:
                break
            combos = [c + b for c in combos for b in term_branches]
            if len(combos) > 8:
                bad = "cross-field OR fan-out too large (>8 sibling rules)"; break
        if bad:
            skipped.append((name, bad)); continue
        combos = [merge_same_field(c) for c in combos]
        if any(c is None for c in combos):
            skipped.append((name, "conflicting anchored patterns on one field")); continue

        parsed.append((name, doc, svc, combos, neg_fields))
        services_used.setdefault(svc, None)

    # allocate base rules (one per zeek log we actually reference)
    base_ids = {}
    for svc in sorted(services_used):
        base_ids[svc] = next_id
        rules_xml.append(
            f'  <rule id="{next_id}" level="0">\n'
            f'    <decoded_as>json</decoded_as>\n'
            f'    <location>/opt/zeek/logs/current/{SERVICE_LOG[svc]}</location>\n'
            f'    <description>Zeek {svc}.log (base for Sigma-converted rules)</description>\n'
            f'    <group>zeek,sigma,</group>\n'
            f'  </rule>')
        next_id += 1

    # emit converted rules
    for name, doc, svc, combos, neg_fields in parsed:
        title = doc.get("title", name)
        level = LEVEL_MAP.get(str(doc.get("level", "medium")).lower(), 7)
        mids = mitre_ids(doc.get("tags"))
        sid = doc.get("id", "")
        for i, fields in enumerate(combos):
            suffix = f" ({i+1}/{len(combos)})" if len(combos) > 1 else ""
            body = [f'  <rule id="{next_id}" level="{level}">',
                    f'    <if_sid>{base_ids[svc]}</if_sid>']
            for fname, pat in fields:
                body.append(f'    <field name="{fname}" type="pcre2">{xml_escape(pat)}</field>')
            for fname, pat in neg_fields:
                body.append(f'    <field name="{fname}" negate="yes" type="pcre2">{xml_escape(pat)}</field>')
            body.append(f'    <description>Sigma: {xml_escape(title)}{suffix}</description>')
            if mids:
                body.append("    <mitre>" + "".join(f"<id>{m}</id>" for m in mids) + "</mitre>")
            body.append(f'    <group>zeek,sigma,{svc},</group>')
            if sid:
                body.append(f'    <!-- sigma-id: {xml_escape(sid)} src: {xml_escape(name)} -->')
            body.append("  </rule>")
            rules_xml.append("\n".join(body))
            next_id += 1
        converted.append((name, len(combos)))

    with open(out_path, "w") as fh:
        fh.write('<!-- Auto-generated from SigmaHQ by sigma2wazuh.py. Do not hand-edit. -->\n')
        fh.write('<group name="sigma,zeek,">\n')
        fh.write("\n".join(rules_xml))
        fh.write("\n</group>\n")

    print(f"CONVERTED {len(converted)} sigma rules -> {sum(c for _, c in converted)} wazuh rules")
    for n, c in converted:
        print(f"  [ok]   {n}" + (f"  ({c} sibling rules)" if c > 1 else ""))
    print(f"\nSKIPPED {len(skipped)} (not silently approximated):")
    for n, why in skipped:
        print(f"  [skip] {n}: {why}")


if __name__ == "__main__":
    main()
