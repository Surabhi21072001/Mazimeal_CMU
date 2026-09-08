-- ============================================================================
--  Reference seed data
--
--  Enough real reference data to exercise the full chain end to end:
--    profile -> category -> baseline -> modifier -> target
--    ingredient -> nutrition -> synergy/bioavailability/GI -> recipe
--
--  Run after install.sql:  psql -d synergia -f db/seed/00_reference.sql
--  Idempotent — every insert is ON CONFLICT DO NOTHING.
--
--  ---------------------------------------------------------------------------
--  UNRESOLVED: the C001-C021 category mapping
--  ---------------------------------------------------------------------------
--  Sheet 04 sources categories from "Jessica's spreadsheet" and gives two
--  anchors: C001 = newborn female, C016 = early adult female. Twenty-one codes
--  cannot be reconstructed from two anchors — no ordering of age bands by sex
--  produces both. That file was not supplied with the schema.
--
--  The 18 rows below (9 age bands x 2 sexes, C001-C018) are a WORKING
--  PLACEHOLDER chosen to satisfy the schema's constraints and let
--  fn_derive_category_id() run. They are NOT the real clinical mapping and
--  C016 here is not early-adult-female. Replace this block wholesale once the
--  source spreadsheet arrives; nothing else in the schema depends on the codes
--  themselves, only on the FK.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- categories  (PLACEHOLDER — see header)
-- ---------------------------------------------------------------------------
INSERT INTO public.categories (category_id, category_name, age_group, sex, description) VALUES
    ('C001', 'newborn_female',        '0-6m',   'F', 'Newborn female, 0-6 months'),
    ('C002', 'newborn_male',          '0-6m',   'M', 'Newborn male, 0-6 months'),
    ('C003', 'infant_female',         '7-11m',  'F', 'Infant female, 7-11 months'),
    ('C004', 'infant_male',           '7-11m',  'M', 'Infant male, 7-11 months'),
    ('C005', 'toddler_female',        '1-3y',   'F', 'Toddler female, 1-3 years'),
    ('C006', 'toddler_male',          '1-3y',   'M', 'Toddler male, 1-3 years'),
    ('C007', 'young_child_female',    '4-8y',   'F', 'Young child female, 4-8 years'),
    ('C008', 'young_child_male',      '4-8y',   'M', 'Young child male, 4-8 years'),
    ('C009', 'older_child_female',    '9-13y',  'F', 'Older child female, 9-13 years'),
    ('C010', 'older_child_male',      '9-13y',  'M', 'Older child male, 9-13 years'),
    ('C011', 'adolescent_female',     '14-18y', 'F', 'Adolescent female, 14-18 years'),
    ('C012', 'adolescent_male',       '14-18y', 'M', 'Adolescent male, 14-18 years'),
    ('C013', 'early_adult_female',    '19-50y', 'F', 'Adult female, 19-50 years'),
    ('C014', 'early_adult_male',      '19-50y', 'M', 'Adult male, 19-50 years'),
    ('C015', 'mature_adult_female',   '51-70y', 'F', 'Adult female, 51-70 years'),
    ('C016', 'mature_adult_male',     '51-70y', 'M', 'Adult male, 51-70 years'),
    ('C017', 'older_adult_female',    '70+y',   'F', 'Older adult female, 70+'),
    ('C018', 'older_adult_male',      '70+y',   'M', 'Older adult male, 70+')
