#!/usr/bin/env python3
"""Bounded read-only probe, not a daily collector or editorial gate."""
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, HTTPRedirectHandler, build_opener

BASE = Path(__file__).resolve().parent
SOURCES = [
    ("E1", "https://eungdapso.seoul.go.kr/gud/chart/chart_progress.do"),
    ("C_LIST", "https://cis.seoul.go.kr/TotalAlimi_new/CnrtList.action"),
    ("C_PAYMENTS", "https://cis.seoul.go.kr/TotalAlimi_new/CnrtExList.action"),
    ("P_LIST", "https://idea.seoul.go.kr/front/allSuggest/list.do?tab=cateAll"),
    ("P1", "https://idea.seoul.go.kr/front/freeSuggest/view.do?pageIndex=1&sDiscussionSn=&sKind=M&sPracticeSn=&sRegDateE=&sRegDateS=&sSuggest_divi=&searchCondition=&searchCondition2=1&searchCondition3=&searchKeyword=&searchSYear=&searchUseYn=Y&sn=202770&suggestask_sn="),
    ("P2", "https://idea.seoul.go.kr/front/freeSuggest/view.do?pageIndex=1&sDiscussionSn=&sKind=M&sPracticeSn=&sRegDateE=&sRegDateS=&sSuggest_divi=&searchCondition=&searchCondition2=1&searchCondition3=&searchKeyword=&searchSYear=&searchUseYn=Y&sn=202769&suggestask_sn="),
    ("P3", "https://idea.seoul.go.kr/front/freeSuggest/view.do?pageIndex=1&sDiscussionSn=&sKind=M&sPracticeSn=&sRegDateE=&sRegDateS=&sSuggest_divi=&searchCondition=&searchCondition2=1&searchCondition3=&searchKeyword=&searchSYear=&searchUseYn=Y&sn=202768&suggestask_sn="),
]
MARKERS = ("다자녀", "특정건축물", "불꽃축제", "천왕산", "별빛내린천", "구봉산", "풍납2동")
def norm(value):
    return re.sub(r"\s+", " ", value).strip()

def sanitize(value):
    value = re.sub(r"(?i)((?:jsessionid|dmcsession|sessionid)\s*[=:]\s*[\"']?)[A-Za-z0-9._~-]+",
                   r"\1[REDACTED]", value)
    value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[EMAIL]", value)
    # Common Korean domestic and +82 contact formats; sanitize before truncating.
    return re.sub(r"(?<!\d)(?:0\d{1,2}|\+82[- .]?(?:0?\d{1,2}))[- .)]?\d{3,4}[- .]?\d{4}(?!\d)",
                  "[PHONE]", value)

