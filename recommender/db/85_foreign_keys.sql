-- ============================================================================
--  Foreign keys — declared centrally rather than inline
--
--  The workbook contains cross-domain references in both directions
--  (household_members -> categories in sheet 04, ingredient_attributes ->
--  nutrient_rules in sheet 03, user_allergen_map -> ingredients in sheet 05),
--  so no single table-creation order satisfies every FK inline. Collecting them
--  here also makes the SCALE-mode gap auditable in one place.
--
--  ---------------------------------------------------------------------------
--  READ THIS BEFORE CHOOSING SCALE MODE
--  ---------------------------------------------------------------------------
--  Postgres will not let a foreign key reference a partitioned table unless it
--  targets a unique constraint containing the partition key. Sheet 09
--  partitions household_members by household_id, ingredients by food_category,
--  and recipes by data_source — none of which appear in the referencing tables.
--
--  The result: 23 foreign keys CANNOT EXIST in SCALE mode. They are listed at
--  the bottom of this file. Every one of them must be enforced in application
--  code instead. Options, in order of preference:
--
--    1. Denormalise the partition key into the child table (e.g. carry
--       household_id on member_conditions) and use a composite FK. Costs 16
--       bytes a row; keeps the database authoritative.
--    2. Enforce in a service layer with a nightly orphan-detection job.
--    3. Do not partition these tables until the row counts actually demand it.
--
--  Option 3 is the honest recommendation for the near term: at anything under
--  ~10M rows a table these partitions cost referential integrity and buy
--  nothing measurable. MVP mode is not a toy — it is the correct starting point.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- Always valid: the referenced table is never partitioned
-- ---------------------------------------------------------------------------

-- Sheet 01 · Identity
ALTER TABLE public.sessions
    ADD CONSTRAINT fk_sessions_user
    FOREIGN KEY (user_id) REFERENCES public.users (user_id) ON DELETE CASCADE;

-- Audit rows must outlive their subject: never cascade a delete into the log.
ALTER TABLE public.audit_log
    ADD CONSTRAINT fk_audit_log_user
    FOREIGN KEY (user_id) REFERENCES public.users (user_id) ON DELETE SET NULL;

-- Sheet 02 · Household
ALTER TABLE public.households
    ADD CONSTRAINT fk_households_creator
    FOREIGN KEY (created_by_user_id) REFERENCES public.users (user_id);

ALTER TABLE public.household_members
    ADD CONSTRAINT fk_hm_household
    FOREIGN KEY (household_id) REFERENCES public.households (household_id) ON DELETE CASCADE;

ALTER TABLE public.household_members
    ADD CONSTRAINT fk_hm_category
    FOREIGN KEY (category_id) REFERENCES public.categories (category_id);

ALTER TABLE public.member_conditions
    ADD CONSTRAINT fk_mc_condition
    FOREIGN KEY (condition_code) REFERENCES public.conditions (condition_code);

ALTER TABLE public.user_allergen_map
    ADD CONSTRAINT fk_uam_household
    FOREIGN KEY (household_id) REFERENCES public.households (household_id) ON DELETE CASCADE;

-- Sheet 03 · Conditions & rules
ALTER TABLE public.condition_attributes
    ADD CONSTRAINT fk_ca_condition
    FOREIGN KEY (condition_code) REFERENCES public.conditions (condition_code) ON DELETE CASCADE;

ALTER TABLE public.condition_attributes
    ADD CONSTRAINT fk_ca_document
    FOREIGN KEY (document_id) REFERENCES public.documents (document_id);

ALTER TABLE public.nutrient_rules
    ADD CONSTRAINT fk_nr_category
    FOREIGN KEY (applies_to_category) REFERENCES public.categories (category_id);

ALTER TABLE public.nutrient_rules
    ADD CONSTRAINT fk_nr_condition
    FOREIGN KEY (applies_to_condition) REFERENCES public.conditions (condition_code);

ALTER TABLE public.nutrient_rules
    ADD CONSTRAINT fk_nr_document
    FOREIGN KEY (document_id) REFERENCES public.documents (document_id);

ALTER TABLE public.nutrient_modifiers
    ADD CONSTRAINT fk_nm_nutrient
    FOREIGN KEY (nutrient_id) REFERENCES public.nutrients_master (nutrient_id);

-- Sheet 04 · Baselines & targets
ALTER TABLE public.profile_nutrient_baselines
    ADD CONSTRAINT fk_pnb_category
    FOREIGN KEY (category_id) REFERENCES public.categories (category_id);

