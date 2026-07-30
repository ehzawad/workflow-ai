# Claude project context

This repository implements an executive knowledge and coordination workflow inspired by a role that combines Obsidian vault ownership, information consolidation, automation design, AI-assisted decision support, and executive communications.

Read `AGENTS.md` first. The highest-risk boundaries are source ingestion, AI extraction, vault path construction, approval state transitions, and network dispatch. Preserve the rule that model output can **propose** a communication but cannot authorize or send it.

The Anthropic provider uses the Python SDK's structured-output helper with a Pydantic model. Keep model names configurable, keep extraction prompts provider-neutral, and ensure tests never require a live API key.
