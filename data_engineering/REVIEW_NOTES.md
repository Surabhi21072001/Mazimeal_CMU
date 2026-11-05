# Integration review for Surabhi and Kevin

Reviewed against `main` at `e67a499`, November 5, 2026. This branch is based on
`main` because the repository currently has no `dev` branch. It is for review,
not an instruction to apply the migration directly to the live database.

## Changes made to Andrew's contribution

1. Reused the team's existing source registry and selected-source nutrition
   view. The older single-source uniqueness assumption is removed.
2. Kept the team's current rule response metadata, UI review table and user
   profile/target tables. No duplicate profile or plausibility-review system.
3. Changed the reproducible seed to the team's 400 recipes and default reporting
   to the exact 50 Food.com IDs read by the app. The old 24 extra sample recipes
   remain in Andrew's separate local demo database.
4. Added source-backed recipe completeness, gram and mapping checks. Nutrient
   totals stay NULL unless every required ingredient has reviewed inputs and
   compatible units. Changes invalidate affected reviews.
5. Fixed database readers that could roll back a caller's pending transaction
   when an optional column was absent. Kept actual instruction step numbers for
   the engine's matched-step references and excluded soft-deleted recipes.
6. Added isolated setup, repeatable reports, a local read-only viewer and
   PostgreSQL integration tests. Credentials, generated exports and private
   source checkouts are excluded.

## Validation on the committed seeds

- Fresh local import: 400 recipes, 559 ingredients, 555 source mappings,
  15,210 ingredient nutrient rows and 54 business rules. `validate_week1()`
  reported no FAIL results.
- Default report: all 50 CSV recipes resolved by external ID, with 469
  ingredient lines; one line has no grams and all 469 await quantity review.
- The current API adapter reads the seed list and a real recipe. All 50 recipe
  packets preserve the team's enriched evaluation fields.
- Unit suite: 92 tests reported OK, with two workbook-dependent suites skipped
  because the workbook is absent from the repository.
- PostgreSQL suite: 20 tests passed, including multi-source selection, missing
  nutrients, zero values, mixed units, review invalidation, migration re-run,
  existing profile/target preservation and separation from UI plausibility.

These results are from the isolated seed database, not a re-audit of Supabase.

## Decisions and data work still needed

- **Kevin:** decide how `de_recipe_nutrient_readiness.ready` and NULL totals
  should reach the API/UI. This branch does not change the existing endpoint's
  estimated nutrition behavior. Check migration permissions with the actual
  backend role in staging before deployment.
- **Andrew with the recipe reviewer:** resolve source quantities and ingredient
  completeness before recording approvals. For example, the seeded Falafel
  instructions mention breadcrumbs and a pita pocket, but its ingredient list
  contains neither. Do not infer their amounts from published calories.
- **Andrew and Surabhi:** review mappings and additional ingredient tags; a
  high fuzzy-match score is not approval. The seeded Falafel also maps plain
  low-fat yogurt to whole-milk yogurt, a preparation/food-identity review item.
- **Surabhi and Guy-Georges:** confirm rule conditions and automation limits.
  Existing evaluator behavior is preserved. For example, the current Falafel
  result treats tomatoes as cooked because a step mentions a cooked patty and
  chopped tomatoes together; that is not proof the tomatoes were cooked. The
  earlier local evaluator experiments are not silently substituted here.
- **Profile integration:** the new profile tables store allergies/preferences;
  this data-readiness layer does not implement personalized filtering or make
  an allergy-safety guarantee.

Start with the migration and [setup guide](README.md). Review and integrate the
data layer first; then coordinate API behavior and source-backed corrections.
