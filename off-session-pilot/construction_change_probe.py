#!/usr/bin/env python3
"""Bounded construction-change linkage probe, not an active collector.

Read four public Seoul Construction Notification listings once, capture only
the first five row/link diagnostics, and distinguish exact ID joins from title
similarity. One snapshot cannot establish a daily publishing cadence.
"""
import json
import re
from collections import Counter
from datetime import date
from urllib.parse import urlparse

from contract_route_probe import LISTS as CONTRACT_LISTS, first_entries, read_text
from probe_sources import Page, norm, sanitize

ORIGIN = "https://cis.seoul.go.kr"
CHANGE_LISTS = {
    "EXTENSION": ORIGIN + "/TotalAlimi_new/PicChgList.action",
    "DESIGN": ORIGIN + "/TotalAlimi_new/DocList.action",
    "PENALTY": ORIGIN + "/TotalAlimi_new/PenaltyList.action",
    "PROGRESS": ORIGIN + "/TotalAlimi_new/SmrizeBsnsNews.action",
}
MAX_ENTRIES = 5
DATE = re.compile(r"20\d{2}[-./]\d{1,2}[-./]\d{1,2}")
CALL = re.compile(r"^\s*([A-Za-z_$][\w$]{0,60})\s*\(")
QUOTED = re.compile(r"'([^']{1,100})'|\"([^\"]{1,100})\"")
PROJECT_ID = re.compile(r"(?:pjt_cd|pjtCd|projectId)\s*[=:]\s*['\"]?([A-Za-z0-9]{6,40})", re.I)

def safe_date(raw):
    try:
        return date.fromisoformat(raw.replace(".", "-").replace("/", "-"))
    except ValueError:
        return None

def registration_date(context):
    match = re.search(r"등록일\s*[:：]?\s*(20\d{2}[-./]\d{1,2}[-./]\d{1,2})", context)
    return match.group(1).replace(".", "-").replace("/", "-") if match else None

def describe_link(anchor):
    onclick = anchor.get("onclick", "")
    href = anchor.get("href", "")
    call = CALL.match(onclick)
    args = [a or b for a, b in QUOTED.findall(onclick)][:6]
    explicit = PROJECT_ID.findall(onclick + " " + href)
    # These are identifiers, not a proven cross-page join.
    return {
        "function": call.group(1) if call else None,
        "quoted_args": [sanitize(x)[:100] for x in args],
        "project_ids_named": explicit[:3],
        "href_path": urlparse(href).path[:150] if href and href != "#none" else None,
    }

def row_context(visible, title, next_title=""):
    at = visible.find(title)
    if at < 0:
        return ""
    stop = visible.find(next_title, at + len(title)) if next_title else -1
    if stop < 0 or stop - at > 550:
        stop = at + 550
    return visible[at:stop]

def list_anchors(html, sample_id):
    page = Page(html)
    # Navigation/footer links are excluded. Rows may have #none popup links.
    candidates = [a for a in page.anchors
                  if a["text"] and a["onclick"] and
                  ("cmdPopInfo" in a["onclick"] or
                   "PopInfo" in a["onclick"] or
                   "cmdPop" in a["onclick"])]
    if not candidates:
        candidates = [a for a in page.anchors
                      if a["text"] and a["onclick"] and len(a["text"]) >= 12]
    return candidates[:MAX_ENTRIES], page

def inspect_list(html, sample_id):
    anchors, page = list_anchors(html, sample_id)
    visible = sanitize(norm(" ".join(page.chunks)))
    items = []
    for index, anchor in enumerate(anchors):
        title = sanitize(anchor["text"])[:180]
        next_title = anchors[index + 1]["text"] if index + 1 < len(anchors) else ""
        context = row_context(visible, anchor["text"], next_title)
        items.append({
            "title": title,
            "link": describe_link(anchor),
            "registration_date": registration_date(context),
            "row_excerpt": sanitize(context)[:360],
        })
    dates = [item["registration_date"] for item in items if item["registration_date"]]
    return {
        "sample_id": sample_id,
        "items": items,
        "first_five_registration_dates": dict(Counter(dates)),
        "has_row_level_dates": bool(dates),
        "snapshot_cadence": "NOT_ESTABLISHED",
        "article_gate": "NOT_EVALUATED",
        "visible_characters": len(visible),
    }

def inspect_progress(html):
    page = Page(html)
    visible = sanitize(norm(" ".join(page.chunks)))
    # Progress cards are not contract list rows; retain bounded text
    # context around the first five "사업기간" labels, not a project-ID join.
    body = visible.split("# 주요사업진행현황", 1)[-1]
    snippets = []
    for match in list(re.finditer("사업기간", body))[:MAX_ENTRIES]:
        snippets.append(body[max(0, match.start() - 100):match.start() + 250])
    return {
        "sample_id": "PROGRESS",
        "first_five_card_excerpts": snippets,
        "registration_date_status": "NOT_OBSERVED",
        "snapshot_cadence": "NOT_ESTABLISHED",
        "article_gate": "NOT_EVALUATED",
        "visible_characters": len(visible),
    }

def exact_contract_join(change_items, contract_items):
    ids = {item["record_key"] for item in contract_items}
    matches = []
    for item in change_items:
        for project_id in item["link"]["project_ids_named"]:
            if project_id in ids:
                matches.append({"title": item["title"], "project_id": project_id})
    return {
        "exact_project_id_matches": matches,
        "title_only_join": "NOT_ACCEPTED",
        "scope": "FIRST_FIVE_PER_LIST_ONLY",
    }

def main():
    results = {}
    contract_items = []
    try:
        contract_items = first_entries(read_text(CONTRACT_LISTS["C_LIST"]))
    except Exception as exc:
        print("CHANGE_LINK " + json.dumps({
            "sample_id": "C_LIST_REFERENCE", "access": "FAILED",
            "error": sanitize(str(exc))[:150]}, ensure_ascii=False))
    for sample_id, url in CHANGE_LISTS.items():
        try:
            html = read_text(url)
            result = inspect_progress(html) if sample_id == "PROGRESS" else inspect_list(html, sample_id)
            result["access"] = "HTTP_TEXT_RECEIVED"
            if sample_id != "PROGRESS":
                result["contract_join"] = exact_contract_join(result["items"], contract_items)
            results[sample_id] = result
        except Exception as exc:
            result = {"sample_id": sample_id, "access": "FAILED",
                      "error": sanitize(str(exc))[:150],
                      "snapshot_cadence": "NOT_ESTABLISHED",
                      "article_gate": "NOT_EVALUATED"}
        print("CHANGE_LINK " + json.dumps(result, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
