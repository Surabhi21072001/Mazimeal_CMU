# Phase 2 — RecipeFacts

`RecipeFacts` is a normalized, read-only snapshot of a single recipe. It is the
stable boundary between **database data** and **business-rule evaluation**:
future evaluation code depends on this object's shape, not on the database
schema.

It is a runtime Python object only. No new tables, nothing persisted, no
nutrition data duplicated. It reads existing MaziMeal tables and never
fabricates missing values.

## Flow

```
recipes
  → recipe_ingredients
  → ingredients
  → ingredient_rule_tags
  → recipe_nutrition
  → recipe_steps
  → RecipeFacts
  → candidate rule detection (detect_rules_from_facts)
```

## Structure implemented

```python
@dataclass(frozen=True)
class RecipeIngredientFact:
    ingredient_id: str
    ingredient_name: str
    quantity: float | None
    unit: str | None
    rule_codes: tuple[str, ...]        # codes tagged on this ingredient

@dataclass(frozen=True)
class RecipeFacts:
    recipe_id: str
    recipe_name: str
    ingredients: tuple[RecipeIngredientFact, ...]
    ingredient_codes: frozenset[str]   # union of all codes in the recipe
    nutrients: dict[str, float]        # NATIVE recipe_nutrition ids -> per_serving
    instructions: str | None           # joined recipe_steps, or None
    metadata: dict                     # meal_category, servings, units, scheme, ...
```

Both classes have `as_dict()` for serialization. `ingredient_codes` serializes
to a sorted list so the output is deterministic and JSON-friendly.

`build_recipe_facts(conn, recipe_id)` assembles one object. It raises
`RecipeNotFound` for an unknown id. It takes any DB-API connection
(psycopg2/psycopg3/sqlite3), same as `detect_rules.py`.

## Existing tables queried

| Table | Columns used | Into |
|---|---|---|
| `recipes` | `recipe_name`, `meal_category`, `servings`, `calories_per_serving`, `data_source`, `recipe_description` | `recipe_name`, `metadata` |
| `recipe_ingredients` | `ingredient_id`, `quantity`, `unit` | per-ingredient facts |
| `ingredients` | `ingredient_name` | per-ingredient facts |
| `ingredient_rule_tags` | `rule_code` | `rule_codes` per ingredient, `ingredient_codes` |
| `recipe_nutrition` | `nutrient_id`, `per_serving`, `unit` | `nutrients`, `metadata.nutrient_units` |
| `recipe_steps` | `step_number`, `instruction` | `instructions` |

Loaders degrade gracefully: if `recipe_nutrition` or `recipe_steps` is absent,
the corresponding field is empty/None rather than an error (checked via
`to_regclass` on Postgres, `sqlite_master` on SQLite). The ingredient loader
also falls back to a no-quantity query for minimal schemas (the test fixture).

## What can be populated now

- recipe id + name + metadata (meal category, servings, calories, source, description)
- every ingredient with quantity, unit, and its rule codes
- the union of all rule codes in the recipe
- per-serving nutrition using the **native** `recipe_nutrition` ids
- instructions, joined and numbered from `recipe_steps`

## What cannot be populated (and why)

- **Semantic `NUT_*`-keyed nutrients.** `recipe_nutrition` stores native ids
  (`Energy`, `Macro_Protein`, `Macro_Carbohydrate`, `Fiber`, `Sugar`, `Sodium`,
  `Cholesterol`, `Saturated_Fat`). There is **no mapping** in the repository
  between those ids and the `NUT_*` rule codes (`NUT_IRON`, `NUT_VITC`, …), so
  none is invented. `RecipeFacts.nutrients` preserves the native ids, and
  `metadata["nutrient_id_scheme"] = "native_recipe_nutrition"` flags this. A
  **nutrient-code mapping layer is a future step**.
- **Micronutrients** (iron, vitamin C, etc.) are not in `recipe_nutrition` at
  all; they live in `ingredient_nutrition` per 100 g and would need
  quantity-weighted aggregation — out of scope here.
- **Process conditions** (e.g. "garlic rested before heating"). `instructions`
  carries the raw text only. Parsing it into structured conditions is a later
  step and is explicitly **not** done here (no LLM, no regex extraction).

## Relationship to detect_rules

`detect_rules.py` was refactored to consume `RecipeFacts` while keeping its
public API:

- `detect_rules_from_facts(conn, facts)` — preferred entry point.
- `detect_rules(conn, recipe_id)` — unchanged signature; builds facts
  internally then delegates. Output is identical to before (verified).
- `recipe_trigger_codes(conn, recipe_id)` — preserved for back-compat, now
  derived from facts.

Rule semantics are unchanged: a rule is a **candidate** when its `trigger_code`
is among the recipe's `ingredient_codes`, and only `is_active` rules are
returned. No applicability/condition evaluation is performed.

## CLI

```bash
# inspect the facts object
python3 scripts/recipe_facts.py --dsn "dbname=mazimeal_dev" <recipe_id>
python3 scripts/recipe_facts.py --dsn "dbname=mazimeal_dev" --json <recipe_id>

# facts + detected candidate rules together
python3 scripts/detect_rules.py --dsn "dbname=mazimeal_dev" --show-facts <recipe_id>
```

## The next step (not implemented yet)

```
RecipeFacts + CandidateRule  →  condition / applicability evaluation
```

That future layer will read a rule's `conditions_and_limits` / `population_scope`
and the facts (ingredients, quantities, nutrients, instructions) to decide
whether a candidate rule actually applies, and how. It will also likely
introduce the nutrient-code mapping noted above. None of that is built here —
this phase stops at producing a clean, stable `RecipeFacts`.


