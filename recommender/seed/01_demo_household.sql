-- 01_demo_household.sql
-- A household with two members whose needs differ, plus recipes with real
-- gram quantities so the recommender has something to rank.
--
--   Jeff  28M, 72.5kg, very active, muscle gain     -> high protein target
--   Maya  31F, 60kg, moderate, iron deficiency,     -> high iron target,
--         peanut allergy                               peanut recipes blocked
--
-- Nutrition values are per 100g, rounded from USDA FoodData Central.
-- Run after 00_reference.sql. Idempotent.

-- ---------------------------------------------------------------------------
-- Extra nutrients on the reference nutrient set for the demo
-- ---------------------------------------------------------------------------
INSERT INTO nutrient_modifiers
    (rule_id, nutrient_id, rule_category, sex, condition_field, condition_value,
     modifier_type, modifier_value, unit, priority, status, long_description) VALUES
    ('IRON_COND_ANY_C002_001', 'Iron', 'Condition', NULL, 'condition_code', 'C002',
     'Add', 9.0000, 'mg', 2, 'Validated',
     'Illustrative: raise dietary iron target for diagnosed iron deficiency. Real value is a dietitian decision.')
ON CONFLICT (rule_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Ingredients
-- ---------------------------------------------------------------------------
INSERT INTO ingredients
    (ingredient_id, usda_fdc_id, ingredient_name, food_category, is_allergen, allergen_type,
     typical_serving_g, data_source) VALUES
    ('01930000-0000-7000-8000-000000000010', 171477, 'Chicken breast, cooked', 'Poultry Products', FALSE, NULL, 120, 'USDA'),
    ('01930000-0000-7000-8000-000000000011', 175168, 'Salmon, cooked',         'Finfish and Shellfish Products', TRUE, 'Fish', 120, 'USDA'),
    ('01930000-0000-7000-8000-000000000012', 169967, 'Broccoli, cooked',       'Vegetables and Vegetable Products', FALSE, NULL, 90, 'USDA'),
    ('01930000-0000-7000-8000-000000000013', 173424, 'Egg, whole, cooked',     'Dairy and Egg Products', TRUE, 'Eggs', 50, 'USDA'),
    ('01930000-0000-7000-8000-000000000014', 170903, 'Greek yogurt, plain',    'Dairy and Egg Products', TRUE, 'Dairy', 170, 'USDA'),
    ('01930000-0000-7000-8000-000000000015', 169705, 'Oats, rolled, dry',      'Breakfast Cereals', FALSE, NULL, 40, 'USDA'),
    ('01930000-0000-7000-8000-000000000016', 168483, 'Sweet potato, baked',    'Vegetables and Vegetable Products', FALSE, NULL, 130, 'USDA'),
    ('01930000-0000-7000-8000-000000000017', 173757, 'Chickpeas, cooked',      'Legumes and Legume Products', FALSE, NULL, 160, 'USDA'),
    ('01930000-0000-7000-8000-000000000018', 168917, 'Quinoa, cooked',         'Cereal Grains and Pasta', FALSE, NULL, 185, 'USDA'),
    ('01930000-0000-7000-8000-000000000019', 172470, 'Peanut butter',          'Legumes and Legume Products', TRUE, 'Nuts', 32, 'USDA'),
    ('01930000-0000-7000-8000-000000000020', 172475, 'Tofu, firm',             'Legumes and Legume Products', TRUE, 'Soy', 120, 'USDA'),
    ('01930000-0000-7000-8000-000000000021', 171413, 'Olive oil',              'Fats and Oils', FALSE, NULL, 14, 'USDA')
ON CONFLICT DO NOTHING;

INSERT INTO ingredient_nutrition (ingredient_id, nutrient_id, value_per_100g, unit) VALUES
    -- chicken breast
    ('01930000-0000-7000-8000-000000000010', 'Energy', 165, 'kcal'),
    ('01930000-0000-7000-8000-000000000010', 'Macro_Protein', 31, 'g'),
    ('01930000-0000-7000-8000-000000000010', 'Iron', 1.0, 'mg'),
    ('01930000-0000-7000-8000-000000000010', 'Vitamin_B12', 0.3, 'mcg'),
    -- salmon
    ('01930000-0000-7000-8000-000000000011', 'Energy', 206, 'kcal'),
    ('01930000-0000-7000-8000-000000000011', 'Macro_Protein', 22, 'g'),
    ('01930000-0000-7000-8000-000000000011', 'Vitamin_D', 11, 'mcg'),
    ('01930000-0000-7000-8000-000000000011', 'Vitamin_B12', 3.2, 'mcg'),
    -- broccoli
    ('01930000-0000-7000-8000-000000000012', 'Energy', 35, 'kcal'),
    ('01930000-0000-7000-8000-000000000012', 'Fiber', 3.3, 'g'),
    ('01930000-0000-7000-8000-000000000012', 'Vitamin_C', 65, 'mg'),
    ('01930000-0000-7000-8000-000000000012', 'Calcium', 40, 'mg'),
    ('01930000-0000-7000-8000-000000000012', 'Folate', 108, 'mcg'),
    ('01930000-0000-7000-8000-000000000012', 'Iron', 0.7, 'mg'),
    -- egg
    ('01930000-0000-7000-8000-000000000013', 'Energy', 155, 'kcal'),
    ('01930000-0000-7000-8000-000000000013', 'Macro_Protein', 13, 'g'),
    ('01930000-0000-7000-8000-000000000013', 'Iron', 1.8, 'mg'),
    ('01930000-0000-7000-8000-000000000013', 'Vitamin_D', 2.2, 'mcg'),
    ('01930000-0000-7000-8000-000000000013', 'Vitamin_B12', 1.1, 'mcg'),
    -- greek yogurt
    ('01930000-0000-7000-8000-000000000014', 'Energy', 59, 'kcal'),
    ('01930000-0000-7000-8000-000000000014', 'Macro_Protein', 10, 'g'),
    ('01930000-0000-7000-8000-000000000014', 'Calcium', 110, 'mg'),
    ('01930000-0000-7000-8000-000000000014', 'Vitamin_B12', 0.8, 'mcg'),
    -- oats
    ('01930000-0000-7000-8000-000000000015', 'Energy', 389, 'kcal'),
    ('01930000-0000-7000-8000-000000000015', 'Macro_Protein', 13, 'g'),
    ('01930000-0000-7000-8000-000000000015', 'Fiber', 10, 'g'),
    ('01930000-0000-7000-8000-000000000015', 'Iron', 4.3, 'mg'),
    -- sweet potato
    ('01930000-0000-7000-8000-000000000016', 'Energy', 90, 'kcal'),
    ('01930000-0000-7000-8000-000000000016', 'Fiber', 3.3, 'g'),
    ('01930000-0000-7000-8000-000000000016', 'Vitamin_C', 20, 'mg'),
    -- chickpeas
    ('01930000-0000-7000-8000-000000000017', 'Energy', 164, 'kcal'),
    ('01930000-0000-7000-8000-000000000017', 'Macro_Protein', 9, 'g'),
    ('01930000-0000-7000-8000-000000000017', 'Fiber', 7.6, 'g'),
    ('01930000-0000-7000-8000-000000000017', 'Iron', 2.9, 'mg'),
    ('01930000-0000-7000-8000-000000000017', 'Folate', 172, 'mcg'),
    -- quinoa
    ('01930000-0000-7000-8000-000000000018', 'Energy', 120, 'kcal'),
    ('01930000-0000-7000-8000-000000000018', 'Macro_Protein', 4.4, 'g'),
    ('01930000-0000-7000-8000-000000000018', 'Fiber', 2.8, 'g'),
    ('01930000-0000-7000-8000-000000000018', 'Iron', 1.5, 'mg'),
    -- peanut butter
    ('01930000-0000-7000-8000-000000000019', 'Energy', 588, 'kcal'),
    ('01930000-0000-7000-8000-000000000019', 'Macro_Protein', 25, 'g'),
    ('01930000-0000-7000-8000-000000000019', 'Fiber', 6, 'g'),
    ('01930000-0000-7000-8000-000000000019', 'Iron', 1.9, 'mg'),
    -- tofu
    ('01930000-0000-7000-8000-000000000020', 'Energy', 144, 'kcal'),
    ('01930000-0000-7000-8000-000000000020', 'Macro_Protein', 17, 'g'),
    ('01930000-0000-7000-8000-000000000020', 'Calcium', 350, 'mg'),
    ('01930000-0000-7000-8000-000000000020', 'Iron', 2.7, 'mg'),
    -- olive oil
    ('01930000-0000-7000-8000-000000000021', 'Energy', 884, 'kcal'),
    -- fill gaps on reference ingredients
    ('01930000-0000-7000-8000-000000000001', 'Energy', 23, 'kcal'),      -- spinach
    ('01930000-0000-7000-8000-000000000001', 'Macro_Protein', 2.9, 'g'),
    ('01930000-0000-7000-8000-000000000001', 'Fiber', 2.2, 'g'),
    ('01930000-0000-7000-8000-000000000001', 'Calcium', 99, 'mg'),
    ('01930000-0000-7000-8000-000000000004', 'Energy', 130, 'kcal'),     -- rice
    ('01930000-0000-7000-8000-000000000004', 'Macro_Protein', 2.7, 'g'),
    ('01930000-0000-7000-8000-000000000005', 'Energy', 116, 'kcal'),     -- lentils
    ('01930000-0000-7000-8000-000000000005', 'Fiber', 7.9, 'g'),
    ('01930000-0000-7000-8000-000000000005', 'Folate', 181, 'mcg')
ON CONFLICT (ingredient_id, nutrient_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Recipes, all 4 servings, gram quantities
-- ---------------------------------------------------------------------------
INSERT INTO recipes (recipe_id, recipe_name, recipe_description, prep_time_min, cook_time_min,
                     difficulty_level, servings, meal_category, dietary_tags, data_source, is_ai_generated) VALUES
    ('01930000-0000-7000-8000-0000000000f2', 'Grilled Chicken and Broccoli Rice Bowl',
     'Lean protein with greens over rice.', 10, 25, 'Easy', 4, 'Dinner', ARRAY['high_protein', 'dairy_free'], 'Manual', FALSE),
    ('01930000-0000-7000-8000-0000000000f3', 'Overnight Oats with Greek Yogurt',
     'Make the night before. Fiber and calcium to start the day.', 10, 0, 'Easy', 4, 'Breakfast', ARRAY['vegetarian'], 'Manual', FALSE),
    ('01930000-0000-7000-8000-0000000000f4', 'Baked Salmon with Sweet Potato',
     'Vitamin D and omega-3 from the salmon, slow carbs from the potato.', 10, 30, 'Easy', 4, 'Dinner', ARRAY['dairy_free', 'gluten_free'], 'Manual', FALSE),
    ('01930000-0000-7000-8000-0000000000f5', 'Peanut Butter Oat Bites',
     'No-bake snack. Contains peanuts.', 15, 0, 'Easy', 4, 'Snack', ARRAY['vegan'], 'Manual', FALSE),
    ('01930000-0000-7000-8000-0000000000f6', 'Tofu and Chickpea Curry with Spinach',
     'Plant iron from three sources, finished with lemon to help absorption.', 15, 30, 'Medium', 4, 'Dinner', ARRAY['vegan', 'gluten_free'], 'Manual', FALSE),
    ('01930000-0000-7000-8000-0000000000f7', 'Quinoa Egg Breakfast Bowl',
     'Complete protein from quinoa and eggs, broccoli for vitamin C.', 10, 15, 'Easy', 4, 'Breakfast', ARRAY['vegetarian', 'gluten_free'], 'Manual', FALSE)
ON CONFLICT DO NOTHING;

INSERT INTO recipe_ingredients (recipe_id, ingredient_id, quantity, unit) VALUES
    -- chicken bowl
    ('01930000-0000-7000-8000-0000000000f2', '01930000-0000-7000-8000-000000000010', 500, 'g'),
    ('01930000-0000-7000-8000-0000000000f2', '01930000-0000-7000-8000-000000000012', 400, 'g'),
    ('01930000-0000-7000-8000-0000000000f2', '01930000-0000-7000-8000-000000000004', 600, 'g'),
    ('01930000-0000-7000-8000-0000000000f2', '01930000-0000-7000-8000-000000000021', 2, 'tbsp'),
    -- overnight oats
    ('01930000-0000-7000-8000-0000000000f3', '01930000-0000-7000-8000-000000000015', 200, 'g'),
    ('01930000-0000-7000-8000-0000000000f3', '01930000-0000-7000-8000-000000000014', 400, 'g'),
    ('01930000-0000-7000-8000-0000000000f3', '01930000-0000-7000-8000-000000000006', 300, 'ml'),
    -- salmon
    ('01930000-0000-7000-8000-0000000000f4', '01930000-0000-7000-8000-000000000011', 500, 'g'),
    ('01930000-0000-7000-8000-0000000000f4', '01930000-0000-7000-8000-000000000016', 600, 'g'),
    ('01930000-0000-7000-8000-0000000000f4', '01930000-0000-7000-8000-000000000012', 300, 'g'),
    ('01930000-0000-7000-8000-0000000000f4', '01930000-0000-7000-8000-000000000021', 1, 'tbsp'),
    -- peanut bites
    ('01930000-0000-7000-8000-0000000000f5', '01930000-0000-7000-8000-000000000015', 200, 'g'),
    ('01930000-0000-7000-8000-0000000000f5', '01930000-0000-7000-8000-000000000019', 150, 'g'),
    -- tofu curry
    ('01930000-0000-7000-8000-0000000000f6', '01930000-0000-7000-8000-000000000020', 400, 'g'),
    ('01930000-0000-7000-8000-0000000000f6', '01930000-0000-7000-8000-000000000017', 400, 'g'),
    ('01930000-0000-7000-8000-0000000000f6', '01930000-0000-7000-8000-000000000001', 200, 'g'),
    ('01930000-0000-7000-8000-0000000000f6', '01930000-0000-7000-8000-000000000004', 600, 'g'),
    ('01930000-0000-7000-8000-0000000000f6', '01930000-0000-7000-8000-000000000002', 30, 'ml'),
    -- quinoa egg bowl
    ('01930000-0000-7000-8000-0000000000f7', '01930000-0000-7000-8000-000000000018', 600, 'g'),
    ('01930000-0000-7000-8000-0000000000f7', '01930000-0000-7000-8000-000000000013', 8, 'whole'),
    ('01930000-0000-7000-8000-0000000000f7', '01930000-0000-7000-8000-000000000012', 300, 'g')
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- The household
-- ---------------------------------------------------------------------------
INSERT INTO users (user_id, email, username, password_hash) VALUES
    ('01930000-0000-7000-8000-0000000000a1', 'jeff@example.com', 'jeff_l', 'demo')
ON CONFLICT DO NOTHING;

INSERT INTO households (household_id, created_by_user_id, household_name, country_region) VALUES
    ('01930000-0000-7000-8000-0000000000b1', '01930000-0000-7000-8000-0000000000a1', 'Demo Household', 'US')
ON CONFLICT DO NOTHING;

INSERT INTO household_members (member_id, household_id, member_name, age, sex_at_birth, weight_kg, height_cm, activity_level, goal) VALUES
    ('01930000-0000-7000-8000-0000000000d1', '01930000-0000-7000-8000-0000000000b1', 'Jeff', 28, 'M', 72.5, 178, 'very_active', 'muscle_gain'),
    ('01930000-0000-7000-8000-0000000000d2', '01930000-0000-7000-8000-0000000000b1', 'Maya', 31, 'F', 60.0, 165, 'moderate',    'wellness')
ON CONFLICT DO NOTHING;

INSERT INTO member_conditions (member_id, condition_type, condition_code, value_text, severity) VALUES
    ('01930000-0000-7000-8000-0000000000d2', 'condition', 'C002', NULL, 'moderate'),
    ('01930000-0000-7000-8000-0000000000d2', 'allergy',   NULL,   'peanuts', 'severe')
ON CONFLICT DO NOTHING;

-- Maya's peanut allergy resolved to the ingredient, blocked for the whole household
INSERT INTO user_allergen_map (household_id, member_id, ingredient_id, is_household_hard_block, severity) VALUES
    ('01930000-0000-7000-8000-0000000000b1', '01930000-0000-7000-8000-0000000000d2',
     '01930000-0000-7000-8000-000000000019', TRUE, 'severe')
ON CONFLICT DO NOTHING;

-- Compute both members' daily targets
SELECT fn_compute_member_targets('01930000-0000-7000-8000-0000000000d1') AS jeff_targets,
       fn_compute_member_targets('01930000-0000-7000-8000-0000000000d2') AS maya_targets;

-- ---------------------------------------------------------------------------
-- What each has eaten today. Jeff had a protein-heavy breakfast; Maya had
-- toast and coffee. This is what makes their recommendations differ.
-- ---------------------------------------------------------------------------
INSERT INTO nutrient_daily_log (member_id, log_date, nutrient_id, consumed_value, target_value)
SELECT t.member_id, current_date, t.nutrient_id,
       CASE t.nutrient_id
           WHEN 'Macro_Protein' THEN 55
           WHEN 'Energy'        THEN 700
           WHEN 'Calcium'       THEN 300
           WHEN 'Iron'          THEN 3
           ELSE 0 END,
       t.final_target_value
FROM   profile_nutrient_targets t
WHERE  t.member_id = '01930000-0000-7000-8000-0000000000d1'
ON CONFLICT (member_id, log_date, nutrient_id) DO NOTHING;

INSERT INTO nutrient_daily_log (member_id, log_date, nutrient_id, consumed_value, target_value)
SELECT t.member_id, current_date, t.nutrient_id,
       CASE t.nutrient_id
           WHEN 'Macro_Protein' THEN 8
           WHEN 'Energy'        THEN 250
           WHEN 'Fiber'         THEN 2
           ELSE 0 END,
       t.final_target_value
FROM   profile_nutrient_targets t
WHERE  t.member_id = '01930000-0000-7000-8000-0000000000d2'
ON CONFLICT (member_id, log_date, nutrient_id) DO NOTHING;
