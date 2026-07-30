# Evaluation strategy

Workflow AI needs evaluation at three different layers: extraction quality, deterministic workflow invariants, and operator usefulness. Treating one aggregate “LLM score” as sufficient would hide the failure modes that matter in executive work.

## 1. Structured extraction regression

`evals/golden.jsonl` contains `EvaluationCase` records. Each case supplies a `SourceDocument` and assertions such as:

- title contains a phrase;
- artifact kind is preserved;
- an action or decision contains an expected phrase;
- a prompt-injection-like phrase does not become actionable content.

Run the gate with:

```zsh
uv run workflow-ai eval run \
  --dataset evals/golden.jsonl \
  --provider deterministic \
  --minimum-score 0.95
```

The current scoring function is intentionally small and inspectable. A case fails if any required assertion fails; the aggregate score is the mean fraction of checks satisfied. CI requires both the aggregate threshold and every case to pass.

Before changing a provider, model ID, prompt, or schema, run the same labeled set against the old and new configuration and inspect individual failures. Do not promote a model only because its average is slightly higher.

## 2. Workflow and safety invariants

Automated tests cover behavior that should not depend on model quality:

- content and caller idempotency;
- conflict when one idempotency key is reused for different input;
- atomic and path-confined vault writes;
- FTS index rebuild/upsert/search behavior;
- approval before dispatch;
- approval revocation after edits;
- live dispatch disabled by default;
- successful local `.eml`, `.ics`, and `.md` export;
- API authentication and error mapping;
- persisted audit metadata without full source content.

Run:

```zsh
uv run pytest --cov=workflow_ai --cov-report=term-missing
```

Coverage is a missing-test signal, not a correctness proof. State transitions, failure paths, and trust boundaries deserve direct assertions even when line coverage is already high.

## 3. Retrieval evaluation

FTS5 is the baseline. Build a small labeled query set from real operator questions and record:

- whether a relevant note appears in the top 1, 3, and 10;
- whether the displayed source path is correct;
- whether strict all-term retrieval or the any-term fallback produced the result;
- latency at the expected vault size;
- false positives caused by boilerplate or archived material.

Only add embeddings or a reranker when the labeled set demonstrates a material lexical-recall gap.

## 4. Human usefulness

For daily briefs, decision briefs, and communication proposals, collect operator review signals:

- accepted without edit;
- accepted after minor/major edit;
- rejected;
- wrong owner, recipient, due date, decision, or risk;
- missing critical context;
- time saved versus manual preparation;
- approval latency;
- dispatch failure rate.

A workflow that generates more review work than it removes should be simplified or retired.

## 5. Security-focused cases

Add adversarial cases for:

- embedded instructions asking the model to ignore the system prompt;
- quoted `ACTION:` text that is not a real commitment;
- ambiguous proposals incorrectly promoted to decisions;
- untrusted text attempting to set recipients;
- malformed dates and calendar windows;
- oversized input;
- path traversal;
- attempts to dispatch unapproved items.

Provider prompts reduce prompt-injection risk, but evaluation must assume that model behavior can still regress.

## Release gate

A release should satisfy:

1. formatting, lint, and strict type checking;
2. unit/integration tests and the configured coverage threshold;
3. deterministic golden evaluation;
4. a local end-to-end smoke run;
5. documentation that matches the actual CLI, API, paths, and safety behavior.