ON CONFLICT (category_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- nutrients_master — the MVP core 25
-- usda_nutrient_code values are USDA FoodData Central nutrient numbers.
-- ---------------------------------------------------------------------------
INSERT INTO public.nutrients_master
    (nutrient_id, nutrient_name, nutrient_category, default_unit, usda_nutrient_code, phase, notes) VALUES
    ('Energy',            'Energy',            'Macro',         'kcal', '208', 'MVP', NULL),
    ('Macro_Protein',     'Protein',           'Macro',         'g',    '203', 'MVP', 'Targets expressed as g/kg body weight'),
    ('Macro_Fat',         'Total Fat',         'Macro',         'g',    '204', 'MVP', NULL),
    ('Macro_Carbohydrate','Carbohydrate',      'Macro',         'g',    '205', 'MVP', NULL),
    ('Fiber',             'Dietary Fiber',     'Macro',         'g',    '291', 'MVP', NULL),
    ('Calcium',           'Calcium',           'Mineral',       'mg',   '301', 'MVP', NULL),
    ('Iron',              'Iron',              'Mineral',       'mg',   '303', 'MVP', 'Heme vs non-heme absorption differs ~5x'),
    ('Magnesium',         'Magnesium',         'Mineral',       'mg',   '304', 'MVP', NULL),
    ('Phosphorus',        'Phosphorus',        'Mineral',       'mg',   '305', 'MVP', NULL),
    ('Potassium',         'Potassium',         'Mineral',       'mg',   '306', 'MVP', NULL),
    ('Sodium',            'Sodium',            'Mineral',       'mg',   '307', 'MVP', NULL),
    ('Zinc',              'Zinc',              'Mineral',       'mg',   '309', 'MVP', NULL),
    ('Copper',            'Copper',            'Mineral',       'mg',   '312', 'MVP', NULL),
    ('Selenium',          'Selenium',          'Mineral',       'mcg',  '317', 'MVP', NULL),
    ('Vitamin_A',         'Vitamin A',         'Fat-soluble',   'mcg',  '320', 'MVP', 'RAE: retinol + provitamin A carotenoids'),
    ('Vitamin_D',         'Vitamin D',         'Fat-soluble',   'mcg',  '328', 'MVP', 'D2 + D3'),
    ('Vitamin_E',         'Vitamin E',         'Fat-soluble',   'mg',   '323', 'MVP', 'Alpha-tocopherol'),
    ('Vitamin_K',         'Vitamin K',         'Fat-soluble',   'mcg',  '430', 'MVP', 'K1 phylloquinone; K2 menaquinones tracked in Phase2'),
    ('Vitamin_C',         'Vitamin C',         'Water-soluble', 'mg',   '401', 'MVP', 'Enhances non-heme iron absorption'),
    ('Thiamin',           'Thiamin',           'Water-soluble', 'mg',   '404', 'MVP', 'B1'),
    ('Riboflavin',        'Riboflavin',        'Water-soluble', 'mg',   '405', 'MVP', 'B2'),
    ('Niacin',            'Niacin',            'Water-soluble', 'mg',   '406', 'MVP', 'B3'),
    ('Vitamin_B6',        'Vitamin B6',        'Water-soluble', 'mg',   '415', 'MVP', NULL),
    ('Folate',            'Folate',            'Water-soluble', 'mcg',  '435', 'MVP', 'DFE. Elevated requirement in pregnancy'),
    ('Vitamin_B12',       'Vitamin B12',       'Water-soluble', 'mcg',  '418', 'MVP', 'Absorption declines with age and with metformin'),
    ('Saturated_Fat',     'Saturated Fat',     'Macro',         'g',    '606', 'MVP', NULL),
    ('Sugar',             'Total Sugars',      'Macro',         'g',    '269', 'MVP', NULL),
    ('Cholesterol',       'Cholesterol',       'Other',         'mg',   '601', 'MVP', NULL)
ON CONFLICT (nutrient_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- usda_nutrient_ref — import mapping
-- ---------------------------------------------------------------------------
INSERT INTO public.usda_nutrient_ref (usda_nutrient_id, nutrient_id, usda_nutrient_name, usda_unit, conversion_factor)
SELECT usda_nutrient_code, nutrient_id, nutrient_name, default_unit, 1.0
FROM   public.nutrients_master
WHERE  usda_nutrient_code IS NOT NULL
ON CONFLICT (usda_nutrient_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- documents — evidence for the seeded rules
-- ---------------------------------------------------------------------------
INSERT INTO public.documents (document_id, title, document_type, url, rule_id_tags, category_tags) VALUES
    ('001', 'Ascorbic acid enhancement of non-heme iron absorption', 'peer_review',
            'https://pubmed.ncbi.nlm.nih.gov/2507689/', 'R001', NULL),
    ('002', 'Allicin formation: effect of resting crushed garlic before heating', 'peer_review',
            'https://pubmed.ncbi.nlm.nih.gov/11238797/', 'R002', NULL),
    ('003', 'Starch retrogradation and resistant starch formation on cooling', 'peer_review',
            'https://pubmed.ncbi.nlm.nih.gov/26693746/', 'R011', NULL),
    ('004', 'Dietary Reference Intakes — USDA / National Academies', 'USDA',
            'https://www.nal.usda.gov/human-nutrition-and-food-safety/dri-calculator', NULL, NULL)
ON CONFLICT (document_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- conditions
-- ---------------------------------------------------------------------------
INSERT INTO public.conditions (condition_code, condition_name, condition_category, requires_dietitian, hipaa_sensitive) VALUES
    ('C001', 'Type II Diabetes',      'metabolic',      TRUE,  TRUE),
    ('C002', 'Iron Deficiency Anemia','metabolic',      FALSE, TRUE),
    ('C003', 'Hypertension',          'cardiovascular', FALSE, TRUE),
    ('C004', 'Coeliac Disease',       'GI',             TRUE,  TRUE),
    ('C005', 'Chronic Kidney Disease','metabolic',      TRUE,  TRUE)
ON CONFLICT (condition_code) DO NOTHING;

INSERT INTO public.condition_attributes
    (attribute_id, condition_code, attribute_name, attribute_type, attribute_value, is_ai_guidance, dietitian_selectable, document_id) VALUES
    ('AT001', 'C001', 'Insulin resistance moderate', 'physiological',   'moderate',  TRUE, FALSE, NULL),
    ('AT002', 'C001', 'Metformin therapy',           'pharmacological', 'Metformin', TRUE, TRUE,  NULL),
    ('AT005', 'C002', 'Non-heme iron absorption low','physiological',   'low',       TRUE, FALSE, '001')
ON CONFLICT (attribute_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- nutrient_rules
-- ---------------------------------------------------------------------------
INSERT INTO public.nutrient_rules
    (rule_id, rule_name, rule_description, rule_type, applies_to_category, applies_to_condition,
     is_hard_constraint, document_id, short_description, source) VALUES
    ('R001', 'Vitamin_C_Iron_Synergy',
             'Consuming vitamin C in the same meal as a non-heme iron source substantially increases iron absorption.',
             'nutrient_threshold', NULL, 'C002', FALSE, '001',
             'Pair iron-rich plants with vitamin C.', 'https://pubmed.ncbi.nlm.nih.gov/2507689/'),
    ('R002', 'Allicin_Rest_Period',
             'Crushed or chopped garlic must rest ~10 minutes before heating to allow alliinase to convert alliin to allicin.',
             'prep_method', NULL, NULL, FALSE, '002',
             'Rest crushed garlic 10 minutes before cooking.', 'https://pubmed.ncbi.nlm.nih.gov/11238797/'),
    ('R011', 'Glycemic_Retrogradation',
             'Cooking then cooling starch raises resistant starch and materially lowers the glycemic response, persisting after reheating.',
             'prep_method', NULL, 'C001', FALSE, '003',
             'Cook, chill, then reheat rice and potatoes.', 'https://pubmed.ncbi.nlm.nih.gov/26693746/'),
    ('R085', 'No_Honey_Under_12m',
             'Honey must never be given to infants under 12 months due to the risk of infant botulism.',
             'food_safety', 'C001', NULL, TRUE, NULL,
             'No honey before 12 months.', 'https://www.cdc.gov/botulism/'),
    ('R596', 'Food_Sequence_VPC',
             'Eating vegetables first, protein second and carbohydrate last lowers the post-meal glucose excursion.',
             'behavioural', NULL, 'C001', FALSE, NULL,
             'Vegetables, then protein, then carbohydrate.', NULL)
ON CONFLICT (rule_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- nutrient_modifiers
-- Only Activity_level and Goal modifiers are seeded, matching what
-- fn_compute_member_targets() can currently resolve. See its SCOPE NOTE.
-- ---------------------------------------------------------------------------
INSERT INTO public.nutrient_modifiers
    (rule_id, nutrient_id, rule_category, sex, condition_field, condition_value,
     modifier_type, modifier_value, unit, priority, status, long_description) VALUES
    ('PROT_ACT_ANY_VERYACTIVE_001', 'Macro_Protein', 'Activity_level', NULL, 'activity_level', 'very_active',
     'Add', 0.4000, 'g/kg/day', 2, 'Validated',
     'Endurance and resistance training raise protein requirement above the 0.8 g/kg RDA.'),
    ('PROT_ACT_ANY_ATHLETE_001',    'Macro_Protein', 'Activity_level', NULL, 'activity_level', 'athlete',
     'Add', 0.8000, 'g/kg/day', 3, 'Validated',
     'Competitive athletes: 1.6-2.0 g/kg/day is the commonly cited range.'),
    ('PROT_GOAL_ANY_MUSCLE_001',    'Macro_Protein', 'Goal',           NULL, 'goal',           'muscle_gain',
     'Add', 0.4000, 'g/kg/day', 1, 'Validated',
     'Hypertrophy goal adds to the activity-level requirement.'),
    ('ENER_GOAL_ANY_LOSS_001',      'Energy',        'Goal',           NULL, 'goal',           'weight_loss',
     'Multiply', 0.8500, 'kcal', 1, 'Validated',
     'Moderate 15% deficit. Steeper deficits are not auto-planned.')
ON CONFLICT (rule_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- profile_nutrient_baselines — USDA DRI for the two adult categories
-- Seeded for C013 (adult female 19-50) and C014 (adult male 19-50) only; the
-- full ~25K-row matrix is an import job, not a seed file.
-- ---------------------------------------------------------------------------
INSERT INTO public.profile_nutrient_baselines
    (category_id, nutrient_id, baseline_value, unit, per, upper_threshold_day, source_url) VALUES
    ('C013', 'Energy',            2000,   'kcal', 'Day', NULL,  'https://www.nal.usda.gov/human-nutrition-and-food-safety/dri-calculator'),
    ('C013', 'Macro_Protein',     0.8000, 'g/kg/day', 'Day', NULL, 'https://www.nal.usda.gov/human-nutrition-and-food-safety/dri-calculator'),
    ('C013', 'Fiber',             25,     'g',   'Day', NULL,  NULL),
    ('C013', 'Iron',              18,     'mg',  'Day', 45,    NULL),
    ('C013', 'Calcium',           1000,   'mg',  'Day', 2500,  NULL),
    ('C013', 'Vitamin_C',         75,     'mg',  'Day', 2000,  NULL),
    ('C013', 'Vitamin_D',         15,     'mcg', 'Day', 100,   NULL),
    ('C013', 'Folate',            400,    'mcg', 'Day', 1000,  NULL),
    ('C013', 'Vitamin_B12',       2.4,    'mcg', 'Day', NULL,  NULL),
    ('C014', 'Energy',            2500,   'kcal', 'Day', NULL, NULL),
    ('C014', 'Macro_Protein',     0.8000, 'g/kg/day', 'Day', NULL, NULL),
    ('C014', 'Fiber',             38,     'g',   'Day', NULL,  NULL),
    ('C014', 'Iron',              8,      'mg',  'Day', 45,    NULL),
    ('C014', 'Calcium',           1000,   'mg',  'Day', 2500,  NULL),
    ('C014', 'Vitamin_C',         90,     'mg',  'Day', 2000,  NULL),
    ('C014', 'Vitamin_D',         15,     'mcg', 'Day', 100,   NULL),
    ('C014', 'Folate',            400,    'mcg', 'Day', 1000,  NULL),
    ('C014', 'Vitamin_B12',       2.4,    'mcg', 'Day', NULL,  NULL)
ON CONFLICT (category_id, nutrient_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- cultural_categories
-- ---------------------------------------------------------------------------
INSERT INTO public.cultural_categories (category_id, category_name, region, style_tags) VALUES
    ('01930000-0000-7000-8000-0000000000c1', 'Mediterranean', 'Southern Europe', ARRAY['family_friendly','quick_easy']),
    ('01930000-0000-7000-8000-0000000000c2', 'South Asian',   'Indian subcontinent', ARRAY['comfort_food']),
    ('01930000-0000-7000-8000-0000000000c3', 'East Asian',    'East Asia', ARRAY['quick_easy'])
ON CONFLICT (category_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- ingredients — enough to demonstrate synergy, bioavailability and GI
-- Fixed UUIDs so downstream seed rows can reference them.
-- ---------------------------------------------------------------------------
INSERT INTO public.ingredients
    (ingredient_id, usda_fdc_id, ingredient_name, ingredient_name_aliases, food_category,
     is_allergen, allergen_type, is_pet_toxic, pet_toxic_notes, typical_serving_g, data_source) VALUES
    ('01930000-0000-7000-8000-000000000001', 168462, 'Spinach, raw', ARRAY['espinaca','palak'],
     'Vegetables and Vegetable Products', FALSE, NULL, FALSE, NULL, 30, 'USDA'),
    ('01930000-0000-7000-8000-000000000002', 167774, 'Lemon juice, raw', ARRAY['limon'],
     'Fruits and Fruit Juices', FALSE, NULL, FALSE, NULL, 15, 'USDA'),
    ('01930000-0000-7000-8000-000000000003', 169230, 'Garlic, raw', ARRAY['ajo','lehsun'],
     'Vegetables and Vegetable Products', FALSE, NULL, TRUE,
     'Alliums damage feline and canine red blood cells. Never feed as scraps.', 3, 'USDA'),
    ('01930000-0000-7000-8000-000000000004', 168878, 'Rice, white, long-grain, cooked', ARRAY['arroz','chawal'],
     'Cereal Grains and Pasta', FALSE, NULL, FALSE, NULL, 158, 'USDA'),
    ('01930000-0000-7000-8000-000000000005', 175167, 'Lentils, cooked', ARRAY['dal','masoor'],
     'Legumes and Legume Products', FALSE, NULL, FALSE, NULL, 198, 'USDA'),
    ('01930000-0000-7000-8000-000000000006', 171705, 'Milk, whole', ARRAY['leche'],
     'Dairy and Egg Products', TRUE, 'Dairy', FALSE, NULL, 244, 'USDA'),
    ('01930000-0000-7000-8000-000000000007', 174832, 'Oat beverage, unsweetened', ARRAY['oat milk'],
     'Beverages', FALSE, NULL, FALSE, NULL, 240, 'Open Food Facts')
ON CONFLICT DO NOTHING;

INSERT INTO public.ingredient_nutrition
    (ingredient_id, nutrient_id, value_per_100g, unit, bioavailability_pct, bioavailability_notes) VALUES
    ('01930000-0000-7000-8000-000000000001', 'Iron',       2.7100, 'mg', 7.00,
     'Non-heme. Roughly triples when eaten with a vitamin C source in the same meal.'),
    ('01930000-0000-7000-8000-000000000001', 'Vitamin_C', 28.1000, 'mg', NULL, NULL),
    ('01930000-0000-7000-8000-000000000001', 'Folate',   194.0000, 'mcg', NULL, NULL),
    ('01930000-0000-7000-8000-000000000002', 'Vitamin_C', 38.7000, 'mg', NULL, NULL),
    ('01930000-0000-7000-8000-000000000004', 'Macro_Carbohydrate', 28.1700, 'g', NULL, NULL),
    ('01930000-0000-7000-8000-000000000005', 'Macro_Protein',       9.0200, 'g', NULL, NULL),
    ('01930000-0000-7000-8000-000000000005', 'Iron',                3.3300, 'mg', 6.00, 'Non-heme.'),
    ('01930000-0000-7000-8000-000000000006', 'Calcium',           123.0000, 'mg', NULL, NULL)
ON CONFLICT (ingredient_id, nutrient_id) DO NOTHING;

INSERT INTO public.ingredient_attributes (ingredient_id, attribute_type, attribute_value, rule_id) VALUES
    ('01930000-0000-7000-8000-000000000001', 'dietary_restriction', 'vegan',        NULL),
    ('01930000-0000-7000-8000-000000000001', 'food_property',       'high_oxalate', NULL),
    ('01930000-0000-7000-8000-000000000003', 'prep_method',         'raw_optimal',  'R002'),
    ('01930000-0000-7000-8000-000000000006', 'dietary_restriction', 'contains_dairy', NULL)
ON CONFLICT (ingredient_id, attribute_type, attribute_value) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Food science
-- ---------------------------------------------------------------------------
INSERT INTO public.ingredient_synergy_pairs
    (ingredient_id_a, ingredient_id_b, synergy_type, affected_nutrient_id, effect_multiplier,
     effect_description, preparation_required, rule_id, evidence_level, source) VALUES
    ('01930000-0000-7000-8000-000000000001', '01930000-0000-7000-8000-000000000002',
     'absorption_boost', 'Iron', 3.000,
     'Vitamin C converts ferric to ferrous iron, roughly tripling absorption from plant sources.',
     'Both consumed in the same meal', 'R001', 'strong',
     'https://pubmed.ncbi.nlm.nih.gov/2507689/')
ON CONFLICT DO NOTHING;

INSERT INTO public.ingredient_bioavailability
    (ingredient_id, prep_method, affected_nutrient_id, bioavailability_pct, vs_baseline_pct,
     prep_instruction, rule_id, evidence_level) VALUES
    ('01930000-0000-7000-8000-000000000003', 'crushed_rested_10min', 'Vitamin_C', 100.00, 100.00,
     'Crush or chop the garlic, then let it stand 10 minutes before it meets heat.', 'R002', 'strong'),
    ('01930000-0000-7000-8000-000000000003', 'crushed_cooked_immediately', 'Vitamin_C', 30.00, -70.00,
     'Heating immediately after crushing deactivates alliinase before allicin forms.', 'R002', 'strong')
ON CONFLICT (ingredient_id, prep_method, affected_nutrient_id) DO NOTHING;

INSERT INTO public.ingredient_substitutions
    (original_ingredient_id, substitute_ingredient_id, reason_type, nutrient_equivalence_pct, ratio, notes) VALUES
    ('01930000-0000-7000-8000-000000000006', '01930000-0000-7000-8000-000000000007',
     'allergen', 35.00, 1.000,
     'Oat beverage is far lower in protein and calcium unless fortified. Check the label.')
ON CONFLICT (original_ingredient_id, substitute_ingredient_id, reason_type) DO NOTHING;

INSERT INTO public.glycemic_index_data
    (ingredient_id, prep_method, glycemic_index, glycemic_load, resistant_starch_pct, notes) VALUES
    ('01930000-0000-7000-8000-000000000004', 'cooked',                  73, 29.00,  0.60, 'Baseline white rice.'),
    ('01930000-0000-7000-8000-000000000004', 'cooked_cooled',           54, 21.00,  2.80, 'Retrogradation after 12h at 4C — rule R011.'),
    ('01930000-0000-7000-8000-000000000004', 'cooked_cooled_reheated',  58, 22.00,  2.40, 'Most of the resistant starch survives reheating.')
ON CONFLICT (ingredient_id, prep_method) DO NOTHING;

-- ---------------------------------------------------------------------------
-- A worked recipe: every food-science feature in one dish
-- ---------------------------------------------------------------------------
INSERT INTO public.recipes
    (recipe_id, recipe_name, recipe_description, prep_time_min, cook_time_min, difficulty_level,
     servings, calories_per_serving, glycemic_index_estimate, cultural_category_id, regional_origin,
     data_source, is_ai_generated, active_rule_ids_csv) VALUES
    ('01930000-0000-7000-8000-0000000000f1',
     'Spinach and Lentil Dal with Rested Garlic',
     'Iron-forward dal finished with lemon for absorption, garlic rested before it meets the pan, '
     'served over rice cooked ahead and chilled to lower its glycemic load.',
     15, 35, 'Easy', 4, 410, 54.00,
     '01930000-0000-7000-8000-0000000000c2', 'India', 'Manual', FALSE, 'R001,R002,R011,R596')
ON CONFLICT DO NOTHING;

INSERT INTO public.recipe_ingredients
    (recipe_id, ingredient_id, quantity, unit, preparation_note, is_optional, can_substitute, synergy_role, sequence_order) VALUES
    ('01930000-0000-7000-8000-0000000000f1', '01930000-0000-7000-8000-000000000001',
     200, 'g', 'washed, roughly chopped', FALSE, TRUE, 'iron_source', 1),
    ('01930000-0000-7000-8000-0000000000f1', '01930000-0000-7000-8000-000000000005',
     300, 'g', 'cooked', FALSE, TRUE, 'iron_source', 2),
    ('01930000-0000-7000-8000-0000000000f1', '01930000-0000-7000-8000-000000000002',
     30, 'ml', 'juiced, added off the heat', FALSE, FALSE, 'vit_c_enhancer', 2),
    ('01930000-0000-7000-8000-0000000000f1', '01930000-0000-7000-8000-000000000003',
     4, 'cloves', 'crushed, rested 10 minutes', FALSE, TRUE, NULL, 2),
    ('01930000-0000-7000-8000-0000000000f1', '01930000-0000-7000-8000-000000000004',
     600, 'g', 'cooked the day before, chilled, reheated', FALSE, TRUE, 'resistant_starch', 3)
ON CONFLICT DO NOTHING;

INSERT INTO public.recipe_steps (recipe_id, step_number, instruction, bioavail_rule_id, duration_min, timing_note) VALUES
    ('01930000-0000-7000-8000-0000000000f1', 1,
     'Crush the garlic and set it aside. Do not cook it yet.', 'R002', 10,
     'The 10-minute rest is what lets allicin form.'),
    ('01930000-0000-7000-8000-0000000000f1', 2,
     'Warm the rice cooked and chilled the previous day.', 'R011', 5,
     'Cooling then reheating keeps the resistant starch.'),
    ('01930000-0000-7000-8000-0000000000f1', 3,
     'Soften the rested garlic in oil, add the lentils and spinach, and cook until the spinach wilts.', NULL, 15, NULL),
    ('01930000-0000-7000-8000-0000000000f1', 4,
     'Take the pan off the heat and stir the lemon juice through.', 'R001', 1,
     'Off the heat: vitamin C degrades quickly when it boils.')
ON CONFLICT (recipe_id, step_number) DO NOTHING;

INSERT INTO public.recipe_rules_map (recipe_id, rule_id, rule_satisfied, confidence_score, notes) VALUES
    ('01930000-0000-7000-8000-0000000000f1', 'R001', TRUE, 0.950, 'Lemon juice paired with two non-heme iron sources.'),
    ('01930000-0000-7000-8000-0000000000f1', 'R002', TRUE, 0.990, 'Rest period is an explicit step.'),
    ('01930000-0000-7000-8000-0000000000f1', 'R011', TRUE, 0.900, 'Rice is cooked, chilled and reheated.'),
    ('01930000-0000-7000-8000-0000000000f1', 'R596', TRUE, 0.750, 'sequence_order set: vegetables, protein, carbohydrate.')
ON CONFLICT (recipe_id, rule_id) DO NOTHING;
