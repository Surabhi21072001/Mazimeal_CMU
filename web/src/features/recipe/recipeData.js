// Data for the recipe screen. Three reads: the recipe row, its steps, and
// fn_recipe_nutrition(recipe_id, overrides, servings), which returns the
// ingredient lines with grams and the nutrition panel, recalculated when
// lines or servings change. Without Supabase, one recipe comes from a
// snapshot of the same output so the screen still works.
import { hasSupabaseEnv, supabase } from "../../shared/services/supabase/client";
import snapshot from "./recipeSnapshot.json";

export async function loadRecipe(recipeId) {
  if (!hasSupabaseEnv || !supabase) {
    return { ...snapshot, source: "snapshot" };
  }
  const [recipeRes, stepsRes, nutritionRes] = await Promise.all([
    supabase
      .from("recipes")
      .select("recipe_id, recipe_name, recipe_description, prep_time_min, cook_time_min, servings, meal_category, dietary_tags, difficulty_level")
      .eq("recipe_id", recipeId)
      .maybeSingle(),
    supabase
      .from("recipe_steps")
      .select("step_number, instruction, duration_min, timing_note")
      .eq("recipe_id", recipeId)
      .order("step_number"),
    supabase.rpc("fn_recipe_nutrition", { p_recipe_id: recipeId }),
  ]);
  const error = recipeRes.error || stepsRes.error || nutritionRes.error;
  if (error || !recipeRes.data) {
    console.warn("recipe load failed, using snapshot.", error);
    return { ...snapshot, source: "snapshot", error: error?.message };
  }
  return { recipe: recipeRes.data, steps: stepsRes.data || [], nutrition: nutritionRes.data, source: "live" };
}

// Recalculate with changed lines and/or a different serving count.
// overrides: [{ line_id, quantity, measure }, { line_id, remove: true }, ...]
export async function recalcRecipe(recipeId, overrides = [], servings = null) {
  if (!hasSupabaseEnv || !supabase) {
    return snapshot.nutrition;
  }
  const params = { p_recipe_id: recipeId, p_overrides: overrides };
  if (servings) params.p_servings = servings;
  const { data, error } = await supabase.rpc("fn_recipe_nutrition", params);
  if (error) throw error;
  return data;
}

// Log a meal for one or more household members. portions: [{ member_id, servings }].
// The log id is generated here so a retried call can't count twice.
export async function logMeal(recipeId, portions, { mealType = null, overrides = [], logId = null } = {}) {
  if (!hasSupabaseEnv || !supabase) {
    throw new Error("Logging needs a database connection.");
  }
  const params = {
    p_recipe_id: recipeId,
    p_portions: portions,
    p_meal_type: mealType,
    p_overrides: overrides,
    p_log_id: logId || (globalThis.crypto?.randomUUID ? crypto.randomUUID() : null),
  };
  const { data, error } = await supabase.rpc("fn_log_meal", params);
  if (error) throw error;
  return data;
}

// The four tiles at the top of the panel.
export const HEADLINE = ["Energy", "Macro_Protein", "Macro_Carbohydrate", "Macro_Fat"];

export function nutrientLabel(id) {
  return String(id || "").replace(/^Macro_/, "").replace(/_/g, " ");
}

// 0.25 -> "¼", 1.5 -> "1½", 0.333 -> "⅓"
export function formatQuantity(q) {
  const n = Number(q);
  if (!Number.isFinite(n)) return "";
  const whole = Math.floor(n);
  const frac = n - whole;
  const glyph =
    Math.abs(frac - 0.25) < 0.02 ? "¼" :
    Math.abs(frac - 0.333) < 0.02 ? "⅓" :
    Math.abs(frac - 0.5) < 0.02 ? "½" :
    Math.abs(frac - 0.667) < 0.02 ? "⅔" :
    Math.abs(frac - 0.75) < 0.02 ? "¾" : null;
  if (glyph) return `${whole || ""}${glyph}`;
  return Number.isInteger(n) ? String(n) : n.toFixed(2).replace(/\.?0+$/, "");
}

export function formatGrams(g) {
  const n = Number(g);
  if (!Number.isFinite(n)) return "";
  return n >= 100 ? `${Math.round(n)} g` : `${n.toFixed(1).replace(/\.0$/, "")} g`;
}

// "estimated" note for the panel. Imported recipes have no units in the
// source, so grams are estimates; the calibration factor says how far the
// derived calories were from the published ones before correction.
export function qualityNote(nutrition) {
  if (!nutrition) return null;
  const f = Number(nutrition.calibration_factor);
  const cov = Number(nutrition.coverage);
  if (cov < 0.9) return `Nutrition data covers ${Math.round(cov * 100)}% of the ingredients.`;
  if (Number.isFinite(f) && (f < 0.6 || f > 1.6)) return "Ingredient amounts are estimated; micronutrients are approximate.";
  return null;
}
