#!/usr/bin/env bash
set -euo pipefail

export WORKFLOW_AI_LLM_PROVIDER=deterministic

uv run workflow-ai init
uv run workflow-ai ingest examples/inputs/leadership-sync.txt \
  --kind meeting \
  --project "Atlas Launch" \
  --stakeholder chief-of-staff@example.com
uv run workflow-ai search "legal approval onboarding"
uv run workflow-ai brief daily --date 2026-07-31
uv run workflow-ai brief decision "Should Atlas keep the August 18 launch date?"
uv run workflow-ai outbox list --status proposed
uv run workflow-ai eval run --dataset evals/golden.jsonl --minimum-score 0.95

cat <<'MSG'

The demo intentionally stops before approval. Review a proposed outbox item, then run:

  uv run workflow-ai outbox approve <OUTBOX_ID> --actor "Your Name"
  uv run workflow-ai outbox dispatch <OUTBOX_ID> --actor "Your Name" --mode filesystem

The resulting .eml, .ics, or .md file will appear under .workflow-ai/dispatch/.
MSG
