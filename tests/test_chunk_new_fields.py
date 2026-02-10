import pytest


def test_chunk_has_contextual_text_field():
    from app.models.chunk import Chunk
    assert hasattr(Chunk, "contextual_text")


def test_chunk_has_search_text_field():
    from app.models.chunk import Chunk
    assert hasattr(Chunk, "search_text")


def test_chunk_has_tsv_field():
    from app.models.chunk import Chunk
    assert hasattr(Chunk, "tsv")


def test_chunk_has_bridge_binding_status_field():
    from app.models.chunk import Chunk
    assert hasattr(Chunk, "bridge_binding_status")