ALTER TABLE public.profile_nutrient_baselines
    ADD CONSTRAINT fk_pnb_nutrient
    FOREIGN KEY (nutrient_id) REFERENCES public.nutrients_master (nutrient_id);

ALTER TABLE public.profile_nutrient_targets
    ADD CONSTRAINT fk_pnt_nutrient
    FOREIGN KEY (nutrient_id) REFERENCES public.nutrients_master (nutrient_id);

-- Sheet 05 · Ingredients
ALTER TABLE public.ingredient_nutrition
    ADD CONSTRAINT fk_in_nutrient
    FOREIGN KEY (nutrient_id) REFERENCES public.nutrients_master (nutrient_id);

ALTER TABLE public.ingredient_nutrition
    ADD CONSTRAINT fk_in_source
    FOREIGN KEY (source_id) REFERENCES public.data_sources (source_id);

ALTER TABLE public.ingredient_measures
    ADD CONSTRAINT fk_im_source
    FOREIGN KEY (source_id) REFERENCES public.data_sources (source_id);

ALTER TABLE public.ingredient_source_map
    ADD CONSTRAINT fk_ism_source
    FOREIGN KEY (source_id) REFERENCES public.data_sources (source_id);

ALTER TABLE public.usda_nutrient_ref
    ADD CONSTRAINT fk_unr_nutrient
    FOREIGN KEY (nutrient_id) REFERENCES public.nutrients_master (nutrient_id);

ALTER TABLE public.ingredient_attributes
    ADD CONSTRAINT fk_ia_rule
    FOREIGN KEY (rule_id) REFERENCES public.nutrient_rules (rule_id);

-- Sheet 06 · Food science
ALTER TABLE public.ingredient_synergy_pairs
    ADD CONSTRAINT fk_syn_nutrient
    FOREIGN KEY (affected_nutrient_id) REFERENCES public.nutrients_master (nutrient_id);

ALTER TABLE public.ingredient_synergy_pairs
    ADD CONSTRAINT fk_syn_rule
    FOREIGN KEY (rule_id) REFERENCES public.nutrient_rules (rule_id);

ALTER TABLE public.ingredient_bioavailability
    ADD CONSTRAINT fk_ib_nutrient
    FOREIGN KEY (affected_nutrient_id) REFERENCES public.nutrients_master (nutrient_id);

ALTER TABLE public.ingredient_bioavailability
    ADD CONSTRAINT fk_ib_rule
    FOREIGN KEY (rule_id) REFERENCES public.nutrient_rules (rule_id);

ALTER TABLE public.ingredient_substitutions
    ADD CONSTRAINT fk_is_condition
    FOREIGN KEY (condition_code) REFERENCES public.conditions (condition_code);

ALTER TABLE public.ingredient_substitutions
    ADD CONSTRAINT fk_is_rule
    FOREIGN KEY (rule_id) REFERENCES public.nutrient_rules (rule_id);

-- Sheet 07 · Recipes
ALTER TABLE public.recipes
    ADD CONSTRAINT fk_rec_cultural_category
    FOREIGN KEY (cultural_category_id) REFERENCES public.cultural_categories (category_id);

ALTER TABLE public.recipe_steps
    ADD CONSTRAINT fk_rs_bioavail_rule
    FOREIGN KEY (bioavail_rule_id) REFERENCES public.nutrient_rules (rule_id);

ALTER TABLE public.recipe_rules_map
    ADD CONSTRAINT fk_rrm_rule
    FOREIGN KEY (rule_id) REFERENCES public.nutrient_rules (rule_id);

ALTER TABLE public.recipe_nutrition
    ADD CONSTRAINT fk_rn_nutrient
    FOREIGN KEY (nutrient_id) REFERENCES public.nutrients_master (nutrient_id);

-- Sheet 08 · Plan & tracking
ALTER TABLE public.household_recipe_plan
    ADD CONSTRAINT fk_hrp_household
    FOREIGN KEY (household_id) REFERENCES public.households (household_id) ON DELETE CASCADE;

ALTER TABLE public.profile_recipe_history
    ADD CONSTRAINT fk_prh_household
    FOREIGN KEY (household_id) REFERENCES public.households (household_id) ON DELETE CASCADE;

ALTER TABLE public.nutrient_daily_log
    ADD CONSTRAINT fk_ndl_nutrient
    FOREIGN KEY (nutrient_id) REFERENCES public.nutrients_master (nutrient_id);

