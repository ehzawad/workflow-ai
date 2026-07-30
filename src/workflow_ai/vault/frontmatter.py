"""Minimal YAML frontmatter codec for Obsidian-compatible Markdown."""

from __future__ import annotations

from typing import Any

import yaml

from workflow_ai.exceptions import InputRejectedError


def dump_markdown(metadata: dict[str, Any], body: str) -> str:
    yaml_text = yaml.safe_dump(
        metadata,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=1_000,
    ).strip()
    return f"---\n{yaml_text}\n---\n\n{body.rstrip()}\n"


def load_markdown(text: str) -> tuple[dict[str, Any], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text

    closing_index: int | None = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            closing_index = index
            break
    if closing_index is None:
        raise InputRejectedError("Markdown begins with frontmatter but has no closing delimiter")

    raw_metadata = "\n".join(lines[1:closing_index])
    loaded = yaml.safe_load(raw_metadata) if raw_metadata.strip() else {}
    if loaded is None:
        loaded = {}
    if not isinstance(loaded, dict):
        raise InputRejectedError("YAML frontmatter must be an object")
    body = "\n".join(lines[closing_index + 1 :]).lstrip("\n")
    return loaded, body
