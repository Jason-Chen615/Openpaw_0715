#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prepare_memory.py — Convert LoCoMo dataset samples to Markdown memory files.

Usage (small dataset):
    python prepare_memory.py
    python prepare_memory.py --data locomo_small.json --output-dir memory/

Usage (full dataset):
    python prepare_memory.py --data locomo10.json --output-dir memory/

Output:
    memory/locomo_conv26.md
    memory/locomo_conv30.md
    ...

No third-party dependencies required (stdlib only).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

_MONTH_MAP: dict[str, str] = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05",      "june": "06",     "july": "07",  "august": "08",
    "september": "09","october": "10",  "november": "11","december": "12",
}

# "1:56 pm on 8 May, 2023"  /  "10:37 am on 27 June, 2023"
_DATE_RE = re.compile(
    r"\d+:\d+\s*(?:am|pm)\s+on\s+(\d+)\s+(\w+),?\s+(\d{4})",
    re.IGNORECASE,
)


def parse_date(date_str: str) -> str:
    """Return YYYY-MM-DD if parseable, otherwise return the original string."""
    if not date_str:
        return ""
    m = _DATE_RE.search(date_str)
    if m:
        day   = m.group(1).zfill(2)
        month = _MONTH_MAP.get(m.group(2).lower(), m.group(2))
        year  = m.group(3)
        return f"{year}-{month}-{day}"
    return date_str


# ---------------------------------------------------------------------------
# Turn formatter
# ---------------------------------------------------------------------------

def format_turn(turn: dict) -> str:
    """Format one dialogue turn, appending image info when present."""
    speaker  = turn.get("speaker", "Unknown")
    text     = turn.get("text", "").strip()
    caption  = turn.get("blip_caption", "")
    img_urls = turn.get("img_url", [])
    query    = turn.get("query", "")

    lines = [f"{speaker}:", text]

    if caption or img_urls:
        img_parts: list[str] = []
        if caption:
            img_parts.append(caption)
        if query:
            img_parts.append(f"query: {query}")
        if img_urls:
            url = img_urls[0] if isinstance(img_urls, list) else img_urls
            img_parts.append(f"url: {url}")
        lines.append(f"[Image: {' | '.join(img_parts)}]")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# session_summary / event_summary formatters  (handle str / list / dict)
# ---------------------------------------------------------------------------

def format_session_summary(data) -> str:
    if not data:
        return ""
    if isinstance(data, str):
        return data
    if isinstance(data, list):
        parts: list[str] = []
        for idx, item in enumerate(data, start=1):
            if isinstance(item, str):
                parts.append(f"Session {idx}: {item}")
            elif isinstance(item, dict):
                sess_id = item.get("session_id", item.get("id", f"Session {idx}"))
                summary = item.get("summary", item.get("text", ""))
                if summary:
                    parts.append(f"{sess_id}: {summary}")
                else:
                    parts.extend(f"{k}: {v}" for k, v in item.items())
            else:
                parts.append(str(item))
        return "\n".join(parts)
    if isinstance(data, dict):
        return "\n".join(
            f"{k}: {v}" if isinstance(v, str) else f"{k}: {json.dumps(v, ensure_ascii=False)}"
            for k, v in data.items()
        )
    return str(data)


def format_event_summary(data) -> str:
    if not data:
        return ""
    if isinstance(data, str):
        return data
    if isinstance(data, list):
        lines: list[str] = []
        for item in data:
            if isinstance(item, str):
                lines.append(f"- {item}")
            elif isinstance(item, dict):
                date   = item.get("date", item.get("date_time", ""))
                events = (
                    item.get("events") or item.get("event") or
                    item.get("description") or item.get("summary") or []
                )
                if date:
                    lines.append(date)
                if isinstance(events, list):
                    lines.extend(f"- {ev}" for ev in events)
                elif isinstance(events, str) and events:
                    lines.append(f"- {events}")
                elif not date:
                    lines.extend(f"- {k}: {v}" for k, v in item.items())
                if date or events:
                    lines.append("")
            else:
                lines.append(f"- {item}")
        return "\n".join(lines).rstrip()
    if isinstance(data, dict):
        lines = []
        for date_key, events in data.items():
            lines.append(date_key)
            if isinstance(events, list):
                lines.extend(f"- {ev}" for ev in events)
            elif isinstance(events, str):
                lines.append(f"- {events}")
            lines.append("")
        return "\n".join(lines).rstrip()
    return str(data)


# ---------------------------------------------------------------------------
# Core converter
# ---------------------------------------------------------------------------

