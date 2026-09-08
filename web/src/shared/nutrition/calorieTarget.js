// Daily calorie target from the profile form. Mifflin-St Jeor for adults.

function parseHeightToCm(heightValue) {
  if (!heightValue) return null;
  const normalized = String(heightValue).trim().toLowerCase();
  const feetInchesMatch = normalized.match(/(\d+)\s*ft\s*(\d+)?\s*in?/);
  if (feetInchesMatch) {
    const feet = Number(feetInchesMatch[1] || 0);
    const inches = Number(feetInchesMatch[2] || 0);
    return Math.round((feet * 12 + inches) * 2.54);
  }

  const cmMatch = normalized.match(/(\d+(?:\.\d+)?)\s*cm/);
  if (cmMatch) {
    return Number(cmMatch[1]);
  }

  const plainNumber = Number(normalized.replace(/[^\d.]/g, ""));
  if (!Number.isFinite(plainNumber) || plainNumber <= 0) return null;
  return plainNumber > 100 ? plainNumber : Math.round(plainNumber * 2.54);
}

function parseWeightToKg(weightValue) {
  if (!weightValue) return null;
  const normalized = String(weightValue).trim().toLowerCase();
  const kgMatch = normalized.match(/(\d+(?:\.\d+)?)\s*kg/);
  if (kgMatch) {
    return Number(kgMatch[1]);
  }

  const plainNumber = Number(normalized.replace(/[^\d.]/g, ""));
  if (!Number.isFinite(plainNumber) || plainNumber <= 0) return null;
  return plainNumber > 140 ? Math.round((plainNumber / 2.20462) * 10) / 10 : plainNumber;
}

function getActivityFactor(activity) {
  const normalized = String(activity || "").toLowerCase();
  if (normalized.includes("sedentary")) return 1.2;
  if (normalized.includes("light")) return 1.375;
  if (normalized.includes("active")) return 1.55;
  if (normalized.includes("very")) return 1.725;
  return 1.45;
}

function getGoalAdjustment(goal) {
  const normalized = String(goal || "").toLowerCase();
  if (normalized.includes("lose")) return -350;
  if (normalized.includes("muscle") || normalized.includes("gain")) return 220;
  if (normalized.includes("heart") || normalized.includes("energ")) return -80;
  return 0;
}

export function calculateDailyCalorieTarget(profile) {
  if (!profile || profile.invited) return 2000;

  const age = Number(profile.age);
  const weightKg = parseWeightToKg(profile.weight);
  const heightCm = parseHeightToCm(profile.height);
  const hasCoreMetrics = Number.isFinite(age) && age > 0 && Number.isFinite(weightKg) && Number.isFinite(heightCm);

  if (!hasCoreMetrics) return 2000;

  const sex = String(profile.sex || "").toLowerCase();
  const role = String(profile.role || "").toLowerCase();
  const activityFactor = getActivityFactor(profile.activity);
  const goalAdjustment = getGoalAdjustment(profile.goal);

  let estimatedTarget;

  if (role.includes("child") || age < 18) {
    const childBase = 22 * weightKg + 450;
    estimatedTarget = childBase * Math.min(activityFactor, 1.6);
  } else {
    const bmr =
      sex.includes("male")
        ? 10 * weightKg + 6.25 * heightCm - 5 * age + 5
        : 10 * weightKg + 6.25 * heightCm - 5 * age - 161;
    estimatedTarget = bmr * activityFactor;
  }

  const adjustedTarget = estimatedTarget + goalAdjustment;
  return Math.round(Math.min(3400, Math.max(1400, adjustedTarget)) / 10) * 10;
}

export function describeCalorieGoal(profile, calorieGoal) {
  if (!profile || profile.invited) {
    return `Using a standard ${calorieGoal} kcal daily target.`;
  }

  const summaryParts = [];
  if (profile.sex) summaryParts.push(profile.sex);
  if (profile.age) summaryParts.push(`${profile.age} yrs`);
  if (profile.weight) summaryParts.push(profile.weight.includes("kg") ? profile.weight : `${profile.weight} lb`);
  if (profile.height) summaryParts.push(profile.height);
  if (profile.activity) summaryParts.push(profile.activity);
  if (profile.goal) summaryParts.push(profile.goal);

  return `Based on ${profile.name || "your"}'s profile: ${summaryParts.join(" • ")} = ${calorieGoal} kcal target.`;
}

export function formatNutrientLabel(label) {
  const text = String(label || "");
  const compactMap = {
    VitaminC: "Vitamin C",
    VitaminD: "Vitamin D",
    VitaminA: "Vitamin A",
    Omega3: "Omega-3",
    HealthyFats: "Healthy Fats",
    FamilyAppeal: "Family Appeal",
  };

  if (compactMap[text]) return compactMap[text];
  return text.replace(/([a-z])([A-Z])/g, "$1 $2");
}
