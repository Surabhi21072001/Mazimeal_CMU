# MaziMeal V2 — API and data contract

Status: draft for the team, 2026-10-19. Owner: frontend/backend.

This is the contract the four workstreams build against. The frontend and the
backend are written against it today using fixtures; the other three
workstreams replace the fixtures with real data without the contract changing.

```
React (Vercel)
   │   one source only: /api/*
   ▼
FastAPI  ──→ repository interface
   │           ├── FixtureRepo   reads api/fixtures/*.json   (today)
   │           ├── PostgresRepo  the existing schema         (when data lands)
   │           └── Neo4jRepo     only if the team goes that way
   ├──→ recommender  (workstream 3, a Python function we wrap)
   └──→ LLM          (AI suggestions; key stays server side)
```

The storage decision is deliberately not baked in. Nothing above the repository
interface knows where the data comes from.

---

## 1. What each workstream owes this contract

| From | What | Shape | Needed by |
|---|---|---|---|
| Data (1) | gram weight per ingredient line, nutrition per serving with a source label, required/optional flag | fields in `recipe_detail` | before the nutrition panel is real |
| Data (1) | FDA/DRI targets per member | fields in `household` | same |
| Data (1) | fake user preferences | `household.members[].preferences` | now — the filter demo needs it |
| Rules (2) | recipe ↔ rule links **with the position they hit** | `recipe_detail.matched_rules` | before step highlighting is real |
| Recommender (3) | ranked recipes for one member, one meal | `recommend()` below | before the list page is real |

### Where the rules come from

Rules are fetched separately from the recipe, because they are detected rather
than stored on it:

```
GET /api/recipes/{id}          the recipe
GET /api/recipes/{id}/rules    the rules detected on it
```

The shape the rules workstream returns is in `docs/rules_api_contract.md`. This
backend calls both and composes the single payload below, so the screens never
see the split - and the split can change without touching them.

### The one thing that is easy to miss

`matched_rules` needs **where** the rule hit, not just that it hit:

```json
{ "rule_id": "BIO-002", "applies_to": { "type": "step", "step_number": 2 } }
{ "rule_id": "SYN-001", "applies_to": { "type": "ingredients", "line_ids": [5, 15] } }
```

Without `applies_to`, the cook screen cannot highlight the ingredient inside a
step, cannot put the "Key Step" badge on the right row, and cannot show the
synergy card against the pair that caused it. A rule list alone is not enough.

---

## 2. The recommender interface (workstream 3)

We agreed the recommender arrives as a Python function. The backend wraps it,
handles errors, and caches. It never touches HTTP.

```python
def recommend(
    member_id: str,
    date: datetime.date,
    target_nutrient: str | None,   # one nutrient, chosen by the user
    meal: str | None,              # Breakfast | Lunch | Dinner | Snack
    preferences: dict,             # allergies, dislikes, dietary patterns, cuisines
    limit: int = 5,
) -> list[dict]                    # each item matches Recommendation below
```

One meal per call, as agreed. A whole-day plan is out of scope for now.

**Recommendation**

```json
{
  "recipe_id": "falafel-001",
  "name": "Falafel with Herbed Cucumber Yogurt",
  "meal": "Lunch",
  "kcal_per_serving": 464.2,
  "time_min": 45,
  "tags": ["vegetarian", "high_fiber"],
  "score": 87.4,
  "nutrient_contribution": {
    "nutrient": "Iron",
    "per_serving": 6.0,
    "unit": "mg",
    "pct_of_remaining_need": 25,
    "source": "derived",
    "confidence": 0.6
  },
  "matched_rule_ids": ["SYN-001", "BIO-002", "INH-001", "INH-002", "INH-003"],
  "why": "Pairs plant iron with vitamin C already, and one preparation change would raise what she absorbs.",
  "blocked_by": null
}
```

`why` is one sentence for the card. The recommender may return it; if it does
not, the backend composes it from `nutrient_contribution` and the matched
rules.

`blocked_by` is non-null for recipes the filter removed, e.g.
`{"reason": "household allergen", "detail": "peanut butter"}`. The list page
shows a few of these on purpose: a recommender that visibly refuses food is
more convincing than one that only shows winners.

**Every nutrition number carries `source` and `confidence`.** `source` is
`"published"` (measured, from the dataset) or `"derived"` (computed from
ingredient weights). The UI renders them differently. This is the project's
answer to the client's hallucination worry, so it is part of the contract, not
a nicety.

