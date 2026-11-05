# User Nutrition Profile Layer (MVP)

Storage-only layer for a single user's nutrition profile and daily nutrient
targets. No recommendation, scoring, filtering, or gap-calculation logic is
implemented here — just the tables and example data they will later feed.

## Tables

### `user_profile` (schema/13_user_profile.sql)
One row per user. UUID PK, `TIMESTAMPTZ` timestamps, named `ck_` constraints —
matching the rest of the schema.

| column | notes |
|---|---|
| user_id | UUID PK, `gen_random_uuid()` |
| name | required |
| age_years | required, `0 < age < 130` |
| sex | required, one of `female` / `male` / `other` / `prefer_not_to_say` |
| height_cm, weight_kg | optional, must be `> 0` when present |
| activity_level | optional: `sedentary` / `light` / `moderate` / `active` / `very_active` |
| goal | optional: `maintain_weight` / `lose_weight` / `gain_weight` |
| diet_type | optional free text (e.g. `mediterranean`) |
| allergies | `TEXT[]` — **HARD constraints later** (not enforced yet) |
| preferences | `TEXT[]` — **SOFT ranking signals later** (not enforced yet) |
| created_at, updated_at | `TIMESTAMPTZ DEFAULT now()` |

Allergies/preferences are arrays on the profile for the MVP (mirroring
`recipes.dietary_tags`), not separate tables.

### `user_nutrient_targets` (schema/14_user_nutrient_targets.sql)
Many targets per user. Composite PK `(user_id, nutrient_id)`; `ON DELETE
CASCADE` from `user_profile`.

| column | notes |
|---|---|
| user_id | FK → user_profile, cascade delete |
| nutrient_id | `VARCHAR(40)`, **same scheme as recipe_nutrition** |
| daily_target | required, `>= 0`, stored as a **daily** value |
| unit | required (`kcal`, `g`, `mg`, `mcg`) |
| minimum_target | optional floor (`>= 0`) |
| upper_limit | optional ceiling (`>= 0`) |
| target_source | `USDA` / `NIH` / `DRI` / `MaziMeal calculated` / `Manual` |

Bounds check: when both are set, `minimum_target <= upper_limit`.

## Nutrient ID convention
`nutrient_id` reuses the existing MaziMeal scheme from `recipe_nutrition` /
`ingredient_nutrition` (`Energy`, `Macro_Protein`, `Iron`, `Vitamin_C`,
`Calcium`, …). **No new scheme was invented.** There is currently no
`nutrients_master` table in the repo (the existing nutrition tables reference a
future one in comments but it was never created), so no FK is added here —
consistent with those tables. If a `nutrients_master` is added later, attach the
FK then.

## Targets are DAILY
Stored as daily values. Weekly is derived downstream as `daily_target * 7`.
Recommendation logic will operate at meal/day level.

## Example seed (schema/seed/user_example.sql)
Idempotent (fixed UUID + `ON CONFLICT DO UPDATE`). **DEMO DATA ONLY** — the
values are illustrative, not medically validated; `target_source = 'Manual'`.

Maya — age 34, female, 167.6 cm, 64 kg, moderate activity, maintain_weight,
mediterranean; allergies `{peanut}`; preferences `{chicken, onion}`.

| nutrient_id | daily_target | unit | upper_limit |
|---|---|---|---|
| Energy | 2000 | kcal | — |
| Macro_Protein | 70 | g | — |
| Iron | 18 | mg | 45 |
| Vitamin_C | 75 | mg | 2000 |
| Calcium | 1000 | mg | 2500 |

## Future flow (NOT implemented yet)

```
user_profile + user_nutrient_targets
        ↓
UserNutritionFacts            (runtime object, like RecipeFacts)

RecipeFacts + UserNutritionFacts + Business Rules
        ↓
Recipe suitability / recommendation
```

Intended downstream behaviour:

| Signal | Effect |
|---|---|
| Allergy violation | HARD BLOCK |
| Diet violation | HARD BLOCK |
| Nutrition target | determine nutritional suitability (under-target / over-upper-limit) |
| Preference | SOFT ranking signal |

None of that logic exists yet — this task created only the storage layer.

## Loading

```bash
psql mazimeal_dev -v ON_ERROR_STOP=1 -f schema/13_user_profile.sql
psql mazimeal_dev -v ON_ERROR_STOP=1 -f schema/14_user_nutrient_targets.sql
psql mazimeal_dev -v ON_ERROR_STOP=1 -f schema/seed/user_example.sql   # idempotent
```
