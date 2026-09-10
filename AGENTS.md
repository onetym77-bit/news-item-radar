# Repository instructions

## Source of truth

Read `agent-system-v1/SYSTEM_MANIFEST.md` before changing the discovery system. Files not named by the manifest are not automatically active.

## Change rules

- Preserve Korean text as UTF-8.
- Keep source collection, question-quality review, evidence testing, and final article gating as separate stages.
- Do not turn an unverified hypothesis into a final article candidate.
- Do not commit API keys, secrets, raw source archives, bulk generated output, or local machine paths.
- Use environment variables for `YOUTUBE_API_KEY`, `NAVER_CLIENT_ID`, and `NAVER_CLIENT_SECRET`.
- Keep the four tracked YouTube state files under `interest-radar-v2/output/`; do not commit `source_material_*.json` or `source_material_latest.txt`.
- Git history replaces local snapshot folders. Do not add new files under `agent-system-v1/snapshots/`.
- Modify ledgers and editorial feedback only when the task explicitly requires a state transition or recorded editorial decision.

## Validation

After policy, configuration, collector, ledger, or briefing-gate changes, run:

```bash
python agent-system-v1/validate_discovery_system.py
```

Report validation results and any files intentionally excluded from the change.