class Page(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.chunks = []
        self.title = []
        self.in_title = False
        self.anchor = None
        self.anchors = []
        self.feed(html)
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip += 1
        if self.skip:
            return
        attrs = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag == "a":
            self.anchor = {"href":attrs.get("href",""), "onclick":attrs.get("onclick",""), "text":[]}
        # Accessible chart values may be in image alt or aria labels.
        for key in ("alt","aria-label"):
            if attrs.get(key) and "님의 프로필" not in attrs[key]:
                self.chunks.append(norm(attrs[key]))
    def handle_endtag(self, tag):
        if tag in ("script","style","noscript"):
            self.skip = max(0,self.skip-1)
        if self.skip:
            return
        if tag == "title":
            self.in_title = False
        if tag == "a" and self.anchor is not None:
            self.anchor["text"] = norm(" ".join(self.anchor["text"]))
            self.anchors.append(self.anchor)
            self.anchor = None
    def handle_data(self, text):
        if self.skip or not norm(text):
            return
        text = norm(text)
        self.chunks.append(text)
        if self.in_title:
            self.title.append(text)
        if self.anchor is not None:
            self.anchor["text"].append(text)

def same_host(url, original):
    p = urlparse(url)
    return p.scheme == "https" and p.hostname == urlparse(original).hostname and not p.username and not p.password

class OfficialRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not same_host(newurl,req.full_url):
            raise ValueError("Redirect outside the original official HTTPS host")
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def inspect(html, sample_id=""):
    page = Page(html)
    text = sanitize(norm(" ".join(page.chunks)))
    anchors = [{k:sanitize(v)[:400] for k,v in a.items()}
               for a in page.anchors if any(m in a["text"] for m in MARKERS)][:8]
    list_entries = []
    seen = set()
    for anchor in page.anchors:
        key = None
        parsed = urlparse(anchor["href"])
        sn = parse_qs(parsed.query).get("sn",[""])[0]
        if sample_id == "P_LIST" and parsed.path == "/front/freeSuggest/view.do" and sn.isdigit():
            if not re.match(r"^(?:공감수|비공감수|의견수|처리상태)",anchor["text"]):
                key = ("proposal",sn)
        elif sample_id in ("C_LIST","C_PAYMENTS") and "cmdPopInfo(" in anchor["onclick"]:
            key = ("contract_link",anchor["onclick"])
        if key is not None and anchor["text"] and key not in seen:
            seen.add(key)
            list_entries.append({k:sanitize(v)[:400] for k,v in anchor.items()})
        if len(list_entries) == 3:
            break
    dates = list(dict.fromkeys(re.findall(r"20\d{2}[.\-/]\s*\d{1,2}[.\-/]\s*\d{1,2}",text)))[:12]
    stats = {}
    for label in ("기간 내 민원 건 수","서울시","자치구","강남구","광진구","교통"):
        match = re.search(re.escape(label)+r"\s*[:(]?\s*([\d,]+)\s*건",text)
        if match:
            stats[label] = int(match.group(1).replace(",",""))
    # A short, redacted excerpt is diagnostic context, never proof of a full parsed record.
    snippets = []
    for marker in MARKERS:
        at = text.find(marker)
        if at >= 0:
            snippets.append({"marker":marker,"text":text[at:at+450]})
        if len(snippets) == 2:
            break
    return {"title":sanitize(norm(" ".join(page.title)))[:300], "text_characters":len(text),
            "first_three_linked_entries":list_entries,
            "sample_anchors":anchors, "visible_dates":dates,
            "stat_values":stats, "diagnostic_excerpts":snippets,
            "full_record_parse":"NOT_IMPLEMENTED", "article_gate":"NOT_EVALUATED"}

def fetch(sample_id,url):
    started=time.monotonic()
    result={"sample_id":sample_id,"url":url,"fetched_at":datetime.now(timezone.utc).isoformat(),
            "http_status":None,"access":"FAILED","attempts":0}
    for attempt in range(2):
        if attempt:
            time.sleep(1)
        result["attempts"] += 1
        try:
            req=Request(url,headers={"User-Agent":"NewsItemRadarReadOnlyPilot/1.0","Accept-Language":"ko"})
            with build_opener(OfficialRedirect()).open(req,timeout=18) as res:
                raw=res.read(3_000_001)
                if len(raw)>3_000_000:
                    raise ValueError("Response exceeds 3 MB probe limit")
                result.update(http_status=res.status,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
                for encoding in (res.headers.get_content_charset(),"utf-8","cp949"):
                    if not encoding:
                        continue
                    try:
                        html=raw.decode(encoding)
                        break
                    except (UnicodeDecodeError,LookupError):
                        pass
                else:
                    raise ValueError("Unknown text encoding")
                result.update(access="HTTP_TEXT_RECEIVED",**inspect(html,sample_id))
                result.pop("error",None)
                break
        except (HTTPError,URLError,TimeoutError,OSError,ValueError) as exc:
            result["error"]=sanitize(str(exc))[:220]
            if isinstance(exc,HTTPError):
                result["http_status"]=exc.code
            if not (attempt==0 and "name resolution" in str(exc)):
                break
    result["elapsed_ms"]=round((time.monotonic()-started)*1000)
    return result

def main():
    results=[]
    blocked=set()
    for sample_id,url in SOURCES:
        host=urlparse(url).hostname
        if host in blocked:
            result={"sample_id":sample_id,"url":url,"access":"SKIPPED_AFTER_403_OR_429"}
        else:
            if results:
                time.sleep(1)
            result=fetch(sample_id,url)
            if result.get("http_status") in (403,429):
                blocked.add(host)
        results.append(result)
        print("PROBE "+json.dumps(result,ensure_ascii=False))
    output=BASE/"output"
    output.mkdir(exist_ok=True)
    (output/"connection_probe.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
    return 0  # diagnostic execution success != source extraction success

if __name__=="__main__":
    raise SystemExit(main())
