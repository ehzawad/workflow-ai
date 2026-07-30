"""Safe default dispatcher that exports reviewable files instead of sending."""

from __future__ import annotations

from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path

from workflow_ai.integrations.base import Dispatcher
from workflow_ai.models import (
    CommunicationChannel,
    DispatchReceipt,
    OutboxRecord,
)
from workflow_ai.utils import atomic_write_text, safe_child, slugify


class FilesystemDispatcher(Dispatcher):
    name = "filesystem"
    live = False

    def __init__(self, output_root: Path) -> None:
        self.output_root = output_root.resolve()

    async def dispatch(self, item: OutboxRecord) -> DispatchReceipt:
        self.output_root.mkdir(parents=True, exist_ok=True)
        draft = item.draft
        stem = f"{item.created_at.date().isoformat()}-{slugify(draft.subject, max_length=55)}-{item.id[:8]}"

        if draft.channel is CommunicationChannel.EMAIL:
            path = safe_child(self.output_root, f"email/{stem}.eml")
            message = EmailMessage()
            message["Subject"] = draft.subject
            message["To"] = ", ".join(draft.recipients)
            message["X-Workflow-AI-Outbox-ID"] = item.id
            message.set_content(draft.body)
            atomic_write_text(path, message.as_string())
        elif draft.channel is CommunicationChannel.CALENDAR:
            path = safe_child(self.output_root, f"calendar/{stem}.ics")
            atomic_write_text(path, _calendar_ics(item))
        else:
            path = safe_child(self.output_root, f"stakeholder/{stem}.md")
            recipients = ", ".join(draft.recipients) or "_Unassigned_"
            content = (
                f"# {draft.subject}\n\n"
                f"**Recipients:** {recipients}\n\n"
                f"{draft.body.rstrip()}\n"
            )
            atomic_write_text(path, content)

        return DispatchReceipt(
            dispatcher=self.name,
            external_id=str(path),
            detail={"format": path.suffix.lstrip("."), "network_side_effect": False},
        )


def _calendar_ics(item: OutboxRecord) -> str:
    draft = item.draft
    assert draft.start_at is not None
    assert draft.end_at is not None
    attendees = "\r\n".join(
        f"ATTENDEE:mailto:{_ics_escape(recipient)}" for recipient in draft.recipients
    )
    if attendees:
        attendees += "\r\n"
    return (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//Workflow AI//Executive Workflow OS//EN\r\n"
        "CALSCALE:GREGORIAN\r\n"
        "METHOD:PUBLISH\r\n"
        "BEGIN:VEVENT\r\n"
        f"UID:{item.id}@workflow-ai\r\n"
        f"DTSTAMP:{_ics_datetime(item.updated_at)}\r\n"
        f"DTSTART:{_ics_datetime(draft.start_at)}\r\n"
        f"DTEND:{_ics_datetime(draft.end_at)}\r\n"
        f"SUMMARY:{_ics_escape(draft.subject)}\r\n"
        f"DESCRIPTION:{_ics_escape(draft.body)}\r\n"
        f"LOCATION:{_ics_escape(draft.location or '')}\r\n"
        f"{attendees}"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )


def _ics_datetime(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _ics_escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )
