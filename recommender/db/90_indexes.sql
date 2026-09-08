-- ============================================================================
--  Sheet 09 · Index Strategy
--
--  Primary keys and UNIQUE constraints already created their own indexes in the
--  table DDL; this file adds only the access-path indexes the workbook's query
--  patterns require. Nothing here is speculative — every index below serves a
--  named query pattern from sheet 09 or a documented lookup on its own sheet.
--
--  Index choices, and why:
--    BTREE   — equality and range lookups on selective columns
--    BRIN    — append-only timestamp columns. A BRIN index on created_at is a
--              few kilobytes where a BTREE would be gigabytes, because the
--              physical row order already matches the time order.
--    GIN     — arrays (ANY() membership), JSONB keys, full-text tsvector
--    PARTIAL — indexes only the rows matching a predicate. deleted_at is NULL
--              for ~99% of rows, so a partial index on the deleted ones stays
--              tiny.
--
--  In production, add CONCURRENTLY to every CREATE INDEX below. It is omitted
--  here because CONCURRENTLY cannot run inside the transaction install.sql uses.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- Sheet 01 · Identity & auth
-- ---------------------------------------------------------------------------

-- Login path. Functional unique index makes case-insensitive email both correct
-- and indexed, and replaces a plain UNIQUE(email) that would allow
-- Jeff@x.com and jeff@x.com to coexist.
CREATE UNIQUE INDEX idx_users_email_lower ON public.users (lower(email));

CREATE INDEX idx_users_role         ON public.users (role);
CREATE INDEX idx_users_last_login   ON public.users (last_login_at);
CREATE INDEX idx_users_created_brin ON public.users USING BRIN (created_at);
CREATE INDEX idx_users_deleted      ON public.users (deleted_at) WHERE deleted_at IS NOT NULL;

CREATE INDEX idx_sessions_user      ON public.sessions (user_id);
CREATE INDEX idx_sessions_expires   ON public.sessions (expires_at);   -- hourly cleanup job
CREATE INDEX idx_sessions_revoked   ON public.sessions (revoked_at) WHERE revoked_at IS NOT NULL;
CREATE INDEX idx_sessions_created_brin ON public.sessions USING BRIN (created_at);

CREATE INDEX idx_audit_user_time    ON public.audit_log (user_id, occurred_at);
CREATE INDEX idx_audit_action       ON public.audit_log (action);
CREATE INDEX idx_audit_record       ON public.audit_log (table_name, record_id);
CREATE INDEX idx_audit_occurred_brin ON public.audit_log USING BRIN (occurred_at);

-- ---------------------------------------------------------------------------
-- Sheet 02 · Household & members
-- ---------------------------------------------------------------------------
CREATE INDEX idx_households_creator ON public.households (created_by_user_id);
CREATE INDEX idx_households_country ON public.households (country_region);
CREATE INDEX idx_households_tier    ON public.households (subscription_tier);
CREATE INDEX idx_households_deleted ON public.households (deleted_at) WHERE deleted_at IS NOT NULL;

-- Covering index: fetches every member of a household in a single index-only
-- scan, no heap access. This is on the critical path of essentially every
-- authenticated request.
CREATE INDEX idx_hm_household ON public.household_members (household_id)
    INCLUDE (member_id, member_name, category_id);

CREATE INDEX idx_hm_category     ON public.household_members (category_id);
CREATE INDEX idx_hm_goal         ON public.household_members (goal);
CREATE INDEX idx_hm_updated      ON public.household_members (updated_at);
CREATE INDEX idx_hm_deleted      ON public.household_members (deleted_at) WHERE deleted_at IS NOT NULL;
CREATE INDEX idx_hm_diet         ON public.household_members USING GIN (lifestyle_dietary);
CREATE INDEX idx_hm_food_pref    ON public.household_members USING GIN (food_preference_csv);

CREATE INDEX idx_mc_member_type  ON public.member_conditions (member_id, condition_type);
CREATE INDEX idx_mc_condition    ON public.member_conditions (condition_code);

CREATE INDEX idx_uam_household   ON public.user_allergen_map (household_id);
CREATE INDEX idx_uam_member      ON public.user_allergen_map (member_id);
CREATE INDEX idx_uam_ingredient  ON public.user_allergen_map (ingredient_id);
-- One block row per household+ingredient; the union is a set, not a bag.
CREATE UNIQUE INDEX idx_uam_hh_ing_uq ON public.user_allergen_map (household_id, ingredient_id)
    WHERE ingredient_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Sheet 03 · Conditions & rules
