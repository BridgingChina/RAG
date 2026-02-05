"""Markdown parser with YAML front matter support.

Parses markdown documents into structured data for ingestion.
Supports YAML front matter (bridge, source_type, title) and
extracts sections by heading level.
"""
import re
from dataclasses import dataclass, field

import yaml


@dataclass
class Section:
    """A section extracted from markdown."""
    title: str
    level: int  # Heading level (1 for #, 2 for ##, etc.)
    content: str


@dataclass
class MarkdownDocument:
    """Parsed markdown document."""
    frontmatter: dict = field(default_factory=dict)
    sections: list[Section] = field(default_factory=list)


# Regex patterns
FRONTMATTER_PATTERN = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n",
    re.DOTALL,
)
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def parse_markdown(content: str) -> MarkdownDocument:
    """Parse markdown content into structured document.

    Args:
        content: Raw markdown text

    Returns:
        MarkdownDocument with frontmatter and sections
    """
    if not content.strip():
        return MarkdownDocument()

    frontmatter: dict = {}
    body = content

    # Extract front matter
    match = FRONTMATTER_PATTERN.match(content)
    if match:
        try:
            loaded = yaml.safe_load(match.group(1)) or {}
            frontmatter = loaded if isinstance(loaded, dict) else {}
        except yaml.YAMLError:
            frontmatter = {}
        body = content[match.end():]

    # Extract sections
    sections = _extract_sections(body)

    return MarkdownDocument(frontmatter=frontmatter, sections=sections)


def _extract_sections(body: str) -> list[Section]:
    """Extract sections from markdown body.

    Args:
        body: Markdown content without front matter

    Returns:
        List of Section objects
    """
    if not body.strip():
        return []

    # Find all headings
    headings = list(HEADING_PATTERN.finditer(body))

    if not headings:
        # No headings found, treat entire body as one section
        return [Section(title="", level=0, content=body.strip())]

    sections = []
    for i, heading in enumerate(headings):
        level = len(heading.group(1))
        title = heading.group(2).strip()

        # Content starts after heading, ends at next heading or EOF
        start = heading.end()
        if i + 1 < len(headings):
            end = headings[i + 1].start()
        else:
            end = len(body)

        content = body[start:end].strip()
        sections.append(Section(title=title, level=level, content=content))

    return sections
