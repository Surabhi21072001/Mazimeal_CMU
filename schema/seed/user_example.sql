-- schema/seed/user_example.sql
-- Example single user + daily nutrient targets for development/demo.
-- Load after schema/13_user_profile.sql and schema/14_user_nutrient_targets.sql.
--
-- Idempotent: fixed user_id + ON CONFLICT DO UPDATE, safe to run repeatedly.
--
-- !!! DEMO DATA ONLY !!!
-- These values are illustrative placeholders, NOT medically validated targets
-- for this (fictional) person. target_source is marked 'Manual' to reflect
-- that. Replace with sourced DRI/NIH values before any real use.

BEGIN;

-- Fixed UUID so re-seeding updates the same row rather than creating new users.
INSERT INTO user_profile
    (user_id, name, age_years, sex, height_cm, weight_kg,
     activity_level, goal, diet_type, allergies, preferences)
VALUES
    ('11111111-1111-1111-1111-111111111111',
     'Maya', 34, 'female', 167.6, 64.0,
     'moderate', 'maintain_weight', 'mediterranean',
     ARRAY['peanut']::text[],
     ARRAY['chicken', 'onion']::text[])
ON CONFLICT (user_id) DO UPDATE SET
    name           = EXCLUDED.name,
    age_years      = EXCLUDED.age_years,
    sex            = EXCLUDED.sex,
    height_cm      = EXCLUDED.height_cm,
    weight_kg      = EXCLUDED.weight_kg,
    activity_level = EXCLUDED.activity_level,
    goal           = EXCLUDED.goal,
    diet_type      = EXCLUDED.diet_type,
    allergies      = EXCLUDED.allergies,
    preferences    = EXCLUDED.preferences,
    updated_at     = now();

-- Daily targets (DEMO values). nutrient_id matches recipe_nutrition's scheme.
INSERT INTO user_nutrient_targets
    (user_id, nutrient_id, daily_target, unit, minimum_target, upper_limit, target_source)
VALUES
    ('11111111-1111-1111-1111-111111111111', 'Energy',        2000, 'kcal', NULL, NULL, 'Manual'),
    ('11111111-1111-1111-1111-111111111111', 'Macro_Protein',   70, 'g',    NULL, NULL, 'Manual'),
    ('11111111-1111-1111-1111-111111111111', 'Iron',            18, 'mg',   NULL,   45, 'Manual'),
    ('11111111-1111-1111-1111-111111111111', 'Vitamin_C',       75, 'mg',   NULL, 2000, 'Manual'),
    ('11111111-1111-1111-1111-111111111111', 'Calcium',       1000, 'mg',   NULL, 2500, 'Manual')
ON CONFLICT (user_id, nutrient_id) DO UPDATE SET
    daily_target   = EXCLUDED.daily_target,
    unit           = EXCLUDED.unit,
    minimum_target = EXCLUDED.minimum_target,
    upper_limit    = EXCLUDED.upper_limit,
    target_source  = EXCLUDED.target_source;

COMMIT;
