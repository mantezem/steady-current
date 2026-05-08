from __future__ import annotations

import re


HEADING_PATTERN = re.compile(r"(?m)^(#{1,3}\s+.+|[A-Z][A-Za-z0-9 /-]{6,}:)$")


def semantic_chunks(text: str, max_chars: int = 1800) -> list[str]:
    """Split on headings and paragraphs, preserving coherent sections."""
    sections: list[str] = []
    current: list[str] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        block = block.strip()
        if not block:
            continue
        starts_new_section = bool(HEADING_PATTERN.match(block)) and current
        would_overflow = sum(len(part) for part in current) + len(block) > max_chars
        if starts_new_section or would_overflow:
            sections.append("\n\n".join(current))
            current = []
        current.append(block)
    if current:
        sections.append("\n\n".join(current))
    return sections
