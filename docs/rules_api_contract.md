# Rules API — what the screens need from rule detection

For the rules-engine workstream. Most of this is a serialisation of what
`scripts/detect_rules.py` already produces; two fields are new.

The screens fetch a recipe, then fetch the rules detected on it. Keeping them
apart is deliberate: rules are detected, not a property of the recipe, and they
change when the rule set changes while the recipe does not.

```
GET /api/recipes/{recipe_id}          the recipe, its ingredients and steps
GET /api/recipes/{recipe_id}/rules    the rules detected on it   <- this document
```

---

## Response

```json
{
  "recipe_id": "<uuid>",
  "detected_at": "<ISO 8601 timestamp>",
  "rules": [
    {
      "rule_id": "BIO-002",
      "rule_name": "Crush garlic and rest before heating",
      "rule_category": "Bioavailability",
      "automation_status": "recipe_safe",
      "evidence_tier": "B",

      "trigger_code": "ING_GARLIC",
      "target_code": "CMP_ALLICIN",
      "target_nutrient_or_outcome": "allicin formation",

      "action": "<business_rules.action>",
      "recipe_engine_instruction": "<business_rules.recipe_engine_instruction>",
      "mechanism": "<business_rules.mechanism>",
      "conditions_and_limits": "<business_rules.conditions_and_limits>",
      "source_title": "<business_rules.source_title>",
      "source_url": "<business_rules.source_url>",

      "matched_on": {
        "ingredients": [
          {
            "line_id": "<recipe_ingredients.line_id>",
            "ingredient_id": "<ingredients.ingredient_id>",
            "name": "garlic"
          }
        ],
        "steps": [2]
      },
      "reason": "recipe contains ingredient tagged ING_GARLIC"
    }
  ]
}
```

## Fields

| Field | Where it comes from today | Status |
|---|---|---|
| `rule_id`, `rule_name`, `rule_category`, `automation_status`, `evidence_tier` | `business_rules` | exists |
| `trigger_code`, `target_code`, `target_nutrient_or_outcome` | `business_rules` | exists |
| `action`, `recipe_engine_instruction`, `mechanism`, `conditions_and_limits`, `source_title`, `source_url` | `business_rules` | exists |
| `reason` | `DetectedRule.reason` | exists |
| `matched_on.ingredients[]` | the `ingredient_rule_tags` join, as ids instead of prose | **new** |
| `matched_on.steps[]` | not detected today | **optional** |

Only two things are new; the rest is already stored.

### `matched_on.ingredients`

The structured form of what `reason` says in words. The cook screen highlights
the exact lines a rule fired on, so it needs:

- `line_id` — which line of *this* recipe (`recipe_ingredients.line_id`)
- `ingredient_id` — which ingredient (`ingredients.ingredient_id`)
- `name` — for debugging; the screen uses its own copy

A rule can match several lines. `SYN-001` fires on the chickpeas *and* on the
vitamin C sources beside them, and the screen highlights all of them.

### `matched_on.steps`

A list of `recipe_steps.step_number`. Detection does not read step text today,
so send `[]` or omit the key — the step a tip belongs to is worked out on our
side for now. Move it here later if it needs to be more accurate than name
matching can be.

---

## Worked example

Falafel with Herbed Cucumber Yogurt. Four rules, including one that matches no
ingredient at all.

