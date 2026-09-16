#!/usr/bin/env python3
"""Bounded read-only observer for official Seoul citizen proposals."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parent
LIST_URL = "https://idea.seoul.go.kr/front/allSuggest/list.do?tab=cateAll"
HOST = "idea.seoul.go.kr"
LIMIT = 5
USER_AGENT = "NewsItemRadarCitizenProposalPilot/1.0"

def norm(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()

def sanitize(value: str) -> str:
    value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[EMAIL]", value)
    value = re.sub(
        r"(?<!\d)(?:0\d{1,2}|\+82[- .]?(?:0?\d{1,2}))[- .)]?\d{3,4}[- .]?\d{4}(?!\d)",
        "[PHONE]", value,
    )
    value = re.sub(r"(?i)((?:jsessionid|dmcsession|sessionid)\s*[=:]\s*[\"']?)[A-Za-z0-9._~-]+",
                   r"\1[REDACTED]", value)
    return value

class OfficialRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlparse(newurl)
        if parsed.scheme != "https" or parsed.hostname != HOST or parsed.username or parsed.password:
            raise ValueError("redirect outside official HTTPS host")
        return super().redirect_request(req, fp, code, msg, headers, newurl)

class VisiblePage(HTMLParser):
    def __init__(self, html: str):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.chunks: list[str] = []
        self.anchor = None
        self.anchors: list[dict] = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip += 1
        if self.skip:
            return
        values = dict(attrs)
        if tag == "a":
            self.anchor = {"href": values.get("href", ""), "text": [], "position": len(self.chunks)}
        for key in ("alt", "aria-label"):
            value = norm(values.get(key, ""))
            if value and "님의 프로필" not in value:
                self.chunks.append(value)

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag == "a" and self.anchor is not None:
            self.anchor["text"] = norm(" ".join(self.anchor["text"]))
            self.anchors.append(self.anchor)
            self.anchor = None

    def handle_data(self, data):
        if self.skip:
            return
        value = norm(data)
        if not value:
            return
        self.chunks.append(value)
        if self.anchor is not None:
            self.anchor["text"].append(value)

def decode_response(raw: bytes, charset: str | None) -> str:
    for encoding in (charset, "utf-8", "cp949"):
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
    with build_opener(OfficialRedirect()).open(req, timeout=20) as response:
        raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("response exceeds 2 MB pilot limit")
        return decode_response(raw, response.headers.get_content_charset()), hashlib.sha256(raw).hexdigest()

def parse_list(html: str, limit: int = LIMIT) -> list[dict]:
    page = VisiblePage(html)
    proposals = []
    seen = set()
    for anchor in page.anchors:
        absolute = urljoin(LIST_URL, anchor["href"])
        parsed = urlparse(absolute)
        sn = parse_qs(parsed.query).get("sn", [""])[0]
        if parsed.hostname != HOST or parsed.path != "/front/freeSuggest/view.do" or not sn.isdigit():
            continue
        title = sanitize(anchor["text"])
        if not title or re.match(r"^(?:공감수|비공감수|의견수|처리상태)", title) or sn in seen:
            continue
        nearby = norm(" ".join(page.chunks[anchor["position"]:anchor["position"] + 18]))
        date_match = re.search(r"20\d{2}[-./]\d{1,2}[-./]\d{1,2}", nearby)
        status_match = re.search(r"처리상태\s*([^\s]+(?:\s+[^\s]+)?)", nearby)
        proposals.append({
            "proposal_id": sn,
            "title": title[:220],
            "posted_date": date_match.group(0).replace(".", "-").replace("/", "-") if date_match else None,
            "listed_status": status_match.group(1)[:60] if status_match else None,
            "source_url": absolute,
        })
        seen.add(sn)
        if len(proposals) == limit:
            break
    if not proposals:
        raise ValueError("no proposal detail links found on official list")
    return proposals

HEARSAY = ("소문", "전해 들", "들었다고", "카더라", "라고 합니다", "라고 들", "누가 말")
FIRST_PERSON = ("저는", "제가", "저희 가족", "우리 가족", "직접 ", "이용하면서", "신청했", "방문했", "겪었", "거주하고", "살고 있", "통근하", "통학하")
FRICTION = ("불편", "부담", "피해", "거절", "반려", "대기", "방문", "이동", "시간", "비용", "막혔", "고장", "위험", "혼잡", "이용하지 못", "사용하지 못")
IDEA = ("제안", "도입", "설치", "개선", "바랍니다", "해주세요", "필요합니다", "시행해")

def matched_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term.strip() for term in terms if term in text]

def classify_text(text: str) -> dict:
    hearsay = matched_terms(text, HEARSAY)
    first = matched_terms(text, FIRST_PERSON)
    friction = matched_terms(text, FRICTION)
    idea = matched_terms(text, IDEA)
    if hearsay:
        category = "HEARSAY"
        plan = "전언의 원출처와 공식 시행·공고 자료 존재 여부를 먼저 확인한다."
    elif first and friction:
        category = "SELF_REPORTED_EXPERIENCE"
        plan = "제안자가 진술한 발생 절차·장소·시점을 공식 안내와 대조하고, 같은 조건에서 반복되는지 별도 당사자·현장 자료로 확인한다."
    elif idea:
        category = "POLICY_IDEA"
        plan = "현재 제도·절차가 실제로 없는지와 기존 대안의 적용 범위를 먼저 확인한다."
    else:
        category = "UNRESOLVED"
        plan = "발생 사실, 당사자성, 구체적 시민 부담을 원문과 공식 자료에서 추가 확인한다."
    return {
        "statement_type": category,
        "matched_basis": {
            "hearsay_terms": hearsay[:4],
            "first_person_terms": first[:4],
            "friction_terms": friction[:4],
            "idea_terms": idea[:4],
        },
        "claim_status": "UNVERIFIED",
        "verification_plan": plan,
        "editorial_question": "NOT_GENERATED",
        "article_gate": "NOT_EVALUATED",
    }

def relevant_detail_text(html: str, title: str) -> str | None:
    page = VisiblePage(html)
    text = sanitize(norm(" ".join(page.chunks)))
    needle = title.replace("...", "")[:12]
    position = text.find(needle) if needle else -1
    if position < 0:
        return None
    detail = text[position:position + 12000]
    for boundary in ("관련 제안", "다른 제안", "댓글 목록", "의견 목록"):
        end = detail.find(boundary)
        if end > 0:
            detail = detail[:end]
    return detail

def observe(fetcher=fetch, limit: int = LIMIT) -> dict:
    list_html, list_hash = fetcher(LIST_URL)
    proposals = parse_list(list_html, limit)
    rows = []
    for proposal in proposals:
        detail_html, detail_hash = fetcher(proposal["source_url"])
        detail_text = relevant_detail_text(detail_html, proposal["title"])
        classified = classify_text(detail_text) if detail_text is not None else {
            "statement_type": "UNRESOLVED",
            "matched_basis": {},
            "claim_status": "UNVERIFIED",
            "verification_plan": "목록 제목과 상세 원문의 대응을 확인한 후 다시 분류한다.",
            "editorial_question": "NOT_GENERATED",
            "article_gate": "NOT_EVALUATED",
        }
        rows.append({
            **proposal,
            "detail_sha256": detail_hash,
            "detail_text_characters_examined": len(detail_text or ""),
            "detail_scope": "TITLE_ANCHORED_BOUNDED_TEXT" if detail_text is not None else "UNCONFIRMED",
            **classified,
        })
    return {
        "schema": 1,
        "observed_at_kst": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds"),
        "source_url": LIST_URL,
        "coverage": f"FIRST_{len(rows)}_UNIQUE_PROPOSALS",
        "list_sha256": list_hash,
        "records": rows,
        "privacy": {
            "author_name_stored": False,
            "contact_stored": False,
            "raw_html_stored": False,
            "full_body_stored": False,
        },
        "interpretation_limits": [
            "분류는 원문 문구의 형식이며 사실 확인 결과가 아니다.",
            "공감·비공감·조회 수는 대표성이나 사실성 근거로 사용하지 않는다.",
            "직접 경험형도 독립 확인 전에는 기사 후보가 아니다.",
        ],
        "article_gate": "NOT_EVALUATED",
    }

def render(result: dict) -> str:
    lines = [
        "# 상상대로 서울 시민제안 원문 분류 시험", "",
        f"- 관측: {result['observed_at_kst']}",
        f"- 범위: 공식 목록 상단의 고유 제안 {len(result['records'])}건",
        "- 판정 경계: 문장 형식 분류만 수행. 사실 확인·질문 품질 평가·기사 판정은 하지 않음.",
        "- 저장 경계: 작성자명·연락처·원문 전체·원문 HTML을 저장하지 않음.", "",
    ]
    labels = {
        "SELF_REPORTED_EXPERIENCE": "당사자 경험 진술형",
        "HEARSAY": "전언·소문형",
        "POLICY_IDEA": "정책 아이디어형",
        "UNRESOLVED": "판별 대기",
    }
    for index, row in enumerate(result["records"], 1):
        lines += [
            f"## {index}. {row['title']}", "",
            f"- 게시일 후보: {row['posted_date'] or '확인 대기'}",
            f"- 문장 형식: **{labels[row['statement_type']]}**",
            "- 사실 상태: **미확인 주장**",
            f"- 첫 확인: {row['verification_plan']}",
            "- 편집 질문: 생성하지 않음",
            f"- [공식 원문]({row['source_url']})", "",
        ]
    lines += [
        "## 이 결과로 할 수 없는 판단", "",
        "- 시민 피해가 실제로 발생했다고 확정할 수 없습니다.",
        "- 제안 수나 공감 수로 서울 시민 전체의 관심을 추정할 수 없습니다.",
        "- 이 파일의 항목을 일일 브리핑·아이템 장부에 자동 등록할 수 없습니다.", "",
    ]
    return "\n".join(lines)

def main() -> int:
    result = observe()
    output = BASE / "output"
    output.mkdir(exist_ok=True)
    (output / "observation_latest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "review_queue_latest.md").write_text(render(result), encoding="utf-8")
    print(render(result))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