-- ---------------------------------------------------------------------------
-- MVP mode only: 23 FKs whose target is partitioned under SCALE mode
-- ---------------------------------------------------------------------------
\if :scale
  \echo '!! SCALE mode: skipping 23 foreign keys into partitioned tables.'
  \echo '!! These must be enforced in the application. See v_unenforced_fks.'
\else

-- -> household_members
ALTER TABLE public.member_conditions
    ADD CONSTRAINT fk_mc_member
    FOREIGN KEY (member_id) REFERENCES public.household_members (member_id) ON DELETE CASCADE;

ALTER TABLE public.user_allergen_map
    ADD CONSTRAINT fk_uam_member
    FOREIGN KEY (member_id) REFERENCES public.household_members (member_id) ON DELETE CASCADE;

ALTER TABLE public.profile_nutrient_targets
    ADD CONSTRAINT fk_pnt_member
    FOREIGN KEY (member_id) REFERENCES public.household_members (member_id) ON DELETE CASCADE;

ALTER TABLE public.profile_recipe_history
    ADD CONSTRAINT fk_prh_member
    FOREIGN KEY (member_id) REFERENCES public.household_members (member_id) ON DELETE CASCADE;

ALTER TABLE public.nutrient_daily_log
    ADD CONSTRAINT fk_ndl_member
    FOREIGN KEY (member_id) REFERENCES public.household_members (member_id) ON DELETE CASCADE;

-- -> ingredients
ALTER TABLE public.user_allergen_map
    ADD CONSTRAINT fk_uam_ingredient
    FOREIGN KEY (ingredient_id) REFERENCES public.ingredients (ingredient_id);

ALTER TABLE public.ingredient_nutrition
    ADD CONSTRAINT fk_in_ingredient
    FOREIGN KEY (ingredient_id) REFERENCES public.ingredients (ingredient_id) ON DELETE CASCADE;

ALTER TABLE public.ingredient_attributes
    ADD CONSTRAINT fk_ia_ingredient
    FOREIGN KEY (ingredient_id) REFERENCES public.ingredients (ingredient_id) ON DELETE CASCADE;

ALTER TABLE public.ingredient_measures
    ADD CONSTRAINT fk_im_ingredient
    FOREIGN KEY (ingredient_id) REFERENCES public.ingredients (ingredient_id) ON DELETE CASCADE;

ALTER TABLE public.ingredient_source_map
    ADD CONSTRAINT fk_ism_ingredient
    FOREIGN KEY (ingredient_id) REFERENCES public.ingredients (ingredient_id) ON DELETE CASCADE;

ALTER TABLE public.ingredient_synergy_pairs
    ADD CONSTRAINT fk_syn_ingredient_a
    FOREIGN KEY (ingredient_id_a) REFERENCES public.ingredients (ingredient_id) ON DELETE CASCADE;

ALTER TABLE public.ingredient_synergy_pairs
    ADD CONSTRAINT fk_syn_ingredient_b
    FOREIGN KEY (ingredient_id_b) REFERENCES public.ingredients (ingredient_id) ON DELETE CASCADE;

ALTER TABLE public.ingredient_bioavailability
    ADD CONSTRAINT fk_ib_ingredient
    FOREIGN KEY (ingredient_id) REFERENCES public.ingredients (ingredient_id) ON DELETE CASCADE;

ALTER TABLE public.ingredient_substitutions
    ADD CONSTRAINT fk_is_original
    FOREIGN KEY (original_ingredient_id) REFERENCES public.ingredients (ingredient_id) ON DELETE CASCADE;

ALTER TABLE public.ingredient_substitutions
    ADD CONSTRAINT fk_is_substitute
    FOREIGN KEY (substitute_ingredient_id) REFERENCES public.ingredients (ingredient_id) ON DELETE CASCADE;

ALTER TABLE public.glycemic_index_data
    ADD CONSTRAINT fk_gi_ingredient
    FOREIGN KEY (ingredient_id) REFERENCES public.ingredients (ingredient_id) ON DELETE CASCADE;

ALTER TABLE public.recipe_ingredients
    ADD CONSTRAINT fk_ri_ingredient
    FOREIGN KEY (ingredient_id) REFERENCES public.ingredients (ingredient_id);

-- -> recipes
ALTER TABLE public.recipe_ingredients
    ADD CONSTRAINT fk_ri_recipe
    FOREIGN KEY (recipe_id) REFERENCES public.recipes (recipe_id) ON DELETE CASCADE;

ALTER TABLE public.recipe_steps
    ADD CONSTRAINT fk_rs_recipe
    FOREIGN KEY (recipe_id) REFERENCES public.recipes (recipe_id) ON DELETE CASCADE;

