# MaziMeal \| Recipe Optimizer Test Plan

*Execution-ready draft • 22 October 2026 • Prepared by Huining Diao*

Status: PROPOSED / NOT EXECUTED. The team must confirm the optimizer entry point, rule-import version, and reviewer workflow before running integration tests.

## 1 \| Purpose and scope

Verify that the optimizer detects applicable nutrition rules, respects automation limits and priorities, produces safe/explainable recipe variants, and routes outputs for human review. This plan covers rule logic, recipe integrity, Excel updates, and reviewer visibility. It does NOT claim that the current repository already implements these functions.

Out of scope for this first round: clinical outcome validation, real nutrient-absorption measurements, production load testing, and live AI chat inference. AI-generated comment checks are a separate but linked test track owned with Kevin.

## 2 \| Source of truth and data readiness

| Source | Confirmed content | How to use |
| --- | --- | --- |
| Dr. Gleason Excel: IN WORK - MaziMeal Recipe Optimization Rules (3).xlsx | 54 rules: BIO 15, SYN 12, INH 12, GLY 15; each has rule_id, triggers, instructions, conditions, automation_status. | Expected rule behavior; capture file date/version before testing. |
| platform-dev.zip → schema/seed/recipes.csv + recipe_ingredients.csv | Named seed recipes and ingredients; e.g., Chicken Stir-Fry, Veggie Quinoa Bowl, Pasta Primavera. | Baseline test fixtures. Match by recipe_name; obtain DB recipe_id after import. |
| platform-dev.zip → schema/seed/foodcom_400.sql | Larger Food.com recipe seed. | Regression sampling after basic cases pass; do not assume same IDs as small CSV. |
| platform-dev.zip → recommender/README.md; schema/04_nutrient_rules.sql | Baseline recommendation logic and nutrient_rules schema. | Not proof that the new optimizer or 54-rule import is implemented. |
| MaziMeal Overview + Food Synergy / Cook Mode mockups | Recipe identity, constraints, reviewer workflow and future UI examples. | Product acceptance guidance; mockups are not working test results. |

Important data gap: seed CSV does not include a stable recipe_id column; database-generated IDs must be exported at runtime. Current schema/04_nutrient_rules.sql uses a different rule_type vocabulary from the Excel; Andrew/Surabhi must confirm mapping/import before rule-level integration tests.

## 3 \| Test environment and setup

1. Use a separate test database/project, not the live application. Record branch, commit hash, schema migration version, rules Excel version, and test date.
2. Import seed recipes and ingredients; export recipe_name → actual database recipe_id. Confirm nutrition rules were imported and the 54 Excel rule IDs resolve in the engine.
3. Ask Surabhi for the callable optimizer entry point (UI/API/CLI), request/response example, and how to supply user profile/context. Do not assume a function name.
4. Ask Guy-Georges for before/after rule-merging output and loop/iteration logging. Ask Kevin for reviewer-role test account and the review-page URL when ready.
5. Create two test profiles: P0 = no special constraints; P1 = medication/medical context unknown (must not auto-apply conditional or do_not_automate guidance). These are test profiles, not actual users.
6. Capture baseline recipe ingredients, steps, and tags before each run. Reset test data between cases; save raw engine output and screenshots.
## 4 \| Run procedure (repeat for each case)

1. Find the recipe by exact recipe_name and record its real database recipe_id; for constructed edge cases, label fixture SYNTHETIC and save its exact input JSON/recipe.
2. Run the optimizer with the specified test profile, rule set/version, and a deterministic configuration if supported. Save input and full output.
3. Compare detected rule IDs, automation statuses, proposed ingredient/step changes, variants, explanations, and review flags with expected behavior below.
4. Mark PASS only if every stated check holds; otherwise FAIL, BLOCKED (feature/data missing), or NEEDS EXPERT REVIEW (nutrition judgment). Attach evidence and an issue owner.
5. For any fix, rerun the same fixture and at least one related regression case. Never convert a proposed test into a passed test without evidence.
## 5 \| Test cases — real seed recipes

