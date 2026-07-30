# Threat model

## Assets

- executive meeting, project, and stakeholder information;
- provider API keys and optional API authentication key;
- action owners, recipients, due dates, and decision context;
- the integrity of the Obsidian vault;
- approval state and dispatch receipts;
- operator trust in generated briefs and drafts.

## Trust boundaries

1. **Imported source → application.** Source text may be malformed, misleading, confidential, or prompt-injection content.
2. **Application → AI provider.** When a network provider is selected, source data leaves the local machine under that provider's contract and retention controls.
3. **Provider output → deterministic workflows.** Parsed output remains probabilistic even after schema validation.
4. **Operator → approval state.** An approval is an authorization event and must be attributable.
5. **Approved outbox → dispatcher.** Filesystem export is local; webhook mode creates an external side effect.
6. **HTTP caller → API.** The service may be reachable beyond localhost if deployed carelessly.

## Implemented controls

### Untrusted source handling

- Provider prompts state that source content is data, not instruction.
- Pydantic models reject unknown fields.
- Actions and decisions are represented separately from narrative summary.
- The deterministic provider only treats directives at the beginning of a line as structured commands.
- Input size is bounded by `WORKFLOW_AI_MAX_SOURCE_CHARS`.

### Side-effect control

- Drafts begin in `proposed` state.
- Only `approved` items can be dispatched.
- Editing clears prior approval.
- Failed dispatch requires named re-approval or an edit before retry.
- Webhook dispatch requires `WORKFLOW_AI_LIVE_DISPATCH_ENABLED=true` and a configured URL.
- Filesystem mode creates reviewable artifacts without a network request.

### Filesystem and persistence

- Vault/runtime paths must resolve beneath the workspace root.
- Child paths reject absolute paths and traversal.
- Markdown writes use a temporary file and atomic replacement.
- SQLite operations use transactions and short-lived connections.
- Audit events intentionally store identifiers, counts, hashes, and error types instead of source bodies.

### Authentication and credentials

- The API can require `X-API-Key` via `WORKFLOW_AI_API_KEY`.
- Provider keys are loaded as `SecretStr` settings and are not intentionally written to the vault or workflow store.
- Production exposure should sit behind TLS and identity-aware access controls; the built-in key is a minimal deployment control, not a complete authorization system.

## Residual risks

### No DLP or source redaction

The system preserves original source text in Markdown. It does not scan or redact credentials, personal data, or regulated information. An operator who ingests a secret will persist that secret in the vault and may send it to the selected AI provider. Do not ingest credentials. Add a reviewed DLP/redaction stage before processing sensitive production sources.

### Model error

Structured output guarantees shape, not truth. A provider can omit a commitment, infer a wrong owner, or overstate a decision. Human review and source provenance remain mandatory for consequential use.

### Recipient resolution

Recipients are accepted only from operator metadata or explicit email-shaped action owners, but there is no enterprise directory validation, allowlist, role policy, or look-alike-domain detection.

### Local data security

SQLite and Markdown are not encrypted by the application. Disk encryption, OS permissions, backups, and endpoint security are deployment responsibilities.

### Webhook semantics

The generic webhook has no built-in destination-specific idempotency, signature scheme, or rollback. Treat it as an integration example, not a production messaging connector.

### Single-user authorization

The project has no user, role, or tenant model. A caller who knows the API key has the same application authority as any other caller.

## Production requirements

Before handling a real executive's data:

- define data classification and retention;
- use encrypted storage and backups;
- use SSO/OIDC and role-based authorization;
- choose provider data controls appropriate to the organization;
- add DLP/redaction and recipient policy;
- use least-privilege OAuth for native integrations;
- add immutable audit export and alerting;
- define recovery objectives and incident ownership;
- conduct a threat-model review for each new connector.
