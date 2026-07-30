# Job-description-to-system mapping

This document translates every visible responsibility and qualification in the supplied role into a concrete engineering artifact, an operating behavior, and a verification path.

## Knowledge and vault management

### “Take operational ownership of the executive's Obsidian knowledge vault, including structure, taxonomy, and ongoing maintenance”

**System response**

- `src/workflow_ai/vault/taxonomy.py` creates an opinionated but non-destructive hierarchy: Inbox, People, Meetings, Projects, Decisions, Areas, Briefs, Resources, Archive, and Templates.
- `src/workflow_ai/vault/writer.py` produces ordinary Markdown with YAML properties that Obsidian can read without a plugin.
- Project names create maps of content under `30_Projects/<slug>/README.md`.
- `workflow-ai init` is safe to rerun: existing notes are not overwritten.
- `workflow-ai reindex` repairs or refreshes the derived search index from the Markdown source of truth.

**Operational behavior**

The role is not merely “write notes.” Operational ownership means defining naming rules, preventing duplicate records, preserving provenance, maintaining retrieval quality, and making the structure legible to another operator. The runbook therefore includes daily inbox processing, weekly taxonomy review, monthly archive review, and recovery steps.

**Verification**

- `tests/test_vault.py`
- `tests/test_intake.py::test_project_index_is_created`
- `workflow-ai init && workflow-ai reindex`

### “Consolidate large volumes of information from meetings, projects, transcripts, and notes into organized, retrievable formats”

**System response**

- `SourceDocument.kind` distinguishes meetings, transcripts, project updates, notes, email, decisions, and briefs.
- All providers emit the same `KnowledgeArtifact` contract.
- Artifacts contain summary, participants, projects, topics, decisions, actions, risks, open questions, suggested links, sensitivity, and occurrence time.
- The original source remains embedded in a collapsed provenance section.
- SQLite FTS5 indexes note title, body, tags, and projects for local retrieval.
- Intake is content-hashed and idempotent, preventing accidental duplication when transcripts are retried or re-uploaded.

**Minor detail captured**

“Organized” and “retrievable” are separate properties. A taxonomically correct note can still be hard to find; a search hit can still lack trustworthy provenance. The system provides both deterministic placement and a separate rebuildable retrieval index.

### “Develop and maintain a roadmap for ongoing knowledge management and information-flow improvements”

**System response**

- `docs/automation-roadmap.md` describes capability stages, success metrics, risks, and exit criteria.
- `docs/architecture.md` exposes current system constraints rather than burying them.
- `docs/adr/0001-local-first-obsidian.md` records why Markdown is durable while SQLite is derived.
- Audit events support measurement of intake failures, queue size, approval latency, and dispatch failures.
- Golden evaluations create a regression gate before prompts or providers are changed.

## Automation and systems design

### “Design and build automation workflows that reduce manual coordination work for the executive”

**System response**

The communication planner converts explicit commitments into proposals:

- stakeholder update draft from summary, decisions, actions, and risks;
- email follow-up when an action owner is an email address;
- tentative calendar review block when an action has a due date.

The design reduces copy/paste and omission risk while retaining a human authorization boundary.

### “Build and refine AI-driven systems using Claude, prompts, and integrated tools to support executive decision-making”

**System response**

- The Anthropic adapter uses schema-constrained Pydantic output.
- The OpenAI adapter implements the same contract for portability and comparative evaluation.
- The deterministic provider permits offline operation, tests, and graceful degradation.
- Decision briefs retrieve bounded vault evidence before synthesis and require uncertainties and evidence references.
- Prompts explicitly distinguish source data from instruction to reduce prompt-injection risk.
- Provider selection and model identifiers are configuration, so model changes do not leak into domain logic.

**Minor detail captured**

The phrase “using Claude, prompts, and integrated tools” implies more than conversational fluency. The repository demonstrates prompt contracts, JSON-schema discipline, provider adapters, retrieval context construction, tool-side effect separation, evaluation, and error handling.

