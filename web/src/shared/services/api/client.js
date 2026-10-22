// One source of data for the new screens: our own backend.
//
// When VITE_API_BASE_URL is set we call it. When it is not set, or the call
// fails, we fall back to the fixtures bundled with the build, so the app runs
// with no backend at all - which is how it is deployed for the client demo.
// Every payload carries `source`, and the UI shows a badge when it is not live.
import household from "../../fixtures/household.json";
import recommendationsMayaLunch from "../../fixtures/recommendations_maya_lunch.json";
import falafel from "../../fixtures/recipe_falafel-001.json";
import souvlaki from "../../fixtures/recipe_souvlaki-002.json";
import sloppyJoes from "../../fixtures/recipe_sloppy-joes-003.json";
import tunaSalad from "../../fixtures/recipe_tuna-salad-004.json";
import tomatoSpaghetti from "../../fixtures/recipe_tomato-spaghetti-005.json";
import suggestionsFalafel from "../../fixtures/suggestions_falafel-001.json";

const BASE = import.meta.env.VITE_API_BASE_URL || "";

export const RECIPE_FIXTURES = {
  "falafel-001": falafel,
  "souvlaki-002": souvlaki,
  "sloppy-joes-003": sloppyJoes,
  "tuna-salad-004": tunaSalad,
  "tomato-spaghetti-005": tomatoSpaghetti,
};

export const DEFAULT_RECIPE_ID = "falafel-001";

// Two different questions, which were tangled together until they gave a
// connected page a badge saying it was offline:
//   transport - did this come over the network, or out of the bundle?
//   source    - what kind of data is it: fixtures, the live database, a model?
// The backend legitimately answers "fixture" while being perfectly reachable.
function withSource(payload, source, transport, error) {
  if (!payload) return null;
  return { ...payload, source, transport, ...(error ? { error } : {}) };
}

async function request(path, fallback, options) {
  if (!BASE) return withSource(fallback, "fixture", "bundled");
  try {
    const response = await fetch(`${BASE}${path}`, options);
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    const data = await response.json();
    return withSource(data, data.source || "live", "api");
  } catch (error) {
    console.warn(`API call failed for ${path}; using bundled fixture.`, error);
    return withSource(fallback, "fixture", "bundled", error.message);
  }
}

export function getHousehold() {
  return request("/api/household", household);
}

export function getRecommendations({ memberId = "maya", meal = "Lunch", targetNutrient = "Iron", limit = 5 } = {}) {
  const query = new URLSearchParams({
    member_id: memberId,
    meal,
    target_nutrient: targetNutrient,
    limit: String(limit),
  });
  return request(`/api/recommendations?${query}`, recommendationsMayaLunch);
}

export function getRecipe(recipeId) {
  const fallback = RECIPE_FIXTURES[recipeId] || null;
  return request(`/api/recipes/${recipeId}`, fallback);
}

export function getSuggestions(recipeId, memberId = "maya", ruleIds = [], { refresh = false } = {}) {
  // The backend serves reviewed text when a person has approved it, a cached
  // rewrite when one exists, and runs the model otherwise. `refresh` skips
  // both and rewrites - that is the button testers press.
  const fallback = recipeId === "falafel-001" ? suggestionsFalafel : { recipe_id: recipeId, suggestions: [], source: "stub" };
  const query = refresh ? "?refresh=true" : "";
  return request(`/api/recipes/${recipeId}/suggestions${query}`, fallback, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ member_id: memberId, rule_ids: ruleIds }),
  });
}

// A free question about one recipe. Nothing is cached: the backend grounds the
// answer in the recipe, its rules and the member's targets, and refuses when
// the model strays outside them.
export function askQuestion(recipeId, question, memberId = "maya") {
  const fallback = {
    answer:
      "The assistant needs the backend running. Start it and reload, or read the suggestions above, which come from the rules themselves.",
    source: "unavailable",
  };
  return request(`/api/recipes/${recipeId}/ask`, fallback, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, member_id: memberId }),
  });
}

export function isConnected(payload) {
  return payload?.transport === "api";
}

export function isLive(payload) {
  return payload?.source === "live" || payload?.source === "recommender";
}
