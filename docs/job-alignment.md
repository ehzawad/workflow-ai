# Job-description alignment

This matrix maps the supplied role to concrete, runnable evidence. It distinguishes implemented behavior from planned integrations.

## Knowledge and vault management

| Role detail | Implemented evidence | Verification |
|---|---|---|
| Operational ownership of an executive Obsidian vault | Non-destructive taxonomy initialization, YAML frontmatter, stable naming, project maps of content, atomic writes, and a rebuildable search index | `uv run workflow-ai init`; open `vault/` in Obsidian |
| Structure and taxonomy | `src/workflow_ai/vault/taxonomy.py`, `docs/taxonomy.md`, and `VaultWriter` route meetings, projects, decisions, briefs, and unclassified notes into governed locations | Ingest both sample inputs and inspect generated paths/frontmatter |
| Ongoing maintenance | Re-indexing, source provenance, archive semantics, project indexes, audit events, a runbook, and a recurring maintenance cadence | `uv run workflow-ai reindex`; read `docs/runbook.md` |
| Consolidate meetings, projects, transcripts, and notes | `SourceDocument` normalizes input context; all providers emit a strict `KnowledgeArtifact` with summary, people, projects, topics, decisions, actions, risks, and questions | `uv run workflow-ai ingest ... --kind meeting` |
| Organized and retrievable formats | Human-readable Markdown is paired with an FTS5 index over title, body, tags, and projects | `uv run workflow-ai search "legal approval"` |
| Maintain an information-flow roadmap | A staged roadmap ties future automation to measured friction, success metrics, controls, and exit criteria | `docs/automation-roadmap.md` |

## Automation and systems design

| Role detail | Implemented evidence | Verification |
|---|---|---|
| Reduce manual coordination | Explicit commitments generate proposed stakeholder updates, owner emails, and due-date calendar review blocks | Ingest the leadership sample and run `workflow-ai outbox list` |
| Build AI systems with Claude and prompts | `AnthropicProvider` performs schema-constrained extraction and decision-brief generation through the same provider contract | Configure the Anthropic extra and run the golden evaluation |
| Advanced ChatGPT / JSON prompting | `OpenAIProvider` uses the Responses API structured parser with Pydantic models rather than fragile prose-to-JSON parsing | Configure the OpenAI extra and run the golden evaluation |
| Integrated tools for executive decisions | Bounded FTS retrieval, typed provider synthesis, source paths, uncertainty, options, and recommended next steps compose into a decision brief | `workflow-ai brief decision "..."` |
| Continuously evaluate automation | Workflow/audit state, extraction regression cases, approval state, dispatch failures, tests, and roadmap metrics make improvement measurable | `workflow-ai eval run`; `workflow-ai audit` |
| Strong system design and system creation | Explicit provider, vault, index, persistence, workflow, API, CLI, and dispatcher boundaries | `docs/architecture.md` |

## Executive coordination and support

| Role detail | Implemented evidence | Verification |
|---|---|---|
| Coordinate email, calendar, and stakeholder messaging | Channel-neutral `CommunicationDraft`; approval-gated outbox; local `.eml`, `.ics`, and `.md` exports; optional disabled-by-default webhook | Approve and dispatch a proposed item in filesystem mode |
| Keep context at hand | Fast local search, project links, daily briefs, and evidence-linked decision briefs | Search during the demo; inspect `60_Briefs/` |
| High-quality English writing | Prompts, stakeholder drafts, decision briefs, runbook, architecture, and templates use explicit ownership and uncertainty language | Inspect generated Markdown and outbox files |
| Attention to detail | Idempotency conflicts, source hashes, timezone-aware timestamps, strict schemas, path confinement, edit-revokes-approval, and state-checked dispatch | Run the tests and read the state machine |
| Fast-paced environment | Zero-key local mode, provider portability, CLI/API parity, retry-safe workflows, containerization, and CI | `bash scripts/demo.sh`; `docker compose up --build` |

## Qualification signals

The repository cannot prove years of employment, a degree, or prior executive-support tenure. It supplies direct engineering evidence relevant to those qualifications: typed contracts, state machines, transactional persistence, information architecture, retrieval, prompt boundaries, evaluation, tests, operational documentation, and deployment scaffolding.

## Deliberately not claimed

This version does not ingest `.eml`/`.ics` files as special formats, resolve contacts, inspect calendar free/busy, or mutate Gmail/Google Calendar/Slack. The connector boundary and review semantics are implemented; organization-specific OAuth, recipient policy, retention, and delivery idempotency remain roadmap work.
