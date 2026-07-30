# Security policy

## Supported versions

Until the first stable release, the `main` branch is the supported development line.

## Reporting a vulnerability

Do not open a public issue for a vulnerability involving credentials, private vault data, path traversal, authorization, prompt injection, or unintended dispatch. Use GitHub private vulnerability reporting for this repository.

## Secure defaults

- The deterministic provider works without credentials or network calls.
- Live webhook dispatch is disabled unless `WORKFLOW_AI_LIVE_DISPATCH_ENABLED=true`.
- Every communication starts as `proposed` and requires named approval before dispatch.
- Editing a draft revokes prior approval.
- The default dispatcher writes a local review artifact instead of contacting a third party.
- Vault/runtime paths are confined beneath the configured workspace root.
- API authentication can be enabled with `WORKFLOW_AI_API_KEY`; deployed services should also use TLS and an identity-aware gateway.
- Audit events store operational metadata rather than full source text.

## Important limitation: source content is preserved

Workflow AI embeds original source text in the generated Markdown note so an operator can verify provenance. The project does **not** include a DLP or secret-redaction engine. Do not ingest passwords, API keys, private keys, access tokens, or other credentials. When a network AI provider is selected, source content may also be transmitted to that provider.

Provider credentials are loaded through environment-backed `SecretStr` settings and are not intentionally written by the application, but deployment logs, shell history, crash tooling, or operator actions can still expose them. Use a secret manager in production.

## Operational advice

Use encrypted storage, least-privilege filesystem permissions, separate development and production credentials, encrypted backups, key rotation, outbound network controls, and organization-specific data-retention policy. Review the threat model before enabling any live integration.

See [`docs/threat-model.md`](docs/threat-model.md) for trust boundaries and residual risks.
