import { useState, useEffect } from "react";
import { C } from "../../shared/theme/colors";
import { calculateDailyCalorieTarget, describeCalorieGoal, formatNutrientLabel } from "../../shared/nutrition/calorieTarget";
import RecommendedMeals from "./RecommendedMeals";
import RecipeDetail from "../recipe/RecipeDetail";
import { gapSentences, loadHome } from "./homeData";

export default function HomeDashboardClassic({
  user,
  setStep,
  plannerDay,
  profile,
  mealLogByDay,
  setMealLogByDay,
  hydrationByDay,
  setHydrationByDay,
}) {
  const [activeClassicModal, setActiveClassicModal] = useState(null);
  const [hydrationForm, setHydrationForm] = useState({ water: 0 });
  const [sleepHours, setSleepHours] = useState(7.5);
  const [showStreakCelebration, setShowStreakCelebration] = useState(false);
  const [assistantMessageIndex, setAssistantMessageIndex] = useState(0);
  const [classicCookMeal, setClassicCookMeal] = useState(null);
  const [openRecipeId, setOpenRecipeId] = useState(null);
  const [home, setHome] = useState(null);
  const [homeLoading, setHomeLoading] = useState(true);

  const [homeVersion, setHomeVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    loadHome()
      .then((data) => { if (!cancelled) setHome(data); })
      .finally(() => { if (!cancelled) setHomeLoading(false); });
    return () => { cancelled = true; };
  }, [homeVersion]);

  const items = plannerDay
    ? plannerDay.mealOrder.map((slot) => {
        const meal = plannerDay.meals[slot];
        return {
          id: slot,
          meal: meal.label || meal.slotType || "Meal",
          name: meal.name,
          calories: meal.calories,
          protein: meal.protein,
          image: meal.image,
          nutrients: meal.nutrients || {},
          sideSuggestion: meal.sideSuggestion || "",
          sideSuggestionSource: meal.sideSuggestionSource || "",
        };
      })
    : [
        { id: "breakfast", meal: "Breakfast", name: "Avocado Toast + Berry Smoothie", calories: 340, protein: 14, nutrients: { Protein: 62, Fiber: 58, HealthyFats: 68 } },
        { id: "lunch", meal: "Lunch", name: "Chicken + Veggie Bowl", calories: 520, protein: 30, nutrients: { Protein: 82, Carbs: 66, Balance: 74 } },
        { id: "dinner", meal: "Salmon Mediterranean Plate", name: "Salmon Mediterranean Plate", calories: 540, protein: 32, nutrients: { Protein: 88, Omega3: 84, Satiety: 72 } },
        { id: "snack", meal: "Snack", name: "Hummus & Veggies", calories: 160, protein: 6, nutrients: { Fiber: 61, Protein: 36, Energy: 44 } },
      ];
  const dayLogKey = plannerDay?.key || "fallback-day";
  const defaultMealLog = items.reduce((acc, item) => {
    acc[item.id] = false;
    return acc;
  }, {});
  const defaultHydrationLog = { water: 2 };
  const mealLog = mealLogByDay[dayLogKey] || defaultMealLog;
  const totalMeals = items.length;
  const totalCalories = plannerDay ? plannerDay.totalCalories : items.reduce((sum, item) => sum + item.calories, 0);
  const loggedItems = items.filter((item) => mealLog[item.id]);
  const loggedCalories = loggedItems.reduce((sum, item) => sum + (item.calories || 0), 0);
  const calorieGoal = calculateDailyCalorieTarget(profile);
  const calorieGoalExplanation = describeCalorieGoal(profile, calorieGoal);
  const calorieAlignment = Math.min(Math.round((loggedCalories / calorieGoal) * 100), 100);
  const progressRing = Math.min(Math.max(calorieAlignment, 8), 100);
  const progressCircumference = 2 * Math.PI * 58;
  const progressOffset = progressCircumference * (1 - progressRing / 100);
  const hydrationLog = hydrationByDay[dayLogKey] || defaultHydrationLog;
  const hydrationCount = Math.min(8, Math.max(0, Number(hydrationLog.water || 0)));
  const hydrationPercent = Math.round((hydrationCount / 8) * 100);
  const hydrationRemaining = Math.max(0, 8 - hydrationCount);
  const hydrationMessage =
    hydrationCount >= 8
      ? "Fully hydrated and feeling strong."
      : hydrationCount >= 5
      ? `${hydrationRemaining} more glass${hydrationRemaining === 1 ? "" : "es"} to reach today's goal.`
      : `${hydrationRemaining} glasses left. A few more sips will lift your energy today.`;
  const highlightedMeal = items.find((item) => item.meal.toLowerCase().includes("dinner")) || items[0];
  const savedSideMeal = items.find((item) => item.sideSuggestion) || null;
  const topNutrients = Object.entries(
    items.reduce((acc, item) => {
      const calories = item.calories || 1;
      Object.entries(item.nutrients || {}).forEach(([rawLabel, rawValue]) => {
        const value = Number(rawValue);
        if (!Number.isFinite(value)) return;
        if (!acc[rawLabel]) {
          acc[rawLabel] = { total: 0, weight: 0 };
        }
        acc[rawLabel].total += value * calories;
        acc[rawLabel].weight += calories;
      });
      return acc;
    }, {})
  )
    .map(([label, bucket]) => ({
      label: formatNutrientLabel(label),
      value: Math.min(100, Math.max(12, Math.round(bucket.total / bucket.weight))),
    }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 5);
  const nutrientColors = ["#6AA33F", "#3D86D9", "#F09B1C", "#7D6BA8", "#C55B4A"];
  const smartTips = home?.members?.length
    ? gapSentences(home)
    : [
        "It's hot today - stay extra hydrated!",
        "Add more fiber to your meals today.",
        "Boost your Vitamin C - pair lunch with citrus.",
      ];
  const achievements = [
    "You've cooked 3 days in a row! Amazing consistency!",
    "You're 70% to your weekly protein goal!",
    "Hydration on track - keep it up!",
    "Streak unlocked: Healthy Habit Builder Level 1!",
  ];
  const assistantMessages = [
    "How can I assist you today?",
    "How about lunch ideas?",
    "Want a faster dinner swap?",
  ];
  const cookMeal = classicCookMeal || highlightedMeal;

  const plannerInspiredShell = {
    position: "relative",
    overflow: "hidden",
    background: "linear-gradient(180deg, rgba(255,253,248,0.96), rgba(248,245,238,0.94))",
    border: `1.5px solid ${C.border}`,
    boxShadow: "0 18px 38px rgba(72, 88, 120, 0.08)",
  };

  const plannerInspiredGlass = {
    border: `1px solid ${C.border}`,
    background: "rgba(255,255,255,0.84)",
    backdropFilter: "blur(8px)",
    boxShadow: "0 10px 24px rgba(72, 88, 120, 0.08)",
  };

  const getClassicCookSteps = (meal) => {
    const mealName = String(meal?.name || "").toLowerCase();

    if (mealName.includes("stir-fry")) {
      return [
        "Prep the vegetables first so the pan stays hot and the cook stays fast.",
        "Sear the protein in a single layer until lightly golden, then remove briefly.",
        "Stir-fry broccoli, peppers, and aromatics until crisp-tender.",
        "Return the protein, add sauce, and toss just until glossy.",
      ];
    }

    if (mealName.includes("salmon")) {
      return [
        "Pat the salmon dry and season it before it hits the pan.",
        "Sear skin-side down first to build texture and lock in moisture.",
        "Add lemon and herbs near the end so the flavors stay bright.",
        "Rest briefly before serving with greens or grains.",
      ];
    }

    if (mealName.includes("bowl") || mealName.includes("quinoa")) {
      return [
        "Warm the grain base first so the full bowl feels freshly assembled.",
        "Layer protein and vegetables separately to keep textures distinct.",
        "Add dressing or sauce last to keep the greens vibrant.",
        "Finish with seeds or citrus for contrast and freshness.",
      ];
    }

    return [
      "Prep ingredients first so cooking stays smooth and consistent.",
      "Cook the main protein or base until just done, not overworked.",
      "Add vegetables in stages to keep color and texture.",
      "Finish with a bright garnish or dressing before serving.",
    ];
  };

  const getClassicBioavailabilityTip = (meal) => {
    const mealName = String(meal?.name || "").toLowerCase();

    if (mealName.includes("stir-fry") || mealName.includes("chicken")) {
      return "Pair the vegetables with a squeeze of citrus at the end to support iron absorption from the greens.";
    }

    if (mealName.includes("salmon")) {
      return "Healthy fats in salmon help absorb fat-soluble vitamins like A, D, E, and K from the vegetables on the plate.";
    }

    if (mealName.includes("quinoa") || mealName.includes("bowl")) {
      return "Adding lemon or another vitamin C source can improve mineral uptake from beans, greens, and grains.";
    }

    return "A small source of healthy fat or citrus often improves nutrient absorption and makes the meal feel more complete.";
  };

  useEffect(() => {
    setMealLogByDay((current) => {
      if (current[dayLogKey]) return current;
      return {
        ...current,
        [dayLogKey]: defaultMealLog,
      };
    });
  }, [dayLogKey]);

  useEffect(() => {
    setHydrationByDay((current) => {
      if (current[dayLogKey]) return current;
      return {
        ...current,
        [dayLogKey]: defaultHydrationLog,
      };
    });
  }, [dayLogKey]);

  useEffect(() => {
    setHydrationForm(hydrationByDay[dayLogKey] || defaultHydrationLog);
  }, [dayLogKey, hydrationByDay]);

  useEffect(() => {
    if (!showStreakCelebration) return undefined;
    const timeout = setTimeout(() => setShowStreakCelebration(false), 3600);
    return () => clearTimeout(timeout);
  }, [showStreakCelebration]);

  const saveHydrationLog = () => {
    setHydrationByDay((current) => ({
      ...current,
      [dayLogKey]: {
        water: Math.max(0, Math.min(8, Number(hydrationForm.water || 0))),
      },
    }));
    setActiveClassicModal(null);
  };

  const quickActions = [
    ["hydration", "💧", "Hydration"],
    ["meal", "🍽️", "Log Meal"],
    ["sleep", "🌙", "Sleep Log"],
    ["streak", "🔥", "Streaks"],
  ];

  return (
    <div style={{ padding: "26px 20px 94px", maxWidth: 1180, margin: "0 auto", display: "grid", gap: 22 }}>
      <div className="card" style={{ ...plannerInspiredShell, position: "relative", overflow: "hidden", padding: 0 }}>
        <div style={{ position: "absolute", inset: 0, backgroundImage: `linear-gradient(180deg, rgba(255,255,255,0.16), rgba(248,245,238,0.82)), url('${highlightedMeal.image || "https://images.unsplash.com/photo-1512058564366-18510be2db19?auto=format&fit=crop&w=1200&q=80"}')`, backgroundSize: "cover", backgroundPosition: "center" }} />
        <div style={{ position: "absolute", inset: 0, background: "linear-gradient(180deg, rgba(255,255,255,0.22), rgba(255,255,255,0.9))" }} />
        <div style={{ position: "relative", zIndex: 1, padding: "30px 28px 24px", display: "grid", gap: 20 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 16 }}>
            <div style={{ maxWidth: 700 }}>
              <div style={{ display: "inline-flex", gap: 10, alignItems: "center", marginBottom: 16, fontSize: 13, color: "#3A5B7E", fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase" }}>
                <span style={{ width: 10, height: 10, borderRadius: "50%", background: "#5AA032" }} />
                Classic dashboard
              </div>
              <h1 style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 44, color: "#163F77", margin: 0, lineHeight: 1.05 }}>
                Your classic home, now with planner energy.
              </h1>
              <p style={{ marginTop: 16, maxWidth: 620, color: "#4A607A", fontSize: 17, lineHeight: 1.7 }}>
                A more intelligent daily view with progress tracking, hydration nudges, and nutrient highlights designed to feel fresh, easy, and motivating.
              </p>
            </div>
            <div style={{ minWidth: 260, display: "grid", gap: 12, ...plannerInspiredGlass, borderRadius: 24, padding: "18px 20px" }}>
              <div style={{ color: "#5A7E9F", fontWeight: 700, fontSize: 13, letterSpacing: "0.12em", textTransform: "uppercase" }}>This week</div>
              <div style={{ fontSize: 32, fontWeight: 800, color: "#1E3E64" }}>4 habits in motion</div>
              <div style={{ color: "#5D6D84" }}>Your classic view is now more dynamic, with clearer planner-inspired focus.</div>
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 14 }}>
            <div style={{ ...plannerInspiredGlass, borderRadius: 20, padding: "18px 20px" }}>
              <div style={{ color: "#426BA4", fontWeight: 800, fontSize: 15 }}>Daily alignment</div>
              <div style={{ marginTop: 10, fontSize: 28, fontWeight: 800, color: "#163F77" }}>{calorieAlignment}%</div>
              <div style={{ marginTop: 8, color: "#5C7087", fontSize: 14 }}>Of your calorie target captured in the classic plan.</div>
            </div>
            <div style={{ ...plannerInspiredGlass, borderRadius: 20, padding: "18px 20px" }}>
              <div style={{ color: "#4F7E32", fontWeight: 800, fontSize: 15 }}>Hydration boost</div>
              <div style={{ marginTop: 10, fontSize: 28, fontWeight: 800, color: "#2A6FB3" }}>{hydrationCount} / 8</div>
              <div style={{ marginTop: 8, color: "#5A6F85", fontSize: 14 }}>{hydrationMessage}</div>
            </div>
            <div style={{ ...plannerInspiredGlass, borderRadius: 20, padding: "18px 20px" }}>
              <div style={{ color: "#8E5B26", fontWeight: 800, fontSize: 15 }}>Energy cues</div>
              <div style={{ marginTop: 10, fontSize: 28, fontWeight: 800, color: "#E57A00" }}>{loggedCalories} kcal</div>
              <div style={{ marginTop: 8, color: "#666B7C", fontSize: 14 }}>Logged from today’s meals so far.</div>
            </div>
          </div>
        </div>
      </div>

      <RecommendedMeals
        home={home}
        loading={homeLoading}
        onSelectRecipe={(pick) => setOpenRecipeId(pick.recipe_id)}
      />

      {openRecipeId && (
        <RecipeDetail
          recipeId={openRecipeId}
          members={home?.members}
          onLogged={() => setHomeVersion((v) => v + 1)}
          onClose={() => setOpenRecipeId(null)}
          onCook={({ recipe, nutrition }) => {
            const kcal = nutrition?.nutrients?.find((n) => n.nutrient === "Energy")?.per_serving;
            setClassicCookMeal({ name: recipe.recipe_name, calories: kcal ? Math.round(kcal) : null });
            setOpenRecipeId(null);
            setActiveClassicModal("cook");
          }}
        />
      )}

      <div className="card" style={{ ...plannerInspiredShell, padding: 0, overflow: "hidden" }}>
        <div style={{ display: "grid", gridTemplateColumns: "220px minmax(0, 1fr) 330px", gap: 0, alignItems: "stretch" }}>
          <div style={{ padding: 22, borderRight: "1px solid #E4E8F0", display: "grid", placeItems: "center", background: "linear-gradient(180deg, #FFFDFC, #FBF7EF)" }}>
            <div style={{ display: "grid", justifyItems: "center", gap: 12 }}>
              <div style={{ position: "relative", width: 146, height: 146 }}>
                <svg viewBox="0 0 146 146" style={{ width: 146, height: 146, transform: "rotate(-90deg)" }}>
                  <circle cx="73" cy="73" r="58" fill="none" stroke="#F3DDAC" strokeWidth="8" />
                  <circle
                    cx="73"
                    cy="73"
                    r="58"
                    fill="none"
                    stroke="#F48A12"
                    strokeWidth="8"
                    strokeLinecap="round"
                    strokeDasharray={`${progressCircumference} ${progressCircumference}`}
                    strokeDashoffset={progressOffset}
                  />
                </svg>
                <div
                  style={{
                    position: "absolute",
                    inset: 18,
                    borderRadius: "50%",
                    background: "linear-gradient(180deg, #FFFDF8, #F6F0E3)",
                    border: "1px solid #F1E3BF",
                    boxShadow: "inset 0 1px 0 rgba(255,255,255,0.95)",
                    display: "grid",
                    placeItems: "center",
                    textAlign: "center",
                    padding: "0 12px",
                  }}
                >
                  <div>
                    <div style={{ fontSize: 20, fontWeight: 800, color: "#E57A00", lineHeight: 1 }}>{calorieAlignment}%</div>
                    <div
                      title={calorieGoalExplanation}
                      style={{
                        fontSize: 11,
                        color: "#6E7991",
                        marginTop: 7,
                        cursor: "help",
                        textDecoration: "underline dotted #B7C0CE 1px",
                        textUnderlineOffset: 3,
                        lineHeight: 1.25,
                      }}
                    >
                      of your calorie goal
                    </div>
                  </div>
                </div>
              </div>
              <div
                style={{
                  borderRadius: 999,
                  padding: "8px 14px",
                  background: "linear-gradient(180deg, #F2F7FF, #E3EEF9)",
                  border: "1px solid #C9D7EA",
                  color: "#44627F",
                  fontSize: 12,
                  fontWeight: 700,
                  boxShadow: "0 6px 14px rgba(92, 110, 145, 0.08)",
                }}
              >
                {loggedCalories} / {calorieGoal} kcal logged
              </div>
            </div>
          </div>

          <div style={{ padding: 18 }}>
            <div style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 18, color: "#163F77", marginBottom: 8 }}>Nutrients</div>
            <div style={{ color: "#72829B", fontSize: 12, marginBottom: 14 }}>Top 5 nutrient strengths from your selected planner day</div>
            {topNutrients.map((nutrient, index) => (
              <div key={nutrient.label} style={{ display: "grid", gridTemplateColumns: "132px 1fr 42px", gap: 12, alignItems: "center", marginBottom: 12 }}>
                <div style={{ color: "#273C64", fontWeight: 700, fontSize: 15 }}>{nutrient.label}</div>
                <div style={{ height: 12, background: "#E5E5E5", borderRadius: 999, overflow: "hidden", border: "1px solid #D9D9D9" }}>
                  <div style={{ width: `${nutrient.value}%`, height: "100%", background: nutrientColors[index % nutrientColors.length], borderRadius: 999 }} />
                </div>
                <div style={{ color: "#60718B", fontWeight: 700, fontSize: 13, textAlign: "right" }}>{nutrient.value}</div>
              </div>
            ))}
          </div>

          <div style={{ padding: 18, borderLeft: "1px solid #E4E8F0", background: "linear-gradient(180deg, #FFFEFB, #F8FBFF)" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
              <div style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 18, color: "#163F77" }}>Hydration</div>
              <button
                onClick={() => setActiveClassicModal("hydration")}
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: 8,
                  border: "1.5px solid #90CAF9",
                  background: "linear-gradient(180deg, #E3F2FF, #D3E7FB)",
                  color: "#1565C0",
                  fontWeight: 700,
                  fontSize: 18,
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  transition: "all 0.2s ease",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = "linear-gradient(180deg, #C3E9FF, #B3E5FC)";
                  e.currentTarget.style.boxShadow = "0 4px 12px rgba(21, 101, 192, 0.2)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = "linear-gradient(180deg, #E3F2FF, #D3E7FB)";
                  e.currentTarget.style.boxShadow = "none";
                }}
              >
                +
              </button>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 106px", gap: 14, alignItems: "start" }}>
              <div>
                <div style={{ color: "#204B82", fontWeight: 700, fontSize: 24, lineHeight: 1.1 }}>{hydrationCount} / 8 glasses</div>
                <div style={{ color: "#67809F", fontSize: 13, marginTop: 6, maxWidth: 210, lineHeight: 1.4 }}>{hydrationMessage}</div>
                <div style={{ color: "#8A9AB0", fontSize: 11.5, marginTop: 6 }}>
                  Water: {hydrationLog.water || 0} glasses
                </div>
              </div>
              <div style={{ padding: "12px 10px", borderRadius: 18, background: "linear-gradient(180deg, #F3FAFF, #E6F2FF)", border: "1px solid #CFE0F7", textAlign: "center", minWidth: 0, alignSelf: "start" }}>
                <div style={{ color: "#2A6FB3", fontWeight: 800, fontSize: 18 }}>{hydrationPercent}%</div>
                <div style={{ color: "#67809F", fontSize: 11, textTransform: "uppercase", letterSpacing: 0.8 }}>Complete</div>
              </div>
            </div>
            <div style={{ height: 10, borderRadius: 999, background: "#E8EEF7", marginTop: 16, overflow: "hidden", border: "1px solid #D7E1EE" }}>
              <div style={{ width: `${hydrationPercent}%`, height: "100%", background: "linear-gradient(90deg, #6EC5FF, #2A6FB3)", borderRadius: 999, transition: "width 0.35s ease" }} />
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(8, minmax(0, 1fr))", gap: 6, marginTop: 16 }}>
              {Array.from({ length: 8 }, (_, index) => {
                const filled = index < hydrationCount;
                return (
                  <div
                    key={index}
                    style={{
                      height: 56,
                      borderRadius: "8px 8px 12px 12px",
                      border: `1px solid ${filled ? "#AFC6DB" : "#D7DFEB"}`,
                      background: "linear-gradient(180deg, #FFFFFF 0%, #F3F6FA 100%)",
                      position: "relative",
                      overflow: "hidden",
                      clipPath: "polygon(18% 0%, 82% 0%, 94% 100%, 6% 100%)",
                      boxShadow: filled
                        ? "0 6px 12px rgba(109, 178, 235, 0.14), inset 0 1px 0 rgba(255,255,255,0.96)"
                        : "inset 0 1px 0 rgba(255,255,255,0.86)",
                    }}
                  >
                    <div
                      style={{
                        position: "absolute",
                        top: 2,
                        left: "50%",
                        transform: "translateX(-50%)",
                        width: "72%",
                        height: 5,
                        borderRadius: 999,
                        background: "#DDE5ED",
                        boxShadow: "0 1px 0 rgba(255,255,255,0.85)",
                      }}
                    />
                    <div
                      style={{
                        position: "absolute",
                        left: 5,
                        right: 5,
                        bottom: 5,
                        height: filled ? 32 : 5,
                        borderRadius: "5px 5px 8px 8px",
                        background: filled
                          ? "linear-gradient(180deg, #D8EEFF 0%, #8BCBFF 18%, #4BA5E8 62%, #2A6FB3 100%)"
                          : "#EEF3F8",
                        transition: "height 0.35s ease",
                      }}
                    />
                    <div
                      style={{
                        position: "absolute",
                        top: 7,
                        left: 8,
                        width: 6,
                        bottom: 8,
                        borderRadius: 999,
                        background: "rgba(255,255,255,0.42)",
                      }}
                    />
                    <div
                      style={{
                        position: "absolute",
                        left: 3,
                        right: 3,
                        bottom: 1,
                        height: 5,
                        borderRadius: "0 0 10px 10px",
                        background: "rgba(185, 197, 210, 0.55)",
                      }}
                    />
                  </div>
                );
              })}
            </div>
          </div>
        </div>
        <div style={{ borderTop: "1px solid #E4E8F0", padding: "12px 18px", background: "#FFF6E7", color: "#3E5C20", fontWeight: 700 }}>
          🌿 AI Tip: Add a fiber-rich snack for a balanced day.
        </div>
      </div>

      <div className="card" style={{ ...plannerInspiredShell, padding: 0, overflow: "hidden" }}>
        <div style={{ position: "relative", minHeight: 380, background: "linear-gradient(180deg, rgba(255,253,248,0.96), rgba(248,245,238,0.94))" }}>
          <div style={{ position: "absolute", inset: 0, background: "linear-gradient(180deg, rgba(255,255,255,0.18), rgba(245,241,232,0.74))" }} />
          <div style={{ position: "relative", zIndex: 1, padding: "28px 28px 24px", display: "grid", gridTemplateColumns: "minmax(0, 1.45fr) minmax(280px, 1fr)", gap: 18, alignItems: "start" }}>
            <div style={{ display: "grid", gap: 18 }}>
              <div style={{ color: C.accent, fontSize: 13, fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase" }}>Today’s Menu</div>
              <div style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 32, color: "#163F77", lineHeight: 1.05 }}>
                Stuffed pepper tray · 510 kcal · Prep: 25 min
              </div>
              <div style={{ color: "#4A607A", fontSize: 15, lineHeight: 1.75, maxWidth: 620 }}>
                A warm, satisfying dinner that keeps your energy steady with bright vegetables, punchy seasoning, and smart portion rhythm.
              </div>
              <div style={{ display: "grid", gap: 12, marginTop: 8 }}>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
                  <button
                    className="btn-primary"
                    style={{ background: "linear-gradient(180deg, #4EA0F1, #2A6FB3)", borderColor: "#2A6FB3", minWidth: 140 }}
                    onClick={() => {
                      setClassicCookMeal(highlightedMeal);
                      setActiveClassicModal("cook");
                    }}
                  >
                    Cook Now
                  </button>
                  <button className="btn-ghost" style={{ background: "#F9FBFF", borderColor: "#CCD5E5", color: "#24487B" }} onClick={() => setActiveClassicModal("meal")}>Log Meal</button>
                  <button
                    className="btn-ghost"
                    style={{ background: "#F9FBFF", borderColor: "#CCD5E5", color: "#24487B" }}
                    onClick={() => setStep("recipesClassic")}
                  >
                    View Alternatives ›
                  </button>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: 10 }}>
                  <button
                    type="button"
                    className="btn-ghost"
                    onClick={() => setActiveClassicModal("hydration")}
                    style={{ background: "#F9FBFF", borderColor: "#CCD5E5", color: "#24487B", minHeight: 44 }}
                  >
                    💧 Hydration
                  </button>
                  <button
                    type="button"
                    className="btn-ghost"
                    onClick={() => setActiveClassicModal("meal")}
                    style={{ background: "#F9FBFF", borderColor: "#CCD5E5", color: "#24487B", minHeight: 44 }}
                  >
                    🍽 Log Meal
                  </button>
                  <button
                    type="button"
                    className="btn-ghost"
                    onClick={() => setActiveClassicModal("sleep")}
                    style={{ background: "#F9FBFF", borderColor: "#CCD5E5", color: "#24487B", minHeight: 44 }}
                  >
                    🌙 Sleep Log
                  </button>
                  <button
                    type="button"
                    className="btn-ghost"
                    onClick={() => {
                      setShowStreakCelebration(true);
                      setActiveClassicModal(null);
                    }}
                    style={{ background: "#F9FBFF", borderColor: "#CCD5E5", color: "#24487B", minHeight: 44 }}
                  >
                    🔥 Streak
                  </button>
                </div>
              </div>
            </div>

            <div style={{ display: "grid", gap: 14 }}>
              <div style={{ ...plannerInspiredGlass, borderRadius: 22, padding: "22px 20px", minHeight: 160, background: "rgba(255,255,255,0.94)" }}>
                <div style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 17, color: "#163F77", marginBottom: 12 }}>Your Achievements</div>
                {achievements.map((achievement, index) => (
                  <div key={achievement} style={{ display: "flex", gap: 12, alignItems: "flex-start", marginBottom: index < achievements.length - 1 ? 12 : 0 }}>
                    <span style={{ fontSize: 20, lineHeight: 1.1 }}>{index === 0 ? "🔔" : index === 1 ? "🏅" : index === 2 ? "💧" : "🔥"}</span>
                    <span style={{ color: "#284468", fontWeight: 600, lineHeight: 1.5 }}>{achievement}</span>
                  </div>
                ))}
              </div>

              <div style={{ ...plannerInspiredGlass, borderRadius: 22, padding: "22px 20px", minHeight: 160, background: "rgba(255,255,255,0.94)" }}>
                <div style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 17, color: "#163F77", marginBottom: 12 }}>Smart Insights</div>
                <div style={{ display: "grid", gap: 10 }}>
                  {smartTips.map((tip, index) => (
                    <div key={tip} style={{ color: "#284468", fontWeight: 600, lineHeight: 1.55 }}>
                      {index === 0 ? "☀️" : index === 1 ? "🥦" : "🍋"} {tip}
                    </div>
                  ))}
                </div>
                <button className="btn-primary" style={{ marginTop: 14, width: "100%", background: "linear-gradient(180deg, #F49A1A, #E67900)", borderColor: "#E67900" }}>Get Tips ›</button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {showStreakCelebration && (
        <div style={{ position: "fixed", inset: 0, display: "grid", placeItems: "center", pointerEvents: "none", zIndex: 210 }}>
          <div style={{ position: "absolute", inset: 0, background: "rgba(255,255,255,0.22)" }} />
          <div
            className="card"
            style={{
              position: "relative",
              width: "min(640px, calc(100vw - 40px))",
              padding: "18px 22px 20px",
              border: "1px solid #E6DCC2",
              background: "linear-gradient(180deg, rgba(255,251,242,0.98), rgba(248,242,225,0.98))",
              boxShadow: "0 22px 60px rgba(196, 138, 38, 0.24)",
              textAlign: "center",
              overflow: "hidden",
            }}
          >
            <div style={{ position: "absolute", inset: 0, background: "radial-gradient(circle at center, rgba(255, 222, 143, 0.28), transparent 58%)" }} />
            {Array.from({ length: 22 }, (_, index) => (
              <span
                key={index}
                style={{
                  position: "absolute",
                  left: `${6 + (index * 4.1) % 92}%`,
                  top: `${10 + (index * 7.4) % 70}%`,
                  width: 10,
                  height: 10,
                  borderRadius: 2,
                  background: index % 4 === 0 ? "#F8B84A" : index % 4 === 1 ? "#7CC6D2" : index % 4 === 2 ? "#F7D86E" : "#8CC152",
                  transform: `rotate(${index * 13}deg)`,
                  opacity: 0.9,
                }}
              />
            ))}
            <div style={{ position: "relative", zIndex: 1 }}>
              <div style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 20, color: "#6B3A12" }}>🔥 Streak Unlocked!</div>
              <div style={{ color: "#2B4265", fontWeight: 600, marginTop: 14, fontSize: 15 }}>You've cooked 3 days in a row - keep the momentum going.</div>
              <div style={{ color: "#2B4265", marginTop: 16, fontSize: 16 }}>
                Healthy Habit Builder <span style={{ fontSize: 28, verticalAlign: "middle" }}>🧑‍🍳</span> Level 1 earned.
              </div>
            </div>
          </div>
        </div>
      )}

      {activeClassicModal && activeClassicModal !== "streak" && (
        <div
          onClick={() => setActiveClassicModal(null)}
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(34, 46, 66, 0.28)",
            display: "grid",
            placeItems: "center",
            padding: activeClassicModal === "cook" ? "84px 20px 24px" : 20,
            zIndex: 220,
          }}
        >
          <div
            className="card"
            onClick={(event) => event.stopPropagation()}
            style={{
              width: activeClassicModal === "cook" ? "min(920px, calc(100vw - 48px))" : "min(420px, calc(100vw - 36px))",
              maxHeight: activeClassicModal === "cook" ? "calc(100vh - 56px)" : "auto",
              marginTop: activeClassicModal === "cook" ? 12 : 0,
              border: "1px solid #E6DCC2",
              background: "linear-gradient(180deg, #FFFDF7, #FAF2E3)",
              boxShadow: "0 24px 60px rgba(72, 88, 120, 0.24)",
              overflow: "hidden",
              display: "grid",
              gridTemplateRows: "auto minmax(0, 1fr)",
            }}
          >
            <div
              style={{
                position: "relative",
                padding: activeClassicModal === "cook" ? "18px 76px 18px 28px" : "16px 56px 16px 20px",
                borderBottom: "1px solid #E6DCC2",
                textAlign: "center",
                fontFamily: "'Lora'",
                fontWeight: 700,
                fontSize: 22,
                color: "#3B3B3B",
                lineHeight: 1.2,
              }}
            >
              <button
                type="button"
                onClick={() => setActiveClassicModal(null)}
                aria-label="Close popup"
                style={{
                  position: "absolute",
                  top: "50%",
                  right: 16,
                  transform: "translateY(-50%)",
                  width: 34,
                  height: 34,
                  borderRadius: "50%",
                  border: "1px solid #D7DFEB",
                  background: "#FFFFFF",
                  color: "#72829B",
                  fontSize: 22,
                  lineHeight: 1,
                  cursor: "pointer",
                  display: "grid",
                  placeItems: "center",
                }}
              >
                ×
              </button>
              {activeClassicModal === "meal"
                ? "Log Your Meal"
                : activeClassicModal === "hydration"
                ? "Log Hydration"
                : activeClassicModal === "sleep"
                ? "Log Sleep"
                : "Cook This Meal"}
            </div>

            {activeClassicModal === "meal" && (
              <div style={{ padding: "14px 20px 18px", display: "grid", gap: 0 }}>
                {[
                  ["breakfast", "Breakfast"],
                  ["lunch", "Lunch"],
                  ["snack", "Snack"],
                  ["dinner", "Dinner"],
                ].map(([key, label], index, arr) => (
                  <label key={key} style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 0", borderBottom: index < arr.length - 1 ? "1px solid #E8D9C7" : "none", fontSize: 18, color: "#2F2F2F", marginBottom: 0 }}>
                    <input
                      type="checkbox"
                      checked={mealLog[key]}
                      onChange={() =>
                        setMealLogByDay((current) => ({
                          ...current,
                          [dayLogKey]: {
                            ...(current[dayLogKey] || defaultMealLog),
                            [key]: !mealLog[key],
                          },
                        }))
                      }
                      style={{ width: 22, height: 22 }}
                    />
                    {label}
                  </label>
                ))}
                <button className="btn-primary" style={{ width: 140, margin: "18px auto 0", background: "linear-gradient(180deg, #F49A1A, #E67900)", borderColor: "#E67900" }} onClick={() => setActiveClassicModal(null)}>Save</button>
              </div>
            )}

            {activeClassicModal === "hydration" && (
              <div style={{ padding: "22px 20px 20px", display: "grid", gap: 18 }}>
                {[
                  ["water", "💧 Water", "glasses"],
                ].map(([key, label, unit]) => (
                  <div key={key} style={{ display: "grid", gap: 10 }}>
                    <div style={{ fontSize: 16, fontWeight: 700, color: "#163F77" }}>{label}</div>
                    
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", justifyContent: "space-between" }}>
                      <button
                        onClick={() => setHydrationForm(current => ({ ...current, [key]: Math.max(0, Math.min(8, current[key] + 1)) }))}
                        style={{ flex: 1, minWidth: 56, padding: "10px 8px", background: "#E3F2FF", border: "1px solid #90CAF9", borderRadius: 8, color: "#1565C0", fontWeight: 700, fontSize: 14, cursor: "pointer", transition: "all 0.2s ease" }}
                      >
                        +1
                      </button>
                      <button
                        onClick={() => setHydrationForm(current => ({ ...current, [key]: Math.max(0, Math.min(8, current[key] + 2)) }))}
                        style={{ flex: 1, minWidth: 56, padding: "10px 8px", background: "#B3E5FC", border: "1px solid #81D4FA", borderRadius: 8, color: "#01579B", fontWeight: 700, fontSize: 14, cursor: "pointer" }}
                      >
                        +2
                      </button>
                      <button
                        onClick={() => setHydrationForm(current => ({ ...current, [key]: 0 }))}
                        style={{ flex: 1, minWidth: 56, padding: "10px 8px", background: "#FFEBEE", border: "1px solid #EF9A9A", borderRadius: 8, color: "#C62828", fontWeight: 700, fontSize: 14, cursor: "pointer" }}
                      >
                        Reset
                      </button>
                    </div>

                    <div style={{ display: "grid", gridTemplateColumns: "1fr auto auto", gap: 12, alignItems: "center", background: "#F9FCFF", border: "1px solid #CFE0F7", borderRadius: 12, padding: "12px 14px" }}>
                      <div style={{ color: "#60718B", fontSize: 14 }}>Current: <span style={{ fontWeight: 700, color: "#214A86", fontSize: 16 }}>{hydrationForm[key]} {unit}</span></div>
                      <button
                        onClick={() => setHydrationForm(current => ({ ...current, [key]: Math.max(0, current[key] - 1) }))}
                        style={{ width: 36, height: 36, borderRadius: "50%", border: "1px solid #BED4F1", background: "#FFFFFF", color: "#1565C0", fontWeight: 700, fontSize: 18, cursor: "pointer", display: "grid", placeItems: "center" }}
                      >
                        −
                      </button>
                      <button
                        onClick={() => setHydrationForm(current => ({ ...current, [key]: Math.max(0, Math.min(8, current[key] + 1)) }))}
                        style={{ width: 36, height: 36, borderRadius: "50%", border: "1px solid #90CAF9", background: "#E3F2FF", color: "#1565C0", fontWeight: 700, fontSize: 18, cursor: "pointer", display: "grid", placeItems: "center" }}
                      >
                        +
                      </button>
                    </div>
                  </div>
                ))}

                <div style={{ background: "#FFF4D9", border: "1px solid #F0D38A", borderRadius: 10, padding: "12px 14px", color: "#6B3A12", fontSize: 13, fontWeight: 600, lineHeight: 1.5, textAlign: "center" }}>
                  💡 Daily Goal: 8 glasses of water • {Math.max(0, 8 - (hydrationForm.water || 0))} more to go!
                </div>

                <div style={{ display: "flex", gap: 10 }}>
                  <button className="btn-ghost" style={{ flex: 1, background: "#F9FBFF", borderColor: "#CCD5E5", color: "#24487B" }} onClick={() => setActiveClassicModal(null)}>Cancel</button>
                  <button className="btn-primary" style={{ flex: 1, background: "linear-gradient(180deg, #4EA0F1, #2A6FB3)", borderColor: "#2A6FB3" }} onClick={saveHydrationLog}>Save Hydration</button>
                </div>
              </div>
            )}

            {activeClassicModal === "sleep" && (
              <div style={{ padding: "18px 20px 20px", display: "grid", gap: 18 }}>
                <div style={{ textAlign: "center", color: "#2F2F2F", fontSize: 18 }}>Slide to record hours slept:</div>
                <div style={{ justifySelf: "center", background: "#F9FCFF", border: "1px solid #D7DFEB", borderRadius: 10, padding: "8px 16px", fontSize: 22, fontWeight: 800, color: "#2A6FB3" }}>
                  {sleepHours.toFixed(1)} hrs
                </div>
                <div style={{ padding: "0 8px" }}>
                  <input
                    type="range"
                    min="0"
                    max="12"
                    step="0.5"
                    value={sleepHours}
                    onChange={(event) => setSleepHours(Number(event.target.value))}
                    style={{ width: "100%", accentColor: "#2A6FB3" }}
                  />
                  <div style={{ display: "flex", justifyContent: "space-between", color: "#5A6B86", fontSize: 12, marginTop: 6 }}>
                    {[0, 2, 4, 6, 8, 10, 12].map((hour) => (
                      <span key={hour}>{hour}</span>
                    ))}
                  </div>
                </div>
                <button className="btn-primary" style={{ width: 140, margin: "0 auto", background: "linear-gradient(180deg, #4EA0F1, #2A6FB3)", borderColor: "#2A6FB3" }} onClick={() => setActiveClassicModal(null)}>Save</button>
              </div>
            )}

            {activeClassicModal === "cook" && (
              <div style={{ padding: "22px 24px 24px", display: "grid", gap: 18, overflowY: "auto" }}>
                <div style={{ display: "grid", gridTemplateColumns: "minmax(280px, 0.92fr) minmax(0, 1.08fr)", gap: 20, alignItems: "start" }}>
                  <div style={{ display: "grid", gap: 14 }}>
                    <div style={{ height: 240, borderRadius: 18, backgroundImage: `linear-gradient(180deg, rgba(0,0,0,0.08), rgba(0,0,0,0.2)), url('${cookMeal?.image || "https://images.unsplash.com/photo-1512058564366-18510be2db19?auto=format&fit=crop&w=1400&q=80"}')`, backgroundSize: "cover", backgroundPosition: "center", boxShadow: "0 10px 26px rgba(72, 88, 120, 0.14)" }} />
                    <div className="card" style={{ padding: 16, border: "1px solid #D7DFEB", background: "linear-gradient(180deg, #FFFFFF, #F9FBFF)" }}>
                      <div style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 22, color: "#214A86" }}>{cookMeal?.name || "Today's Recipe"}</div>
                      <div style={{ marginTop: 8, color: "#60718B", fontSize: 15, lineHeight: 1.5 }}>
                        {cookMeal?.calories || 0} kcal • {cookMeal?.protein || 0}g protein • Guided cook flow for home cooking.
                      </div>
                    </div>
                    <div style={{ border: "1px solid #DBE8BF", background: "linear-gradient(180deg, #F8FDEB, #EEF8D3)", borderRadius: 12, padding: "14px 16px" }}>
                      <div style={{ color: "#4E7C1F", fontWeight: 800, marginBottom: 6 }}>Bioavailability Tip</div>
                      <div style={{ color: "#556B35", lineHeight: 1.55 }}>{getClassicBioavailabilityTip(cookMeal)}</div>
                    </div>
                  </div>

                  <div className="card" style={{ padding: 18, border: "1px solid #D7DFEB", background: "linear-gradient(180deg, #FFFFFF, #F9FBFF)" }}>
                    <div style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 20, color: "#163F77", marginBottom: 14 }}>Cooking Steps</div>
                    <div style={{ display: "grid", gap: 12 }}>
                      {getClassicCookSteps(cookMeal).map((step, index) => (
                        <div key={step} style={{ display: "grid", gridTemplateColumns: "34px 1fr", gap: 14, alignItems: "start", paddingBottom: 12, borderBottom: index < getClassicCookSteps(cookMeal).length - 1 ? "1px solid #E6EDF7" : "none" }}>
                          <div style={{ width: 34, height: 34, borderRadius: "50%", background: "#EAF2FC", border: "1px solid #BED4F1", color: "#214A86", display: "grid", placeItems: "center", fontWeight: 800, fontSize: 14 }}>
                            {index + 1}
                          </div>
                          <div style={{ color: "#334B6F", lineHeight: 1.6, paddingTop: 4 }}>{step}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                <div style={{ display: "flex", justifyContent: "center", gap: 12, flexWrap: "wrap", paddingTop: 2 }}>
                  <button className="btn-primary" style={{ minWidth: 150, background: "linear-gradient(180deg, #F49A1A, #E67900)", borderColor: "#E67900" }} onClick={() => {}}>
                    Open Full Cook Mode
                  </button>
                  <button className="btn-ghost" style={{ minWidth: 120, background: "#F9FBFF", borderColor: "#CCD5E5", color: "#24487B" }} onClick={() => setActiveClassicModal(null)}>
                    Close
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      <div style={{ position: "fixed", right: 18, bottom: 18, zIndex: 205, display: "grid", justifyItems: "end", gap: 10 }}>
        <div style={{ background: "#F7FBFF", border: "1px solid #C9D3E3", color: "#24487B", borderRadius: 16, padding: "8px 14px", boxShadow: "0 8px 18px rgba(72, 88, 120, 0.14)", fontWeight: 600, fontSize: 12.5 }}>
          {assistantMessages[assistantMessageIndex]}
        </div>
        <button
          type="button"
          onClick={() => setAssistantMessageIndex((current) => (current + 1) % assistantMessages.length)}
          style={{
            width: 84,
            height: 84,
            borderRadius: "50%",
            border: "4px solid #183E73",
            background: "radial-gradient(circle at 30% 30%, #315A8F, #183E73 70%)",
            boxShadow: "0 14px 28px rgba(24, 62, 115, 0.24)",
            cursor: "pointer",
            fontSize: 38,
          }}
        >
          🧑‍🍳
        </button>
      </div>
    </div>
  );
}