| ID/recipe | Rule(s) | Input fact | Expected checks |
| --- | --- | --- | --- |
| TC01<br>Pasta Primavera | GLY-007 | Baseline pasta recipe says “Cook pasta until al dente.” | Recognize al-dente preparation; do not add redundant duplicate instruction. No unsupported glycemic percentage claim. |
| TC02<br>Veggie Quinoa Bowl | SYN-001, SYN-008 | Contains chickpeas/spinach and lemon tahini drizzle. | Check plant-iron + vitamin-C-containing ingredient conditions; do not treat any generic acid/vinegar as equivalent. Flag uncertainty if quantities/nutrient mapping unavailable. |
| TC03<br>Chicken Stir-Fry | BIO-002 | Ingredient “Garlic ginger sauce” and step “ginger-garlic sauce.” | Do not assume fresh crushed garlic; ask for missing preparation details or flag as uncertain rather than blindly inserting rest time. |
| TC04<br>Pasta Primavera | BIO-003 | Contains cherry tomatoes; steps sauté vegetables. | Suggest tomato + culinary oil only if oil/processing conditions warrant it; avoid asserting oil absent if recipe detail is incomplete. |
| TC05<br>Chicken Stir-Fry | BIO-007, INH-007 | Contains broccoli; cooked with chicken/vegetables. | Check crucifer prep/heating logic; suggest suitable prep variants without claiming exact temperature or time not in source. |
| TC06<br>Veggie Quinoa Bowl | BIO-008, INH-002 | Contains chickpeas; seed does not specify dry vs canned. | Do not require soaking canned/precooked legumes; request preparation context or mark rule as uncertain. |
| TC07<br>Pasta Primavera | INH-003 | Contains Parmesan but no calcium supplement or iron supplement context. | Must NOT infer large calcium supplement from Parmesan or automatically remove cheese under INH-003. |
| TC08<br>Chicken Stir-Fry | GLY-001, GLY-003 | Contains brown rice and chicken. | Do not automatically replace an already less-refined grain or add redundant protein; show only applicable, justified changes. |

## 6 \| Test cases — controlled edge fixtures

The following fixtures are deliberately constructed for testing; they are NOT claimed to exist in the repository. Record their exact ingredients, quantities, steps, and profile when created.

| ID | Fixture/rule | Expected checks |
| --- | --- | --- |
| TC09 | Turmeric dish without pepper<br>SYN-003 \| P1: medication status unknown. | Offer only a conditional, reviewer-visible option; no universal automatic black-pepper addition. |
| TC10 | Carbohydrate dish + overlapping fat rules<br>GLY-004, SYN-002 \| Carotenoid vegetable + starch; no fat; P0. | Respect low-glycemic priority and profile constraints; avoid adding fat twice; preserve both rule rationales. |
| TC11 | Iron-focused plant meal + tea<br>INH-001, SYN-001 \| Plant-iron food, vitamin-C source and tea. | Suggest beverage timing as instruction; do not block the recipe. Keep synergy and inhibitor outcomes separately traceable. |
| TC12 | Iron supplement + calcium supplement<br>INH-003 \| P1, supplements listed; clinician context unavailable. | do_not_automate: no medication/supplement timing change applied; route for expert/clinical review. |
| TC13 | Two rules that trigger each other<br>INH-012 + overlapping applicable rules \| Fixture agreed with Guy-Georges; repeat optimizer run. | Terminates within team-defined cap; no repeated identical change; log all rule triggers and final explanation. |
| TC14 | Recipe with allergy + proposed addition<br>SYN-001 or GLY-003 \| P0 with declared allergy to a proposed ingredient. | Never add an allergen; safe alternative or needs review. Confirm actual hard-constraint behavior with team. |
| TC15 | Recipe identity / authenticity<br>GLY-001 \| Culturally specific dish; proposed staple substitution. | Provide an optional variant, preserve essential cooking/identity constraints or route to reviewer. |
| TC16 | Changed Excel rule<br>Any safe test rule \| In test copy, update rule wording/trigger and re-import. | Change appears in engine after documented workflow; unchanged rule IDs stable; prior output/version traceable. |
| TC17 | Expert review of recipe variants<br>Review workflow \| Generated variants: applicable / not applicable / needs context. | Reviewer can inspect outcomes; edit/approve/reject as supported; only approved content is user-visible. |
| TC18 | AI comment review and publication<br>Kevin AI text workflow \| Use Kevin’s planned 30–50 offline-generated comment samples. | No unsupported figures; rejected/unapproved text not public; reviewer status recorded. Test set and threshold to confirm with Kevin. |

