-- 06_recipe_steps.sql
-- Ordered cooking steps. From the schema doc, sheet 07_Recipes.
-- Added now because the Food.com dataset provides instructions and they
-- shouldn't be squashed into the description.

CREATE TABLE IF NOT EXISTS recipe_steps (
    step_id          UUID         NOT NULL DEFAULT gen_random_uuid(),
    recipe_id        UUID         NOT NULL,
    step_number      SMALLINT     NOT NULL,
    instruction      TEXT         NOT NULL,
    bioavail_rule_id VARCHAR(30),           -- FK to nutrient_rules later
    duration_min     SMALLINT,
    timing_note      VARCHAR(150),

    CONSTRAINT pk_recipe_steps PRIMARY KEY (step_id),
    CONSTRAINT fk_rs_recipe FOREIGN KEY (recipe_id)
        REFERENCES recipes (recipe_id) ON DELETE CASCADE,
    CONSTRAINT uq_rs_recipe_step UNIQUE (recipe_id, step_number),
    CONSTRAINT ck_rs_number   CHECK (step_number > 0),
    CONSTRAINT ck_rs_duration CHECK (duration_min IS NULL OR duration_min >= 0)
);

COMMENT ON COLUMN recipe_steps.bioavail_rule_id IS 'Rule embedded in this step, e.g. rest garlic 10 min. Set later.';
