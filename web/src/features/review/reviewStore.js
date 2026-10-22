// Reviewed content, kept as versions.
//
// The screen always shows the newest version; the older ones stay so a person
// can see what was changed and so we can count how often the model was right
// without help. Storage is localStorage for now - the shape is what moves to
// Supabase later, not the mechanism.
//
// One distinction the data has to keep: removing a rule here means "this rule
// does not apply to this recipe". It never touches the rule itself, which
// belongs to the research database and applies to 400 other recipes.
const KEY = "mazimeal:review";

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

function readAll() {
  try {
    const raw = window.localStorage.getItem(KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function writeAll(all) {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(all));
  } catch {
    // a private window refuses storage; the screen still works for this visit
  }
}

// What produced this text, so a later change of rules or model can be spotted.
export function fingerprint(recipe, payload) {
  const ruleIds = (recipe?.matched_rules || []).map((r) => r.rule_id).sort().join(",");
  return `${recipe?.recipe_id}|${ruleIds}|${payload?.model || payload?.source || "unknown"}`;
}

export function getRecord(recipeId) {
  return readAll()[recipeId] || null;
}

// The version the screens should read. Falls back to what the backend sent
// when nobody has reviewed this recipe yet.
export function currentVersion(recipeId) {
  const record = getRecord(recipeId);
  if (!record) return null;
  return record.versions.find((v) => v.version === record.current_version) || null;
}

export function seed(recipe, payload) {
  const existing = getRecord(recipe.recipe_id);
  if (existing) return existing;

  const record = {
    recipe_id: recipe.recipe_id,
    recipe_name: recipe.name,
    current_version: 1,
    versions: [
      {
        version: 1,
        author: payload?.model ? `model:${payload.model.split("/").pop()}` : "model:template",
        parent: null,
        created_at: new Date().toISOString(),
        inputs_fingerprint: fingerprint(recipe, payload),
        suggestions: (payload?.suggestions || []).map((s) => ({ ...s })),
        summary: payload?.summary ? { ...payload.summary } : null,
        rules_removed: [],
        status_overrides: {},
        position_overrides: {},
        headline_rule_id: null,
        not_optimizable: false,
        review: null,
      },
    ],
  };
  const all = readAll();
  all[recipe.recipe_id] = record;
  writeAll(all);
  return record;
}

// A review always writes a new version, even when nothing changed. That is
// what makes "the model needed no help" a countable fact rather than an
// absence of one.
export function addVersion(recipeId, { suggestions, summary, rulesRemoved, statusOverrides, positionOverrides, headlineRuleId, notOptimizable, outcome, tags, note, session, fingerprintValue }) {
  const all = readAll();
  const record = all[recipeId];
  if (!record) return null;

  const previous = record.versions.find((v) => v.version === record.current_version);
  const next = {
    version: record.current_version + 1,
    author: `human:${session?.name || session?.user_id || "reviewer"}`,
    parent: record.current_version,
    created_at: new Date().toISOString(),
    inputs_fingerprint: fingerprintValue || previous?.inputs_fingerprint || null,
    suggestions: suggestions ?? previous?.suggestions ?? [],
    summary: summary ?? previous?.summary ?? null,
    rules_removed: rulesRemoved ?? previous?.rules_removed ?? [],
    status_overrides: statusOverrides ?? previous?.status_overrides ?? {},
    position_overrides: positionOverrides ?? previous?.position_overrides ?? {},
    headline_rule_id: headlineRuleId ?? previous?.headline_rule_id ?? null,
    not_optimizable: notOptimizable ?? previous?.not_optimizable ?? false,
    review: {
      outcome,
      tags: tags || [],
      note: note || "",
      reviewer: session?.name || session?.user_id || "reviewer",
      reviewed_at: new Date().toISOString(),
    },
  };

  record.versions.push(next);
  record.current_version = next.version;
  writeAll(all);
  return record;
}

// What the review screen counts at the top: how often the model was left
// alone. This is the accuracy number, built out of ordinary review work.
// Undoing an edit is itself a decision, so it writes a version like any other
// rather than deleting what came before. The history is the point: it is how
// anyone later can see that an edit was tried and withdrawn.
export function revertToOriginal(recipeId, session) {
  const record = getRecord(recipeId);
  if (!record || record.versions.length < 2) return record;
  const first = record.versions[0];

  return addVersion(recipeId, {
    suggestions: first.suggestions.map((s) => ({ ...s })),
    summary: first.summary ? { ...first.summary } : null,
    rulesRemoved: [...(first.rules_removed || [])],
    statusOverrides: { ...(first.status_overrides || {}) },
    positionOverrides: { ...(first.position_overrides || {}) },
    notOptimizable: Boolean(first.not_optimizable),
    outcome: OUTCOME.REVERTED,
    tags: [],
    note: `Back to version 1, written by ${first.author}`,
    session,
    fingerprintValue: first.inputs_fingerprint,
  });
}

export function stats() {
  const all = readAll();
  let reviewed = 0;
  let confirmed = 0;
  let edited = 0;
  let rejected = 0;
  let reverted = 0;
  const tagCounts = {};

  Object.values(all).forEach((record) => {
    record.versions.forEach((version) => {
      if (!version.review) return;
      reviewed += 1;
      if (version.review.outcome === OUTCOME.CONFIRMED) confirmed += 1;
      if (version.review.outcome === OUTCOME.EDITED) edited += 1;
      if (version.review.outcome === OUTCOME.REJECTED) rejected += 1;
      if (version.review.outcome === OUTCOME.REVERTED) reverted += 1;
      (version.review.tags || []).forEach((tag) => {
        tagCounts[tag] = (tagCounts[tag] || 0) + 1;
      });
    });
  });

  // A revert says something about an earlier edit, not about the model's
  // output, so it is counted but kept out of the accuracy ratio.
  const judged = confirmed + edited + rejected;
  return {
    reviewed,
    confirmed,
    edited,
    rejected,
    reverted,
    tagCounts,
    unchangedRate: judged ? Math.round((100 * confirmed) / judged) : null,
  };
}

// What the cook screen should show once a reviewer has been through it.
// Without this the review screen writes versions nobody ever sees.
export function applyReview(recipe, payload) {
  const version = currentVersion(recipe?.recipe_id);
  if (!version) return { recipe, payload };

  const removed = new Set(version.rules_removed || []);
  const statuses = version.status_overrides || {};
  const positions = version.position_overrides || {};

  const rules = (recipe.matched_rules || [])
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

export function clearAll() {
  writeAll({});
}
