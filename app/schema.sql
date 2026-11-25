CREATE TABLE IF NOT EXISTS sources (
    id text PRIMARY KEY,
    metadata jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS passages (
    id text PRIMARY KEY,
    source_id text NOT NULL REFERENCES sources(id),
    centre text,
    locator text NOT NULL,
    text text NOT NULL,
    keywords text NOT NULL,
    embedding vector(384) NOT NULL
);
CREATE INDEX IF NOT EXISTS passages_vector_idx ON passages USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS requests (
    id uuid PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE IF NOT EXISTS proposals (
    id uuid PRIMARY KEY,
    request_id uuid NOT NULL UNIQUE REFERENCES requests(id),
    centre text NOT NULL,
    reason text NOT NULL,
    source_ids text[] NOT NULL CHECK (cardinality(source_ids) > 0),
    state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','approved','rejected')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE IF NOT EXISTS reviews (
    proposal_id uuid PRIMARY KEY REFERENCES proposals(id),
    reviewer text NOT NULL,
    decision text NOT NULL CHECK (decision IN ('approve','reject')),
    decided_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE IF NOT EXISTS followups (
    id uuid PRIMARY KEY,
    proposal_id uuid NOT NULL UNIQUE REFERENCES reviews(proposal_id),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE IF NOT EXISTS audit (
    seq bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id uuid NOT NULL REFERENCES requests(id),
    proposal_id uuid REFERENCES proposals(id),
    event text NOT NULL,
    actor text NOT NULL,
    source_ids text[] NOT NULL,
    detail jsonb NOT NULL,
    at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS audit_request_idx ON audit (request_id, seq);
