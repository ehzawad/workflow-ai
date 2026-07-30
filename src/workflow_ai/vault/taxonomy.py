"""Opinionated PARA-like Obsidian taxonomy and non-destructive initialization."""

from __future__ import annotations

from pathlib import Path

from workflow_ai.utils import atomic_write_text, safe_child

SECTIONS: dict[str, str] = {
    "00_Inbox": "Unprocessed or lightly classified material awaiting review.",
    "10_People": "Relationship context, stakeholder notes, and people profiles.",
    "20_Meetings": "Meeting records and transcripts, grouped by year.",
    "30_Projects": "Active outcomes with project maps of content.",
    "40_Decisions": "Durable decisions, rationale, owners, and reversibility notes.",
    "50_Areas": "Ongoing areas of responsibility without a fixed end date.",
    "60_Briefs": "Daily, weekly, and decision briefs for executive review.",
    "70_Resources": "Reference material and reusable research.",
    "90_Archive": "Inactive or superseded material retained for provenance.",
    "Templates": "Obsidian templates for common knowledge objects.",
}


def initialize_vault(root: Path) -> list[Path]:
    """Create missing taxonomy scaffolding without modifying existing notes."""

    root.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for folder, description in SECTIONS.items():
        directory = safe_child(root, folder)
        directory.mkdir(parents=True, exist_ok=True)
        readme = directory / "README.md"
        if not readme.exists() and folder != "Templates":
            atomic_write_text(
                readme,
                f"# {folder.replace('_', ' ')}\n\n{description}\n",
            )
            created.append(readme)

    home = safe_child(root, "Home.md")
    if not home.exists():
        links = "\n".join(
            f"- [[{folder}/README|{folder.replace('_', ' ')}]] — {description}"
            for folder, description in SECTIONS.items()
            if folder != "Templates"
        )
        atomic_write_text(
            home,
            "# Executive Workflow Home\n\n"
            "This vault is the durable knowledge layer for Workflow AI.\n\n"
            "## Taxonomy\n\n"
            f"{links}\n\n"
            "## Operating rhythm\n\n"
            "- Process the inbox daily.\n"
            "- Review open actions and risks in the daily brief.\n"
            "- Record decisions with rationale and evidence.\n"
            "- Archive completed projects instead of deleting provenance.\n",
        )
        created.append(home)

    templates = {
        "Templates/Meeting.md": """# {{title}}

## Context

## Decisions

## Action items

- [ ]

## Risks

## Open questions
""",
        "Templates/Decision.md": """# Decision: {{title}}

## Decision

## Why now

## Options considered

## Evidence

## Reversibility and review date
""",
        "Templates/Project.md": """# {{project}}

## Outcome

## Current state

## Next milestones

## Open actions

## Key decisions
""",
    }
    for relative, content in templates.items():
        path = safe_child(root, relative)
        if not path.exists():
            atomic_write_text(path, content)
            created.append(path)
    return created
