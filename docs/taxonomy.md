# Vault taxonomy and maintenance policy

## Design goals

The taxonomy should answer four questions quickly:

1. What has not yet been processed?
2. Which outcome, person, decision, or area does this information belong to?
3. What should the executive know or do next?
4. Where did the claim come from?

Folder structure is used for lifecycle and broad object type. YAML properties and links carry cross-cutting dimensions such as project, topic, people, sensitivity, date, and workflow run.

## Folders

| Folder | Meaning | Maintenance rule |
|---|---|---|
| `00_Inbox` | Notes and emails that do not yet have a stronger destination | Process daily; do not allow permanent dumping |
| `10_People` | Stakeholder and relationship context | One canonical note per person; avoid sensitive gossip |
| `20_Meetings` | Meetings and transcripts grouped by year | Capture decisions and actions in the same intake cycle |
| `30_Projects` | Time-bounded outcomes | Maintain a project README/MOC and archive after completion |
| `40_Decisions` | Durable decision records | Record rationale, owner, evidence, reversibility, review date |
| `50_Areas` | Ongoing responsibility | Review monthly for health and stale obligations |
| `60_Briefs` | Daily and decision briefs | Treat as derived synthesis with source links |
| `70_Resources` | Reference material | Link to the project/area that justifies retention |
| `90_Archive` | Inactive or superseded material | Preserve provenance; do not use as default current context |
| `Templates` | Human-authored note templates | Version changes carefully because they shape future records |

## Required properties on generated artifacts

- `title`
- `type`
- `date`
- `status`
- `sensitivity`
- `projects`
- `topics`
- `participants`
- `tags`
- `workflow_ai.schema_version`
- `workflow_ai.run_id`
- `workflow_ai.source_name`
- `workflow_ai.source_hash`
- `workflow_ai.ingested_at`
- `workflow_ai.artifact`

The nested `workflow_ai.artifact` object is machine-readable. The note body is optimized for human scanning. Both derive from the same Pydantic object to prevent semantic drift.

## Naming

Generated filenames use ISO date, a lowercase slug, and—where collision risk is high—a source-hash suffix. Names should remain stable if the same source is retried.

Examples:

```text
20_Meetings/2026/2026-07-30-product-launch-leadership-sync.md
30_Projects/atlas-launch/2026-07-31-atlas-infrastructure-update.md
00_Inbox/2026-07-31-vendor-email-a31f8d20.md
60_Briefs/2026/2026-07-31-daily-brief.md
```

## Link policy

- Link artifacts to project maps when a project is known.
- Link decision briefs to every retrieved evidence note.
- Prefer a canonical note over several spelling variants.
- Suggested links extracted from content are proposals, not guaranteed matches.
- Avoid linking merely because two notes share a common generic word.

## Lifecycle

### Daily

- ingest new source material;
- review failed workflows;
- process proposed communications;
- generate or review the daily brief;
- resolve obviously wrong owners, dates, or project classification.

### Weekly

- review Inbox age;
- inspect projects without recent updates;
- close or reassign stale action items;
- review high/critical risks;
- sample search results for retrieval quality;
- review automation metrics.

### Monthly

- archive completed projects;
- merge duplicate people/project notes;
- review taxonomy exceptions;
- refresh templates;
- run the full evaluation suite before provider or prompt changes.
