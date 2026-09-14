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
           "이용률", "집행률", "없습니다", "불용", "대기", "시간", "부담", "편중")
NUMBER = re.compile(r"\d[\d,.]*\s*(?:%|명|건|원|억|만|곳|대|개)")
UA = "Mozilla/5.0 (compatible; NewsItemRadarPilot/1.0; +https://github.com/onetym77-bit/news-item-radar)"

def norm(text):
    return re.sub(r"\s+", " ", text).strip()

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
        self.chunks = []
        self.rows = []
        self.row = None
        self.links = []
        self.frames = []
        self.title = []
        self.in_title = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.skip += 1
        if self.skip:
            return
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
        if tag in {"script", "style", "noscript"}:
            self.skip = max(0, self.skip - 1)
        if self.skip:
            return
        if tag == "title":
            self.in_title = False
        if tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None

    def handle_data(self, text):
        if self.skip or not norm(text):
            return
        text = norm(text)
        self.chunks.append(text)
        if self.row is not None:
            self.row["chunks"].append(text)
        if self.in_title:
            self.title.append(text)

def allowed(url, source):
    u = urlparse(url)
    return u.scheme == "https" and u.hostname in source["hosts"]

def canonical(url):
    u = urlparse(url)
    ids = [(k, v) for k, v in parse_qsl(u.query) if k in {"uid", "key"}]
    return urlunparse(u._replace(query=urlencode(ids), fragment=""))

def detail_from(attrs, base, source):
    for key, value in attrs:
        if key == "data-uid" and source.get("uid_path") and value.isdigit():
            url = urljoin(base, source["uid_path"]) + "?uid=" + value
            if allowed(url, source):
                return canonical(url)
        candidates = [value] if key in {"href", "src"} else re.findall(r"""['"]([^'"]+)['"]""", value)
        for candidate in candidates:
            url = urljoin(base, candidate)
            if allowed(url, source) and DETAIL.search(url) and any(k in {"key","uid"} for k, _ in parse_qsl(urlparse(url).query)):
                return canonical(url)
    return ""

def select_rows(page, base, source, count=4):
    rows, seen = [], set()
    for r in page.rows:
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

def transcript(page):
    text = norm(" ".join(page.chunks))
    markers = list(re.finditer(r"[○◯]", text))
    if ERROR_BODY.search(text) or len(markers) < 2:
        return "", []
    parts = [text[m.end(): markers[i+1].start() if i+1 < len(markers) else len(text)]
             for i, m in enumerate(markers)]
    # At least two speech turns and meaningful Korean content, not a successful HTTP shell.
    body = " ○ ".join(parts)
    if len(re.findall(r"[가-힣]", body)) < 200:
        return "", []
    return body, parts

def review_windows(parts):
    # Navigation terms and generic finance words alone cannot select a passage.
    # No numeric evidence is required: a concrete service phenomenon can start a question.
    ranked = []
    for i, part in enumerate(parts):
        if len(part) < 90:
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
        positions = [part.find(t) for t in signals if t in part]
        positions += [part.find(t) for topic in topics for t in TOPICS[topic] if t in part]
        positions = sorted(set(p for p in positions if p >= 0))
        # Pick the densest relevant context, not the opening greetings of a long speech.
        anchor = max(positions, key=lambda p:sum(abs(q-p)<=240 for q in positions)) if positions else 0
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
                result["final_url"] = res.url
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

def run(source, as_of):
    client = Client(source)
    listing = client.get(source["list_url"])
    result = {"id":source["id"], "name":source["name"], "list_url":source["list_url"],
              "expected":4, "listing_ok":listing is not None, "listed":0, "selected":[],
              "public_release_date":None, "selection":"official_first_page_order_top4"}
    if listing is None:
        result["diagnosis"] = "LIST_FETCH_FAILED"
    else:
        selected, total = select_rows(listing, source["list_url"], source)
        result["listed"] = total
        if not selected:
            result["diagnosis"] = "LIST_PARSE_EMPTY"
            result["diagnostic_links"] = [u for u in listing.links if "record" in u or "minute" in u][:12]
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
                    row["speech_turns"] = len(parts)
                    row["review_windows"] = review_windows(parts) if body else []
                    row["diagnosis"] = "BODY_OK" if body else "EMPTY_OR_UNPARSED_BODY"
                    row["title"] = norm(" ".join(page.title))
                    row["title_date"] = day(row["title"])
                    rawtext = norm(" ".join(page.chunks))
                    heading = re.search(r"일\s*시\s*[:：]?\s*(20\d{2}.{0,30})", rawtext)
                    row["header_date"] = day(heading.group(1)) if heading else ""
                    dates = [d for d in (row["title_date"],row["header_date"]) if d]
                    row["date_conflict"] = any(d != row["meeting_date"] for d in dates)
                    row["date_crosschecked"] = bool(dates) and not row["date_conflict"]
                    if row["date_conflict"]:
                        row["diagnosis"] = "BODY_METADATA_CONFLICT"
                else:
                    row["diagnosis"] = "DETAIL_FETCH_FAILED"
            result["selected"].append(row)
        if selected:
            result["diagnosis"] = "SAMPLE_COMPLETE" if len(selected)==4 and all(r["body_ok"] and not r.get("date_conflict") for r in selected) else "SAMPLE_INCOMPLETE"
    result["requests"] = client.logs
    result["bodies"] = sum(r["body_ok"] for r in result["selected"])
    result["documents_with_review_windows"] = sum(bool(r["review_windows"]) for r in result["selected"])
    result["editorial_precision"] = None
    return result

def write(results, as_of):
    output = BASE / "output"
    output.mkdir(exist_ok=True)
    payload = {"collected_at":datetime.now(KST).isoformat(timespec="seconds"),
               "as_of":str(as_of), "intended_documents":20, "sources":results,
               "editorial_precision":None, "core_source_status":"NOT_EVALUATED"}
    (output/"pilot_latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2),encoding="utf-8")
    lines = ["# 자치구의회 5곳 수집 시험","",f"기준일: {as_of}",
             "공식 최신목록 첫 4건씩 선정. 접근 실패는 대체하지 않음. 공개일은 미확인.",
             "자동 발언 단서는 편집 판정 전이며 질문 정밀도·핵심소스 승인으로 계산하지 않음.","",
             "| 구 | 목록행 | 선정 | 본문 | 검토문단 있는 문서 | 수집 판정 |",
             "|---|---:|---:|---:|---:|---|"]
    for r in results:
        lines.append(f"| {r['name']} | {r['listed']} | {len(r['selected'])}/4 | {r['bodies']}/4 | {r['documents_with_review_windows']} | {r['diagnosis']} |")
        print("METRIC "+json.dumps({k:r[k] for k in ("id","listed","bodies","documents_with_review_windows","diagnosis")},ensure_ascii=False))
    for r in results:
        lines += ["",f"## {r['name']}",""]
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
    args = parser.parse_args()
    sources = json.loads((BASE/"sources.json").read_text(encoding="utf-8"))
    results = [run(source,args.as_of) for source in sources]
    write(results,args.as_of)
    # Successful diagnostic execution is distinct from source availability.
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