---

## 3. Endpoints

All responses are JSON. No auth: the demo runs as one fixed household.

### `GET /api/household`

The demo household, its members, and where each member stands today.

```json
{
  "household_id": "demo-household",
  "name": "Demo Household",
  "date": "2026-10-19",
  "members": [
    {
      "member_id": "maya",
      "name": "Maya",
      "age": 31,
      "sex": "F",
      "conditions": ["iron_deficiency"],
      "preferences": {
        "allergies": ["peanut"],
        "dislikes": ["mushroom"],
        "dietary_patterns": ["vegetarian"],
        "cuisines": ["Mediterranean", "South Asian"]
      },
      "targets": [
        {
          "nutrient": "Iron", "unit": "mg",
          "target": 27.0, "baseline": 18.0,
          "consumed": 3.1, "remaining": 23.9,
          "upper_limit": 45.0,
          "adjusted_by": ["IRON_COND_ANY_C002_001"]
        }
      ]
    }
  ]
}
```

`baseline`, `adjusted_by` and `adjusted_reason` exist so the UI can say *why*
her target is not the standard one. That sentence is the clearest demonstration
of personalisation we have.

**`baseline` must be in the same unit as `target`, or be null.** Some DRI
baselines are per kilogram of body weight (protein is 0.8 g/kg/day), and
printing "116 g, not the standard 0.8 g" is nonsense. Send null in that case;
`adjusted_reason` still carries the explanation.

### The headline template

The cook screen's headline is one component filled from data, identical for
every member and nutrient:

```
25% of today's iron                                    ← pct of what is left
6.0 mg per serving · Maya still needs 23.9 mg          ← value and remaining
Mostly from chickpeas, scallions and chopped tomato    ← top_sources
Maya's target is 27 mg, not the standard 18 mg  [iron deficiency]
```

Which nutrient it talks about is chosen by the page, not hardcoded: a nutrient
whose target was adjusted for that person wins, otherwise the one they are
furthest behind on, and a recipe that covers less than 10% of the gap is never
headlined. A nutrient can be forced with `#/cook/<id>?n=Iron`, which is how the
recommendation page will link through once it exists.

Lines three and four disappear when their data is missing, so a recipe with no
ingredient breakdown still produces a correct headline. That makes
`top_sources` optional for the data workstream in the short term, and valuable
as soon as it lands.

### `GET /api/recommendations`

Query: `member_id`, `meal`, `target_nutrient` (optional), `limit` (default 5).
Returns the recommender output plus the filter's rejects.

```json
{
  "member_id": "maya",
  "meal": "Lunch",
  "target_nutrient": "Iron",
  "results": [ /* Recommendation */ ],
  "blocked": [ /* Recommendation with blocked_by set */ ],
  "generated_at": "2026-10-19T12:30:00Z",
  "source": "fixture"
}
```

`source` is `"fixture"`, `"recommender"`, or `"cache"`. The UI shows a small
badge when it is not live, the same way the current home page does.

### `GET /api/recipes/{recipe_id}`

Everything the cook screen needs, in one call. This is the biggest payload and
the one the screenshot depends on.

```json
{
  "recipe_id": "falafel-001",
  "name": "Falafel with Herbed Cucumber Yogurt",
  "meal": "Lunch",
  "servings": 4,
  "time_min": 45,
  "tags": ["vegetarian", "high_fiber"],
  "image_url": null,

  "ingredients": [
    {
      "line_id": 5,
      "name": "chickpeas",
      "quantity": 1.5,
      "unit": "cup",
      "grams": 246.0,
      "grams_source": "rule",
      "is_optional": false,
      "required_by_rule": null,
      "notes": "drained and rinsed"
    }
  ],

  "nutrition_per_serving": [
    { "nutrient": "Energy", "label": "Calories", "value": 464.2, "unit": "kcal",
      "source": "published", "confidence": 1.0, "pct_of_target": 23, "top_sources": [] },
    { "nutrient": "Iron", "label": "Iron", "value": 6.0, "unit": "mg",
      "source": "derived", "confidence": 0.6, "pct_of_target": 22,
      "top_sources": [
        { "line_id": 5, "name": "chickpeas", "value": 3.4, "unit": "mg", "pct_of_recipe": 57 },
        { "line_id": 2, "name": "scallions", "value": 0.9, "unit": "mg", "pct_of_recipe": 15 }
      ] }
  ],

  "steps": [
    {
      "step_number": 2,
      "title": "Blend the herbs and garlic",
      "instruction": "Add the scallions, garlic, cilantro and mint to the food processor.",
      "duration_min": 2,
      "is_key_step": true,
      "ingredient_line_ids": [1, 2, 3, 4],
      "technique": "blend"
    }
  ],

  "matched_rules": [
    {
      "rule_id": "BIO-002",
      "name": "Crush garlic and rest before heating",
      "status": "not_satisfied",
      "automation_status": "recipe_safe",
      "evidence_tier": "B",
      "applies_to": { "type": "step", "step_number": 2 },
      "engine_action": "Crush or mince the garlic, then rest it about 10 minutes before it meets heat.",
      "why": "Resting lets alliinase convert alliin to allicin; heating too early stops the reaction.",
      "source_url": "https://pubmed.ncbi.nlm.nih.gov/11160543/"
    }
  ],

  "source": "fixture"
}
```