```json
{
  "recipe_id": "01a0a120-4fd9-7b1e-9f3c-2c7e5a9d1b44",
  "detected_at": "2026-10-22T14:03:11Z",
  "rules": [
    {
      "rule_id": "SYN-001",
      "rule_name": "Vitamin C with nonheme iron",
      "rule_category": "Food Synergies",
      "automation_status": "recipe_safe",
      "evidence_tier": "A",
      "trigger_code": "NUT_NONHEME_IRON",
      "target_code": "NUT_IRON",
      "target_nutrient_or_outcome": "iron absorption",
      "action": "Add a vitamin C-rich food in the same meal",
      "recipe_engine_instruction": "Pair beans, lentils, tofu, fortified grains, or greens with a vitamin C source in the same meal.",
      "mechanism": "Ascorbic acid reduces ferric to ferrous iron and forms soluble complexes.",
      "conditions_and_limits": "Meal effect depends on dose and matrix; do not apply to heme iron.",
      "source_title": "Iron: Fact Sheet for Health Professionals",
      "source_url": "https://ods.od.nih.gov/factsheets/Iron-HealthProfessional/",
      "matched_on": {
        "ingredients": [
          { "line_id": "9f1c...", "ingredient_id": "4fe0...", "name": "chickpeas" },
          { "line_id": "a22b...", "ingredient_id": "4fe6...", "name": "chopped tomato" },
          { "line_id": "b71e...", "ingredient_id": "4fea...", "name": "fresh lemon juice" }
        ],
        "steps": []
      },
      "reason": "recipe contains ingredient tagged NUT_NONHEME_IRON"
    },
    {
      "rule_id": "BIO-002",
      "rule_name": "Crush garlic and rest before heating",
      "rule_category": "Bioavailability",
      "automation_status": "recipe_safe",
      "evidence_tier": "B",
      "trigger_code": "ING_GARLIC",
      "target_code": "CMP_ALLICIN",
      "target_nutrient_or_outcome": "allicin formation",
      "action": "Crush or mince; rest about 10 minutes before heating",
      "recipe_engine_instruction": "When garlic is cooked, place crushing/mincing before a short rest.",
      "mechanism": "Tissue disruption lets alliinase convert alliin to allicin.",
      "conditions_and_limits": "Allicin is unstable; do not promise a clinical dose.",
      "source_title": "Heating garlic inhibits its anticancer properties",
      "source_url": "https://pubmed.ncbi.nlm.nih.gov/11160543/",
      "matched_on": {
        "ingredients": [
          { "line_id": "3c04...", "ingredient_id": "4fdc...", "name": "garlic" }
        ],
        "steps": [2]
      },
      "reason": "recipe contains ingredient tagged ING_GARLIC"
    },
    {
      "rule_id": "INH-002",
      "rule_name": "High-phytate matrix with iron/zinc",
      "rule_category": "Inhibitors",
      "automation_status": "recipe_safe",
      "evidence_tier": "A",
      "trigger_code": "CMP_PHYTATE",
      "target_code": "NUT_IRON_ZINC",
      "target_nutrient_or_outcome": "iron and zinc absorption",
      "action": "Reduce phytate through soaking, fermentation, germination, or processing",
      "recipe_engine_instruction": "Apply processing mitigation rather than removing nutritious foods.",
      "mechanism": "Phytate chelates minerals and reduces intestinal availability.",
      "conditions_and_limits": "Phytate foods have important benefits; avoid globally labelling them.",
      "source_title": "Iron: Fact Sheet for Health Professionals",
      "source_url": "https://ods.od.nih.gov/factsheets/Iron-HealthProfessional/",
      "matched_on": {
        "ingredients": [
          { "line_id": "9f1c...", "ingredient_id": "4fe0...", "name": "chickpeas" }
        ],
        "steps": []
      },
      "reason": "recipe contains ingredient tagged CMP_PHYTATE"
    },
    {
      "rule_id": "INH-001",
      "rule_name": "Tea or coffee with nonheme iron meal",
      "rule_category": "Inhibitors",
      "automation_status": "instruction_only",
      "evidence_tier": "A",
      "trigger_code": "BEV_TEA_COFFEE",
      "target_code": "NUT_IRON",
      "target_nutrient_or_outcome": "nonheme iron absorption",
      "action": "Move tea/coffee away from iron-focused meals",
      "recipe_engine_instruction": "If iron optimization is active, avoid recommending tea/coffee with the meal.",
      "mechanism": "Polyphenols bind nonheme iron and reduce absorption.",
      "conditions_and_limits": "Effect depends on beverage strength, timing and iron status.",
      "source_title": "Inhibition of food iron absorption by coffee",
      "source_url": "https://pubmed.ncbi.nlm.nih.gov/6402915/",
      "matched_on": { "ingredients": [], "steps": [] },
      "reason": "iron-focused meal; rule applies to the meal rather than an ingredient"
    }
  ]
}
```

---

## Rules of the road

**A rule with no ingredient match is normal.** `INH-001` is about what is drunk
beside the meal, so `matched_on` is empty and `reason` explains why. Keep these
in the response; the screen shows them as serving advice rather than dropping
them.

**Detection is yours; the verdict is ours.** You report what fired. Whether the
recipe *already satisfies* a rule — the garlic is already rested, the vitamin C
is already there — is decided on our side from the steps and ingredients, and
decides whether the cook is told "do this" or "this already works". Please do
not send a satisfied/not-satisfied field; two systems deciding the same thing
will disagree eventually.

**Send `do_not_automate` rules too.** They never reach a cook, but the reviewer
screen needs them, and a rule that says "a person must decide" is exactly the
one worth showing a person.

**Empty result is `200` with `"rules": []`**, not a 404. An unknown recipe is
`404` with `{"error": "recipe_not_found"}`.

**Order does not matter.** The screen sorts by what it needs to show first.

**One call per recipe is fine.** If a list screen ever needs rules for several
recipes at once, a `POST` taking `recipe_ids[]` and returning the same objects
keyed by recipe id would save the round trips. Worth adding when something
actually needs it, not before.

---

## How this is consumed

Our backend calls both endpoints and composes one payload for the screens, so
the shape above can change without the front end noticing. What it becomes is
in `api/SPEC.md` under `GET /api/recipes/{recipe_id}`: `matched_rules` with an
`applies_to` that is either a step or a set of ingredient lines, plus a `status`
we derive.
