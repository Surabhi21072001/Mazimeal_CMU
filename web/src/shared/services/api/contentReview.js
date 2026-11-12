// The suggestion text's review record. Transport and identity live in authed.js.
//
// These used to be reads and writes of localStorage. They are API calls now
// because a correction is a statement about the recipe, not about the machine
// it was typed on: another reviewer has to see it, and so does every cook.
import { call } from "./authed";

// Reviewer-only, and it has a side effect worth knowing about: a recipe nobody
// has opened gets version 1 written from the model's output, server-side. That
// baseline is what every later diff is read against, so the server produces it
// rather than trusting a browser to say what the model "originally" wrote.
export function getReviewRecord(recipeId) {
  return call(`/api/review/content/${encodeURIComponent(recipeId)}`);
}

// One decision. No reviewer and no author: the server takes both from the
// token. Fields left out are inherited from the current version, so a reviewer
// who changes one tip does not silently undo another reviewer's rule removal.
export function saveReviewVersion(recipeId, body) {
  return call(`/api/review/content/${encodeURIComponent(recipeId)}`, {
    method: "POST",
    body,
  });
}

export function getReviewStats() {
  return call("/api/review/content-stats");
}

// Open, and used by the cook screen: the corrected text is what a cook is
// meant to read.
export function getCurrentReviewVersion(recipeId) {
  return call(`/api/recipes/${encodeURIComponent(recipeId)}/review`, { auth: false });
}