Rule `status` is one of `satisfied`, `not_satisfied`, `advisory`, `needs_review`.
The UI maps them to colour: green for satisfied, amber for an engine change,
neutral for advisory, coral for needs_review. `automation_status` comes
straight from the client's rules workbook and decides whether the engine may
act alone.

### `POST /api/recipes/{recipe_id}/suggestions`

Body: `{ "member_id": "maya", "rule_ids": ["BIO-002", "INH-001"] }`

The AI panel. **The model writes sentences; it never produces numbers.** The
backend passes it the recipe, the matched rules and the member's gaps as facts;
every returned suggestion cites the rule it came from.

```json
{
  "suggestions": [
    {
      "rule_id": "BIO-002",
      "headline": "Let the garlic rest before it hits the oil",
      "body": "Crush the garlic first and leave it for ten minutes while you shape the patties.",
      "source_url": "https://pubmed.ncbi.nlm.nih.gov/11160543/",
      "evidence_tier": "B"
    }
  ],
  "source": "stub",
  "disclaimer": "Generated from matched rules. Nutrition figures come from the database, not the model."
}
```

`source` is `"stub"` today (canned text, no LLM call), later `"llm"` or
`"cache"`. If the model fails, the endpoint falls back to the rule's own
`engine_action` text, so the panel is never empty.

### `GET /api/health`

`{ "status": "ok", "repo": "fixture", "recommender": "stub" }`

---

## 4. Errors, loading, empty

The frontend needs these defined or it will invent them:

| Case | HTTP | Body | UI |
|---|---|---|---|
| Unknown recipe | 404 | `{"error": "recipe_not_found", "recipe_id": "..."}` | empty state with a way back |
| Recommender raised | 200 | results from cache or fixture, `source` says so | "sample data" badge |
| LLM unavailable | 200 | rule text, `source: "stub"` | panel renders normally |
| Backend down | — | — | the page keeps its last payload and shows a retry |

Nothing in the UI shows a spinner that can run forever; every fetch has a
fallback payload.

---

## 5. Fixtures

`api/fixtures/` holds one file per endpoint response. They are the contract in
executable form: the backend serves them as-is when `USE_FIXTURES=1`, and the
frontend cannot tell the difference between a fixture and real data.

| File | Serves |
|---|---|
| `household.json` | `GET /api/household` |
| `recommendations_maya_lunch.json` | `GET /api/recommendations` |
| `recipe_falafel-001.json` | `GET /api/recipes/falafel-001` |
| `recipe_*.json` | the other recipes in the list |
| `suggestions_falafel-001.json` | the AI panel |

The numbers in the fixtures are taken from the real database where we have
them: the Falafel recipe, its ingredients and steps, Maya's iron target of
27 mg against the 18 mg baseline, and the per-serving values. What is invented
is clearly invented: the gram weights, the step titles and durations, and
today's consumed totals.

When a workstream delivers, it replaces one file or one repository method. The
rest of the system does not move.

---

## 6. Open questions

1. Does the recommender return recipes the filter rejected, or only winners?
   The list page wants a few rejects to show the filter working.
2. Can the rules workstream give `applies_to` positions, or only rule ids?
   If only ids, step highlighting falls back to keyword matching and will be
   approximate.
3. Which household is canonical? The frontend has Maya at 34; the database has
   Maya at 31 with an iron-deficiency condition. The fixtures use the database
   version. The frontend's hardcoded profiles should be retired.
4. Where does the backend run for the demo? Local for now, which means the demo
   machine runs both halves.
