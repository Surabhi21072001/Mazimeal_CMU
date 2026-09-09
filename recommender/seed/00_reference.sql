-- ============================================================================
--  Reference seed data
--
--  Real reference data for the full chain:
--    profile -> category -> baseline -> modifier -> target
--    ingredient -> nutrition -> synergy/bioavailability/GI -> recipe
--
--  Run after install.sql. Safe to run more than once.
--
--  Category codes: the schema doc names C001 as newborn female and C016 as
--  early adult female but doesn't list the rest. The 18 codes below are
--  9 DRI age bands x 2 sexes, in age order. If the doc's own list turns up,
--  swap this block; only the FK depends on the codes.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- categories
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
-- nutrients_master, the MVP core 25
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
-- usda_nutrient_ref, import mapping
-- ---------------------------------------------------------------------------
INSERT INTO public.usda_nutrient_ref (usda_nutrient_id, nutrient_id, usda_nutrient_name, usda_unit, conversion_factor)
SELECT usda_nutrient_code, nutrient_id, nutrient_name, default_unit, 1.0
FROM   public.nutrients_master
WHERE  usda_nutrient_code IS NOT NULL
ON CONFLICT (usda_nutrient_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- documents, evidence for the seeded rules
-- ---------------------------------------------------------------------------
INSERT INTO public.documents (document_id, title, document_type, url, rule_id_tags, category_tags) VALUES
    ('001', 'Ascorbic acid enhancement of non-heme iron absorption', 'peer_review',
            'https://pubmed.ncbi.nlm.nih.gov/2507689/', 'R001', NULL),
    ('002', 'Allicin formation: effect of resting crushed garlic before heating', 'peer_review',
            'https://pubmed.ncbi.nlm.nih.gov/11238797/', 'R002', NULL),
    ('003', 'Starch retrogradation and resistant starch formation on cooling', 'peer_review',
            'https://pubmed.ncbi.nlm.nih.gov/26693746/', 'R011', NULL),
    ('004', 'Dietary Reference Intakes, USDA / National Academies', 'USDA',
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
-- profile_nutrient_baselines
-- Dietary Reference Intakes (RDA, or AI where there is no RDA) and upper
-- limits for every age/sex category from 1 year up, 28 nutrients each.
-- Generated by seed/gen_dri.py; edit that, not this block.
-- Sodium, saturated fat, sugar and cholesterol have a target of 0 and only an
-- upper limit, so the recommender never rewards them.
-- Infants (C001-C004) have no rows on purpose.
-- ---------------------------------------------------------------------------
INSERT INTO public.profile_nutrient_baselines
    (category_id, nutrient_id, baseline_value, unit, per, upper_threshold_day, source_url) VALUES
    ('C005', 'Energy', 1200, 'kcal', 'Day', NULL, 'https://www.dietaryguidelines.gov/sites/default/files/2020-12/Dietary_Guidelines_for_Americans_2020-2025.pdf'),
    ('C005', 'Macro_Protein', 1.05, 'g/kg/day', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C005', 'Macro_Carbohydrate', 130, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C005', 'Fiber', 19, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C005', 'Calcium', 700, 'mg', 'Day', 2500, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C005', 'Iron', 7, 'mg', 'Day', 40, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C005', 'Magnesium', 80, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C005', 'Phosphorus', 460, 'mg', 'Day', 3000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C005', 'Potassium', 2000, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C005', 'Zinc', 3, 'mg', 'Day', 7, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C005', 'Copper', 0.34, 'mg', 'Day', 1, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C005', 'Selenium', 20, 'mcg', 'Day', 90, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C005', 'Vitamin_A', 300, 'mcg', 'Day', 600, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C005', 'Vitamin_D', 15, 'mcg', 'Day', 63, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C005', 'Vitamin_E', 6, 'mg', 'Day', 200, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C005', 'Vitamin_K', 30, 'mcg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C005', 'Vitamin_C', 15, 'mg', 'Day', 400, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C005', 'Thiamin', 0.5, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C005', 'Riboflavin', 0.5, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C005', 'Niacin', 6, 'mg', 'Day', 10, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C005', 'Vitamin_B6', 0.5, 'mg', 'Day', 30, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C005', 'Folate', 150, 'mcg', 'Day', 300, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C005', 'Vitamin_B12', 0.9, 'mcg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C005', 'Sodium', 0, 'mg', 'Day', 1200, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C005', 'Saturated_Fat', 0, 'g', 'Day', 13, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C005', 'Sugar', 0, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C005', 'Cholesterol', 0, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C006', 'Energy', 1200, 'kcal', 'Day', NULL, 'https://www.dietaryguidelines.gov/sites/default/files/2020-12/Dietary_Guidelines_for_Americans_2020-2025.pdf'),
    ('C006', 'Macro_Protein', 1.05, 'g/kg/day', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C006', 'Macro_Carbohydrate', 130, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C006', 'Fiber', 19, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C006', 'Calcium', 700, 'mg', 'Day', 2500, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C006', 'Iron', 7, 'mg', 'Day', 40, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C006', 'Magnesium', 80, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C006', 'Phosphorus', 460, 'mg', 'Day', 3000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C006', 'Potassium', 2000, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C006', 'Zinc', 3, 'mg', 'Day', 7, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C006', 'Copper', 0.34, 'mg', 'Day', 1, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C006', 'Selenium', 20, 'mcg', 'Day', 90, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C006', 'Vitamin_A', 300, 'mcg', 'Day', 600, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C006', 'Vitamin_D', 15, 'mcg', 'Day', 63, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C006', 'Vitamin_E', 6, 'mg', 'Day', 200, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C006', 'Vitamin_K', 30, 'mcg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C006', 'Vitamin_C', 15, 'mg', 'Day', 400, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C006', 'Thiamin', 0.5, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C006', 'Riboflavin', 0.5, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C006', 'Niacin', 6, 'mg', 'Day', 10, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C006', 'Vitamin_B6', 0.5, 'mg', 'Day', 30, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C006', 'Folate', 150, 'mcg', 'Day', 300, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C006', 'Vitamin_B12', 0.9, 'mcg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C006', 'Sodium', 0, 'mg', 'Day', 1200, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C006', 'Saturated_Fat', 0, 'g', 'Day', 13, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C006', 'Sugar', 0, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C006', 'Cholesterol', 0, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C007', 'Energy', 1500, 'kcal', 'Day', NULL, 'https://www.dietaryguidelines.gov/sites/default/files/2020-12/Dietary_Guidelines_for_Americans_2020-2025.pdf'),
    ('C007', 'Macro_Protein', 0.95, 'g/kg/day', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C007', 'Macro_Carbohydrate', 130, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C007', 'Fiber', 25, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C007', 'Calcium', 1000, 'mg', 'Day', 2500, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C007', 'Iron', 10, 'mg', 'Day', 40, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C007', 'Magnesium', 130, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C007', 'Phosphorus', 500, 'mg', 'Day', 3000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C007', 'Potassium', 2300, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C007', 'Zinc', 5, 'mg', 'Day', 12, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C007', 'Copper', 0.44, 'mg', 'Day', 3, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C007', 'Selenium', 30, 'mcg', 'Day', 150, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C007', 'Vitamin_A', 400, 'mcg', 'Day', 900, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C007', 'Vitamin_D', 15, 'mcg', 'Day', 75, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C007', 'Vitamin_E', 7, 'mg', 'Day', 300, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C007', 'Vitamin_K', 55, 'mcg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C007', 'Vitamin_C', 25, 'mg', 'Day', 650, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C007', 'Thiamin', 0.6, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C007', 'Riboflavin', 0.6, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C007', 'Niacin', 8, 'mg', 'Day', 15, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C007', 'Vitamin_B6', 0.6, 'mg', 'Day', 40, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C007', 'Folate', 200, 'mcg', 'Day', 400, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C007', 'Vitamin_B12', 1.2, 'mcg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C007', 'Sodium', 0, 'mg', 'Day', 1500, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C007', 'Saturated_Fat', 0, 'g', 'Day', 17, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C007', 'Sugar', 0, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C007', 'Cholesterol', 0, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C008', 'Energy', 1600, 'kcal', 'Day', NULL, 'https://www.dietaryguidelines.gov/sites/default/files/2020-12/Dietary_Guidelines_for_Americans_2020-2025.pdf'),
    ('C008', 'Macro_Protein', 0.95, 'g/kg/day', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C008', 'Macro_Carbohydrate', 130, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C008', 'Fiber', 25, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C008', 'Calcium', 1000, 'mg', 'Day', 2500, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C008', 'Iron', 10, 'mg', 'Day', 40, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C008', 'Magnesium', 130, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C008', 'Phosphorus', 500, 'mg', 'Day', 3000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C008', 'Potassium', 2300, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C008', 'Zinc', 5, 'mg', 'Day', 12, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C008', 'Copper', 0.44, 'mg', 'Day', 3, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C008', 'Selenium', 30, 'mcg', 'Day', 150, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C008', 'Vitamin_A', 400, 'mcg', 'Day', 900, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C008', 'Vitamin_D', 15, 'mcg', 'Day', 75, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C008', 'Vitamin_E', 7, 'mg', 'Day', 300, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C008', 'Vitamin_K', 55, 'mcg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C008', 'Vitamin_C', 25, 'mg', 'Day', 650, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C008', 'Thiamin', 0.6, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C008', 'Riboflavin', 0.6, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C008', 'Niacin', 8, 'mg', 'Day', 15, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C008', 'Vitamin_B6', 0.6, 'mg', 'Day', 40, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C008', 'Folate', 200, 'mcg', 'Day', 400, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C008', 'Vitamin_B12', 1.2, 'mcg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C008', 'Sodium', 0, 'mg', 'Day', 1500, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C008', 'Saturated_Fat', 0, 'g', 'Day', 18, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C008', 'Sugar', 0, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C008', 'Cholesterol', 0, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C009', 'Energy', 1800, 'kcal', 'Day', NULL, 'https://www.dietaryguidelines.gov/sites/default/files/2020-12/Dietary_Guidelines_for_Americans_2020-2025.pdf'),
    ('C009', 'Macro_Protein', 0.95, 'g/kg/day', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C009', 'Macro_Carbohydrate', 130, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C009', 'Fiber', 26, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C009', 'Calcium', 1300, 'mg', 'Day', 3000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C009', 'Iron', 8, 'mg', 'Day', 40, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C009', 'Magnesium', 240, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C009', 'Phosphorus', 1250, 'mg', 'Day', 4000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C009', 'Potassium', 2300, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C009', 'Zinc', 8, 'mg', 'Day', 23, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C009', 'Copper', 0.7, 'mg', 'Day', 5, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C009', 'Selenium', 40, 'mcg', 'Day', 280, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C009', 'Vitamin_A', 600, 'mcg', 'Day', 1700, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C009', 'Vitamin_D', 15, 'mcg', 'Day', 100, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C009', 'Vitamin_E', 11, 'mg', 'Day', 600, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C009', 'Vitamin_K', 60, 'mcg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C009', 'Vitamin_C', 45, 'mg', 'Day', 1200, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C009', 'Thiamin', 0.9, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C009', 'Riboflavin', 0.9, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C009', 'Niacin', 12, 'mg', 'Day', 20, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C009', 'Vitamin_B6', 1, 'mg', 'Day', 60, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C009', 'Folate', 300, 'mcg', 'Day', 600, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C009', 'Vitamin_B12', 1.8, 'mcg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C009', 'Sodium', 0, 'mg', 'Day', 1800, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C009', 'Saturated_Fat', 0, 'g', 'Day', 20, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C009', 'Sugar', 0, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C009', 'Cholesterol', 0, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C010', 'Energy', 2000, 'kcal', 'Day', NULL, 'https://www.dietaryguidelines.gov/sites/default/files/2020-12/Dietary_Guidelines_for_Americans_2020-2025.pdf'),
    ('C010', 'Macro_Protein', 0.95, 'g/kg/day', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C010', 'Macro_Carbohydrate', 130, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C010', 'Fiber', 31, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C010', 'Calcium', 1300, 'mg', 'Day', 3000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C010', 'Iron', 8, 'mg', 'Day', 40, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C010', 'Magnesium', 240, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C010', 'Phosphorus', 1250, 'mg', 'Day', 4000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C010', 'Potassium', 2500, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C010', 'Zinc', 8, 'mg', 'Day', 23, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C010', 'Copper', 0.7, 'mg', 'Day', 5, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C010', 'Selenium', 40, 'mcg', 'Day', 280, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C010', 'Vitamin_A', 600, 'mcg', 'Day', 1700, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C010', 'Vitamin_D', 15, 'mcg', 'Day', 100, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C010', 'Vitamin_E', 11, 'mg', 'Day', 600, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C010', 'Vitamin_K', 60, 'mcg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C010', 'Vitamin_C', 45, 'mg', 'Day', 1200, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C010', 'Thiamin', 0.9, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C010', 'Riboflavin', 0.9, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C010', 'Niacin', 12, 'mg', 'Day', 20, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C010', 'Vitamin_B6', 1, 'mg', 'Day', 60, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C010', 'Folate', 300, 'mcg', 'Day', 600, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C010', 'Vitamin_B12', 1.8, 'mcg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C010', 'Sodium', 0, 'mg', 'Day', 1800, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C010', 'Saturated_Fat', 0, 'g', 'Day', 22, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C010', 'Sugar', 0, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C010', 'Cholesterol', 0, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C011', 'Energy', 2000, 'kcal', 'Day', NULL, 'https://www.dietaryguidelines.gov/sites/default/files/2020-12/Dietary_Guidelines_for_Americans_2020-2025.pdf'),
    ('C011', 'Macro_Protein', 0.85, 'g/kg/day', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C011', 'Macro_Carbohydrate', 130, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C011', 'Fiber', 26, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C011', 'Calcium', 1300, 'mg', 'Day', 3000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C011', 'Iron', 15, 'mg', 'Day', 45, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C011', 'Magnesium', 360, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C011', 'Phosphorus', 1250, 'mg', 'Day', 4000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C011', 'Potassium', 2300, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C011', 'Zinc', 9, 'mg', 'Day', 34, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C011', 'Copper', 0.89, 'mg', 'Day', 8, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C011', 'Selenium', 55, 'mcg', 'Day', 400, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C011', 'Vitamin_A', 700, 'mcg', 'Day', 2800, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C011', 'Vitamin_D', 15, 'mcg', 'Day', 100, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C011', 'Vitamin_E', 15, 'mg', 'Day', 800, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C011', 'Vitamin_K', 75, 'mcg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C011', 'Vitamin_C', 65, 'mg', 'Day', 1800, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C011', 'Thiamin', 1, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C011', 'Riboflavin', 1, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C011', 'Niacin', 14, 'mg', 'Day', 30, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C011', 'Vitamin_B6', 1.2, 'mg', 'Day', 80, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C011', 'Folate', 400, 'mcg', 'Day', 800, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C011', 'Vitamin_B12', 2.4, 'mcg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C011', 'Sodium', 0, 'mg', 'Day', 2300, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C011', 'Saturated_Fat', 0, 'g', 'Day', 22, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C011', 'Sugar', 0, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C011', 'Cholesterol', 0, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C012', 'Energy', 2600, 'kcal', 'Day', NULL, 'https://www.dietaryguidelines.gov/sites/default/files/2020-12/Dietary_Guidelines_for_Americans_2020-2025.pdf'),
    ('C012', 'Macro_Protein', 0.85, 'g/kg/day', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C012', 'Macro_Carbohydrate', 130, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C012', 'Fiber', 38, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C012', 'Calcium', 1300, 'mg', 'Day', 3000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C012', 'Iron', 11, 'mg', 'Day', 45, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C012', 'Magnesium', 410, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C012', 'Phosphorus', 1250, 'mg', 'Day', 4000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C012', 'Potassium', 3000, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C012', 'Zinc', 11, 'mg', 'Day', 34, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C012', 'Copper', 0.89, 'mg', 'Day', 8, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C012', 'Selenium', 55, 'mcg', 'Day', 400, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C012', 'Vitamin_A', 900, 'mcg', 'Day', 2800, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C012', 'Vitamin_D', 15, 'mcg', 'Day', 100, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C012', 'Vitamin_E', 15, 'mg', 'Day', 800, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C012', 'Vitamin_K', 75, 'mcg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C012', 'Vitamin_C', 75, 'mg', 'Day', 1800, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C012', 'Thiamin', 1.2, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C012', 'Riboflavin', 1.3, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C012', 'Niacin', 16, 'mg', 'Day', 30, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C012', 'Vitamin_B6', 1.3, 'mg', 'Day', 80, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C012', 'Folate', 400, 'mcg', 'Day', 800, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C012', 'Vitamin_B12', 2.4, 'mcg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C012', 'Sodium', 0, 'mg', 'Day', 2300, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C012', 'Saturated_Fat', 0, 'g', 'Day', 29, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C012', 'Sugar', 0, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C012', 'Cholesterol', 0, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C013', 'Energy', 2000, 'kcal', 'Day', NULL, 'https://www.dietaryguidelines.gov/sites/default/files/2020-12/Dietary_Guidelines_for_Americans_2020-2025.pdf'),
    ('C013', 'Macro_Protein', 0.8, 'g/kg/day', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C013', 'Macro_Carbohydrate', 130, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C013', 'Fiber', 25, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C013', 'Calcium', 1000, 'mg', 'Day', 2500, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C013', 'Iron', 18, 'mg', 'Day', 45, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C013', 'Magnesium', 320, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C013', 'Phosphorus', 700, 'mg', 'Day', 4000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C013', 'Potassium', 2600, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C013', 'Zinc', 8, 'mg', 'Day', 40, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C013', 'Copper', 0.9, 'mg', 'Day', 10, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C013', 'Selenium', 55, 'mcg', 'Day', 400, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C013', 'Vitamin_A', 700, 'mcg', 'Day', 3000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C013', 'Vitamin_D', 15, 'mcg', 'Day', 100, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C013', 'Vitamin_E', 15, 'mg', 'Day', 1000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C013', 'Vitamin_K', 90, 'mcg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C013', 'Vitamin_C', 75, 'mg', 'Day', 2000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C013', 'Thiamin', 1.1, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C013', 'Riboflavin', 1.1, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C013', 'Niacin', 14, 'mg', 'Day', 35, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C013', 'Vitamin_B6', 1.3, 'mg', 'Day', 100, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C013', 'Folate', 400, 'mcg', 'Day', 1000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C013', 'Vitamin_B12', 2.4, 'mcg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C013', 'Sodium', 0, 'mg', 'Day', 2300, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C013', 'Saturated_Fat', 0, 'g', 'Day', 22, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C013', 'Sugar', 0, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C013', 'Cholesterol', 0, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C014', 'Energy', 2600, 'kcal', 'Day', NULL, 'https://www.dietaryguidelines.gov/sites/default/files/2020-12/Dietary_Guidelines_for_Americans_2020-2025.pdf'),
    ('C014', 'Macro_Protein', 0.8, 'g/kg/day', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C014', 'Macro_Carbohydrate', 130, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C014', 'Fiber', 38, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C014', 'Calcium', 1000, 'mg', 'Day', 2500, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C014', 'Iron', 8, 'mg', 'Day', 45, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C014', 'Magnesium', 420, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C014', 'Phosphorus', 700, 'mg', 'Day', 4000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C014', 'Potassium', 3400, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C014', 'Zinc', 11, 'mg', 'Day', 40, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C014', 'Copper', 0.9, 'mg', 'Day', 10, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C014', 'Selenium', 55, 'mcg', 'Day', 400, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C014', 'Vitamin_A', 900, 'mcg', 'Day', 3000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C014', 'Vitamin_D', 15, 'mcg', 'Day', 100, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C014', 'Vitamin_E', 15, 'mg', 'Day', 1000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C014', 'Vitamin_K', 120, 'mcg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C014', 'Vitamin_C', 90, 'mg', 'Day', 2000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C014', 'Thiamin', 1.2, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C014', 'Riboflavin', 1.3, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C014', 'Niacin', 16, 'mg', 'Day', 35, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C014', 'Vitamin_B6', 1.3, 'mg', 'Day', 100, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C014', 'Folate', 400, 'mcg', 'Day', 1000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C014', 'Vitamin_B12', 2.4, 'mcg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C014', 'Sodium', 0, 'mg', 'Day', 2300, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C014', 'Saturated_Fat', 0, 'g', 'Day', 29, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C014', 'Sugar', 0, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C014', 'Cholesterol', 0, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C015', 'Energy', 1800, 'kcal', 'Day', NULL, 'https://www.dietaryguidelines.gov/sites/default/files/2020-12/Dietary_Guidelines_for_Americans_2020-2025.pdf'),
    ('C015', 'Macro_Protein', 0.8, 'g/kg/day', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C015', 'Macro_Carbohydrate', 130, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C015', 'Fiber', 21, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C015', 'Calcium', 1200, 'mg', 'Day', 2000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C015', 'Iron', 8, 'mg', 'Day', 45, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C015', 'Magnesium', 320, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C015', 'Phosphorus', 700, 'mg', 'Day', 4000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C015', 'Potassium', 2600, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C015', 'Zinc', 8, 'mg', 'Day', 40, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C015', 'Copper', 0.9, 'mg', 'Day', 10, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C015', 'Selenium', 55, 'mcg', 'Day', 400, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C015', 'Vitamin_A', 700, 'mcg', 'Day', 3000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C015', 'Vitamin_D', 15, 'mcg', 'Day', 100, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C015', 'Vitamin_E', 15, 'mg', 'Day', 1000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C015', 'Vitamin_K', 90, 'mcg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C015', 'Vitamin_C', 75, 'mg', 'Day', 2000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C015', 'Thiamin', 1.1, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C015', 'Riboflavin', 1.1, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C015', 'Niacin', 14, 'mg', 'Day', 35, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C015', 'Vitamin_B6', 1.5, 'mg', 'Day', 100, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C015', 'Folate', 400, 'mcg', 'Day', 1000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C015', 'Vitamin_B12', 2.4, 'mcg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C015', 'Sodium', 0, 'mg', 'Day', 2300, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C015', 'Saturated_Fat', 0, 'g', 'Day', 20, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C015', 'Sugar', 0, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C015', 'Cholesterol', 0, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C016', 'Energy', 2300, 'kcal', 'Day', NULL, 'https://www.dietaryguidelines.gov/sites/default/files/2020-12/Dietary_Guidelines_for_Americans_2020-2025.pdf'),
    ('C016', 'Macro_Protein', 0.8, 'g/kg/day', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C016', 'Macro_Carbohydrate', 130, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C016', 'Fiber', 30, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C016', 'Calcium', 1000, 'mg', 'Day', 2000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C016', 'Iron', 8, 'mg', 'Day', 45, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C016', 'Magnesium', 420, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C016', 'Phosphorus', 700, 'mg', 'Day', 4000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C016', 'Potassium', 3400, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C016', 'Zinc', 11, 'mg', 'Day', 40, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C016', 'Copper', 0.9, 'mg', 'Day', 10, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C016', 'Selenium', 55, 'mcg', 'Day', 400, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C016', 'Vitamin_A', 900, 'mcg', 'Day', 3000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C016', 'Vitamin_D', 15, 'mcg', 'Day', 100, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C016', 'Vitamin_E', 15, 'mg', 'Day', 1000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C016', 'Vitamin_K', 120, 'mcg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C016', 'Vitamin_C', 90, 'mg', 'Day', 2000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C016', 'Thiamin', 1.2, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C016', 'Riboflavin', 1.3, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C016', 'Niacin', 16, 'mg', 'Day', 35, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C016', 'Vitamin_B6', 1.7, 'mg', 'Day', 100, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C016', 'Folate', 400, 'mcg', 'Day', 1000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C016', 'Vitamin_B12', 2.4, 'mcg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C016', 'Sodium', 0, 'mg', 'Day', 2300, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C016', 'Saturated_Fat', 0, 'g', 'Day', 26, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C016', 'Sugar', 0, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C016', 'Cholesterol', 0, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C017', 'Energy', 1800, 'kcal', 'Day', NULL, 'https://www.dietaryguidelines.gov/sites/default/files/2020-12/Dietary_Guidelines_for_Americans_2020-2025.pdf'),
    ('C017', 'Macro_Protein', 0.8, 'g/kg/day', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C017', 'Macro_Carbohydrate', 130, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C017', 'Fiber', 21, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C017', 'Calcium', 1200, 'mg', 'Day', 2000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C017', 'Iron', 8, 'mg', 'Day', 45, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C017', 'Magnesium', 320, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C017', 'Phosphorus', 700, 'mg', 'Day', 3000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C017', 'Potassium', 2600, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C017', 'Zinc', 8, 'mg', 'Day', 40, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C017', 'Copper', 0.9, 'mg', 'Day', 10, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C017', 'Selenium', 55, 'mcg', 'Day', 400, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C017', 'Vitamin_A', 700, 'mcg', 'Day', 3000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C017', 'Vitamin_D', 20, 'mcg', 'Day', 100, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C017', 'Vitamin_E', 15, 'mg', 'Day', 1000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C017', 'Vitamin_K', 90, 'mcg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C017', 'Vitamin_C', 75, 'mg', 'Day', 2000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C017', 'Thiamin', 1.1, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C017', 'Riboflavin', 1.1, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C017', 'Niacin', 14, 'mg', 'Day', 35, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C017', 'Vitamin_B6', 1.5, 'mg', 'Day', 100, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C017', 'Folate', 400, 'mcg', 'Day', 1000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C017', 'Vitamin_B12', 2.4, 'mcg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C017', 'Sodium', 0, 'mg', 'Day', 2300, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C017', 'Saturated_Fat', 0, 'g', 'Day', 20, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C017', 'Sugar', 0, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C017', 'Cholesterol', 0, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C018', 'Energy', 2200, 'kcal', 'Day', NULL, 'https://www.dietaryguidelines.gov/sites/default/files/2020-12/Dietary_Guidelines_for_Americans_2020-2025.pdf'),
    ('C018', 'Macro_Protein', 0.8, 'g/kg/day', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C018', 'Macro_Carbohydrate', 130, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C018', 'Fiber', 30, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C018', 'Calcium', 1200, 'mg', 'Day', 2000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C018', 'Iron', 8, 'mg', 'Day', 45, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C018', 'Magnesium', 420, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C018', 'Phosphorus', 700, 'mg', 'Day', 3000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C018', 'Potassium', 3400, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C018', 'Zinc', 11, 'mg', 'Day', 40, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C018', 'Copper', 0.9, 'mg', 'Day', 10, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C018', 'Selenium', 55, 'mcg', 'Day', 400, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C018', 'Vitamin_A', 900, 'mcg', 'Day', 3000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C018', 'Vitamin_D', 20, 'mcg', 'Day', 100, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C018', 'Vitamin_E', 15, 'mg', 'Day', 1000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C018', 'Vitamin_K', 120, 'mcg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C018', 'Vitamin_C', 90, 'mg', 'Day', 2000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C018', 'Thiamin', 1.2, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C018', 'Riboflavin', 1.3, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C018', 'Niacin', 16, 'mg', 'Day', 35, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C018', 'Vitamin_B6', 1.7, 'mg', 'Day', 100, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C018', 'Folate', 400, 'mcg', 'Day', 1000, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C018', 'Vitamin_B12', 2.4, 'mcg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C018', 'Sodium', 0, 'mg', 'Day', 2300, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C018', 'Saturated_Fat', 0, 'g', 'Day', 24, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C018', 'Sugar', 0, 'g', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/'),
    ('C018', 'Cholesterol', 0, 'mg', 'Day', NULL, 'https://www.ncbi.nlm.nih.gov/books/NBK545442/')
ON CONFLICT (category_id, nutrient_id) DO UPDATE SET
    baseline_value = EXCLUDED.baseline_value, unit = EXCLUDED.unit,
    upper_threshold_day = EXCLUDED.upper_threshold_day, source_url = EXCLUDED.source_url;

-- ---------------------------------------------------------------------------
-- cultural_categories
-- ---------------------------------------------------------------------------
INSERT INTO public.cultural_categories (category_id, category_name, region, style_tags) VALUES
    ('01930000-0000-7000-8000-0000000000c1', 'Mediterranean', 'Southern Europe', ARRAY['family_friendly','quick_easy']),
    ('01930000-0000-7000-8000-0000000000c2', 'South Asian',   'Indian subcontinent', ARRAY['comfort_food']),
    ('01930000-0000-7000-8000-0000000000c3', 'East Asian',    'East Asia', ARRAY['quick_easy'])
ON CONFLICT (category_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- ingredients, enough to demonstrate synergy, bioavailability and GI
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
    ('01930000-0000-7000-8000-000000000004', 'cooked_cooled',           54, 21.00,  2.80, 'Retrogradation after 12h at 4C, rule R011.'),
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
