import { C } from "../../shared/theme/colors";

// A matched rule's status decides its colour everywhere it appears, so the
// same rule reads the same way on a step, in a card and in the AI panel.
export const RULE_STATUS = {
  satisfied: { label: "Already true here", color: C.accent, bg: C.accentLight },
  not_satisfied: { label: "Suggested change", color: C.gold, bg: C.goldLight },
  advisory: { label: "Serving note", color: C.sky, bg: C.skyLight },
  needs_review: { label: "Flagged for review", color: C.coral, bg: C.coralLight },
};

export function statusOf(rule) {
  return RULE_STATUS[rule?.status] || RULE_STATUS.advisory;
}

// The tiers are the client's, defined on the Read Me sheet of their rules
// workbook. A tier says how well established the finding is, not how large the
// effect is - worth spelling out, because people read "A" as "works better".
export const EVIDENCE = {
  A: "Tier A: authoritative guidance, a systematic review, or replicated human evidence.",
  B: "Tier B: limited human evidence, or strong food-processing evidence.",
  C: "Tier C: preliminary or mechanistic evidence only.",
};

export function evidenceTitle(tier) {
  return `${EVIDENCE[tier] || "Evidence tier from the rules database."} A tier is not a measure of effect size.`;
}

// Which rule belongs in the card at the top of the screen.
//
// The one that moves the nutrient this person is here for wins; after that, a
// rule the cook can act on beats one that is already true. Rules waiting for a
// reviewer never appear on the cook screen.
// Our nutrient ids and the workbook's target codes spell the same nutrient
// differently (Vitamin_C here, NUT_VITC there), so match on both spellings.
const NUTRIENT_ALIASES = {
  Iron: ["IRON"],
  Calcium: ["CALCIUM"],
  Zinc: ["ZINC"],
  Vitamin_C: ["VITC", "VITAMIN C", "ASCORBIC"],
  Vitamin_D: ["VITD", "VITAMIN D"],
  Vitamin_K: ["VITK", "VITAMIN K"],
  Vitamin_A: ["VITA", "VITAMIN A", "CAROTEN"],
  Folate: ["FOLATE"],
  Macro_Protein: ["PROTEIN", "AMINO"],
  Fiber: ["FIBER", "FIBRE"],
};

export function pickHeadlineRule(rules = [], focusNutrient) {
  const keys = NUTRIENT_ALIASES[focusNutrient] || [
    String(focusNutrient || "").toUpperCase().replace("MACRO_", ""),
  ];

  const score = (rule) => {
    let points = 0;
    const target = `${rule.target_code || ""} ${rule.target_nutrient || ""}`.toUpperCase();
    if (keys.some((key) => key && target.includes(key))) points += 10;
    if (rule.status === "not_satisfied") points += 3;
    else if (rule.status === "satisfied") points += 2;
    else if (rule.status === "advisory") points += 1;
    if (rule.evidence_tier === "A") points += 1;
    return points;
  };

  const usable = rules.filter((rule) => rule.status !== "needs_review");
  if (!usable.length) return null;
  return usable.reduce((best, rule) => (score(rule) > score(best) ? rule : best));
}

// The eyebrow on that card, so it does not say "food synergy" above a rule
// about soaking chickpeas.
export function headlineKicker(rule) {
  if (!rule) return "";
  if (rule.rule_id?.startsWith("SYN")) return "FOOD SYNERGY";
  if (rule.status === "not_satisfied") return "ONE CHANGE WORTH MAKING";
  if (rule.status === "advisory") return "WORTH KNOWING";
  return "WHY THIS RECIPE WORKS";
}
