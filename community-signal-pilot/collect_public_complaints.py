#!/usr/bin/env python3
"""Bounded L2 sampler for Seoul Eungdapso public complaint cases.

The collector reads only cases that citizens chose to publish. It never stores
full complaint or answer text and never creates an editorial question.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parent
OUTPUT = BASE / "output"
LIST_URL = "https://eungdapso.seoul.go.kr/exp/pub/complaint_pub_lis.do"
DETAIL_PATH = "/exp/pub/complaint_pub_vie.do"
HOST = "eungdapso.seoul.go.kr"
SCAN_LIMIT = 20
DETAIL_LIMIT = 5
MAX_BYTES = 2_000_000
USER_AGENT = "NewsItemRadarPublicComplaintPilot/1.0"

PHONE = re.compile(r"(?<!\d)(?:0\d{1,2}|\+82[- .]?(?:0?\d{1,2}))[- .)]?\d{3,4}[- .]?\d{4}(?!\d)")
EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
RESIDENT_ID = re.compile(r"(?<!\d)\d{6}[- ]?[1-4]\d{6}(?!\d)")
ADDRESS = re.compile(r"(?:[가-힣A-Za-z0-9]{1,24}(?:로|길)\s*\d+(?:-\d+)?|\d+\s*동\s*\d+\s*호)")
DATE = re.compile(r"20\d{2}[-./]\d{1,2}[-./]\d{1,2}")
TOKEN = re.compile(r"(?:rceptNo\s*[=:]\s*|(?:fn|go)?View\s*\(\s*['\"]?)([A-Fa-f0-9]{24,64})", re.I)

CITIZEN_MARKERS = (
    "대기", "불편", "부담", "비용", "지연", "거절", "반려", "누락", "고장",
    "파손", "단차", "침하", "위험", "혼잡", "이용하지 못", "사용하지 못",
    "운행시간", "운행 중단", "접근이 어렵", "반복",
)
SAFETY_MARKERS = ("위험", "안전", "파손", "단차", "침하", "사고")
ACCESS_MARKERS = ("대기", "이용하지 못", "사용하지 못", "운행시간", "운행 중단", "접근이 어렵", "제한")
OFFICIAL_MARKERS = (
    "시범", "제한", "점검", "보수", "조치", "검토", "예산", "계획",
    "불가", "어렵", "미정", "운영 중", "실시 중",
)


def norm(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def sanitize(value: str) -> str:
    value = EMAIL.sub("[이메일 삭제]", value or "")
    value = PHONE.sub("[전화번호 삭제]", value)
    value = RESIDENT_ID.sub("[식별번호 삭제]", value)
    value = ADDRESS.sub("[상세주소 삭제]", value)
    value = re.sub(r"(?i)((?:jsessionid|sessionid)\s*[=:]\s*['\"]?)[A-Za-z0-9._~-]+", r"\1[삭제]", value)
    return norm(value)


class OfficialRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlparse(newurl)
        if parsed.scheme != "https" or parsed.hostname != HOST or parsed.username or parsed.password:
            raise ValueError("redirect outside official HTTPS host")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def decode_response(raw: bytes, charset: str | None) -> str:
    for encoding in (charset, "utf-8", "cp949", "euc-kr"):
        if not encoding:
            continue
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            pass
    raise ValueError("unknown response encoding")


def fetch(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != HOST or parsed.username or parsed.password:
        raise ValueError("only the official HTTPS host is allowed")
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "ko"})
    with build_opener(OfficialRedirect()).open(req, timeout=25) as response:
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("response exceeds 2 MB pilot limit")
        return decode_response(raw, response.headers.get_content_charset()), hashlib.sha256(raw).hexdigest()


class RowParser(HTMLParser):
    def __init__(self, html: str):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.row: dict | None = None
        self.anchor: dict | None = None
        self.rows: list[dict] = []
        self.visible: list[str] = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag in ("script", "style", "noscript"):
            self.skip += 1
            return
        if self.skip:
            return
        if tag == "tr":
            self.row = {"text": [], "anchors": [], "attrs": []}
        if self.row is not None:
            self.row["attrs"].extend(str(value or "") for value in values.values())
        if tag == "a":
            self.anchor = {
                "text": [],
                "attrs": " ".join(str(value or "") for value in values.values()),
            }

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag == "a" and self.anchor is not None:
            self.anchor["text"] = norm(" ".join(self.anchor["text"]))
            if self.row is not None:
                self.row["anchors"].append(self.anchor)
            self.anchor = None
        if tag == "tr" and self.row is not None:
            self.row["text"] = norm(" ".join(self.row["text"]))
            self.row["attrs"] = " ".join(self.row["attrs"])
            if self.row["text"]:
                self.rows.append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.skip:
            return
        value = norm(data)
        if not value:
            return
        self.visible.append(value)
        if self.row is not None:
            self.row["text"].append(value)
        if self.anchor is not None:
            self.anchor["text"].append(value)


def extract_token(value: str) -> str | None:
    match = TOKEN.search(value or "")
    if match:
        return match.group(1).upper()
    parsed = urlparse(value or "")
    token = parse_qs(parsed.query).get("rceptNo", [""])[0]
    if re.fullmatch(r"[A-Fa-f0-9]{24,64}", token):
        return token.upper()
    return None


def parse_list(html: str, limit: int = SCAN_LIMIT) -> list[dict]:
    if limit < 1 or limit > 50:
        raise ValueError("list limit must be between 1 and 50")
    parser = RowParser(html)
    items: list[dict] = []
    seen: set[str] = set()
    for row in parser.rows:
        token = extract_token(row["attrs"])
        chosen_anchor = None
        if not token:
            for anchor in row["anchors"]:
                token = extract_token(anchor["attrs"])
                if token:
                    chosen_anchor = anchor
                    break
        else:
            for anchor in row["anchors"]:
                if extract_token(anchor["attrs"]) == token:
                    chosen_anchor = anchor
                    break
        if not token or token in seen:
            continue
        title = sanitize((chosen_anchor or {}).get("text", ""))
        if not title:
            text = row["text"]
            text = DATE.sub(" ", text)
            text = re.sub(r"\bS\d{6}\b|\b\d{1,3}(?:,\d{3})*\b", " ", text)
            title = sanitize(text)
        dates = [match.group(0).replace(".", "-").replace("/", "-") for match in DATE.finditer(row["text"])]
        code_match = re.search(r"\bS\d{6}\b", row["text"])
        detail_url = f"https://{HOST}{DETAIL_PATH}?" + urlencode({"rceptNo": token})
        items.append({
            "case_id": hashlib.sha256(token.encode("ascii")).hexdigest()[:16],
            "title": title[:160],
            "category_code": code_match.group(0) if code_match else None,
            "applied_date": dates[0] if dates else None,
            "published_date": dates[1] if len(dates) > 1 else None,
            "source_url": detail_url,
            "_public_token": token,
        })
        seen.add(token)
        if len(items) >= limit:
            break
    if not items:
        raise ValueError("no public complaint rows found")
    return items


def visible_detail(html: str, title: str) -> str:
    parser = RowParser(html)
    text = sanitize(norm(" ".join(parser.visible)))
    if title:
        title_tokens = [token for token in re.sub(r"[^0-9A-Za-z가-힣]+", " ", title).split() if len(token) >= 2][:2]
        positions = [text.find(token) for token in title_tokens if text.find(token) >= 0]
        if positions:
            text = text[min(positions):]
    for boundary in ("자동 로그아웃 안내", "민원편람", "개인정보처리방침"):
        position = text.find(boundary)
        if position > 0:
            text = text[:position]
    return text[:30_000]


def matched(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if term in text][:8]


QUESTION_LABELS = ("민원 내용", "민원내용", "신청 내용", "신청내용", "질문 내용", "질문내용")
ANSWER_LABELS = ("답변 내용", "답변내용", "처리 결과", "처리결과", "담당부서 답변")


def _first_label(text: str, labels: tuple[str, ...], start: int = 0) -> tuple[int, str] | None:
    positions = [(text.find(label, start), label) for label in labels if text.find(label, start) >= 0]
    return min(positions, default=None, key=lambda row: row[0])


def split_explicit_sections(text: str) -> dict:
    """Separate citizen and agency text only when the page exposes boundaries.

    An agency paraphrase such as '귀하의 민원내용은 ...' is not a citizen
    section and must never produce citizen problem markers.
    """
    question = _first_label(text, QUESTION_LABELS)
    answer = _first_label(text, ANSWER_LABELS)
    if question and answer and question[0] < answer[0]:
        citizen = text[question[0] + len(question[1]):answer[0]]
        official = text[answer[0] + len(answer[1]):]
        status = "EXPLICIT_QUESTION_AND_ANSWER"
    elif answer:
        citizen = ""
        official = text[answer[0] + len(answer[1]):]
        status = "ANSWER_ONLY"
    else:
        q_match = re.search(r"(?:^|\\s)Q(?:\\s|[:：])", text)
        a_match = re.search(r"(?:^|\\s)A(?:\\s|[:：])", text)
        if q_match and a_match and q_match.end() < a_match.start():
            citizen = text[q_match.end():a_match.start()]
            official = text[a_match.end():]
            status = "EXPLICIT_Q_AND_A"
        else:
            citizen = ""
            official = ""
            status = "BOUNDARY_UNRESOLVED"
    return {
        "status": status,
        "citizen_text": citizen[:12_000],
        "official_text": official[:12_000],
    }


def derive_signals(citizen_text: str, official_text: str, section_status: str) -> dict:
    citizen = matched(citizen_text, CITIZEN_MARKERS)
    safety = matched(citizen_text, SAFETY_MARKERS)
    access = matched(citizen_text, ACCESS_MARKERS)
    official = matched(official_text, OFFICIAL_MARKERS)
    citizen_available = bool(norm(citizen_text))
    answer_available = bool(norm(official_text))
    if safety:
        signal_type = "SAFETY_OR_MAINTENANCE"
    elif access:
        signal_type = "ACCESS_OR_WAITING_FRICTION"
    elif citizen:
        signal_type = "SERVICE_FRICTION"
    else:
        signal_type = "INFORMATION_QUERY_OR_UNRESOLVED"
    if not citizen_available:
        review_status = "CONTEXT_UNRESOLVED"
        reason = "시민 작성 구간을 기관 답변과 분리하지 못해 문제 신호로 판정하지 않았습니다."
    elif citizen and official:
        review_status = "SHADOW_REVIEW"
        reason = "분리된 시민 작성 구간의 문제 표현과 기관 답변 구간의 제약·조치 표현이 함께 확인됐습니다."
    elif citizen:
        review_status = "HOLD"
        reason = "분리된 시민 작성 구간에 문제 표현은 있으나 기관 답변의 구조적 단서를 확인하지 못했습니다."
    else:
        review_status = "INFORMATION_ONLY"
        reason = "분리된 시민 작성 구간에서 구조적 문제 표현을 확인하지 못했습니다."
    return {
        "section_status": section_status,
        "citizen_section_available": citizen_available,
        "answer_section_available": answer_available,
        "signal_type": signal_type,
        "citizen_problem_markers": citizen,
        "official_response_markers": official,
        "review_status": review_status,
        "review_reason": reason,
        "claim_status": "UNVERIFIED_CITIZEN_STATEMENT",
        "official_answer_status": "ATTRIBUTED_RESPONSE_NOT_INDEPENDENT_PROOF",
        "editorial_question": "NOT_GENERATED_AT_L2",
        "article_candidate": False,
    }


def observe(fetcher=fetch, scan_limit: int = SCAN_LIMIT, detail_limit: int = DETAIL_LIMIT) -> dict:
    if detail_limit < 1 or detail_limit > scan_limit:
        raise ValueError("detail limit must be positive and no greater than scan limit")
    observed_at = datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")
    list_html, list_sha = fetcher(LIST_URL)
    listed = parse_list(list_html, scan_limit)
    records = []
    failures = []
    for item in listed[:detail_limit]:
        try:
            detail_html, detail_sha = fetcher(item["source_url"])
            detail_text = visible_detail(detail_html, item["title"])
            sections = split_explicit_sections(detail_text)
            signals = derive_signals(
                sections["citizen_text"],
                sections["official_text"],
                sections["status"],
            )
            record = {key: value for key, value in item.items() if not key.startswith("_")}
            record.update(signals)
            record["detail_sha256"] = detail_sha
            records.append(record)
        except Exception as exc:
            failures.append({"case_id": item["case_id"], "error": type(exc).__name__})
    return {
        "schema": 1,
        "source_id": "eungdapso_public_complaints",
        "source_name": "응답소 공개 민원사례",
        "maturity": "L2",
        "observed_at_kst": observed_at,
        "source_url": LIST_URL,
        "list_sha256": list_sha,
        "limits": {"list_rows": scan_limit, "detail_pages": detail_limit},
        "policy": {
            "public_cases_only": True,
            "full_complaint_text_persisted": False,
            "full_answer_text_persisted": False,
            "personal_information_persisted": False,
            "questions_generated": False,
            "automatic_promotion": False,
        },
        "diagnostics": {
            "listed_count": len(listed),
            "detail_success_count": len(records),
            "detail_failure_count": len(failures),
            "shadow_review_count": sum(row["review_status"] == "SHADOW_REVIEW" for row in records),
            "information_only_count": sum(row["review_status"] == "INFORMATION_ONLY" for row in records),
            "hold_count": sum(row["review_status"] == "HOLD" for row in records),
            "context_unresolved_count": sum(row["review_status"] == "CONTEXT_UNRESOLVED" for row in records),
            "explicit_question_answer_count": sum(
                row["section_status"] in {"EXPLICIT_QUESTION_AND_ANSWER", "EXPLICIT_Q_AND_A"}
                for row in records
            ),
        },
        "records": records,
        "failures": failures,
    }


def render_markdown(document: dict) -> str:
    lines = [
        "# 응답소 공개 민원사례 L2 표본",
        "",
        f"- 관측 시각: {document['observed_at_kst']}",
        f"- 목록 확인: {document['diagnostics']['listed_count']}건",
        f"- 본문 표본 성공: {document['diagnostics']['detail_success_count']}건",
        f"- 그림자 검토 표시: {document['diagnostics']['shadow_review_count']}건",
        f"- 시민·기관 구간 분리 실패: {document['diagnostics']['context_unresolved_count']}건",
        "",
        "> 시민 진술은 사실로 확정하지 않았고, 기관 답변도 독립 검증으로 세지 않습니다.",
        "> 민원·답변 원문과 개인정보는 저장하지 않았으며 이 결과는 기사 후보가 아닙니다.",
        "",
    ]
    for index, row in enumerate(document["records"], 1):
        lines.extend([
            f"## {index}. {row['title']}",
            "",
            f"- 공개일: {row.get('published_date') or '확인 필요'}",
            f"- 본문 구간: {row['section_status']}",
            f"- 신호 유형: {row['signal_type']}",
            f"- 검토 상태: {row['review_status']}",
            f"- 시민 문제 표지: {', '.join(row['citizen_problem_markers']) or '없음'}",
            f"- 기관 답변 표지: {', '.join(row['official_response_markers']) or '없음'}",
            f"- 판단: {row['review_reason']}",
            f"- [공개 원문]({row['source_url']})",
            "",
        ])
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    document = observe()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT / "public_complaints_latest.json"
    md_path = OUTPUT / "public_complaints_latest.md"
    json_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(document), encoding="utf-8")
    print(json.dumps(document["diagnostics"], ensure_ascii=False))


if __name__ == "__main__":
    main()
