"""Tests for Markdown parser."""
import pytest

from app.services.markdown_parser import (
    MarkdownDocument,
    Section,
    parse_markdown,
)


def test_parse_markdown_with_frontmatter():
    """Test parsing markdown with YAML front matter."""
    content = """---
bridge: 赵州桥
source_type: document
title: 赵州桥技术档案
---

# 概述

赵州桥是中国著名的石拱桥。
"""
    doc = parse_markdown(content)

    assert doc.frontmatter["bridge"] == "赵州桥"
    assert doc.frontmatter["source_type"] == "document"
    assert doc.frontmatter["title"] == "赵州桥技术档案"
    assert len(doc.sections) == 1
    assert doc.sections[0].title == "概述"
    assert "中国著名的石拱桥" in doc.sections[0].content


def test_parse_markdown_without_frontmatter():
    """Test parsing markdown without front matter."""
    content = """# 第一章

这是正文内容。
"""
    doc = parse_markdown(content)

    assert doc.frontmatter == {}
    assert len(doc.sections) == 1
    assert doc.sections[0].title == "第一章"


def test_parse_markdown_multiple_sections():
    """Test parsing markdown with multiple sections."""
    content = """---
bridge: 卢沟桥
---

# 结构特点

联拱石桥结构。

## 桥墩设计

船形桥墩减少水流冲击。

# 历史背景

建于金代。
"""
    doc = parse_markdown(content)

    assert len(doc.sections) == 3
    assert doc.sections[0].title == "结构特点"
    assert doc.sections[0].level == 1
    assert doc.sections[1].title == "桥墩设计"
    assert doc.sections[1].level == 2
    assert doc.sections[2].title == "历史背景"
    assert doc.sections[2].level == 1


def test_parse_markdown_section_content():
    """Test that section content is correctly extracted."""
    content = """---
bridge: 测试桥
---

# 主题

第一段落。

第二段落，包含**粗体**和*斜体*。

- 列表项1
- 列表项2
"""
    doc = parse_markdown(content)

    assert len(doc.sections) == 1
    section = doc.sections[0]
    assert "第一段落" in section.content
    assert "第二段落" in section.content
    assert "列表项1" in section.content


def test_parse_markdown_empty_content():
    """Test parsing empty content."""
    doc = parse_markdown("")

    assert doc.frontmatter == {}
    assert doc.sections == []


def test_parse_markdown_frontmatter_only():
    """Test parsing markdown with only front matter."""
    content = """---
bridge: 某桥
title: 测试
---
"""
    doc = parse_markdown(content)

    assert doc.frontmatter["bridge"] == "某桥"
    assert doc.sections == []


def test_section_dataclass():
    """Test Section dataclass."""
    section = Section(title="测试", level=2, content="内容")
    assert section.title == "测试"
    assert section.level == 2
    assert section.content == "内容"


def test_document_dataclass():
    """Test MarkdownDocument dataclass."""
    doc = MarkdownDocument(
        frontmatter={"bridge": "测试桥"},
        sections=[Section(title="章节", level=1, content="内容")],
    )
    assert doc.frontmatter["bridge"] == "测试桥"
    assert len(doc.sections) == 1
