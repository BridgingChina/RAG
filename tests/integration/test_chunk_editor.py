"""Integration tests for chunk editor endpoints."""
import pytest
from sqlalchemy import text

from app.core.constants import EMBEDDING_DIM


@pytest.fixture
def sample_chunk(db_session, test_source, tokenizer):
    """Create a single chunk for editing tests."""
    from app.models import Chunk

    chunk = Chunk(
        source_id=test_source.id,
        content="赵州桥是一座石拱桥，建于隋代。",
        section_title="赵州桥概述",
        lvl1="形制与技术",
        embedding=[0.0] * EMBEDDING_DIM,
        search_text="赵州桥是一座石拱桥，建于隋代。",
        contextual_text="关于赵州桥的基本介绍",
    )
    db_session.add(chunk)
    db_session.flush()

    tsv_text = tokenizer.to_tsvector_text(chunk.search_text)
    db_session.execute(
        text("UPDATE chunks SET tsv = to_tsvector('simple', :tsv_text) WHERE id = :id"),
        {"tsv_text": tsv_text, "id": chunk.id},
    )
    db_session.flush()
    return chunk


def test_update_chunk_content(db_session, sample_chunk, tokenizer):
    """Updating content should recompute search_text, tsv, and set needs_reindex."""
    from app.services.chunk_editor import update_chunk_content

    new_content = "赵州桥是世界上现存最古老的石拱桥。"
    result = update_chunk_content(
        db=db_session,
        chunk=sample_chunk,
        new_content=new_content,
        tokenizer=tokenizer,
    )

    assert result.content == new_content
    assert new_content in result.search_text
    # contextual_text should be preserved in search_text
    assert "关于赵州桥的基本介绍" in result.search_text
    assert result.needs_reindex is True

    # Verify tsv was updated (non-null)
    row = db_session.execute(
        text("SELECT tsv IS NOT NULL as has_tsv FROM chunks WHERE id = :id"),
        {"id": sample_chunk.id},
    ).first()
    assert row.has_tsv is True


def test_update_chunk_content_no_contextual_text(db_session, test_source, tokenizer):
    """Content update without contextual_text should use content as search_text."""
    from app.models import Chunk
    from app.services.chunk_editor import update_chunk_content

    chunk = Chunk(
        source_id=test_source.id,
        content="原始内容",
        embedding=[0.0] * EMBEDDING_DIM,
        search_text="原始内容",
    )
    db_session.add(chunk)
    db_session.flush()

    result = update_chunk_content(
        db=db_session, chunk=chunk, new_content="新内容", tokenizer=tokenizer,
    )

    assert result.content == "新内容"
    assert result.search_text == "新内容"
    assert result.needs_reindex is True