def sample_to_markdown(sample: dict) -> str:
    """Convert one LoCoMo sample dict to a Markdown string."""
    sample_id: str  = sample.get("sample_id", "unknown")
    conversation    = sample.get("conversation", {})
    speaker_a: str  = conversation.get("speaker_a", "Speaker A")
    speaker_b: str  = conversation.get("speaker_b", "Speaker B")

    md: list[str] = []

    # ── Title ──────────────────────────────────────────────────────────────
    md += [f"# User Memory: {sample_id}", ""]

    # ── Basic Information ──────────────────────────────────────────────────
    md += [
        "## Basic Information",
        "",
        f"Sample ID: {sample_id}",
        "",
        f"Participants: {speaker_a} and {speaker_b}",
        "",
    ]

    # ── Conversation History ───────────────────────────────────────────────
    md += ["## Conversation History", ""]

    # Discover sessions dynamically (session_1, session_2, ...)
    session_idx = 1
    while True:
        turns = conversation.get(f"session_{session_idx}")
        if turns is None:
            break

        date_raw = conversation.get(f"session_{session_idx}_date_time", "")
        date_fmt = parse_date(date_raw) if date_raw else ""

        md.append(f"### Session {session_idx}")
        if date_fmt:
            md += [f"Date: {date_fmt}", ""]
        elif date_raw:
            md += [f"Date: {date_raw}", ""]
        else:
            md.append("")

        for turn in turns:
            md += [format_turn(turn), ""]

        session_idx += 1

    # ── Session Summary ────────────────────────────────────────────────────
    session_summary = sample.get("session_summary")
    if session_summary:
        text = format_session_summary(session_summary).strip()
        if text:
            md += ["## Session Summary", "", text, ""]

    # ── Event Summary ──────────────────────────────────────────────────────
    event_summary = sample.get("event_summary")
    if event_summary:
        text = format_event_summary(event_summary).strip()
        if text:
            md += ["## Event Summary", "", text, ""]

    return "\n".join(md)


# ---------------------------------------------------------------------------
# Filename helper
# ---------------------------------------------------------------------------

def make_filename(sample_id: str) -> str:
    """
    "conv-26"  →  "locomo_conv26.md"
    "conv-30"  →  "locomo_conv30.md"
    "some-id"  →  "locomo_some_id.md"
    """
    clean = re.sub(r"[^a-zA-Z0-9]+", "_", sample_id).strip("_")
    return f"locomo_{clean}.md"


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Convert LoCoMo dataset JSON to per-sample Markdown memory files.\n"
            "Works with both locomo_small.json and the full locomo10.json."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--data",
        default="locomo_small.json",
        help="Path to LoCoMo JSON file (default: locomo_small.json)",
    )
    p.add_argument(
        "--output-dir",
        default="memory",
        help="Directory to write .md files into (default: memory/)",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    data_path   = Path(args.data)
    output_dir  = Path(args.output_dir)

    # Resolve relative paths from the script's own directory so the script
    # works correctly regardless of the current working directory.
    script_dir = Path(__file__).parent
    if not data_path.is_absolute():
        data_path = script_dir / data_path
    if not output_dir.is_absolute():
        output_dir = script_dir / output_dir

    if not data_path.exists():
        print(f"[ERROR] Data file not found: {data_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading  : {data_path}")
    with open(data_path, encoding="utf-8") as f:
        dataset: list[dict] = json.load(f)

    print(f"Samples  : {len(dataset)}")

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output   : {output_dir}/")
    print()

    for sample in dataset:
        sample_id = sample.get("sample_id", "unknown")
        filename  = make_filename(sample_id)
        out_path  = output_dir / filename

        content = sample_to_markdown(sample)
        out_path.write_text(content, encoding="utf-8")

        # Count sessions found
        conv = sample.get("conversation", {})
        n_sessions = sum(
            1 for i in range(1, 20) if conv.get(f"session_{i}") is not None
        )
        n_turns = sum(
            len(conv.get(f"session_{i}", []))
            for i in range(1, n_sessions + 1)
        )
        has_session_summary = bool(sample.get("session_summary"))
        has_event_summary   = bool(sample.get("event_summary"))

        print(
            f"  [{sample_id}]  {filename}"
            f"  ({n_sessions} sessions, {n_turns} turns"
            f"{', session_summary' if has_session_summary else ''}"
            f"{', event_summary' if has_event_summary else ''})"
        )

    print(f"\nDone. {len(dataset)} file(s) written to {output_dir}/")


if __name__ == "__main__":
    main()