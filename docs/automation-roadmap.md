# Automation and information-flow roadmap

The roadmap is organized by capability and evidence, not by fashionable tooling. Each stage has an exit criterion so the system does not accumulate half-integrated automations.

## Stage 0 — Baseline and observation

**Goal:** understand current coordination work before automating it.

Capture for two weeks:

- source types and weekly volume;
- time from meeting end to usable notes;
- number of decisions/actions missed or corrected;
- repeated copy/paste steps;
- channels used for follow-up;
- time from draft to approval;
- search failures and duplicate notes;
- confidentiality classes.

**Exit criterion:** top five sources of coordination friction are measurable and ranked.

## Stage 1 — Local-first knowledge normalization

Implemented in v0.1.0:

- Obsidian taxonomy;
- deterministic and AI normalization;
- provenance-preserving Markdown;
- idempotent intake;
- full-text retrieval;
- daily and decision briefs;
- golden regression cases.

**Success metrics**

- median time from source receipt to reviewable note;
- action/decision extraction precision and recall;
- duplicate note rate;
- percentage of notes with project and source provenance;
- retrieval success on a curated question set.

**Exit criterion:** operator trusts the vault as a reliable first place to look.

## Stage 2 — Human-in-the-loop coordination

Implemented foundation:

- communication proposal generation;
- editable outbox;
- approval revocation on edit;
- explicit named approval;
- safe `.eml`/`.ics`/`.md` export;
- optional generic webhook;
- audit trail.

Next work:

- richer recipient directory resolution;
- template/voice profiles by stakeholder class;
- timezone-aware scheduling preferences;
- conflict checks against calendar free/busy;
- attachment/link validation;
- policy rules for confidential sources.

**Success metrics**

- minutes saved per follow-up;
- proposal acceptance/edit/rejection rate;
- recipient correction rate;
- approval latency;
- dispatch failure rate;
- number of prevented unapproved sends.

**Exit criterion:** proposals save time without increasing correction or disclosure risk.

## Stage 3 — Native workspace integrations

Add only after OAuth and policy design:

- Gmail draft creation, not immediate send;
- Google Calendar tentative event creation;
- Slack/Teams channel-specific adapters;
- contact/directory lookup;
- meeting transcript ingestion;
- calendar-triggered pre-read generation.

Required controls:

- least-privilege OAuth scopes;
- tenant and actor identity;
- recipient allow/deny policy;
- dry-run parity;
- idempotency at the provider API boundary;
- external request IDs in dispatch receipts;
- revocation and retry runbooks.

**Exit criterion:** every native mutation is attributable, reversible where possible, and covered by an integration test or contract test.

## Stage 4 — Proactive executive context

Potential workflows:

- pre-meeting brief from attendees, project state, prior decisions, and open commitments;
- stale-decision review reminders;
- project drift detection;
- “waiting on” digest by stakeholder;
- weekly information-flow bottleneck report;
- decision reversibility and review-date tracking.

Guardrail: proactive suggestions enter a review queue. They do not create an endless notification machine.

**Exit criterion:** proactive artifacts are used and rated useful more often than they are dismissed.

## Stage 5 — Multi-user production platform

Only when a single-node vault no longer fits:

- PostgreSQL workflow/outbox state;
- background workers and queues;
- encrypted object storage;
- organization, tenant, and role model;
- SSO/OIDC;
- policy-based authorization;
- immutable audit export;
- observability, rate limiting, cost budgets;
- hybrid retrieval and evaluation service;
- disaster recovery objectives.

**Exit criterion:** security, privacy, recovery, and ownership are explicit organizational commitments—not merely technical TODOs.

## Review cadence

Every month, review:

1. Which manual step consumed the most operator time?
2. Which automation produced the most corrections?
3. Which information arrived too late for a decision?
4. Which knowledge object was hardest to retrieve?
5. Which source or integration created the largest security exposure?
6. What should be removed or simplified?

A roadmap item should move up only when it addresses observed friction and has a measurable safety boundary.