---

# Phase 2 — Condition Evaluation & Process Checks

The layer after candidate detection. It moves a candidate rule (its trigger
code is present) to a decision, using only deterministic checks over the
recipe's ingredients and instruction text. No LLM, no embeddings, no nutrient
thresholds, no user/clinical context, no conflict resolution.

## Full flow

```
Recipe
  → RecipeFacts
  → Candidate Rules            (detect_rules_from_facts: trigger code present)
  → Process Fact Extraction    (extract_process_facts: phrases over instructions)
  → Condition Evaluation       (evaluate_rule: per-rule deterministic logic)
  → APPLICABLE / NOT_APPLICABLE / NEEDS_CONTEXT
```

## Status definitions

| Status | Meaning |
|---|---|
| **CANDIDATE** | the rule's `trigger_code` is present in the recipe (unchanged detection) |
| **APPLICABLE** | trigger present AND the required conditions are satisfied — the rule would add value |
| **NOT_APPLICABLE** | trigger present BUT the recipe already satisfies the rule, or a required condition fails |
| **NEEDS_CONTEXT** | trigger present BUT the engine lacks enough information (no instructions, or no evaluator implemented yet) |

`applicability_status` is separate from `automation_status`. The latter
(`recipe_safe`, `conditional`, …) comes from the workbook and is carried
through unchanged; it is not overloaded with applicability state.

## Applicability result structure

```python
class ApplicabilityStatus(str, Enum):
    APPLICABLE; NOT_APPLICABLE; NEEDS_CONTEXT

@dataclass(frozen=True)
class ProcessFact:
    value: bool
    evidence: str | None      # the instruction line that produced the fact

@dataclass(frozen=True)
class EvaluatedRule:
    rule_id; rule_name; trigger_code; automation_status
    candidate: bool
    applicability_status: ApplicabilityStatus
    conditions_checked / conditions_passed / conditions_failed: tuple[str, ...]
    reason: str
```

Both `ProcessFact` and `EvaluatedRule` have `as_dict()`.

## Process facts implemented

Derived by `extract_process_facts(facts)` via deterministic phrase matching.
Each keeps the matched instruction line as `evidence`. Matching uses same-line
co-occurrence (noun + verb) where it reduces false positives — e.g. "chopped
parsley" must not count as chopping the broccoli.

- `instructions_available`
- `garlic_present`, `garlic_chopped`, `garlic_heated`, `garlic_rest_period_detected`
- `tomato_present`, `tomato_cooked`, `fat_present`
- `pasta_present`, `pasta_cooked`, `pasta_al_dente_instruction`
- `crucifer_present`, `crucifer_chopped`, `crucifer_cooked`
- `egg_present`, `egg_cooked`
- `cooling_detected`, `reheating_detected`

Phrase tables (chop verbs, heat verbs, rest phrases, al dente, fats, cool/reheat)
are small and auditable, kept at the top of `scripts/evaluate_rules.py`.

## Rules with implemented evaluators (5)

Chosen because their condition is deterministically checkable from ingredients +
instructions, using the actual workbook `recipe_engine_instruction` wording:

| Rule | Trigger | Logic |
|---|---|---|
| **BIO-002** Crush garlic and rest before heating | `ING_GARLIC` | APPLICABLE if chopped+heated with no rest; NOT_APPLICABLE if a rest step exists; NEEDS_CONTEXT if no instructions / signals unclear |
| **BIO-003** Cook tomatoes with oil | `ING_TOMATO` | APPLICABLE if cooked without fat; NOT_APPLICABLE if cooked with fat already present |
| **BIO-007** Chop crucifers before cooking | `ING_CRUCIFER` | NOT_APPLICABLE if a crucifer chop step exists; APPLICABLE if cooked without one |
| **BIO-011** Cook eggs rather than raw | `ING_EGG` | NOT_APPLICABLE if egg is cooked; APPLICABLE if no cooking detected |
| **GLY-007** Use al dente pasta | `ING_PASTA` | NOT_APPLICABLE if "al dente" present; APPLICABLE otherwise |

Every evaluator returns NEEDS_CONTEXT when the trigger ingredient is present but
no instructions exist to inspect.

## Rules still returning NEEDS_CONTEXT

Every other candidate rule. The dispatcher (`RULE_EVALUATORS` registry) returns
NEEDS_CONTEXT with reason **"condition evaluator not implemented"** for any rule
without a registered evaluator — never silently APPLICABLE. This currently
includes BIO-001, BIO-004, BIO-005, BIO-006, BIO-013, INH-007, SYN-003, SYN-011
and all non-process rules, which need pairing judgment, ingredient-form
decisions, or nutrient/clinical context not in scope for this phase.

## API & CLI

```python
from evaluate_rules import evaluate_recipe_rules
evaluated = evaluate_recipe_rules(conn, recipe_id)   # list[EvaluatedRule]
```

```bash
python3 scripts/evaluate_rules.py --dsn "dbname=mazimeal_dev" <recipe_id>
python3 scripts/evaluate_rules.py --dsn "dbname=mazimeal_dev" --json <recipe_id>
```

Candidate detection, RecipeFacts, and `detect_rules` are unchanged; a test
asserts the evaluated candidate set equals `detect_rules_from_facts` output.

## The next step (not implemented yet)

Nutrient-threshold evaluation, user/household context, conflict resolution and
prioritization build on `EvaluatedRule`. None of that is done here — this phase
stops at a deterministic, evidence-backed applicability decision per candidate.
