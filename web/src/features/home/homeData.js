// Data for the home page. One call: fn_home(household_id, date) in the
// database returns picks per meal, each member's open nutrient gaps, and the
// recipes hidden for this household. When Supabase isn't configured, the
// page uses a snapshot of that same output so it still works.
import { hasSupabaseEnv, supabase } from "../../shared/services/supabase/client";
import snapshot from "./homeSnapshot.json";

// The demo household from recommender/seed/01_demo_household.sql.
export const DEMO_HOUSEHOLD_ID = "01930000-0000-7000-8000-0000000000b1";

export const MEAL_SLOTS = ["Breakfast", "Lunch", "Dinner", "Snack"];

export async function loadHome({ householdId = DEMO_HOUSEHOLD_ID, date = null, perSlot = 3 } = {}) {
  if (!hasSupabaseEnv || !supabase) {
    return { ...snapshot, source: "snapshot" };
  }
  const params = { p_household_id: householdId, p_per_slot: perSlot };
  if (date) params.p_date = date;
  const { data, error } = await supabase.rpc("fn_home", params);
  if (error) {
    console.warn("fn_home failed, using snapshot.", error);
    return { ...snapshot, source: "snapshot", error: error.message };
  }
  return { ...data, source: "live" };
}

// Macro_Protein -> Protein, Vitamin_B12 -> Vitamin B12
export function nutrientLabel(id) {
  return String(id || "")
    .replace(/^Macro_/, "")
    .replace(/_/g, " ");
}

// "vegan" -> "Vegan", "gluten_free" -> "Gluten free"
export function tagLabel(tag) {
  const t = String(tag || "").replace(/_/g, " ");
  return t.charAt(0).toUpperCase() + t.slice(1);
}

// fiber, protein, Vitamin C
function inSentence(id) {
  const label = nutrientLabel(id);
  return /^Vitamin/.test(label) ? label : label.toLowerCase();
}

// "Closes 100% of Jeff's fiber and 90% of the protein for this meal."
export function reasonSentence(pick) {
  const who = pick?.top_reasons?.member;
  const reasons = (pick?.top_reasons?.reasons || []).filter((r) => r.closes_pct > 0).slice(0, 2);
  if (!who || reasons.length === 0) return "Passes every household restriction.";
  const parts = reasons.map((r, i) =>
    i === 0
      ? `${r.closes_pct}% of ${who}'s ${inSentence(r.nutrient)}`
      : `${r.closes_pct}% of the ${inSentence(r.nutrient)}`
  );
  return `Closes ${parts.join(" and ")} for this meal.`;
}

// Top open gaps per member, for Smart Insights.
export function gapSentences(home, max = 3) {
  return (home?.members || []).map((m) => {
    const open = (m.gaps || []).filter((g) => g.pct_open >= 50).slice(0, max);
    if (open.length === 0) return `${m.name} is on track for today.`;
    const names = open.map((g) => nutrientLabel(g.nutrient));
    const list = names.length > 1 ? `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}` : names[0];
    return `${m.name} still needs most of today's ${list}.`;
  });
}
