// Formatting shared by the admin screens. Separate from bits.jsx so that file
// exports components only.
import { C } from "../../shared/theme/colors";

export const AUTOMATION_TONE = {
  recipe_safe: C.accent,
  conditional: C.gold,
  instruction_only: C.sky,
  do_not_automate: C.coral,
};

export const AUTOMATION_STATUSES = [
  "recipe_safe",
  "conditional",
  "instruction_only",
  "do_not_automate",
];

export const RULE_CATEGORIES = ["bioavailability", "food_synergy", "inhibitor", "glycemic"];

export const EVIDENCE_TIERS = ["A", "B", "C"];

// The business_rules columns a request may set, in the order a reviewer reads
// them. Mirrors EDITABLE in api/app/rule_admin.py; the server rejects anything
// not on its own list, so a drift here is a refused request, not a bad write.
export const FIELDS = [
  { key: "rule_name", label: "Name" },
  { key: "rule_category", label: "Category", options: RULE_CATEGORIES },
  { key: "rule_type", label: "Type" },
  { key: "trigger_food_or_pattern", label: "Trigger, in words" },
  { key: "trigger_code", label: "Trigger code", hint: "An ingredient must carry this code for the rule to fire." },
  { key: "target_nutrient_or_outcome", label: "Target, in words" },
  { key: "target_code", label: "Target code" },
  { key: "action", label: "Action", multiline: true },
  { key: "action_code", label: "Action code" },
  { key: "mechanism", label: "Mechanism", multiline: true },
  { key: "recipe_engine_instruction", label: "Engine instruction", multiline: true },
  { key: "conditions_and_limits", label: "Conditions and limits", multiline: true },
  { key: "population_scope", label: "Population scope" },
  { key: "evidence_tier", label: "Evidence tier", options: EVIDENCE_TIERS },
  { key: "evidence_summary", label: "Evidence summary", multiline: true },
  { key: "automation_status", label: "Automation status", options: AUTOMATION_STATUSES },
  { key: "source_title", label: "Source title" },
  { key: "source_type", label: "Source type" },
  { key: "source_url", label: "Source URL" },
  { key: "review_date", label: "Review date", hint: "YYYY-MM-DD" },
];

// Which of those columns are codes, and what each one is for. They get a
// picker rather than a text input, in both the new-rule form and the editor:
// business_rules has no foreign key on any of the three, so a code that does
// not exist is stored without complaint and the rule is simply dead.
export const CODE_FIELDS = {
  trigger_code: {
    label: "Trigger code — when the rule applies",
    hint: "A recipe matches when one of its ingredients carries this code. This is the one that "
          + "decides whether the rule ever fires.",
  },
  target_code: {
    label: "Target code — what it is about",
    hint: "The nutrient or outcome the rule aims at. Recorded, not used for matching.",
  },
  action_code: {
    label: "Action code — what to do",
    hint: "The kind of change the rule asks for.",
  },
};

export function when(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}

// A rule only fires through an ingredient tagged with its trigger code, so
// "how many ingredients carry it" is the difference between a rule that works
// and one waiting on the tagging work.
export function reachOf(rule) {
  if (!rule.trigger_code) return { label: "no trigger code", tone: C.coral };
  if (!rule.tagged_ingredients) return { label: "no tagged ingredient", tone: C.coral };
  return {
    label: `${rule.tagged_ingredients} ingredient${rule.tagged_ingredients === 1 ? "" : "s"}`,
    tone: C.accent,
  };
}
