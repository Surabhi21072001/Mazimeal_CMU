// Which nutrient the headline talks about.
//
// The same rule runs for every member and every recipe:
//
//   1. a nutrient whose target was adjusted for this person (a condition, a
//      goal, their activity level) wins - that is the reason they are here;
//   2. otherwise the nutrient they are furthest behind on today;
//   3. ties break on how much of the gap this recipe actually covers.
//
// A recipe that barely touches a nutrient (under 10% of the gap) is never
// headlined for it, so the line always says something worth reading. Energy
// and limit-only nutrients are reported in the panel, never chased here.
const NEVER_FOCUS = new Set(["Energy", "Sodium", "Saturated_Fat", "Sugar", "Cholesterol"]);
const MIN_COVERAGE = 0.1;

export function pickFocusNutrient(recipe, member, preferred) {
  const rows = recipe?.nutrition_per_serving || [];
  const byNutrient = new Map((member?.targets || []).map((t) => [t.nutrient, t]));

  const candidates = rows
    .filter((row) => !NEVER_FOCUS.has(row.nutrient))
    .map((row) => {
      const target = byNutrient.get(row.nutrient);
      if (!target || !(target.remaining > 0)) return null;
      return {
        row,
        target,
        coverage: row.value / target.remaining,
        gapShare: target.target ? target.remaining / target.target : 0,
        adjusted: Boolean(target.adjusted_by?.length),
      };
    })
    .filter(Boolean);

  if (preferred) {
    const asked = candidates.find((c) => c.row.nutrient === preferred);
    if (asked) return asked;
  }

  const useful = candidates.filter((c) => c.coverage >= MIN_COVERAGE);
  const pool = useful.length ? useful : candidates;
  if (!pool.length) return null;

  const adjusted = pool.filter((c) => c.adjusted);
  const ranked = adjusted.length ? adjusted : pool;

  return ranked.reduce((best, current) => {
    if (current.gapShare !== best.gapShare) return current.gapShare > best.gapShare ? current : best;
    return current.coverage > best.coverage ? current : best;
  });
}

// "Iron" -> "iron", but "Vitamin C" and "Vitamin B12" keep their capitals
export function nutrientPhrase(label, nutrientId) {
  const text = label || nutrientId || "";
  return /\s|\d/.test(text) ? text : text.toLowerCase();
}

// "chickpeas, tomato and lemon juice"
export function listNames(names) {
  if (names.length <= 1) return names[0] || "";
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

export function round(value) {
  return Math.round(value * 10) / 10;
}
