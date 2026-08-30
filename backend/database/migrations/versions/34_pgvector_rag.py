"""iteration-34 · pgvector + pipeline_embeddings + rca_embeddings

Revision ID: 34_pgvector_rag
Revises: 0c995b5f4ca3
Create Date: 2026-02-19

Enables the pgvector extension (available in the pgvector/pgvector:pg15
image swapped into docker-compose.yml) and creates two vector-backed
tables the RAG endpoints query.

Embedding dimension = 1536 to match OpenAI's `text-embedding-3-small`
which is what `services/embedding_service.py` calls via the Emergent
LLM key.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers ------------------------------------------------------
revision: str = "34_pgvector_rag"
down_revision: Union[str, None] = "0c995b5f4ca3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBED_DIM = 1536


def upgrade() -> None:
    # 1. Enable the pgvector extension (idempotent — pgvector image ships it)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 2. pipeline_embeddings — one row per PipelineRun, embedded from
    #    the natural-language summary the generator already stores in
    #    `explanation`.
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS pipeline_embeddings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id UUID NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
            summary TEXT NOT NULL,
            embedding vector({EMBED_DIM}) NOT NULL,
            model VARCHAR(64) NOT NULL DEFAULT 'text-embedding-3-small',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.create_index("ix_pipeline_embeddings_run", "pipeline_embeddings", ["run_id"])
    # HNSW index over cosine distance — best default for OpenAI embeddings.
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_pipeline_embeddings_vec
        ON pipeline_embeddings
        USING hnsw (embedding vector_cosine_ops)
    """)

    # 3. rca_embeddings — one row per RCAReport, embedded from the
    #    combined summary + top_findings text. Enables "when a new
    #    pipeline fails, retrieve the 3 most similar past RCAs".
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS rca_embeddings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            rca_id UUID NOT NULL,
            content TEXT NOT NULL,
            embedding vector({EMBED_DIM}) NOT NULL,
            model VARCHAR(64) NOT NULL DEFAULT 'text-embedding-3-small',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.create_index("ix_rca_embeddings_rca", "rca_embeddings", ["rca_id"])
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_rca_embeddings_vec
        ON rca_embeddings
        USING hnsw (embedding vector_cosine_ops)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS rca_embeddings")
    op.execute("DROP TABLE IF EXISTS pipeline_embeddings")
    # Leave the extension in place — dropping it would break other future
    # migrations that might want vectors.
