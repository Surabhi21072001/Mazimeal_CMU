-- 006_nutrition_substitute_source.sql
-- A source for values taken from a near match rather than the exact food.
--
-- Why this is needed, from surveying the 50 seed recipes' 206 ingredients:
-- 16 of them are missing at least one of the 28 nutrients, and in almost
-- every case the gap is not an import that dropped rows. The USDA food the
-- ingredient points at genuinely does not report the nutrient. Checked
-- against the API, ingredients.usda_fdc_id = 173068 is
--
--     Beef, Australian, imported, grass-fed, ground, 85% lean / 15% fat, raw
--
-- and SR Legacy publishes 13 of our 28 nutrients for it. Zinc and folate are
-- not among them. The import was faithful; the source is partial.
--
-- That matters more than the count suggests. Weighted by grams rather than by
-- ingredient, ground beef is 454 g of three recipes - 69.5% of Authentic
-- Italian Meatballs - with no zinc or folate value at all, so those two
-- nutrients are computed from a third of a dish and presented as if from all
-- of it.
--
-- The options were to leave it blank, to estimate it, or to take the value
-- from a closely related USDA food that is fully profiled. Blank is honest
-- but loses the nutrient on the recipes where it matters most; an estimate is
-- a number with no provenance, which is the thing the data team's response
-- specifically asked us not to produce. A named substitute food is traceable:
-- the row says which food it came from and that it was not the exact one.
--
-- Precedence 20 puts it behind usda_sr_legacy (10) and ahead of foodcom (50)
-- and mazi_estimate (90). Because v_ingredient_nutrition is
-- DISTINCT ON (ingredient_id, nutrient_id) ORDER BY precedence, a row here
-- can only ever fill a gap - it cannot override an exact-match value, even by
-- mistake - and if the exact food is later published with that nutrient, the
-- new row wins with no deletion needed.

INSERT INTO data_sources
    (source_id, source_name, publisher, region, release, licence,
     attribution_text, url, precedence, ingested_at)
VALUES (
    'usda_fdc_substitute',
    'USDA FoodData Central, closest fully-profiled match',
    'USDA Agricultural Research Service',
    'United States',
    'FDC API, fetched per ingredient',
    'CC0 1.0 (public domain)',
    'U.S. Department of Agriculture, Agricultural Research Service. FoodData '
    'Central. fdc.nal.usda.gov. Used only where the food an ingredient points '
    'at does not report a nutrient; the substitute food is a different USDA '
    'entry for the same ingredient, named in bioavailability_notes on every '
    'row so the choice can be reviewed.',
    'https://fdc.nal.usda.gov/',
    20,
    current_date
)
ON CONFLICT (source_id) DO UPDATE SET
    source_name      = excluded.source_name,
    attribution_text = excluded.attribution_text,
    precedence       = excluded.precedence;
