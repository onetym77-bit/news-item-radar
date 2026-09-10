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

## 3. Manual collection test

The workflow `Collect source signals (manual test)` has no cron trigger. It consumes no API quota until a user manually starts it from the Actions tab.

A successful run:

1. checks out the repository,
2. checks that the three repository secrets exist,
3. runs the v2.3 collector,
4. runs the discovery-system validator,
5. stores raw run output as a GitHub Actions artifact for 14 days, and
6. commits only the four small quota and discovery-state files.

Do not add a schedule until a manual run has succeeded and its API usage report has been reviewed.

## 4. Scheduled migration order

1. Run the collector manually once.
2. Confirm YouTube response reasons, API-call counts, and new-signal yield.
3. Add the three KST collection times to the workflow.
4. Move editorial briefing and weekly audit jobs to online tasks that read this repository and the latest workflow artifact.
5. Pause the old Windows-local scheduled tasks only after the online replacements pass their first run.
