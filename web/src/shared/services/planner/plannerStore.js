import { hasSupabaseEnv, supabase } from "../supabase/client";

const STORAGE_KEY_PREFIX = "mazimeal-weekly-planner";

function storageKey(userKey) {
  return `${STORAGE_KEY_PREFIX}:${userKey || "guest"}`;
}

function isBrowser() {
  return typeof window !== "undefined";
}

function safeParse(value) {
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

export function normalizePlannerState(state) {
  if (!state || !state.anchorDate || !Array.isArray(state.days)) return null;
  return {
    ...state,
    anchorDate: new Date(state.anchorDate),
  };
}

export async function loadPlannerState(userKey) {
  const localValue = isBrowser() ? safeParse(window.localStorage.getItem(storageKey(userKey))) : null;
  const normalizedLocalValue = normalizePlannerState(localValue);

  if (!hasSupabaseEnv || !supabase || !userKey) {
    return normalizedLocalValue;
  }

  try {
    const { data, error } = await supabase
      .from("weekly_plans")
      .select("planner_state")
      .eq("user_key", userKey)
      .maybeSingle();

    if (error) throw error;
    const normalizedRemoteValue = normalizePlannerState(data?.planner_state);
    return normalizedRemoteValue || normalizedLocalValue;
  } catch (error) {
    console.warn("Unable to load planner state from Supabase. Falling back to local storage.", error);
    return normalizedLocalValue;
  }
}

export async function savePlannerState(userKey, plannerState) {
  if (!userKey || !plannerState) return;

  if (isBrowser()) {
    window.localStorage.setItem(storageKey(userKey), JSON.stringify(plannerState));
  }

  if (!hasSupabaseEnv || !supabase) return;

  try {
    const { error } = await supabase.from("weekly_plans").upsert(
      {
        user_key: userKey,
        planner_state: plannerState,
        updated_at: new Date().toISOString(),
      },
      { onConflict: "user_key" }
    );

    if (error) throw error;
  } catch (error) {
    console.warn("Unable to save planner state to Supabase. Local storage copy is still available.", error);
  }
}