## 7 \| Pass / fail rules and metrics

1. Critical safety gate (required 100% on tested cases): no known allergen added; no do_not_automate action silently applied; unapproved content never published; no infinite loop.
2. Rule correctness: per case, expected applicable rules fire and inapplicable rules do not; rule IDs and reasons are visible. Record counts of correct/incorrect/missing triggers.
3. Automation-status compliance: recipe_safe after conflict checks; conditional only with required context; instruction_only as guidance; do_not_automate as flag/review, never direct change.
4. Priority and conflict handling: Low Glycemic > Bioavailability/Food Synergy > Inhibitors (meeting agreement), without overriding allergies, food safety, or clinical constraints.
5. Explainability: every suggested change identifies source rule ID, original vs proposed change, and reason; duplicate recommendations consolidated without losing rule traceability.
6. Completeness: every planned test has a recorded status and evidence link. Proposed initial acceptance threshold: 0 critical failures; other thresholds to be agreed by team and Dr. Gleason.
## 8 \| Test log — copy one row per run

| Test ID | Recipe ID / fixture | Rule IDs | Profile | Expected / actual | Status / evidence / owner |
| --- | --- | --- | --- | --- | --- |
| TC__ | [actual DB ID] | [IDs] | P0 / P1 | [expected] / [actual] | NOT RUN \| [link] \| [name] |
| TC__ | [actual DB ID] | [IDs] | P0 / P1 | [expected] / [actual] | NOT RUN \| [link] \| [name] |

Suggested status definitions: PASS = all checks met; FAIL = observed mismatch; BLOCKED = feature/test data unavailable; NEEDS EXPERT REVIEW = judgment unresolved; NOT RUN = not executed. Record date, commit hash, Excel version, and reviewer decision in the detailed log.

## 9 \| Owners, dependencies, and next actions

| Owner | What to provide / do |
| --- | --- |
| Huining (PM) | Maintain plan and test log; schedule a brief walkthrough; assign evidence owners and track blockers; summarize results for next sync. |
| Andrew | Recipe ID mapping, test database/seed confirmation, Excel→DB import workflow and rule data version. |
| Surabhi | Optimizer input/output contract, rule priority implementation, applicable/not-applicable/context results, trigger mapping. |
| Guy-Georges | Conflict/loop fixtures, merge-vs-unmerged comparison, trace logs and stopping behavior. |
| Kevin | Review UI test access and approval visibility; coordinate separate 30–50 AI-comment test samples with Dr. Gleason. |
| Dr. Gleason | Review conditional nutrition cases, rule interpretation, recipe integrity, and unresolved expert judgments. |

First execution milestone (proposed, no meeting deadline set): 1) confirm entry point and import; 2) run TC01–TC08 against seed recipes; 3) run TC09–TC16 with controlled fixtures; 4) run TC17–TC18 when review UI is ready; 5) expand to a sampled subset of Food.com 400 for regression.

## 10 \| Open decisions before sign-off

1. Which branch/commit and rule spreadsheet revision are the test baseline?
2. Where is the optimizer callable, and how are applicable/not-applicable/needs-context outcomes returned?
3. How are Excel rule IDs mapped to the current DB schema and versioned?
4. What exact recipe variants can the reviewer UI edit/approve/reject (separate from AI text)?
5. What timeout/iteration cap and non-critical pass-rate threshold should the team adopt?
6. Who signs off conditional nutrition rules and recipe-authenticity judgments?
Source note: real recipe names/ingredients are from platform-dev.zip seed CSVs; rule IDs/statuses/conditions from Dr. Gleason’s Excel; priorities and review approach from the Oct 22 Fathom notes; recipe-identity requirement from MaziMeal Overview. All controlled edge fixtures, test IDs, and acceptance proposals were designed for this plan, not copied from production data.