-- ---------------------------------------------------------------------------
CREATE INDEX idx_ca_condition   ON public.condition_attributes (condition_code);
CREATE INDEX idx_nr_condition   ON public.nutrient_rules (applies_to_condition);
CREATE INDEX idx_nr_category    ON public.nutrient_rules (applies_to_category);
CREATE INDEX idx_nr_type        ON public.nutrient_rules (rule_type);
-- Hard constraints are pulled as a set on every scoring pass; they are a small
-- fraction of the table, so a partial index keeps that lookup near-free.
CREATE INDEX idx_nr_hard        ON public.nutrient_rules (rule_id) WHERE is_hard_constraint;

CREATE INDEX idx_nm_nutrient_cat ON public.nutrient_modifiers (nutrient_id, rule_category);
CREATE INDEX idx_nm_status       ON public.nutrient_modifiers (status);

CREATE INDEX idx_documents_type  ON public.documents (document_type);
CREATE INDEX idx_documents_title_fts
    ON public.documents USING GIN (to_tsvector('english', title));

-- ---------------------------------------------------------------------------
-- Sheet 04 · Baselines & targets
-- ---------------------------------------------------------------------------
CREATE INDEX idx_pnb_category  ON public.profile_nutrient_baselines (category_id);
CREATE INDEX idx_pnb_nutrient  ON public.profile_nutrient_baselines (nutrient_id);

CREATE INDEX idx_pnt_member    ON public.profile_nutrient_targets (member_id);
CREATE INDEX idx_pnt_nutrient  ON public.profile_nutrient_targets (nutrient_id);
CREATE INDEX idx_pnt_computed_brin
    ON public.profile_nutrient_targets USING BRIN (computed_at);

-- ---------------------------------------------------------------------------
-- Sheet 05 · Ingredients
-- ---------------------------------------------------------------------------
CREATE INDEX idx_ing_name_fts
    ON public.ingredients USING GIN (to_tsvector('english', ingredient_name));
CREATE INDEX idx_ing_aliases   ON public.ingredients USING GIN (ingredient_name_aliases);
CREATE INDEX idx_ing_category  ON public.ingredients (food_category);
CREATE INDEX idx_ing_allergen  ON public.ingredients (allergen_type) WHERE is_allergen;
CREATE INDEX idx_ing_pet_toxic ON public.ingredients (ingredient_id)  WHERE is_pet_toxic;
CREATE INDEX idx_ing_created_brin ON public.ingredients USING BRIN (created_at);

-- usda_fdc_id must be unique among non-NULL values. A partial unique index
-- expresses that exactly, but Postgres does not allow partial UNIQUE indexes on
-- a partitioned table, so SCALE mode falls back to a composite unique that
-- includes the partition key. The fallback is weaker: it would permit the same
-- FDC id in two different food categories. In practice food_category is derived
-- from the USDA record itself, so a duplicate would indicate an import bug —
-- 94_maintenance.sql ships fn_check_duplicate_fdc_ids() to detect it.
\if :scale
  CREATE UNIQUE INDEX idx_ing_fdc_uq ON public.ingredients (usda_fdc_id, food_category);
  CREATE UNIQUE INDEX idx_ing_name_uq ON public.ingredients (lower(btrim(ingredient_name)), food_category);
\else
  CREATE UNIQUE INDEX idx_ing_fdc_uq ON public.ingredients (usda_fdc_id)
      WHERE usda_fdc_id IS NOT NULL;
  -- Same name rule as the week-1 schema, so its seed files load here too.
  CREATE UNIQUE INDEX idx_ing_name_uq ON public.ingredients (lower(btrim(ingredient_name)));
\endif

CREATE INDEX idx_in_ingredient ON public.ingredient_nutrition (ingredient_id);
CREATE INDEX idx_in_nutrient   ON public.ingredient_nutrition (nutrient_id);

CREATE INDEX idx_ia_ing_type   ON public.ingredient_attributes (ingredient_id, attribute_type);
CREATE INDEX idx_ia_value      ON public.ingredient_attributes (attribute_value);

-- ---------------------------------------------------------------------------
-- Sheet 06 · Food science
-- ---------------------------------------------------------------------------

-- Canonical pair deduplication: (A,B) and (B,A) collapse to one row.
CREATE UNIQUE INDEX idx_syn_pair_uq ON public.ingredient_synergy_pairs
    (LEAST(ingredient_id_a, ingredient_id_b), GREATEST(ingredient_id_a, ingredient_id_b));

CREATE INDEX idx_syn_a        ON public.ingredient_synergy_pairs (ingredient_id_a);
CREATE INDEX idx_syn_b        ON public.ingredient_synergy_pairs (ingredient_id_b);
CREATE INDEX idx_syn_nutrient ON public.ingredient_synergy_pairs (affected_nutrient_id);

CREATE INDEX idx_ib_ingredient ON public.ingredient_bioavailability (ingredient_id);
CREATE INDEX idx_ib_prep       ON public.ingredient_bioavailability (prep_method);

