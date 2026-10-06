import { hasSupabaseEnv, supabase } from "../supabase/client";

// household_members / households only accept specific enum values and a
// 2-letter region code; the onboarding UI offers friendlier labels, so these
// map one to the other. Anything with no close match falls back to the
// safest valid option rather than letting the insert fail.
const SEX_AT_BIRTH = { Female: "F", Male: "M" };
const ACTIVITY_LEVEL = { Sedentary: "sedentary", Moderate: "moderate", Active: "very_active" };
const GOAL = {
  "Maintain weight": "maintenance",
  "Weight loss": "weight_loss",
  "Weight gain": "muscle_gain",
  "Improve health": "wellness",
};
const SEX_AT_BIRTH_REVERSE = { F: "Female", M: "Male" };
const ACTIVITY_LEVEL_REVERSE = { sedentary: "Sedentary", moderate: "Moderate", very_active: "Active", lightly_active: "Active", athlete: "Active" };
const GOAL_REVERSE = { weight_loss: "Weight loss", muscle_gain: "Weight gain", wellness: "Improve health", maintenance: "Maintain weight" };
// UK isn't the real ISO 3166-1 alpha-2 code (GB is), and "Other" isn't a
// code at all, so both need mapping; anything unrecognized falls back to US.
const COUNTRY_REGION = { US: "US", CA: "CA", UK: "GB", AU: "AU" };
const COUNTRY_REGION_REVERSE = { US: "US", CA: "CA", GB: "UK", AU: "AU" };

function lbToKg(lb) {
  const n = Number(lb);
  return Number.isFinite(n) && n > 0 ? Math.round(n * 0.453592 * 100) / 100 : null;
}

function kgToLb(kg) {
  const n = Number(kg);
  return Number.isFinite(n) && n > 0 ? String(Math.round(n / 0.453592)) : "";
}

