# Operations runbook

## Start locally

```zsh
cp .env.example .env
uv sync --group dev
uv run workflow-ai init
uv run workflow-ai serve --host 127.0.0.1 --port 8080
```

Validate:

```zsh
curl -fsS http://127.0.0.1:8080/healthz | jq
uv run workflow-ai search "test"
```

## Important paths

| Path | Purpose |
|---|---|
| `vault/` | Obsidian-compatible Markdown source of organizational knowledge |
| `.workflow-ai/workflow.sqlite` | workflow runs, outbox state, and audit events |
| `.workflow-ai/vault-index.sqlite` | rebuildable FTS5 index |
| `.workflow-ai/dispatch/` | local exported `.eml`, `.ics`, and `.md` files |

Paths can be relocated with `WORKFLOW_AI_WORKSPACE_ROOT`, `WORKFLOW_AI_VAULT_PATH`, and `WORKFLOW_AI_RUNTIME_PATH`, but vault/runtime must remain beneath the workspace root.

## Routine operations

### Ingest

```zsh
uv run workflow-ai ingest path/to/note.md \
  --kind meeting \
  --project "Project Name" \
  --participant "Person Name" \
  --stakeholder chief-of-staff@example.com
```

Use `--idempotency-key` when the upstream system has a stable source/event ID. Reusing that key for different content returns a conflict instead of silently overwriting state.

### Rebuild search

```zsh
uv run workflow-ai reindex
```

Run after manually moving or editing many vault files. The index is derived and can be deleted/rebuilt; `workflow.sqlite` is not derived.

### Review communication proposals

```zsh
uv run workflow-ai outbox list --status proposed
uv run workflow-ai outbox approve <ID> --actor "Operator Name"
uv run workflow-ai outbox dispatch <ID> --actor "Operator Name" --mode filesystem
```

Inspect the exported file before using it in a real email/calendar tool. Never edit database status manually to bypass approval.

### Audit workflow history

```zsh
uv run workflow-ai audit --limit 100
uv run workflow-ai audit --run-id <RUN_ID>
```

Audit output is operational metadata, not the source transcript. Inspect the linked Markdown note when semantic context is needed.

## Backup

Stop writers or take an application-consistent snapshot. Back up both knowledge and transactional state:

```zsh
mkdir -p backups
stamp=$(date -u +%Y%m%dT%H%M%SZ)
tar -czf "backups/workflow-ai-${stamp}.tar.gz" vault .workflow-ai
```

Store backups encrypted and test restore regularly. The dispatch directory may contain recipient information and message text; classify it with the vault, not as harmless cache.

## Restore

```zsh
mv vault "vault.before-restore.$(date +%s)"
mv .workflow-ai ".workflow-ai.before-restore.$(date +%s)"
tar -xzf backups/workflow-ai-<STAMP>.tar.gz
uv run workflow-ai reindex
uv run workflow-ai eval run --dataset evals/golden.jsonl --minimum-score 0.95
```

Then perform a read-only smoke test: health, search, outbox list, and audit. Do not dispatch during restore validation.

## Incident: provider failure

1. Check the configured provider, API key, model ID, and provider status.
2. Inspect the failed run and audit event; avoid copying confidential source text into an issue.
3. Confirm whether the provider received the request before retrying.
4. Retry with the same idempotency key only when the existing run is failed/stale; a concurrent run intentionally conflicts.
5. Use the deterministic provider for local system validation, not as a semantic substitute for production extraction.

## Incident: search returns poor or no results

1. Confirm the source note exists in `vault/`.
2. Run `workflow-ai reindex`.
3. Search for a distinctive project/name phrase.
4. Inspect frontmatter and Markdown encoding if the note was manually edited.
5. Add the operator question and expected source to a labeled retrieval set before changing retrieval architecture.

## Incident: stuck outbox item

- `proposed`: needs review/approval.
- `approved`: eligible for dispatch.
- `failed`: inspect `error`; edit or explicitly re-approve before retry.
- `dispatched`: terminal for content edits; create a new draft for corrections.

A repeated dispatch call for an already dispatched record returns the stored state and does not create another local export.

## Incident: suspected credential exposure

1. Stop the service and disable live dispatch.
2. Revoke and rotate the credential at its issuer.
3. Search the vault, workflow database, dispatch directory, logs, backups, and Git history.
4. Remove or re-encrypt affected artifacts according to organizational policy.
5. Rebuild the FTS index after vault cleanup.
6. Add a regression/control that would have prevented the exposure.

The application does not provide DLP or automatic source redaction.

## Maintenance cadence

Daily: process new sources, review failed runs and proposed drafts, generate the daily brief, and correct wrong owners/dates promptly.

Weekly: reindex after major manual edits, sample retrieval quality, review high risks and overdue actions, and inspect dispatch failures.

Monthly: restore-test a backup, run the complete verification suite, review dependency updates, archive completed projects, and update the information-flow roadmap using observed friction.