CREATE INDEX idx_is_original   ON public.ingredient_substitutions (original_ingredient_id, reason_type);
CREATE INDEX idx_is_substitute ON public.ingredient_substitutions (substitute_ingredient_id);

CREATE INDEX idx_gi_ingredient ON public.glycemic_index_data (ingredient_id);

-- ---------------------------------------------------------------------------
-- Sheet 07 · Recipes
-- ---------------------------------------------------------------------------
CREATE INDEX idx_cc_style_tags ON public.cultural_categories USING GIN (style_tags);

CREATE INDEX idx_recipe_name_fts
    ON public.recipes USING GIN (to_tsvector('english', recipe_name));
CREATE INDEX idx_recipes_prep     ON public.recipes (prep_time_min);
CREATE INDEX idx_recipes_diff     ON public.recipes (difficulty_level);
CREATE INDEX idx_recipes_gi       ON public.recipes (glycemic_index_estimate);
CREATE INDEX idx_recipes_cultural ON public.recipes (cultural_category_id);
CREATE INDEX idx_recipes_source   ON public.recipes (data_source);
CREATE INDEX idx_recipes_ai       ON public.recipes (is_ai_generated);
CREATE INDEX idx_recipes_created_brin ON public.recipes USING BRIN (created_at);
CREATE INDEX idx_recipes_deleted  ON public.recipes (deleted_at) WHERE deleted_at IS NOT NULL;

\if :scale
  CREATE UNIQUE INDEX idx_recipes_external_uq ON public.recipes (external_source_id, data_source);
  CREATE UNIQUE INDEX idx_recipes_name_uq ON public.recipes (lower(recipe_name), data_source);
\else
  CREATE UNIQUE INDEX idx_recipes_external_uq ON public.recipes (external_source_id)
      WHERE external_source_id IS NOT NULL;
  CREATE UNIQUE INDEX idx_recipes_name_uq ON public.recipes (lower(recipe_name))
      WHERE deleted_at IS NULL;
\endif
CREATE INDEX idx_recipes_meal    ON public.recipes (meal_category);
CREATE INDEX idx_recipes_dietary ON public.recipes USING GIN (dietary_tags);

-- (recipe_id, ingredient_id) is covered by uq_ri_recipe_ingredient
CREATE INDEX idx_ri_ingredient ON public.recipe_ingredients (ingredient_id);

CREATE INDEX idx_rs_recipe     ON public.recipe_steps (recipe_id, step_number);

CREATE INDEX idx_rv_recipe     ON public.recipe_videos (recipe_id);
CREATE INDEX idx_rv_language   ON public.recipe_videos (language);
CREATE UNIQUE INDEX idx_rv_youtube_uq ON public.recipe_videos (youtube_video_id)
    WHERE platform = 'YouTube';
-- At most one featured video per recipe.
CREATE UNIQUE INDEX idx_rv_primary_uq ON public.recipe_videos (recipe_id) WHERE is_primary;

CREATE INDEX idx_rrm_rule      ON public.recipe_rules_map (rule_id);

-- ---------------------------------------------------------------------------
-- Sheet 08 · Plan & tracking
-- ---------------------------------------------------------------------------
CREATE INDEX idx_hrp_household_date ON public.household_recipe_plan (household_id, planned_date);
CREATE INDEX idx_hrp_recipe    ON public.household_recipe_plan (recipe_id);
CREATE INDEX idx_hrp_status    ON public.household_recipe_plan (status);
CREATE INDEX idx_hrp_meal_type ON public.household_recipe_plan (meal_type);
CREATE INDEX idx_hrp_created_brin ON public.household_recipe_plan USING BRIN (created_at);

-- DESC matches the dashboard's "most recent first" ordering, letting the
-- planner walk the index backwards without a sort.
CREATE INDEX idx_prh_member_eaten ON public.profile_recipe_history (member_id, eaten_at DESC);
CREATE INDEX idx_prh_recipe    ON public.profile_recipe_history (recipe_id);
CREATE INDEX idx_prh_week      ON public.profile_recipe_history (member_id, week_number);
CREATE INDEX idx_prh_snapshot  ON public.profile_recipe_history USING GIN (nutrient_snapshot);
CREATE INDEX idx_prh_created_brin ON public.profile_recipe_history USING BRIN (created_at);

CREATE INDEX idx_ndl_member_date ON public.nutrient_daily_log (member_id, log_date);
CREATE INDEX idx_ndl_nutrient  ON public.nutrient_daily_log (nutrient_id);
CREATE INDEX idx_ndl_alerts    ON public.nutrient_daily_log (member_id, log_date) WHERE alert_triggered;
CREATE INDEX idx_ndl_date_brin ON public.nutrient_daily_log USING BRIN (log_date);