ALTER TABLE public.recipe_videos
    ADD CONSTRAINT fk_rv_recipe
    FOREIGN KEY (recipe_id) REFERENCES public.recipes (recipe_id) ON DELETE CASCADE;

ALTER TABLE public.recipe_rules_map
    ADD CONSTRAINT fk_rrm_recipe
    FOREIGN KEY (recipe_id) REFERENCES public.recipes (recipe_id) ON DELETE CASCADE;

ALTER TABLE public.recipe_nutrition
    ADD CONSTRAINT fk_rn_recipe
    FOREIGN KEY (recipe_id) REFERENCES public.recipes (recipe_id) ON DELETE CASCADE;

ALTER TABLE public.household_recipe_plan
    ADD CONSTRAINT fk_hrp_recipe
    FOREIGN KEY (recipe_id) REFERENCES public.recipes (recipe_id);

ALTER TABLE public.profile_recipe_history
    ADD CONSTRAINT fk_prh_recipe
    FOREIGN KEY (recipe_id) REFERENCES public.recipes (recipe_id);

\endif

-- ---------------------------------------------------------------------------
-- v_unenforced_fks — the integrity gap, queryable at runtime
--
-- Lists every relationship the workbook implies that the database is not
-- currently enforcing. Empty in MVP mode; 23 rows in SCALE mode. Wire this into
-- a startup assertion so the gap can never be forgotten.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.v_unenforced_fks AS
WITH expected (child_table, child_column, parent_table, parent_column) AS (
    VALUES
        ('member_conditions',        'member_id',                'household_members', 'member_id'),
        ('user_allergen_map',        'member_id',                'household_members', 'member_id'),
        ('profile_nutrient_targets', 'member_id',                'household_members', 'member_id'),
        ('profile_recipe_history',   'member_id',                'household_members', 'member_id'),
        ('nutrient_daily_log',       'member_id',                'household_members', 'member_id'),
        ('user_allergen_map',        'ingredient_id',            'ingredients',       'ingredient_id'),
        ('ingredient_nutrition',     'ingredient_id',            'ingredients',       'ingredient_id'),
        ('ingredient_attributes',    'ingredient_id',            'ingredients',       'ingredient_id'),
        ('ingredient_measures',      'ingredient_id',            'ingredients',       'ingredient_id'),
        ('ingredient_source_map',    'ingredient_id',            'ingredients',       'ingredient_id'),
        ('ingredient_synergy_pairs', 'ingredient_id_a',          'ingredients',       'ingredient_id'),
        ('ingredient_synergy_pairs', 'ingredient_id_b',          'ingredients',       'ingredient_id'),
        ('ingredient_bioavailability','ingredient_id',           'ingredients',       'ingredient_id'),
        ('ingredient_substitutions', 'original_ingredient_id',   'ingredients',       'ingredient_id'),
        ('ingredient_substitutions', 'substitute_ingredient_id', 'ingredients',       'ingredient_id'),
        ('glycemic_index_data',      'ingredient_id',            'ingredients',       'ingredient_id'),
        ('recipe_ingredients',       'ingredient_id',            'ingredients',       'ingredient_id'),
        ('recipe_ingredients',       'recipe_id',                'recipes',           'recipe_id'),
        ('recipe_steps',             'recipe_id',                'recipes',           'recipe_id'),
        ('recipe_videos',            'recipe_id',                'recipes',           'recipe_id'),
        ('recipe_rules_map',         'recipe_id',                'recipes',           'recipe_id'),
        ('household_recipe_plan',    'recipe_id',                'recipes',           'recipe_id'),
        ('profile_recipe_history',   'recipe_id',                'recipes',           'recipe_id')
)
SELECT e.child_table,
       e.child_column,
       e.parent_table,
       e.parent_column,
       'Parent table is partitioned; enforce this relationship in application code.' AS remediation
FROM expected e
WHERE NOT EXISTS (
    SELECT 1
    FROM   pg_constraint      c
    JOIN   pg_class           child ON child.oid = c.conrelid
    JOIN   pg_attribute       a     ON a.attrelid = c.conrelid
                                   AND a.attnum  = ANY (c.conkey)
    WHERE  c.contype    = 'f'
      AND  child.relname = e.child_table
      AND  a.attname     = e.child_column
);

COMMENT ON VIEW public.v_unenforced_fks IS
  'Relationships the workbook implies but the database does not enforce. Must be empty in MVP mode.';
