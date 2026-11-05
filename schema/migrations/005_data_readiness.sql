-- Data-engineering review layer for the current schema/ recipe database.
-- Reuses the team's source registry, multi-source nutrition view and gram fields.
-- No recipe IDs, quantities, mappings, rules, user profiles or UI verdicts change.
-- Run on a staging copy first. Missing reviews remain pending, never approved.
BEGIN;

CREATE TABLE IF NOT EXISTS de_dataset_releases (
    release_id text PRIMARY KEY,
    manifest jsonb NOT NULL,
    imported_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS de_mapping_reviews (
    ingredient_id uuid NOT NULL,
    source_id varchar(30) NOT NULL,
    review_status text NOT NULL DEFAULT 'pending_review'
        CHECK (review_status IN ('pending_review','approved','rejected')),
    review_note text, reviewed_by text, reviewed_at timestamptz,
    PRIMARY KEY (ingredient_id, source_id),
    FOREIGN KEY (ingredient_id, source_id) REFERENCES ingredient_source_map ON DELETE CASCADE,
    CHECK (review_status = 'pending_review' OR
        (nullif(btrim(reviewed_by),'') IS NOT NULL AND reviewed_at IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS de_line_reviews (
    line_id uuid PRIMARY KEY REFERENCES recipe_ingredients ON DELETE CASCADE,
    quantity_review_status text NOT NULL DEFAULT 'pending_review'
        CHECK (quantity_review_status IN ('pending_review','approved','rejected')),
    review_note text, reviewed_by text, reviewed_at timestamptz,
    CHECK (quantity_review_status = 'pending_review' OR
        (nullif(btrim(reviewed_by),'') IS NOT NULL AND reviewed_at IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS de_recipe_reviews (
    recipe_id uuid PRIMARY KEY REFERENCES recipes ON DELETE CASCADE,
    review_status text NOT NULL DEFAULT 'pending_review'
        CHECK (review_status IN ('pending_review','approved','rejected')),
    -- Approval confirms ingredient-list completeness, preparation and servings.
    source_reference text, review_note text, reviewed_by text, reviewed_at timestamptz,
    CHECK (review_status = 'pending_review' OR
        (nullif(btrim(reviewed_by),'') IS NOT NULL AND reviewed_at IS NOT NULL)),
    CHECK (review_status <> 'approved' OR nullif(btrim(source_reference),'') IS NOT NULL)
);
CREATE TABLE IF NOT EXISTS de_line_provenance (
    line_id uuid PRIMARY KEY REFERENCES recipe_ingredients ON DELETE CASCADE,
    raw_ingredient_text text, raw_quantity_text text, source_reference text,
    source_ingredient_position integer CHECK (source_ingredient_position > 0),
    source_quantity_position integer CHECK (source_quantity_position > 0)
);
COMMENT ON TABLE de_line_provenance IS
 'Optional source evidence. Positions must come from the source, not row order. sequence_order still means eating order.';
COMMENT ON TABLE de_recipe_reviews IS
 'Data completeness review; separate from recipe_nutrition_reviews plausibility verdicts. Plausible calories never approve missing grams or mappings.';

-- Absent rows also mean pending review in the views; re-running never clears approval.
INSERT INTO de_mapping_reviews (ingredient_id,source_id)
    SELECT ingredient_id,source_id FROM ingredient_source_map ON CONFLICT DO NOTHING;
INSERT INTO de_line_reviews (line_id) SELECT line_id FROM recipe_ingredients ON CONFLICT DO NOTHING;
INSERT INTO de_recipe_reviews (recipe_id) SELECT recipe_id FROM recipes ON CONFLICT DO NOTHING;

CREATE OR REPLACE FUNCTION de_reset_mapping_review() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF ROW(OLD.source_record_id,OLD.source_description,OLD.match_score,OLD.matched_by)
       IS DISTINCT FROM ROW(NEW.source_record_id,NEW.source_description,NEW.match_score,NEW.matched_by) THEN
        UPDATE de_mapping_reviews SET review_status='pending_review',
            review_note='Source mapping changed; re-review required',reviewed_by=NULL,reviewed_at=NULL
        WHERE ingredient_id=NEW.ingredient_id AND source_id=NEW.source_id;
    END IF;
    RETURN NEW;
END $$;
CREATE OR REPLACE TRIGGER de_mapping_review_changed AFTER UPDATE ON ingredient_source_map
    FOR EACH ROW EXECUTE FUNCTION de_reset_mapping_review();

CREATE OR REPLACE FUNCTION de_reset_line_review() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF ROW(OLD.recipe_id,OLD.ingredient_id,OLD.quantity,OLD.unit,OLD.quantity_g,OLD.measure,
               OLD.grams_source,OLD.quantity_aligned,OLD.preparation_note,OLD.is_optional)
           IS NOT DISTINCT FROM
           ROW(NEW.recipe_id,NEW.ingredient_id,NEW.quantity,NEW.unit,NEW.quantity_g,NEW.measure,
               NEW.grams_source,NEW.quantity_aligned,NEW.preparation_note,NEW.is_optional) THEN
            RETURN NEW;
        END IF;
        UPDATE de_line_reviews SET quantity_review_status='pending_review',
            review_note='Ingredient line changed; re-review required',reviewed_by=NULL,reviewed_at=NULL
        WHERE line_id=NEW.line_id;
    END IF;
    IF TG_OP <> 'INSERT' THEN
        UPDATE de_recipe_reviews SET review_status='pending_review',reviewed_by=NULL,reviewed_at=NULL,
            review_note='Ingredient list or quantity changed; re-review required' WHERE recipe_id=OLD.recipe_id;
    END IF;
    IF TG_OP <> 'DELETE' THEN
        UPDATE de_recipe_reviews SET review_status='pending_review',reviewed_by=NULL,reviewed_at=NULL,
            review_note='Ingredient list or quantity changed; re-review required' WHERE recipe_id=NEW.recipe_id;
        RETURN NEW;
    END IF;
    RETURN OLD;
END $$;
CREATE OR REPLACE TRIGGER de_line_review_changed AFTER INSERT OR UPDATE OR DELETE ON recipe_ingredients
    FOR EACH ROW EXECUTE FUNCTION de_reset_line_review();

CREATE OR REPLACE FUNCTION de_reset_recipe_review() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_TABLE_NAME='recipes' THEN
        IF ROW(OLD.servings,OLD.recipe_name,OLD.recipe_description,OLD.external_source_id,OLD.data_source,OLD.deleted_at)
           IS NOT DISTINCT FROM ROW(NEW.servings,NEW.recipe_name,NEW.recipe_description,NEW.external_source_id,NEW.data_source,NEW.deleted_at) THEN
            RETURN NEW;
        END IF;
    END IF;
    IF TG_OP <> 'INSERT' THEN
        UPDATE de_recipe_reviews SET review_status='pending_review',reviewed_by=NULL,reviewed_at=NULL,
            review_note='Recipe source, servings or instructions changed; re-review required' WHERE recipe_id=OLD.recipe_id;
    END IF;
    IF TG_OP <> 'DELETE' THEN
        UPDATE de_recipe_reviews SET review_status='pending_review',reviewed_by=NULL,reviewed_at=NULL,
            review_note='Recipe source, servings or instructions changed; re-review required' WHERE recipe_id=NEW.recipe_id;
        RETURN NEW;
    END IF;
    RETURN OLD;
END $$;
CREATE OR REPLACE TRIGGER de_recipe_review_changed AFTER UPDATE ON recipes
    FOR EACH ROW EXECUTE FUNCTION de_reset_recipe_review();
CREATE OR REPLACE TRIGGER de_steps_review_changed AFTER INSERT OR UPDATE OR DELETE ON recipe_steps
    FOR EACH ROW EXECUTE FUNCTION de_reset_recipe_review();

CREATE OR REPLACE FUNCTION de_reset_ingredient_reviews() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF ROW(OLD.ingredient_name,OLD.ingredient_name_aliases)
       IS DISTINCT FROM ROW(NEW.ingredient_name,NEW.ingredient_name_aliases) THEN
        UPDATE de_mapping_reviews SET review_status='pending_review',reviewed_by=NULL,reviewed_at=NULL,
            review_note='Ingredient identity changed; re-review required' WHERE ingredient_id=NEW.ingredient_id;
        UPDATE de_recipe_reviews SET review_status='pending_review',reviewed_by=NULL,reviewed_at=NULL,
            review_note='Ingredient identity changed; re-review required'
        WHERE recipe_id IN (SELECT recipe_id FROM recipe_ingredients WHERE ingredient_id=NEW.ingredient_id);
    END IF;
    RETURN NEW;
END $$;
CREATE OR REPLACE TRIGGER de_ingredient_identity_changed AFTER UPDATE ON ingredients
    FOR EACH ROW EXECUTE FUNCTION de_reset_ingredient_reviews();

CREATE OR REPLACE FUNCTION de_reset_provenance_reviews() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE changed_line uuid;
BEGIN
    IF TG_OP='UPDATE' THEN
        IF OLD IS NOT DISTINCT FROM NEW THEN RETURN NEW; END IF;
    END IF;
    IF TG_OP='DELETE' THEN changed_line=OLD.line_id; ELSE changed_line=NEW.line_id; END IF;
    UPDATE de_line_reviews SET quantity_review_status='pending_review',reviewed_by=NULL,reviewed_at=NULL,
        review_note='Source evidence changed; re-review required' WHERE line_id=changed_line;
    UPDATE de_recipe_reviews SET review_status='pending_review',reviewed_by=NULL,reviewed_at=NULL,
        review_note='Source evidence changed; re-review required'
    WHERE recipe_id IN (SELECT recipe_id FROM recipe_ingredients WHERE line_id=changed_line);
    IF TG_OP='DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE OR REPLACE TRIGGER de_line_provenance_changed AFTER INSERT OR UPDATE OR DELETE ON de_line_provenance
    FOR EACH ROW EXECUTE FUNCTION de_reset_provenance_reviews();

CREATE OR REPLACE VIEW de_ingredient_line_readiness WITH (security_invoker=true) AS
SELECT ri.recipe_id,ri.line_id,ri.ingredient_id,i.ingredient_name,
       ri.quantity,ri.unit,ri.quantity_g,ri.grams_source,ri.quantity_aligned,
       m.source_record_id AS usda_record_id,m.source_description,
       coalesce(mr.review_status,'unmapped') AS mapping_status,
       coalesce(lr.quantity_review_status,'pending_review') AS quantity_status,
       EXISTS(SELECT 1 FROM v_ingredient_nutrition n WHERE n.ingredient_id=ri.ingredient_id) AS has_nutrition,
       EXISTS(SELECT 1 FROM ingredient_rule_tags t WHERE t.ingredient_id=ri.ingredient_id) AS has_rule_tags,
       coalesce(ri.quantity_g>0 AND ri.quantity_aligned IS TRUE AND lr.quantity_review_status='approved',false) AS quantity_ready
FROM recipe_ingredients ri JOIN ingredients i USING(ingredient_id)
LEFT JOIN ingredient_source_map m ON m.ingredient_id=ri.ingredient_id AND m.source_id='usda_sr_legacy'
LEFT JOIN de_mapping_reviews mr ON mr.ingredient_id=m.ingredient_id AND mr.source_id=m.source_id
LEFT JOIN de_line_reviews lr USING(line_id);

-- Coverage is PER NUTRIENT. Read the chosen source from v_ingredient_nutrition,
-- then check the review for THAT source. One reviewed USDA match cannot approve
-- a different higher-precedence source. Mixed units block a numeric total.
CREATE OR REPLACE VIEW de_recipe_nutrient_readiness WITH (security_invoker=true) AS
WITH nutrients AS (
    SELECT DISTINCT nutrient_id FROM v_ingredient_nutrition
    UNION SELECT DISTINCT nutrient_id FROM recipe_nutrition
), coverage AS (
    SELECT r.recipe_id,r.recipe_name,n.nutrient_id,
           count(l.line_id) AS ingredient_lines,
           count(v.ingredient_id) AS lines_with_nutrient,
           count(l.line_id) FILTER(WHERE l.quantity_ready) AS lines_quantity_reviewed,
           count(l.line_id) FILTER(WHERE l.quantity_ready AND mr.review_status='approved'
               AND v.ingredient_id IS NOT NULL) AS lines_ready,
           count(DISTINCT v.unit) AS unit_count,min(v.unit) AS unit,
           coalesce(rr.review_status='approved',false) AS recipe_reviewed,
           sum(l.quantity_g/100.0*v.value_per_100g)/nullif(r.servings,0) AS total
    FROM recipes r CROSS JOIN nutrients n
    LEFT JOIN de_ingredient_line_readiness l USING(recipe_id)
    LEFT JOIN v_ingredient_nutrition v ON v.ingredient_id=l.ingredient_id AND v.nutrient_id=n.nutrient_id
    LEFT JOIN de_mapping_reviews mr ON mr.ingredient_id=v.ingredient_id AND mr.source_id=v.source_id
    LEFT JOIN de_recipe_reviews rr ON rr.recipe_id=r.recipe_id
    WHERE r.deleted_at IS NULL
    GROUP BY r.recipe_id,r.recipe_name,n.nutrient_id,r.servings,rr.review_status
)
SELECT recipe_id,recipe_name,nutrient_id,ingredient_lines,lines_with_nutrient,
       lines_quantity_reviewed,lines_ready,unit_count,unit,recipe_reviewed,
       (recipe_reviewed AND ingredient_lines>0 AND lines_ready=ingredient_lines AND unit_count=1) AS ready,
       CASE WHEN recipe_reviewed AND ingredient_lines>0 AND lines_ready=ingredient_lines AND unit_count=1
            THEN total ELSE NULL END AS verified_per_serving
FROM coverage;

CREATE OR REPLACE VIEW de_recipe_readiness WITH (security_invoker=true) AS
SELECT r.recipe_id,r.recipe_name,r.external_source_id,r.data_source,
       count(l.line_id) AS ingredient_lines,
       count(l.line_id) FILTER(WHERE l.has_nutrition) AS lines_with_nutrition,
       count(l.line_id) FILTER(WHERE l.has_rule_tags) AS lines_with_rule_tags,
       count(l.line_id) FILTER(WHERE l.quantity_g IS NULL) AS lines_missing_grams,
       count(l.line_id) FILTER(WHERE NOT l.quantity_ready) AS lines_quantity_unreviewed,
       count(l.line_id) FILTER(WHERE l.quantity_aligned IS NOT TRUE) AS lines_alignment_unconfirmed,
       coalesce(rr.review_status,'pending_review') AS recipe_review_status,
       (SELECT count(*) FROM recipe_steps s WHERE s.recipe_id=r.recipe_id) AS step_count,
       (SELECT count(*) FROM recipe_nutrition n WHERE n.recipe_id=r.recipe_id) AS published_nutrient_count
FROM recipes r LEFT JOIN de_ingredient_line_readiness l USING(recipe_id)
LEFT JOIN de_recipe_reviews rr ON rr.recipe_id=r.recipe_id
WHERE r.deleted_at IS NULL GROUP BY r.recipe_id,rr.review_status;

-- Match the API-only review model. No browser-facing grants or RLS policies.
DO $$ DECLARE t text; role_name text; BEGIN
    FOREACH t IN ARRAY ARRAY['de_dataset_releases','de_mapping_reviews','de_line_reviews','de_recipe_reviews','de_line_provenance'] LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',t);
    END LOOP;
    FOREACH role_name IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=role_name) THEN
            FOREACH t IN ARRAY ARRAY['de_dataset_releases','de_mapping_reviews','de_line_reviews','de_recipe_reviews','de_line_provenance','de_ingredient_line_readiness','de_recipe_nutrient_readiness','de_recipe_readiness'] LOOP
                EXECUTE format('REVOKE ALL ON public.%I FROM %I',t,role_name);
            END LOOP;
        END IF;
    END LOOP;
END $$;
COMMIT;
