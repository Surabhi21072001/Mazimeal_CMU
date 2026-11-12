// What a reviewed version means to the screens.
//
// This file used to BE the store: every version lived in localStorage under
// "mazimeal:review". It no longer stores anything. A correction is a statement
// about the recipe, not about the browser it was typed in, so the versions now
// live in Postgres (recipe_content_versions) and travel through the API, where
// the reviewer is read from the verified token - see
// shared/services/api/contentReview.js.
//
// What is left here is the part that was never storage: the vocabulary of a
// review, and the single function that turns a stored version back into the
// recipe and payload a cook screen renders.
//
// One distinction the data keeps, and the reason it is worth repeating here:
// removing a rule means "this rule does not apply to this recipe". It never
// touches the rule itself, which belongs to the research database and applies
// to 400 other recipes.

export const OUTCOME = {
  CONFIRMED: "confirmed_unchanged",
  EDITED: "edited",
  REJECTED: "rejected",
  REVERTED: "reverted_to_original",
};

// Why a reviewer changed something. Picking from a list beats free text,
// because these are what we count later.
export const EDIT_TAGS = [
  { id: "wording", label: "Wording only" },
  { id: "unsupported_claim", label: "Added something the rule does not say" },
  { id: "wrong_fact", label: "Got a fact wrong" },
  { id: "rule_not_applicable", label: "Rule does not apply here" },
  { id: "wrong_status", label: "Status was wrong" },
  { id: "wrong_position", label: "Shown on the wrong step" },
];

// What the cook screen should show once a reviewer has been through it.
//
// The version is passed in rather than looked up: it arrives over the network
// now, so the caller owns the fetch and this stays a pure function. A null
// version means nobody has reviewed this recipe, and the backend's own output
// is what to show.
export function applyReview(recipe, payload, version) {
  if (!version) return { recipe, payload, pinnedRuleId: null };

  const removed = new Set(version.rules_removed || []);
  const statuses = version.status_overrides || {};
  const positions = version.position_overrides || {};

  const rules = (recipe?.matched_rules || [])
    .filter((rule) => !removed.has(rule.rule_id))
    .map((rule) => {
      const next = { ...rule };
      if (statuses[rule.rule_id]) next.status = statuses[rule.rule_id];
      if (positions[rule.rule_id]) next.applies_to = positions[rule.rule_id];
      return next;
    });

  return {
    recipe: { ...recipe, matched_rules: rules, not_optimizable: version.not_optimizable },
    payload: {
      ...payload,
      suggestions: version.suggestions,
      summary: version.summary ?? payload?.summary,
      source: "reviewed",
      reviewed_by: version.review?.reviewer,
    },
    pinnedRuleId: version.headline_rule_id || null,
  };
}
