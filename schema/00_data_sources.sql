-- 00_data_sources.sql
-- Where ingredient data comes from. One row per upstream database plus one
-- for our own estimates. Nutrient values, measures and matches point here,
-- so attribution and licence are a join away. precedence: lower wins when
-- two sources give a value for the same nutrient.

CREATE TABLE IF NOT EXISTS data_sources (
    source_id         VARCHAR(30)   NOT NULL,
    source_name       VARCHAR(120)  NOT NULL,
    publisher         VARCHAR(120),
    region            VARCHAR(60),
    release           VARCHAR(40),
    licence           VARCHAR(120),
    attribution_text  TEXT,
    url               TEXT,
    precedence        SMALLINT      NOT NULL,
    ingested_at       DATE,

    CONSTRAINT pk_data_sources PRIMARY KEY (source_id),
    CONSTRAINT uq_data_sources_precedence UNIQUE (precedence)
);

INSERT INTO data_sources VALUES
    ('usda_sr_legacy', 'USDA FoodData Central, SR Legacy', 'USDA Agricultural Research Service', 'United States',
     '2018-04 (FDC release 2019-04)', 'CC0 1.0 (public domain)',
     'U.S. Department of Agriculture, Agricultural Research Service. FoodData Central, SR Legacy. fdc.nal.usda.gov',
     'https://fdc.nal.usda.gov/', 10, '2026-09-08'),
    ('foodcom', 'Food.com recipes (Kaggle)', 'Food.com via Kaggle', 'United States',
     'irkaal/foodcom-recipes-and-reviews', 'scraped dataset; check terms before shipping',
     'Recipes and per-serving nutrition from Food.com', 'https://www.kaggle.com/datasets/irkaal/foodcom-recipes-and-reviews', 50, '2026-09-08'),
    ('mazi_estimate', 'MaziMeal estimate', 'MaziMeal', NULL, NULL, NULL,
     'Estimated by MaziMeal when no source publishes a value', NULL, 90, NULL)
ON CONFLICT (source_id) DO NOTHING;
