#!/usr/bin/env python3
"""Read-only district council pilot. No editorial ledger transitions."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import time
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse, parse_qsl, urlencode, urlunparse
from urllib.request import Request, urlopen

BASE = Path(__file__).resolve().parent
KST = timezone(timedelta(hours=9))
DATE = re.compile(r"(?<!\d)(20\d{2})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})")
DETAIL = re.compile(r"/(?:viewer/minutes\.do|record/recordView\.do|record/main)(?:\?|$)", re.I)
ERROR_BODY = re.compile(r"행을 찾을 수 없|존재하지 않는 회의록|등록된 회의록이 없")
TOPICS = {
    "주거": ("주택", "전세", "재개발", "재건축", "공가", "임대"),
    "돌봄": ("돌봄", "급식", "밥상", "요양", "어린이집", "장애", "보건"),
    "교통": ("교통", "버스", "주차", "보행", "통학"),
    "생활시설": ("도서관", "체육", "주민자치", "공간", "시설"),
    "안전환경": ("침수", "하수", "폭염", "쓰레기", "악취", "안전"),
    "노동경제": ("노동", "상권", "소상공인", "임금", "일자리"),
}
SIGNALS = ("격차", "부족", "불편", "증가", "감소", "배제", "미달", "지연",
           "이용률", "집행률", "불용", "대기", "부담", "편중")
NUMBER = re.compile(r"\d[\d,.]*\s*(?:%|명|건|원|억|만|곳|대|개)")
UA = "Mozilla/5.0 (compatible; NewsItemRadarPilot/1.0; +https://github.com/onetym77-bit/news-item-radar)"

def norm(text):
    return re.sub(r"\s+", " ", text).strip()

def clean_diagnostic(text):
    return re.sub(r";jsessionid=[A-Za-z0-9]+", ";jsessionid=[REDACTED]", text, flags=re.I)

def day(text):
    m = DATE.search(text)
    if not m:
        return ""
    try:
        return date(*map(int, m.groups())).isoformat()
    except ValueError:
        return ""

class Page(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.in_script = False
        self.script_sources = []
        self.script_text = []
        self.raw_html = html
        self.chunks = []
        self.rows = []
        self.row = None
        self.links = []
        self.anchors = []
        self.anchor = None
        self.speeches = []
        self.speech_chunks = None
        self.speech_depth = 0
        self.frames = []
        self.title = []
        self.in_title = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.in_script = True
            self.script_sources.extend(v for k,v in attrs if k == "src" and v)
        if tag in {"script", "style", "noscript"}:
            self.skip += 1
        if self.skip:
            return
        if tag == "div":
            if self.speech_chunks is not None:
                self.speech_depth += 1
            elif "speaker_area" in dict(attrs).get("class","").split():
                self.speech_chunks = []
                self.speech_depth = 1
        if tag == "a":
            self.anchor = {"attrs":list(attrs), "chunks":[]}
        if tag == "title":
            self.in_title = True
        if tag == "tr":
            self.row = {"chunks": [], "attrs": []}
        for key, value in attrs:
            if value and key in {"href", "src", "onclick", "data-uid"}:
                if self.row is not None:
                    self.row["attrs"].append([key, value])
                if key in {"href", "src"}:
                    self.links.append(value)
                if key == "src" and tag in {"iframe", "frame"}:
                    self.frames.append(value)

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_script = False
        if tag in {"script", "style", "noscript"}:
            self.skip = max(0, self.skip - 1)
        if self.skip:
            return
        if tag == "div" and self.speech_chunks is not None:
            self.speech_depth -= 1
            if self.speech_depth == 0:
                self.speeches.append(norm(" ".join(self.speech_chunks)))
                self.speech_chunks = None
        if tag == "a" and self.anchor is not None:
            self.anchors.append(self.anchor)
            self.anchor = None
        if tag == "title":
            self.in_title = False
        if tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None

    def handle_data(self, text):
        if self.in_script:
            self.script_text.append(text)
        if self.skip or not norm(text):
            return
        text = norm(text)
        self.chunks.append(text)
        if self.speech_chunks is not None:
            self.speech_chunks.append(text)
        if self.anchor is not None:
            self.anchor['chunks'].append(text)
        if self.row is not None:
            self.row["chunks"].append(text)
        if self.in_title:
            self.title.append(text)

def allowed(url, source):
    u = urlparse(url)
    return u.scheme == "https" and u.hostname in source["hosts"]

def canonical(url, source=None):
    u = urlparse(url)
    keys = (source or {}).get("id_params", ["uid", "key"])
    ids = [(k, v) for k, v in parse_qsl(u.query) if k in keys]
    return urlunparse(u._replace(query=urlencode(ids), fragment=""))

def detail_from(attrs, base, source):
    for key, value in attrs:
        if source.get("popup_adapter") and key in {"onclick","href"}:
            match = re.search(r"fn_popup_page\(\s*'(\d+)'\s*,\s*'(\d+)'\s*,\s*'(\d+)'\s*,\s*'(\d+)'\s*,\s*'[^']*'\s*,\s*'[^']*'\s*,\s*'([01])'\s*,\s*1\s*\)",value)
            if match:
                params=dict(zip(("ntime","contype","subtype","num","istemp"),match.groups()))
                return urljoin(base,"/meeting/confer/popup.do")+"?"+urlencode(params)
        if key == "data-uid" and source.get("uid_path") and value.isdigit():
            url = urljoin(base, source["uid_path"]) + "?uid=" + value
            if allowed(url, source):
                return canonical(url, source)
        candidates = [value] if key in {"href", "src"} else re.findall(r"""['"]([^'"]+)['"]""", value)
        for candidate in candidates:
            url = urljoin(base, candidate)
            pattern = source.get("detail_pattern")
            is_detail = bool(re.search(pattern,url)) if pattern else bool(DETAIL.search(url))
            if allowed(url, source) and is_detail and (source.get("path_identity") or any(k in source.get("id_params",["key","uid"]) for k, _ in parse_qsl(urlparse(url).query))):
                return canonical(url, source)
    return ""

def select_rows(page, base, source, count=4):
    rows, seen = [], set()
    source_rows = page.anchors if source.get("anchor_rows") else page.rows
    for r in source_rows:
        label = norm(" ".join(r["chunks"]))
        when = day(label)
        if not re.search(r"\d+\s*(?:대|회)", label) or not re.search(r"본회의|위원회|행정사무감사|개원식|개회식", label):
            continue
        url = detail_from(r["attrs"], base, source)
        identity = url or label
        if identity in seen:
            continue
        seen.add(identity)
        rows.append({"list_rank": len(rows)+1, "meeting_date": when,
                     "label": label[:300], "url": url,
                     "provisional": bool(re.search(r"\[임시\]|임시회의록|임시본", label)),
                     "unresolved_attrs": r["attrs"][:10] if not url else []})
    # Official listing order is preserved. Failures are never replaced with easy pages.
    return rows[:count], len(rows)

def identity_conflict(label, title):
    for pattern in (r"제?\s*(\d+)\s*대", r"제?\s*(\d+)\s*회(?!의)"):
        left, right = re.search(pattern,label), re.search(pattern,title)
        if left and right and left.group(1) != right.group(1):
            return True
    return False

def transcript(page):
    text = norm(" ".join(page.chunks))
    if ERROR_BODY.search(text):
        return "", []
    if len(page.speeches) >= 2 and len(re.findall(r"[가-힣]", " ".join(page.speeches))) >= 200:
        return " ○ ".join(page.speeches), page.speeches
    speaker = re.compile(
        r"^(?:(?:위원장|부위원장|의장|부의장|위원|의원)\s*[가-힣]{2,5}"
        r"|[가-힣]{2,5}\s*(?:위원|의원)"
        r"|[가-힣·]{0,30}(?:과장|국장|팀장|소장|동장|이사장|대표이사|구청장|담당관|전문위원|담당)\s*[가-힣]{2,5})"
    )
    parts = []
    for chunk in re.split(r"[○◯]", text)[1:]:
        chunk = chunk.strip()
        if parts and re.match(r"(?:출석|결석|청가|서명|기록)", chunk):
            break
        chunk = re.split(r"COPYRIGHT|copyright", chunk, maxsplit=1)[0].strip()
        if speaker.match(chunk):
            parts.append(chunk)
        elif parts and chunk:
            parts[-1] += " ○ " + chunk
    body = " ○ ".join(parts)
    if len(parts) < 2 or len(re.findall(r"[가-힣]", body)) < 200:
        return "", []
    return body, parts

def review_windows(parts):
    # Navigation terms and generic finance words alone cannot select a passage.
    # No numeric evidence is required: a concrete service phenomenon can start a question.
    ranked = []
    for i, part in enumerate(parts):
        if len(part) < 90:
            continue
        if re.match(r"(?:위원장|부위원장|의장|부의장)\s", part) and len(part) < 1200 and any(t in part for t in ("질의하실", "개의를 선포", "안건순서", "성원이 되었으므로")):
            continue
        topics = [k for k, terms in TOPICS.items() if any(t in part for t in terms)]
        signals = [s for s in SIGNALS if s in part]
        if not topics or not (signals or NUMBER.search(part)):
            continue
        score = min(len(signals), 4) + bool(NUMBER.search(part)) + min(len(topics), 2)
        ranked.append((score, i, topics, signals))
    chosen, used = [], set()
    for score, i, topics, signals in sorted(ranked, key=lambda r:(-r[0],r[1])):
        if i in used:
            continue
        # Only short review pointers are persisted. These are not generated article questions.
        part = parts[i]
        signal_positions = [m.start() for term in signals for m in re.finditer(re.escape(term),part)]
        topic_positions = [m.start() for topic in topics for term in TOPICS[topic] for m in re.finditer(re.escape(term),part)]
        anchors = signal_positions or [m.start() for m in NUMBER.finditer(part)] or topic_positions
        # A selected problem/change signal must survive in the stored context.
        anchor = max(anchors, key=lambda p:sum(abs(q-p)<=220 for q in signal_positions)*8 + sum(abs(q-p)<=220 for q in topic_positions)) if anchors else 0
        start = max(0, anchor-180)
        chosen.append({"turn_index": i, "topics": topics, "signals": signals,
                       "speaker_prefix": part[:65], "character_offset": start,
                       "passage": part[start:start+650],
                       "next_turn_context": parts[i+1][:350] if i+1 < len(parts) else "",
                       "attribution": "발언자·집행부 답변 구분은 원문 대조 필요",
                       "editor_status": "UNREVIEWED"})
        used.update({i-1, i, i+1})
        if len(chosen) == 3:
            break
    return chosen

class Client:
    def __init__(self, source):
        self.source = source
        self.logs = []
        self.stopped = False

    def get(self, url):
        if not allowed(url, self.source) or self.stopped or len(self.logs) >= 10:
            return None
        if self.logs:
            time.sleep(1)
        started = time.monotonic()
        result = {"url": url, "status": 0, "bytes": 0}
        try:
            with urlopen(Request(url, headers={"User-Agent": UA, "Accept-Language":"ko"}), timeout=18) as res:
                result["status"] = res.status
                result["final_url"] = clean_diagnostic(res.url)
                if not allowed(res.url, self.source):
                    raise ValueError("Redirect outside configured official hosts")
                raw = res.read(6_000_001)
                if len(raw) > 6_000_000:
                    raise ValueError("Page exceeds pilot byte limit")
                result["bytes"] = len(raw)
                result["sha256"] = hashlib.sha256(raw).hexdigest()
                for enc in [res.headers.get_content_charset(), "utf-8", "cp949"]:
                    if not enc:
                        continue
                    try:
                        html = raw.decode(enc)
                        break
                    except (UnicodeDecodeError, LookupError):
                        pass
                else:
                    raise ValueError("Unrecognized page encoding")
                return Page(html)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            result["error"] = str(exc)[:220]
            if isinstance(exc, HTTPError):
                result["status"] = exc.code
                self.stopped = exc.code in {403,429}
            return None
        finally:
            result["elapsed_ms"] = round((time.monotonic()-started)*1000)
            self.logs.append(result)

def discover_list(page, base, source):
    label = source.get("discover_list_label", "최근회의록")
    for anchor in page.anchors:
        if label not in norm(" ".join(anchor["chunks"])):
            continue
        for key,value in anchor["attrs"]:
            candidates = [value] if key == "href" else re.findall(r"""['"]([^'"]+)['"]""", value or "") if key == "onclick" else []
            for value in candidates:
                url = urljoin(base,value)
                if value and not value.startswith(("#","javascript:")) and allowed(url,source):
                    return url
    return ""

def window_change(current, previous):
    if not current["listing_ok"] or not current["selected"]:
        return "UNKNOWN_COLLECTION"
    rows = current["selected"]
    if len(rows) < current["expected"] or any(not r.get("url") for r in rows):
        return "UNKNOWN_LIST_WINDOW"
    if previous is None:
        return "BASELINE"
    old = previous.get("selected", [])
    if not previous.get("listing_ok") or not old or any(not r.get("url") for r in old):
        return "BASELINE_AFTER_FAILURE"
    if previous.get("expected") != current["expected"]:
        return "BASELINE_WINDOW_CHANGED"
    if len(old) < previous["expected"]:
        return "BASELINE_AFTER_FAILURE"
    def identity(url):
        parsed = urlparse(url)
        return (parsed.path, tuple(sorted(parse_qsl(parsed.query))))
    old_urls = {identity(r["url"]) for r in old}
    return "NEW_IN_VISIBLE_WINDOW" if any(identity(r["url"]) not in old_urls for r in rows) else "NO_NEW_IN_VISIBLE_WINDOW"

def run(source, as_of, count=4):
    client = Client(source)
    listing_url = source["list_url"]
    listing = client.get(listing_url)
    fallback = source.get("list_fallback_url",listing_url)
    if listing is None and fallback and not client.stopped and "name resolution" in client.logs[-1].get("error",""):
        listing_url = fallback
        listing = client.get(listing_url)
    if listing is not None and source.get("discover_list_label"):
        discovered = discover_list(listing,listing_url,source)
        if discovered:
            listing_url = discovered
            listing = client.get(discovered)
    result = {"id":source["id"], "name":source["name"], "list_url":source["list_url"],
              "expected":count, "listing_ok":listing is not None, "effective_list_url":listing_url, "listed":0, "selected":[],
              "public_release_date":None, "selection":f"official_first_page_order_top{count}"}
    if listing is None:
        result["diagnosis"] = "LIST_FETCH_FAILED"
    else:
        selected, total = select_rows(listing, listing_url, source, count)
        result["listed"] = total
        if source.get("diagnostic_js") or not selected:
            result["diagnostic_scripts"] = listing.script_sources[:32]
            inline = "\n".join(listing.script_text)
            functions = re.findall(r"function\s+fn_popup_page[\s\S]{0,2200}",inline)
            result["diagnostic_popup"] = [clean_diagnostic(f) for f in functions[:1]]
            if not selected:
                result["diagnostic_inline_routes"] = [clean_diagnostic(v) for v in re.findall(r".{0,60}(?:location|ajax|url\s*:|\.do).{0,180}",inline)[:12]]
                at = inline.find("/main/getAssemList")
                result["diagnostic_list_function"] = clean_diagnostic(inline[max(0,at-500):at+2300]) if at >= 0 else ""
                result["diagnostic_detail_anchors"] = [a for a in listing.anchors if detail_from(a["attrs"],listing_url,source)][:4]
        if not selected:
            probe_url = source.get("inspect_list_script")
            if probe_url:
                script = client.get(probe_url)
                result["diagnostic_official_script"] = clean_diagnostic(script.raw_html[:18000]) if script else ""
            result["diagnosis"] = "LIST_PARSE_EMPTY"
            result["diagnostic_links"] = [u for u in listing.links if any(s in u for s in ("record","minute","confer","recent","viewer"))][:16]
            result["diagnostic_rows"] = listing.rows[:5]
            result["diagnostic_anchors"] = [a for a in listing.anchors if "회의록" in norm(" ".join(a["chunks"]))][:8]
            result["page_title"] = norm(" ".join(listing.title))
            result["diagnostic_frames"] = listing.frames
            at = listing.raw_html.find("최근 6개월")
            result["diagnostic_recent_markup"] = clean_diagnostic(listing.raw_html[max(0,at-300):at+2800]) if at >= 0 else ""
        for row in selected:
            row.update({"body_ok":False, "review_windows":[],
                        "age_days":(as_of-date.fromisoformat(row["meeting_date"])).days if row["meeting_date"] else None,
                        "publication_status":"PROVISIONAL" if row["provisional"] else "UNCONFIRMED"})
            if row["age_days"] is None:
                row["diagnosis"] = "DATE_UNRESOLVED"
            elif row["age_days"] < 0:
                row["diagnosis"] = "FUTURE_MEETING"
            elif not row["url"]:
                row["diagnosis"] = "DETAIL_LINK_UNRESOLVED"
            else:
                page = client.get(row["url"])
                if page:
                    body, parts = transcript(page)
                    # Some viewers host the transcript in a same-site frame.
                    if not body:
                        inner = detail_from([("src",u) for u in page.frames], row["url"], source)
                        if inner and inner != row["url"]:
                            framed = client.get(inner)
                            if framed:
                                body, parts = transcript(framed)
                                page = framed
                                row["body_url"] = inner
                    row["body_ok"] = bool(body)
                    row["body_characters"] = len(body)
                    row["body_sha256"] = hashlib.sha256(body.encode("utf-8")).hexdigest() if body else ""
                    row["speech_turns"] = len(parts)
                    row["review_windows"] = review_windows(parts) if body else []
                    row["diagnosis"] = "BODY_OK" if body else "EMPTY_OR_UNPARSED_BODY"
                    if not body:
                        row["diagnostic_speaker_markup"] = [clean_diagnostic(page.raw_html[max(0,m.start()-220):m.end()+550]) for m in list(re.finditer(r"위원장|의사담당",page.raw_html))[:4]]
                        row["diagnostic_text_tail"] = norm(" ".join(page.chunks))[-600:]
                    row["title"] = norm(" ".join(page.title))
                    row["title_date"] = day(row["title"])
                    rawtext = norm(" ".join(page.chunks))
                    heading = re.search(r"일\s*시\s*[:：]?\s*(20\d{2}.{0,30})", rawtext)
                    row["header_date"] = day(heading.group(1)) if heading else ""
                    dates = [d for d in (row["title_date"],row["header_date"]) if d]
                    row["date_conflict"] = any(d != row["meeting_date"] for d in dates)
                    row["date_crosschecked"] = bool(dates) and not row["date_conflict"]
                    row["identity_conflict"] = identity_conflict(row["label"],row["title"])
                    row["metadata_check"] = "CONFLICT" if row["date_conflict"] or row["identity_conflict"] else "MATCH" if row["date_crosschecked"] else "UNVERIFIED"
                    if row["metadata_check"] == "CONFLICT":
                        row["diagnosis"] = "BODY_METADATA_CONFLICT"
                        row["review_windows"] = []
                else:
                    row["diagnosis"] = "DETAIL_FETCH_FAILED"
            result["selected"].append(row)
        if selected:
            complete = len(selected)==count and all(r["body_ok"] for r in selected)
            metadata_ok = all(r.get("metadata_check") == "MATCH" for r in selected)
            result["diagnosis"] = "SAMPLE_COMPLETE" if complete and metadata_ok else "SAMPLE_METADATA_REVIEW" if complete else "SAMPLE_INCOMPLETE"
    result["requests"] = client.logs
    result["bodies"] = sum(r["body_ok"] for r in result["selected"])
    result["documents_with_review_windows"] = sum(bool(r["review_windows"]) for r in result["selected"])
    result["metadata_matched"] = sum(r.get("metadata_check") == "MATCH" for r in result["selected"])
    result["editorial_precision"] = None
    return result

def write(results, as_of, output=None):
    output = output or BASE / "output"
    output.mkdir(parents=True,exist_ok=True)
    payload = {"collected_at":datetime.now(KST).isoformat(timespec="seconds"),
               "as_of":str(as_of), "intended_documents":sum(r["expected"] for r in results), "sources":results,
               "editorial_precision":None, "core_source_status":"NOT_EVALUATED"}
    (output/"pilot_latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2),encoding="utf-8")
    lines = [f"# 자치구의회 {len(results)}곳 수집 연결 점검","",f"기준일: {as_of}",
             "공식 목록 앞부분을 고정 선정. 접근 실패는 대체하지 않음. 공개일은 미확인.",
             "자동 발언 단서는 편집 판정 전이며 질문 정밀도·핵심소스 승인으로 계산하지 않음.","",
             "| 구 | 목록행 | 선정 | 본문 | 검토문단 있는 문서 | 수집 판정 |",
             "|---|---:|---:|---:|---:|---|"]
    for r in results:
        lines.append(f"| {r['name']} | {r['listed']} | {len(r['selected'])}/{r['expected']} | {r['bodies']}/{r['expected']} | {r['documents_with_review_windows']} | {r['diagnosis']} |")
        print("METRIC "+json.dumps({k:r[k] for k in ("id","listed","bodies","documents_with_review_windows","metadata_matched","diagnosis","change_status")},ensure_ascii=False))
    for r in results:
        print("SOURCE "+json.dumps({k:v for k,v in r.items() if k not in {"selected","requests"}},ensure_ascii=False))
        lines += ["",f"## {r['name']}","",f"- 신규 여부: {r['change_status']} (이전 관측이 있어야 판정)"]
        for row in r["selected"]:
            lines += [f"- {row['meeting_date']} · {row['label']} · {row['diagnosis']}",
                      f"  - 원문: {row['url'] or '주소 추출 실패'}",
                      f"  - 임시본 표시: {row['provisional']} / 회의 후 경과: {row['age_days']}일"]
            print("DOCUMENT "+json.dumps(row,ensure_ascii=False))
        for request in r["requests"]:
            print("REQUEST "+json.dumps(request,ensure_ascii=False))
    (output/"pilot_latest.md").write_text("\n".join(lines)+"\n",encoding="utf-8")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of",type=date.fromisoformat,default=datetime.now(KST).date())
    parser.add_argument("--sources",type=Path,default=BASE/"sources.json")
    parser.add_argument("--per-source",type=int,choices=range(1,5),default=4)
    parser.add_argument("--workers",type=int,choices=range(1,5),default=1)
    parser.add_argument("--output",type=Path,default=BASE/"output")
    parser.add_argument("--previous",type=Path)
    parser.add_argument("--source-id",nargs="+")
    args = parser.parse_args()
    sources = json.loads(args.sources.read_text(encoding="utf-8"))
    if len({s["id"] for s in sources}) != len(sources):
        parser.error("Duplicate source identifiers")
    if args.source_id:
        if set(args.source_id) - {s["id"] for s in sources}:
            parser.error("Unknown source identifier")
        sources = [s for s in sources if s["id"] in args.source_id]
    old = {}
    if args.previous and args.previous.is_file():
        old = {r["id"]:r for r in json.loads(args.previous.read_text(encoding="utf-8"))["sources"]}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda source: run(source,args.as_of,args.per_source),sources))
    for result in results:
        result["change_status"] = window_change(result,old.get(result["id"]))
    write(results,args.as_of,args.output)
    # Successful diagnostic execution is distinct from source availability.
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
