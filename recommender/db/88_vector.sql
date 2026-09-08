-- ============================================================================
--  pgvector — embedding columns and HNSW indexes
--
--  Two tables carry 1536-dimension embeddings (OpenAI text-embedding-3-small /
--  Gemini embedding size):
--    documents.embedding_vector  — RAG retrieval over the evidence corpus
--    recipes.embedding_vector    — recipe similarity search
--
--  Both are added here rather than in the table DDL so the whole schema still
--  builds on a Postgres without pgvector installed. If this block is skipped,
--  everything except AI search works; run this file again after installing the
--  extension.
--
--  HNSW parameters come from sheet 07: m=16, ef_construction=64, cosine
--  distance, targeting sub-10ms similarity search at 500K recipes.
-- ============================================================================

SELECT CASE WHEN EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')
            THEN 'true' ELSE 'false' END AS has_vector \gset

\if :has_vector

  ALTER TABLE public.documents ADD COLUMN IF NOT EXISTS embedding_vector vector(1536);
  ALTER TABLE public.recipes   ADD COLUMN IF NOT EXISTS embedding_vector vector(1536);

  COMMENT ON COLUMN public.documents.embedding_vector IS
    'pgvector 1536-dim. Populated asynchronously; NULL until the embedding job runs.';
  COMMENT ON COLUMN public.recipes.embedding_vector IS
    'pgvector 1536-dim. Written by the recipe-embedding-update queue, never inline.';

  -- HNSW build is memory-hungry. On a large import, load rows first and create
  -- the index afterwards rather than maintaining it row by row.
  CREATE INDEX IF NOT EXISTS idx_documents_embedding
      ON public.documents USING hnsw (embedding_vector vector_cosine_ops)
      WITH (m = 16, ef_construction = 64);

  CREATE INDEX IF NOT EXISTS idx_recipes_embedding
      ON public.recipes USING hnsw (embedding_vector vector_cosine_ops)
      WITH (m = 16, ef_construction = 64);

  \echo '   pgvector: embedding columns + HNSW indexes created.'

\else

  \echo '!! pgvector missing — embedding columns and HNSW indexes SKIPPED.'
  \echo '!! Install pgvector, then re-run 88_vector.sql. Nothing else is affected.'

\endif

-- ---------------------------------------------------------------------------
-- Reference query — recipe similarity search (sheet 07)
--
--   SET hnsw.ef_search = 64;   -- raise for recall, lower for latency
--   SELECT recipe_id,
--          recipe_name,
--          embedding_vector <=> $1::vector AS distance
--   FROM   public.recipes
--   WHERE  deleted_at IS NULL
--     AND  embedding_vector IS NOT NULL
--   ORDER  BY embedding_vector <=> $1::vector
--   LIMIT  20;
--
-- The ORDER BY must use the same operator as the index (<=> cosine) or the
-- planner will fall back to a sequential scan over 500K rows.
-- ---------------------------------------------------------------------------
