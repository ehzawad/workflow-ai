# ADR 0001: Markdown is durable knowledge; SQLite is derived operational state

- **Status:** Accepted
- **Date:** 2026-07-31

## Context

An executive knowledge system needs human readability, local ownership, portability, low switching cost, reliable retrieval, idempotent workflows, and an auditable communication queue. A single storage technology does not optimize all of these concerns.

Storing everything only in a proprietary SaaS or vector database makes the knowledge layer hard to inspect and migrate. Storing everything only in Markdown makes transactional workflow state, uniqueness constraints, full-text ranking, and approval transitions awkward and error-prone.

## Decision

Use three persistence roles:

1. **Obsidian-compatible Markdown** is the durable knowledge source of truth.
2. **Workflow SQLite** stores idempotency, workflow status, outbox state, approvals, receipts, and audit metadata.
3. **FTS5 SQLite** is a derived retrieval index that can be rebuilt from Markdown.

## Consequences

### Positive

- The vault remains usable without this application.
- Knowledge is readable, diffable, and easy to back up.
- Search can be rebuilt after corruption or schema changes.
- Transactional state transitions and unique idempotency keys are straightforward.
- The system can migrate workflow state to PostgreSQL later without rewriting the vault format.

### Negative

- The system must keep Markdown and the index synchronized.
- Editing generated frontmatter manually can create invalid machine-readable state.
- Complete source text embedded in Markdown increases vault size.
- A multi-node deployment eventually outgrows local SQLite coordination.

## Rejected alternatives

### Vector database as primary store

Rejected because semantic retrieval does not replace human-readable durable records, lifecycle taxonomy, or provenance. A vector index may be added later as a derived projection.

### Obsidian plugin as the only application surface

Rejected for the initial version because it would couple workflow logic to one UI/runtime and make headless automation and API integration harder. The vault remains plugin-compatible, while CLI and FastAPI are portable.

### Fully autonomous agent with direct email/calendar tools

Rejected because model generation and authorization are different responsibilities. The outbox and approval state machine are a core safety property, not temporary scaffolding.