### “Continuously evaluate where new automation, tooling, or system redesign can reduce friction or increase throughput”

**System response**

Potential bottlenecks are observable through:

- workflow status and timestamps;
- duplicate/reused intake rate;
- extraction failure type;
- number of proposed messages per artifact;
- time from proposal to approval;
- failed dispatch rate;
- search/evaluation quality.

The roadmap ties each new automation to a measurable friction signal rather than adding tools because they are fashionable.

## Executive coordination and support

### “Coordinate executive communications across email, calendar, and stakeholder messaging”

**System response**

`CommunicationDraft` is a channel-neutral contract supporting:

- recipients, subject, body;
- calendar start/end, timezone, and location;
- metadata needed by downstream adapters.

The outbox is a state machine:

```text
proposed ──edit──> proposed
proposed ──approve──> approved
approved ──edit──> proposed       # approval is revoked
approved ──dispatch──> dispatched
approved ──failure──> failed
failed ──approve──> approved      # explicit retry authorization
```

The default dispatcher creates `.eml`, `.ics`, and `.md` files. Network dispatch must be explicitly enabled.

### “Partner directly with the executive in meetings and async work to ensure context and information are always at hand”

**System response**

- Fast local search provides context during meetings.
- Project links and maps of content make related notes navigable in Obsidian.
- Daily briefs surface priorities, overdue/high-priority actions, decisions, risks, and open questions.
- Decision briefs package retrieved evidence, options, uncertainties, recommendation, and next steps.
- Source paths remain available for immediate inspection instead of hiding the basis of a summary.

## Must-have signals

### 3–5+ years in an engineering role

The repository cannot prove tenure, but it provides evidence expected from an experienced engineer: explicit boundaries, state transitions, idempotency, auditability, tests, CI, containerization, typed contracts, failure semantics, and documented tradeoffs.

### Strong system design, system creation, taxonomy, and organizational systems

Evidence includes the architecture document, vault taxonomy, domain model, workflow state machines, storage split, compositional service root, ADR, runbook, and staged roadmap.

### Advanced Claude and ChatGPT fluency, including JSON prompting

Evidence includes Pydantic-first structured output for both platforms, current SDK usage, strict data contracts, prompt-injection boundaries, provider portability, and golden evaluations. The implementation intentionally uses schema-constrained output rather than asking a model to “please return JSON” and hoping for valid syntax.

### High English writing proficiency

The generated Markdown templates, operational runbook, architecture narrative, prompts, decision-brief format, and stakeholder-draft format are designed for precise professional writing.

### Strong attention to detail

Examples:

- editing revokes approval;
- dispatch checks state before any side effect;
- audit payloads exclude source content;
- source and operator context are hashed for idempotency;
- path traversal is rejected;
- timestamps are timezone-aware at system boundaries;
- provider imports are lazy and optional;
- existing vault notes are not overwritten by initialization.

### Comfort in a fast-paced, dynamic environment

The deterministic provider supports graceful degradation, workflows are retry-safe, model and provider choice is configuration, the runtime is local and portable, and the roadmap favors incremental automation over a brittle all-at-once agent.

## Nice-to-have signals

### CS degree

The repository demonstrates applied foundations: schemas and type systems, state machines, indexing, transactional persistence, trust boundaries, idempotency, and modular architecture.

### Supporting executives

The domain objects and outputs are executive-oriented: decision briefs, priorities, actions, risk visibility, stakeholder updates, calendar blocks, and provenance that supports rapid questioning.

### Knowledge management or documentation engineering

The vault is treated as an information architecture with lifecycle, taxonomy, naming, linking, retrieval, templates, archive semantics, and maintenance runbooks.

### Obsidian or similar Markdown tools

All durable records are Obsidian-compatible Markdown with YAML properties and wiki links; no proprietary database is required to read the knowledge base.

### AI engineering certifications

The repository provides stronger direct evidence than a certificate alone: current provider APIs, structured outputs, evaluation cases, prompt safety, typed orchestration, tests, and deployment scaffolding.