function heightToCm(height) {
  const feetMatch = String(height || "").match(/(\d+)\s*(?:ft|')/);
  const inchMatch = String(height || "").match(/(\d+)\s*(?:in|")/);
  const totalInches = Number(feetMatch?.[1] || 0) * 12 + Number(inchMatch?.[1] || 0);
  return totalInches > 0 ? Math.round(totalInches * 2.54 * 100) / 100 : null;
}

function cmToHeight(cm) {
  const n = Number(cm);
  if (!Number.isFinite(n) || n <= 0) return "";
  const totalInches = Math.round(n / 2.54);
  const feet = Math.floor(totalInches / 12);
  const inches = totalInches % 12;
  return `${feet} ft ${inches} in`;
}

function lifeStageToDb(profile) {
  switch (profile.lifeStage) {
    case "Pregnant":
      return { life_stage: profile.pregnancyWeek ? `pregnancy_wk_${profile.pregnancyWeek}` : "pregnant", pregnancy_detail: profile.pregnancyWeek || null };
    case "Lactating":
      return { life_stage: "lactating", pregnancy_detail: null };
    case "Menstruating":
      return { life_stage: "menstruating", pregnancy_detail: null };
    case "Menopause":
      return { life_stage: "menopause", pregnancy_detail: null };
    default:
      return { life_stage: null, pregnancy_detail: null };
  }
}

function lifeStageFromDb(lifeStage) {
  if (!lifeStage) return "None";
  if (lifeStage.startsWith("pregnancy") || lifeStage === "pregnant") return "Pregnant";
  if (lifeStage === "lactating") return "Lactating";
  if (lifeStage === "menstruating") return "Menstruating";
  if (lifeStage === "menopause") return "Menopause";
  return "None";
}

function profileToMemberRow(profile, householdId) {
  const { life_stage, pregnancy_detail } = lifeStageToDb(profile);
  return {
    household_id: householdId,
    member_name: profile.name || profile.inviteEmail || "Household member",
    age: profile.age ? Number(profile.age) : null,
    sex_at_birth: SEX_AT_BIRTH[profile.sex] || null,
    weight_kg: lbToKg(profile.weight),
    height_cm: heightToCm(profile.height),
    activity_level: ACTIVITY_LEVEL[profile.activity] || null,
    life_stage,
    pregnancy_detail,
    lifestyle_dietary: profile.dietaryPattern && profile.dietaryPattern !== "None" ? [profile.dietaryPattern] : null,
    goal: GOAL[profile.goal] || null,
    food_preference_csv: profile.preferences
      ? profile.preferences.split(",").map((s) => s.trim()).filter(Boolean)
      : null,
    profile_email: profile.inviteEmail || null,
  };
}

// Converts a household_members row back into the shape ProfileBasicsModule
// and friends expect. Dislikes and per-species pets aren't stored anywhere
// in this schema, so those come back empty rather than guessed.
function memberRowToProfile(row, allergyByMember) {
  return {
    name: row.member_name,
    age: row.age != null ? String(row.age) : "",
    sex: SEX_AT_BIRTH_REVERSE[row.sex_at_birth] || "Other",
    height: cmToHeight(row.height_cm),
    weight: kgToLb(row.weight_kg),
    role: row.age != null && row.age < 18 ? "Child" : "Adult",
    activity: ACTIVITY_LEVEL_REVERSE[row.activity_level] || "Moderate",
    goal: GOAL_REVERSE[row.goal] || "Maintain weight",
    allergies: allergyByMember[row.member_id] || "None",
    dislikes: "None",
    dietaryPattern: row.lifestyle_dietary?.[0] || "None",
    preferences: (row.food_preference_csv || []).join(", "),
    cuisines: ["Mexican"],
    lifeStage: lifeStageFromDb(row.life_stage),
    pregnancyWeek: row.pregnancy_detail || "",
  };
}

function notConfigured() {
  return { error: { message: "Supabase isn't configured in this environment." } };
}

export async function signUp({ name, username, email, password }) {
  if (!hasSupabaseEnv || !supabase) return notConfigured();
  const { data, error } = await supabase.auth.signUp({
    email,
    password,
    options: { data: { full_name: name, username } },
  });
  return { data, error };
}

export async function signIn({ email, password }) {
  if (!hasSupabaseEnv || !supabase) return notConfigured();
  return supabase.auth.signInWithPassword({ email, password });
}

export async function getCurrentUserId() {
  if (!hasSupabaseEnv || !supabase) return null;
  const { data } = await supabase.auth.getUser();
  return data?.user?.id || null;
}

// Writes the household + every collected member profile for a brand new
// signup. Allergies live in member_conditions, not household_members, per
// the schema (condition_type/value_text), so each non-"None" allergy string
// becomes its own row there.
export async function saveHousehold({ userId, household, profiles }) {
  if (!hasSupabaseEnv || !supabase || !userId) return notConfigured();
  if (!profiles?.length) return { error: { message: "At least one profile is required." } };

  const hasPets = Boolean(household?.pets?.cat || household?.pets?.dog);
  const { data: householdRow, error: householdError } = await supabase
    .from("households")
    .insert({
      created_by_user_id: userId,
      household_name: household?.name || null,
      country_region: COUNTRY_REGION[household?.country] || "US",
      has_pets: hasPets,
      pets_receive_scraps: hasPets ? Boolean(household?.scraps) : null,
    })
    .select()
    .single();

  if (householdError) return { error: householdError };

  const memberRows = profiles.map((p) => profileToMemberRow(p, householdRow.household_id));
  const { data: insertedMembers, error: membersError } = await supabase
    .from("household_members")
    .insert(memberRows)
    .select();

  if (membersError) return { error: membersError };

  const allergyRows = profiles
    .map((p, i) => ({ memberId: insertedMembers[i]?.member_id, allergies: p.allergies }))
    .filter((r) => r.memberId && r.allergies && r.allergies !== "None")
    .map((r) => ({ member_id: r.memberId, condition_type: "allergy", value_text: r.allergies }));

  if (allergyRows.length) {
    const { error: allergyError } = await supabase.from("member_conditions").insert(allergyRows);
    if (allergyError) return { error: allergyError };
  }

  return { data: { householdId: householdRow.household_id } };
}

// For a returning user: finds the household they created (if any) and every
// member profile in it, mapped back to the app's UI shape. Returns null when
// this user hasn't completed household setup yet (e.g. used the quick
// sign-up form that only collects a name).
export async function loadHouseholdForUser(userId) {
  if (!hasSupabaseEnv || !supabase || !userId) return null;

  const { data: householdRow, error: householdError } = await supabase
    .from("households")
    .select("*")
    .eq("created_by_user_id", userId)
    .is("deleted_at", null)
    .maybeSingle();

  if (householdError || !householdRow) return null;

  const { data: memberRows, error: membersError } = await supabase
    .from("household_members")
    .select("*")
    .eq("household_id", householdRow.household_id)
    .is("deleted_at", null);

  const household = {
    name: householdRow.household_name || "",
    country: COUNTRY_REGION_REVERSE[householdRow.country_region] || "US",
    members: memberRows?.length || 0,
    pets: { cat: false, dog: false }, // has_pets doesn't distinguish species
    scraps: Boolean(householdRow.pets_receive_scraps),
  };

  if (membersError || !memberRows?.length) return { household, profiles: [] };

  const memberIds = memberRows.map((m) => m.member_id);
  const { data: allergyRows } = await supabase
    .from("member_conditions")
    .select("member_id, value_text")
    .eq("condition_type", "allergy")
    .in("member_id", memberIds);

  const allergyByMember = Object.fromEntries((allergyRows || []).map((a) => [a.member_id, a.value_text]));

  return { household, profiles: memberRows.map((row) => memberRowToProfile(row, allergyByMember)) };
}
