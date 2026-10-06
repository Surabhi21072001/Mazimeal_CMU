-- 10_ingredient_sources.sql
-- Which record in which upstream database an ingredient was matched to, and
-- the view that picks one nutrient value per ingredient by source precedence.
-- Filled by scripts/ingredient_sources.py from the USDA match review file.

CREATE TABLE IF NOT EXISTS ingredient_source_map (
    ingredient_id       UUID          NOT NULL,
    source_id           VARCHAR(30)   NOT NULL,
    source_record_id    VARCHAR(60)   NOT NULL,
    source_description  TEXT,
    match_score         SMALLINT,
    matched_by          VARCHAR(20)   NOT NULL DEFAULT 'fuzzy',
    matched_at          DATE          NOT NULL DEFAULT current_date,

    CONSTRAINT pk_ingredient_source_map PRIMARY KEY (ingredient_id, source_id),
    CONSTRAINT fk_ism_ingredient FOREIGN KEY (ingredient_id)
        REFERENCES ingredients (ingredient_id) ON DELETE CASCADE,
    CONSTRAINT fk_ism_source FOREIGN KEY (source_id) REFERENCES data_sources (source_id),
    CONSTRAINT ck_ism_matched_by CHECK (matched_by IN ('fuzzy', 'alias', 'manual'))
);

COMMENT ON TABLE ingredient_source_map IS 'Provenance: the upstream record each ingredient maps to, per source. source_record_id is the FDC id for USDA.';

-- One value per ingredient and nutrient, from the highest-precedence source
-- that has one. Nutrition maths reads this, not ingredient_nutrition.
CREATE OR REPLACE VIEW v_ingredient_nutrition AS
SELECT DISTINCT ON (n.ingredient_id, n.nutrient_id)
       n.ingredient_id, n.nutrient_id, n.value_per_100g, n.unit,
       n.bioavailability_pct, n.data_quality_flag, n.source_id
FROM   ingredient_nutrition n
JOIN   data_sources s ON s.source_id = n.source_id
ORDER  BY n.ingredient_id, n.nutrient_id, s.precedence;
