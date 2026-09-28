#!/usr/bin/env python3
"""Bounded National Assembly Library local-council minutes API adapter.

The authentication key is supplied by callers and never persisted.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from urllib.parse import parse_qsl, urlencode, urlparse
from urllib.request import Request, urlopen

from collect_pilot import Page, review_windows, transcript


ENDPOINT = "https://clik.nanet.go.kr/openapi/minutes.do"
PUBLIC_VIEW = "https://clik.nanet.go.kr/potal/search/searchView.do"
USER_AGENT = (
    "Mozilla/5.0 (compatible; NewsItemRadarPilot/1.0; "
    "+https://github.com/onetym77-bit/news-item-radar)"
)
MAX_RESPONSE_BYTES = 6_000_000
DOCID = re.compile(r"CLIKC[0-9]+")
ASSEMBLY_ID = re.compile(r"0020(?:0[2-9]|1[0-9]|2[0-6])")


class ClikAPIError(ValueError):
    """A bounded, non-secret-bearing API failure."""


def _unwrap(value):
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        raise ClikAPIError("Unexpected CLIK response envelope")
    payload = value[0]
    if payload.get("RESULT_CODE") != "SUCCESS":
        code = str(payload.get("RESULT_CODE") or "UNKNOWN")
        raise ClikAPIError(f"CLIK API returned {code}")
    return payload


def fetch_payload(api_key, **params):
    if not api_key:
        raise ClikAPIError("CLIK_API_KEY is required")
    query = {"key": api_key, "type": "json", **params}
    request = Request(
        ENDPOINT + "?" + urlencode(query),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except OSError as exc:
        raise ClikAPIError("CLIK API request failed") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ClikAPIError("CLIK API response exceeds byte limit")
    try:
        return _unwrap(json.loads(raw.decode("utf-8-sig")))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ClikAPIError("CLIK API returned invalid JSON") from exc


def public_document_url(docid):
    if not DOCID.fullmatch(str(docid or "")):
        raise ClikAPIError("Invalid CLIK document identifier")
    return PUBLIC_VIEW + "?" + urlencode({"DOCID": docid, "collection": "minutes"})


def record_key(url):
    """Match the stable public-URL identity used by the council watcher."""
    parsed = urlparse(url)
    identity = parsed.path + "?" + urlencode(sorted(parse_qsl(parsed.query)))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def portal_is_stale(portal_rows, official_rows):
    """Return true only when an official council page proves a later meeting."""
    portal_dates = [row.get("meeting_date", "") for row in portal_rows]
    official_dates = [row.get("meeting_date", "") for row in official_rows]
    portal_latest = max((value for value in portal_dates if value), default="")
    official_latest = max((value for value in official_dates if value), default="")
    return bool(portal_latest and official_latest and official_latest > portal_latest)


def _meeting_date(value):
    text = str(value or "")
    if not re.fullmatch(r"20[0-9]{6}", text):
        return ""
    try:
        return date(int(text[:4]), int(text[4:6]), int(text[6:])).isoformat()
    except ValueError:
        return ""


def _validate_source(source):
    assembly_id = str(source.get("clik_assembly_id") or "")
    if not ASSEMBLY_ID.fullmatch(assembly_id):
        raise ClikAPIError("Missing or invalid Seoul district assembly ID")
    return assembly_id


def list_minutes(source, api_key, limit=20):
    assembly_id = _validate_source(source)
    if not 1 <= limit <= 100:
        raise ClikAPIError("CLIK list limit outside documented range")
    payload = fetch_payload(
        api_key,
        displayType="list",
        startCount=0,
        listCount=limit,
        searchType="ALL",
        rasmblyId=assembly_id,
        sort="MTG_DE/DESC",
    )
    entries = payload.get("LIST") or []
    if not isinstance(entries, list):
        raise ClikAPIError("CLIK list rows are not an array")
    records = []
    seen = set()
    for entry in entries:
        row = entry.get("ROW") if isinstance(entry, dict) else None
        if not isinstance(row, dict):
            raise ClikAPIError("CLIK list row schema is invalid")
        docid = str(row.get("DOCID") or "")
        if not DOCID.fullmatch(docid) or row.get("RASMBLY_ID") != assembly_id:
            raise ClikAPIError("CLIK list row identity mismatch")
        if docid in seen:
            continue
        seen.add(docid)
        meeting_date = _meeting_date(row.get("MTG_DE"))
        if not meeting_date:
            raise ClikAPIError("CLIK list row has invalid meeting date")
        records.append({
            "docid": docid,
            "url": public_document_url(docid),
            "meeting_date": meeting_date,
            "label": (
                f"제{row.get('RASMBLY_NUMPR') or ''}대 "
                f"제{row.get('RASMBLY_SESN') or ''}회 "
                f"{row.get('MTGNM') or '회의록'} 제{row.get('MINTS_ODR') or '0'}차"
            ),
        })
    total = payload.get("TOTAL_COUNT")
    try:
        total = int(total)
    except (TypeError, ValueError):
        total = len(records)
    return records, total


def detail_minutes(source, docid, api_key):
    assembly_id = _validate_source(source)
    if not DOCID.fullmatch(str(docid or "")):
        raise ClikAPIError("Invalid CLIK document identifier")
    payload = fetch_payload(api_key, displayType="detail", docid=docid)
    if payload.get("DOCID") != docid or payload.get("RASMBLY_ID") != assembly_id:
        raise ClikAPIError("CLIK detail identity mismatch")
    meeting_date = _meeting_date(payload.get("MTG_DE"))
    if not meeting_date:
        raise ClikAPIError("CLIK detail has invalid meeting date")
    html = payload.get("MINTS_HTML")
    if not isinstance(html, str):
        raise ClikAPIError("CLIK detail body is missing")
    return {
        "docid": docid,
        "meeting_date": meeting_date,
        "html": html,
        "original_file_url": str(payload.get("ORGINL_FILE_URL") or ""),
        "meeting_name": str(payload.get("MTGNM") or ""),
    }


def observation(source, api_key, limit=20):
    rows, total = list_minutes(source, api_key, limit)
    if not rows:
        raise ClikAPIError("CLIK list returned no recent rows")
    return {
        "id": source["id"], "name": source["name"], "status": "OBSERVED",
        "listed": total,
        "records": [{
            "key": record_key(row["url"]),
            "document_id": row["docid"], "url": row["url"],
            "meeting_date": row["meeting_date"],
        } for row in rows],
        "transport": "CLIK_OPEN_API", "api_fallback_reason": "",
    }


def probe_source(source, as_of, api_key):
    rows, _ = list_minutes(source, api_key, 1)
    if not rows:
        return {
            "listing_ok": True, "selected": [], "diagnosis": "EMPTY_API_WINDOW",
            "requests": [{"transport": "CLIK_OPEN_API", "operation": "list", "status": 200}],
            "transport": "CLIK_OPEN_API",
        }
    listed = rows[0]
    detail = detail_minutes(source, listed["docid"], api_key)
    page = Page(detail["html"])
    body, parts = transcript(page)
    same_date = detail["meeting_date"] == listed["meeting_date"]
    body_ok = bool(body)
    future = date.fromisoformat(listed["meeting_date"]) > as_of
    if future:
        diagnosis = "FUTURE_MEETING"
    elif not body_ok:
        diagnosis = "BODY_UNAVAILABLE"
    elif not same_date:
        diagnosis = "METADATA_CONFLICT"
    else:
        diagnosis = "BODY_OK"
    selected = [{
        "url": listed["url"], "document_id": listed["docid"],
        "meeting_date": listed["meeting_date"], "provisional": False,
        "body_ok": body_ok, "body_characters": len(body),
        "speech_turns": len(parts),
        "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest() if body else "",
        "metadata_check": "MATCH" if same_date else "CONFLICT",
        "date_crosschecked": same_date, "identity_conflict": False,
        "diagnosis": diagnosis,
        "review_windows": review_windows(parts) if body_ok else [],
    }]
    return {
        "listing_ok": True, "selected": selected, "diagnosis": diagnosis,
        "requests": [
            {"transport": "CLIK_OPEN_API", "operation": "list", "status": 200},
            {"transport": "CLIK_OPEN_API", "operation": "detail", "status": 200},
        ],
        "transport": "CLIK_OPEN_API",
    }


def fetch_document_context(row, source, api_key):
    detail = detail_minutes(source, row.get("document_id"), api_key)
    page = Page(detail["html"])
    body, parts = transcript(page)
    if not body:
        return {"status": "BODY_UNAVAILABLE", "body": "", "parts": [],
                "request_status": 200}
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if detail["meeting_date"] != row.get("meeting_date"):
        status = "DATE_CONFLICT"
    elif digest != row.get("body_sha256"):
        status = "BODY_CHANGED"
    else:
        status = "BODY_READ"
    return {
        "status": status, "body": body, "parts": parts,
        "request_status": 200, "body_sha256": digest,
        "title_date": detail["meeting_date"],
    }

