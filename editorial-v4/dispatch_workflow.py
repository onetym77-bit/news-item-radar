#!/usr/bin/env python3
"""Dispatch one workflow on main and wait for the exact new run."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API_ROOT = "https://api.github.com"

def parse_inputs(values):
    inputs = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"입력은 key=value 형식이어야 합니다: {value}")
        name, content = value.split("=", 1)
        if not name.strip():
            raise ValueError("빈 입력 이름")
        inputs[name.strip()] = content
    return inputs

def choose_new_run(before_ids, runs):
    candidates = [
        run for run in runs
        if str(run.get("id")) not in before_ids
        and run.get("event") == "workflow_dispatch"
        and run.get("head_branch") == "main"
    ]
    candidates.sort(key=lambda run: (run.get("created_at") or "", int(run.get("id") or 0)))
    return candidates[-1] if candidates else None

class GitHub:
    def __init__(self, repository, token):
        self.repository = repository
        self.token = token

    def request(self, method, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            API_ROOT + path,
            data=data,
            method=method,
            headers={
                "Authorization": "Bearer " + self.token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
                "User-Agent": "news-item-radar-fresh-cycle",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read()
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"GitHub API {error.code}: {detail}") from error
        return json.loads(body) if body else {}

    def list_runs(self, workflow):
        encoded = urllib.parse.quote(workflow, safe="")
        data = self.request(
            "GET",
            f"/repos/{self.repository}/actions/workflows/{encoded}/runs"
            "?event=workflow_dispatch&branch=main&per_page=100",
        )
        return data.get("workflow_runs", [])

    def dispatch(self, workflow, inputs):
        encoded = urllib.parse.quote(workflow, safe="")
        self.request(
            "POST",
            f"/repos/{self.repository}/actions/workflows/{encoded}/dispatches",
            {"ref": "main", "inputs": inputs},
        )

    def get_run(self, run_id):
        return self.request("GET", f"/repos/{self.repository}/actions/runs/{run_id}")

def append_outputs(result):
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as handle:
        for key in ("run_id", "run_url", "head_sha", "conclusion", "completed_at"):
            handle.write(f"{key}={result.get(key, '')}\n")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--input", action="append", default=[])
    parser.add_argument("--timeout-seconds", type=int, default=5400)
    parser.add_argument("--poll-seconds", type=int, default=10)
    parser.add_argument("--result")
    args = parser.parse_args()

    repository = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
    if not repository or not token:
        raise RuntimeError("GITHUB_REPOSITORY 또는 GH_TOKEN 미설정")

    client = GitHub(repository, token)
    before_ids = {str(run.get("id")) for run in client.list_runs(args.workflow)}
    inputs = parse_inputs(args.input)
    print(f"dispatch {args.workflow} inputs={list(inputs)}", flush=True)
    client.dispatch(args.workflow, inputs)

    deadline = time.monotonic() + args.timeout_seconds
    selected = None
    while time.monotonic() < deadline:
        selected = choose_new_run(before_ids, client.list_runs(args.workflow))
        if selected:
            break
        time.sleep(args.poll_seconds)
    if not selected:
        raise TimeoutError(f"새 실행을 찾지 못했습니다: {args.workflow}")

    run_id = int(selected["id"])
    run_url = selected.get("html_url", "")
    print(f"run_id={run_id} url={run_url}", flush=True)
    while time.monotonic() < deadline:
        current = client.get_run(run_id)
        status = current.get("status")
        conclusion = current.get("conclusion") or ""
        print(f"{args.workflow}: {status}/{conclusion or 'pending'}", flush=True)
        if status == "completed":
            result = {
                "workflow": args.workflow,
                "run_id": run_id,
                "run_url": current.get("html_url", run_url),
                "head_sha": current.get("head_sha", ""),
                "conclusion": conclusion,
                "completed_at": current.get("updated_at", ""),
            }
            if args.result:
                target = Path(args.result)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            append_outputs(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
            if conclusion != "success":
                raise RuntimeError(f"{args.workflow} 실행 실패: {conclusion}")
            return
        time.sleep(args.poll_seconds)
    raise TimeoutError(f"실행 완료 대기 시간 초과: {args.workflow} #{run_id}")

if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"::error::{error}", file=sys.stderr)
        raise
