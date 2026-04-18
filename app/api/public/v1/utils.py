"""Shared utility functions for the public API."""


def escape_like(s: str) -> str:
    """Escape SQL LIKE metacharacters."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
