// Nutrition plausibility review. Transport and identity live in authed.js.
import { call } from "./authed";

// Open: the ratio and the counts behind it are already on the cook screen.
export function nutritionQueue() {
  return call("/api/review/nutrition", { auth: false });
}

export function nutritionHistory(recipeId) {
  return call(`/api/review/nutrition/${encodeURIComponent(recipeId)}/history`, { auth: false });
}

// The verdict carries no reviewer and no ratio: the server takes the reviewer
// from the token and the ratio from the database as it stands, so the record
// always says who decided and what they were actually shown.
export function recordNutritionVerdict(recipeId, verdict, reason) {
  return call(`/api/review/nutrition/${encodeURIComponent(recipeId)}`, {
    method: "POST",
    body: { verdict, reason },
  });
}
