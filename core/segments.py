"""Revenue (and operating income) broken down by business segment, product/service and region.

The SEC's company-facts API leaves out dimensional data like segments, so this module
downloads each 10-Q/10-K's XBRL instance, keeps only the handful of facts it needs, and
caches that small extract forever (filed documents never change).
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date, timedelta

from . import sec_client
from .fundamentals import FORMS, _d, quarterize
from .settings import CACHE_DIR

REVENUE_CONCEPTS = [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
]
OPINC_CONCEPTS = ["OperatingIncomeLoss"]
KEEP = set(REVENUE_CONCEPTS + OPINC_CONCEPTS)

AXES = {
    "us-gaap:StatementBusinessSegmentsAxis": "Segment",
    "srt:ProductOrServiceAxis": "Product / service",
    "srt:StatementGeographicalAxis": "Region",
}
SKIP_MEMBER = re.compile(r"Elimination|Intersegment|CorporateNonSegment|ReconcilingItem|Adjustment", re.I)

NS_X = "{http://www.xbrl.org/2003/instance}"
NS_D = "{http://xbrl.org/2006/xbrldi}"
NS_LINK = "{http://www.xbrl.org/2003/linkbase}"
NS_XL = "{http://www.w3.org/1999/xlink}"
EXTRACT_DIR = CACHE_DIR / "filings"


# ------------------------------------------------------------------ download + extract

def _filing_files(cik: int, accn: str) -> list[str]:
    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn.replace('-', '')}/index.json"
    items = sec_client.get_json(url).get("directory", {}).get("item", [])
    return [i["name"] for i in items]


def _pick_instance(names: list[str]) -> str | None:
    for n in names:
        if n.endswith("_htm.xml"):
            return n
    for n in names:
        low = n.lower()
        if low.endswith(".xml") and not re.search(r"_(cal|def|lab|pre)\.xml$", low) \
                and low not in ("filingsummary.xml", "metalinks.xml") and not low.startswith("r"):
            return n
    return None


def parse_instance(xml_bytes: bytes) -> list[dict]:
    """Facts for the concepts we care about, with their dimensions and period."""
    root = ET.fromstring(xml_bytes)
    ctx = {}
    for c in root.iter(NS_X + "context"):
        p = c.find(NS_X + "period")
        s, e = p.find(NS_X + "startDate"), p.find(NS_X + "endDate")
        if s is None or e is None:
            continue
        dims = sorted((m.get("dimension"), (m.text or "").strip()) for m in c.iter(NS_D + "explicitMember"))
        ctx[c.get("id")] = (s.text.strip(), e.text.strip(), dims)
    out = []
    for el in root:
        tag = el.tag.split("}")[-1]
        if tag not in KEEP:
            continue
        c = ctx.get(el.get("contextRef"))
        if not c or el.text is None:
            continue
        try:
            v = float(el.text.strip())
        except ValueError:
            continue
        out.append({"c": tag, "s": c[0], "e": c[1], "d": c[2], "v": v})
    return out


def parse_labels(xml_bytes: bytes) -> dict[str, str]:
    """{'nflx:UnitedStatesAndCanadaMember': 'United States and Canada'} from a label linkbase."""
    root = ET.fromstring(xml_bytes)
    labels = {}
    for link in root.iter(NS_LINK + "labelLink"):
        loc_to_concept, res = {}, defaultdict(dict)
        for loc in link.iter(NS_LINK + "loc"):
            frag = loc.get(NS_XL + "href", "").split("#")[-1]
            if "_" in frag:
                prefix, name = frag.split("_", 1)
                loc_to_concept[loc.get(NS_XL + "label")] = f"{prefix}:{name}"
        for lab in link.iter(NS_LINK + "label"):
            role = lab.get(NS_XL + "role", "").rsplit("/", 1)[-1]
            res[lab.get(NS_XL + "label")][role] = (lab.text or "").strip()
        for arc in link.iter(NS_LINK + "labelArc"):
            concept = loc_to_concept.get(arc.get(NS_XL + "from"))
            r = res.get(arc.get(NS_XL + "to"))
            if concept and r and concept.endswith("Member"):
                text = r.get("terseLabel") or r.get("label") or ""
                labels[concept] = re.sub(r"\s*\[Member\]$", "", text)
    return labels


def _extract(cik: int, accn: str, want_labels: bool) -> dict:
    """Cached extract of one filing: {'facts': [...], 'labels': {...}}."""
    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    path = EXTRACT_DIR / f"{cik}_{accn}.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("labels") is not None or not want_labels:
            return data
    names = _filing_files(cik, accn)
    inst = _pick_instance(names)
    data = {"facts": [], "labels": None}
    if inst:
        base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn.replace('-', '')}/"
        data["facts"] = parse_instance(sec_client.get_bytes(base + inst))
        if want_labels:
            lab = next((n for n in names if n.lower().endswith("_lab.xml")), None)
            data["labels"] = parse_labels(sec_client.get_bytes(base + lab)) if lab else {}
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


def filings_for(facts: dict, since: date) -> list[tuple[str, str]]:
    """(accession, filed) of 10-Q/10-K filings filed on/after `since`, oldest first."""
    seen = {}
    gaap = facts.get("facts", {}).get("us-gaap", {})
    for concept in REVENUE_CONCEPTS + ["NetIncomeLoss"]:
        for unit_rows in gaap.get(concept, {}).get("units", {}).values():
            for r in unit_rows:
                if r.get("form") in FORMS and _d(r["filed"]) >= since:
                    seen[r["accn"]] = r["filed"]
    return sorted(seen.items(), key=lambda kv: kv[1])


# ------------------------------------------------------------------ assemble breakdowns

def _pretty_member(member: str, labels: dict) -> str:
    if member in labels and labels[member]:
        return labels[member]
    name = member.split(":")[-1]
    name = re.sub(r"(Segment)?Member$", "", name)
    words = re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+", name)
    return " ".join(words) or name


def build_breakdowns(cik: int, facts: dict, quarter_ends: list[date], progress=None) -> dict:
    """{'revenue': {'Segment': {end: [(label, value), ...]}, ...}, 'operating_income': {...}}"""
    if not quarter_ends:
        return {}
    since = min(quarter_ends) - timedelta(days=130)  # reaches back to the Q3 10-Q needed for a first Q4
    filings = filings_for(facts, since)
    extracts, labels = [], {}
    for i, (accn, filed) in enumerate(filings):
        if progress:
            progress(i / max(len(filings), 1), f"Reading segment data from filings ({i + 1}/{len(filings)})")
        try:
            ex = _extract(cik, accn, want_labels=(i == len(filings) - 1))
        except sec_client.SecError:
            continue
        extracts.append((filed, ex))
        labels.update(ex.get("labels") or {})
    if progress:
        progress(1.0, "Done")
    return assemble(extracts, labels, quarter_ends)


def assemble(extracts: list[tuple[str, dict]], labels: dict, quarter_ends: list[date]) -> dict:
    # (concept, axis, other_dims) -> member -> {(start, end): value}; later filings override earlier ones
    series = defaultdict(lambda: defaultdict(dict))
    totals = defaultdict(dict)  # concept -> {(start, end): value}
    for filed, ex in sorted(extracts, key=lambda x: x[0]):
        for f in ex["facts"]:
            key = (_d(f["s"]), _d(f["e"]))
            dims = [tuple(x) for x in f["d"]]
            if not dims:
                totals[f["c"]][key] = f["v"]
                continue
            for i, (axis, member) in enumerate(dims):
                if axis not in AXES or SKIP_MEMBER.search(member):
                    continue
                others = tuple(d for j, d in enumerate(dims) if j != i)
                if any(a in AXES and a != "srt:ProductOrServiceAxis" for a, _ in others):
                    continue  # cross-tabs (e.g. segment x region) are too granular
                series[(f["c"], axis, others)][member][key] = f["v"]

    result = {}
    for metric, concepts in (("revenue", REVENUE_CONCEPTS), ("operating_income", OPINC_CONCEPTS)):
        by_axis = {}
        for axis, axis_name in AXES.items():
            if metric == "operating_income" and axis_name != "Segment":
                continue
            best = None
            for (concept, ax, others), members in series.items():
                if ax != axis or concept not in concepts:
                    continue
                q_members = {m: {e: v for e, (v, _) in quarterize(p).items()} for m, p in members.items()}
                q_total = {e: v for e, (v, _) in quarterize(totals.get(concept, {})).items()}
                table, cover = {}, []
                for qe in quarter_ends:
                    rows = [(m, vals[qe]) for m, vals in q_members.items() if qe in vals and vals[qe] != 0]
                    tot = q_total.get(qe)
                    if len(rows) < 2:
                        continue
                    rows = _drop_aggregates(rows, tot) if metric == "revenue" else rows
                    s = sum(v for _, v in rows)
                    if metric == "revenue" and tot:
                        cover.append(s / tot)
                    table[qe] = sorted(((_pretty_member(m, labels), v) for m, v in rows), key=lambda x: -x[1])
                if not table:
                    continue
                if metric == "revenue":
                    good = [c for c in cover if 0.9 <= c <= 1.1]
                    if not good:
                        continue
                    score = (len(table), -abs(1 - sum(good) / len(good)))
                else:
                    score = (len(table), 0)
                if best is None or score > best[0]:
                    best = (score, table)
            if best:
                by_axis[axis_name] = best[1]
        if by_axis:
            result[metric] = by_axis
    return result


def _drop_aggregates(rows, total):
    """Remove subtotal members (e.g. Apple's 'Products' alongside iPhone/Mac/iPad) that double count."""
    rows = list(rows)
    if not total:
        return rows
    for _ in range(3):
        excess = sum(v for _, v in rows) - total
        if excess <= total * 0.03:
            break
        cand = min(rows, key=lambda r: abs(r[1] - excess))
        if abs(cand[1] - excess) <= max(total * 0.02, 1):
            rows.remove(cand)
        else:
            break
    return rows
