# Online operations

This repository separates code editing, credentialed collection, and editorial analysis.

## 1. Codex cloud environment

Create a Codex cloud environment for `onetym77-bit/news-item-radar`.

Recommended initial settings:

- Repository: `onetym77-bit/news-item-radar`
- Branch: `main`
- Setup script: leave empty
- Maintenance script: leave empty
- Agent internet access: off for ordinary code and policy edits
- Environment variables and secrets: leave empty for the initial code-editing environment

The current Python files use only the standard library, so no dependency installation is required.

## 2. GitHub Actions repository secrets

Add these values under **Settings → Secrets and variables → Actions**:

- `YOUTUBE_API_KEY`
- `NAVER_CLIENT_ID`
- `NAVER_CLIENT_SECRET`

Never add their values to a tracked file, issue, pull request, log, or chat.

## 3. Collection workflow

The workflow `Collect source signals` supports both scheduled and manual runs.

Scheduled collection times:

- 08:00 KST every day
- 12:00 KST every day
- 17:30 KST every day

The workflow declares `Asia/Seoul` explicitly. GitHub may start a scheduled job a few minutes late during periods of high load.

Manual inputs:

- `audit_all=false`: use the regular quota-controlled query rotation.
- `audit_all=true`: use the audit query budget. Run only when deliberately checking all configured agendas.
- `validation_only=true`: validate the online snapshot without calling YouTube or Naver.

A normal scheduled run:

1. checks out the latest `main` branch,
2. checks that the three repository secrets exist,
3. compiles the collectors and previews the selected queries without API calls,
4. runs the v2.3 collector with the regular quota policy,
5. validates the online repository snapshot,
6. stores raw run output as a GitHub Actions artifact for 14 days, and
7. commits only the four small quota and discovery-state files.

Collection state is persisted even if a later validation step fails, preventing the next run from undercounting API usage.

## 4. Remaining migration order

1. Confirm the first scheduled run and its state commit.
2. Pause the old Windows-local source-collection schedules to prevent duplicate API calls.
3. Move editorial briefing and weekly audit jobs to online tasks that read this repository and the latest workflow artifact.
4. Pause each remaining local task only after its online replacement passes its first run.
