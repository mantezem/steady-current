CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS topics (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    domain TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    depth INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    difficulty TEXT NOT NULL DEFAULT 'intermediate'
);

CREATE TABLE IF NOT EXISTS topic_relationships (
    id BIGSERIAL PRIMARY KEY,
    source_topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    target_topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL CHECK (relationship_type IN ('parent', 'prerequisite', 'related')),
    UNIQUE (source_topic_id, target_topic_id, relationship_type)
);

CREATE TABLE IF NOT EXISTS user_mastery (
    user_id TEXT NOT NULL,
    topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    mastery DOUBLE PRECISION NOT NULL DEFAULT 0,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0,
    correct_attempts INTEGER NOT NULL DEFAULT 0,
    last_reviewed_at TIMESTAMPTZ,
    PRIMARY KEY (user_id, topic_id)
);

CREATE TABLE IF NOT EXISTS question_attempts (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    correct_answer TEXT NOT NULL DEFAULT '',
    is_correct BOOLEAN NOT NULL,
    explanation TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS resources (
    id BIGSERIAL PRIMARY KEY,
    url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    service TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS document_chunks (
    id BIGSERIAL PRIMARY KEY,
    resource_id BIGINT NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
    topic_id TEXT REFERENCES topics(id) ON DELETE SET NULL,
    content TEXT NOT NULL,
    service TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL,
    source_type TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding vector({embedding_dimensions}),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    content_hash TEXT NOT NULL,
    UNIQUE (resource_id, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_topic_relationships_source ON topic_relationships(source_topic_id);
CREATE INDEX IF NOT EXISTS idx_topic_relationships_target ON topic_relationships(target_topic_id);
CREATE INDEX IF NOT EXISTS idx_user_mastery_user ON user_mastery(user_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_topic ON document_chunks(topic_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_metadata ON document_chunks USING GIN(metadata);
CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding
ON document_chunks USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
