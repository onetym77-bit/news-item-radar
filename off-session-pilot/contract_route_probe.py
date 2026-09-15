#!/usr/bin/env python3
"""Read-only route probe for Seoul construction contract popups.

This is connection diagnostics, not a discovery collector or article gate.
Only two official lists and at most four same-host JavaScript assets are read.
No full HTML, scripts, cookies, or personal data are saved.
"""
import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.request import Request, build_opener

from probe_sources import OfficialRedirect, Page, same_host, sanitize

ORIGIN = "https://cis.seoul.go.kr"
LISTS = {
    "C_LIST": ORIGIN + "/TotalAlimi_new/CnrtList.action",
    "C_PAYMENTS": ORIGIN + "/TotalAlimi_new/CnrtExList.action",
}
MAX_BYTES = 1_000_000
CALL = re.compile(r"^\s*cmdPopInfo\(\s*(.*?)\s*\)\s*;?\s*$", re.S)
ARG = re.compile(r"'([^']{1,80})'|\"([^\"]{1,80})\"")
ACTION = re.compile(r"['\"]([^'\"\s]{1,180}\.action(?:\?[^'\"\s]{0,120})?)['\"]")
FUNCTION = re.compile(r"(?:function\s+cmdPopInfo\s*\(|cmdPopInfo\s*=\s*function\s*\()")

class Scripts(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.sources = []
        self.inline = []
        self.active = False
        self.buffer = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            src = dict(attrs).get("src")
            if src:
                self.sources.append(src)
            else:
                self.active = True
                self.buffer = []

    def handle_data(self, data):
        if self.active:
            self.buffer.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.active:
            self.inline.append("".join(self.buffer))
            self.active = False
            self.buffer = []

def parse_call(onclick):
    match = CALL.fullmatch(onclick or "")
    if not match:
        return None
    raw = match.group(1)
    args = [left or right for left, right in ARG.findall(raw)]
    # Reject any intervening executable expression; these calls must consist
    # only of quoted strings separated by commas.
    stripped = ARG.sub("", raw)
    if re.sub(r"[\s,]", "", stripped) or len(args) not in (3, 4):
        return None
    if not re.fullmatch(r"[A-Za-z0-9]{4,30}", args[0]):
        return None
    if not re.fullmatch(r"R\d{2}TA\d{8,14}", args[1]):
        return None
    return {"record_key": args[0], "contract_id": args[1],
            "installment": args[2] if len(args) == 4 else None,
            "argument_count": len(args)}

def first_entries(html, limit=5):
    entries = []
    for anchor in Page(html).anchors:
        parsed = parse_call(anchor["onclick"])
        if parsed and anchor["text"]:
            entries.append({"title": sanitize(anchor["text"])[:180], **parsed})
        if len(entries) >= limit:
            break
    return entries

def function_body(script):
    match = FUNCTION.search(script)
    if not match:
        return None
    opening = script.find("{", match.end())
    if opening < 0 or opening - match.end() > 400:
        return None
    depth = 0
    for index in range(opening, min(len(script), opening + 5000)):
        if script[index] == "{":
            depth += 1
        elif script[index] == "}":
            depth -= 1
            if depth == 0:
                return script[match.start():index + 1]
    return None

def route_evidence(scripts):
    bodies = [body for script in scripts if (body := function_body(script))]
    if not bodies:
        return {"function_status": "NOT_FOUND", "action_paths": [],
                "transport_hints": []}
    body = bodies[0]
    actions = list(dict.fromkeys(ACTION.findall(body)))[:8]
    hints = [name for name in ("window.open", "ajax", "submit", "form.action",
                              "location.href") if name in body]
    popup_at = body.find("window.open")
    popup_expression = sanitize(body[popup_at:popup_at + 450]) if popup_at >= 0 else ""
    return {"function_status": "FOUND", "action_paths": actions,
            "transport_hints": hints, "popup_expression": popup_expression}

def official_script_urls(sources, list_url):
    urls = []
    for src in sources:
        url = urljoin(list_url, src)
        path = urlparse(url).path
        if same_host(url, list_url) and path.endswith(".js") and url not in urls:
            urls.append(url)
    return urls[:4]

def read_text(url):
    if not same_host(url, ORIGIN):
        raise ValueError("outside official HTTPS host")
    request = Request(url, headers={
        "User-Agent": "NewsItemRadarReadOnlyPilot/1.0",
        "Accept-Language": "ko",
    })
    with build_opener(OfficialRedirect()).open(request, timeout=18) as response:
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("response exceeds 1 MB route limit")
        for encoding in (response.headers.get_content_charset(), "utf-8", "cp949"):
            if encoding:
                try:
                    return raw.decode(encoding)
                except (UnicodeDecodeError, LookupError):
                    pass
    raise ValueError("unknown text encoding")

def inspect_route(sample_id, html, linked_assets=None):
    scripts = Scripts(html)
    entries = first_entries(html)
    inline = route_evidence(scripts.inline)
    result = {
        "sample_id": sample_id,
        "entry_count_checked": len(entries),
        "first_entries": entries[:3],
        "same_contract_in_first_five": len(entries) >= 2 and
            len({item["contract_id"] for item in entries}) == 1,
        "inline_route": inline,
        "same_host_script_paths": [urlparse(url).path for url in
                                   official_script_urls(scripts.sources, LISTS[sample_id])],
        "external_route": route_evidence(linked_assets or []),
        "detail_fetch": "NOT_ATTEMPTED",
        "change_history": "NOT_VERIFIED",
        "progress_link": "NOT_VERIFIED",
        "article_gate": "NOT_EVALUATED",
    }
    return result

def main():
    for sample_id, url in LISTS.items():
        try:
            html = read_text(url)
            scripts = Scripts(html)
            assets = []
            asset_errors = []
            if route_evidence(scripts.inline)["function_status"] == "NOT_FOUND":
                for asset in official_script_urls(scripts.sources, url):
                    try:
                        assets.append(read_text(asset))
                    except Exception as exc:
                        asset_errors.append(sanitize(str(exc))[:120])
            result = inspect_route(sample_id, html, assets)
            result["external_asset_errors"] = asset_errors[:4]
            result["access"] = "HTTP_TEXT_RECEIVED"
        except Exception as exc:
            result = {"sample_id": sample_id, "access": "FAILED",
                      "error": sanitize(str(exc))[:180],
                      "detail_fetch": "NOT_ATTEMPTED",
                      "article_gate": "NOT_EVALUATED"}
        print("CONTRACT_ROUTE " + json.dumps(result, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
