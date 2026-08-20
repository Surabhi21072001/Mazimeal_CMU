import { useState, useEffect, useRef } from "react";
import {
  loadPlannerState,
  normalizePlannerState,
  savePlannerState,
} from "../../shared/services/planner/plannerStore";

// ─── DESIGN TOKENS ────────────────────────────────────────────────────────────────────
const C = {
  bg:         "#F5F1E8",
  surface:    "#FFFDF8",
  card:       "#FFFCF6",
  cardHover:  "#FFF8ED",
  border:     "#DDD2BF",
  borderFocus:"#2F6A4F",
  accent:     "#2F6A4F",
  accentDark: "#214A39",
  accentLight:"#E4F5E9",
  accentGlow: "rgba(47,106,79,0.14)",
  gold:       "#B7862D",
  goldLight:  "#FFF4D9",
  coral:      "#C55B4A",
  coralLight: "#FCE7E0",
  sky:        "#4C956C",
  skyLight:   "#E4F1E8",
  lavender:   "#7D6BA8",
  lavLight:   "#F0EAFB",
  navy:       "#163127",
  text:       "#163127",
  subtext:    "#5D665E",
  muted:      "#7B857D",
  dim:        "#A9B1A6",
  white:      "#FFFFFF",
};

// ─── MOCK DATA ────────────────────────────────────────────────────────────────
const CONDITIONS = ["Diabetes (Type 2)", "Iron Deficiency", "Celiac Disease", "Lactose Intolerance",
  "High Cholesterol", "Hypertension", "Pregnancy", "PCOS", "IBS", "None"];
const ALLERGIES = ["Shellfish", "Nuts", "Gluten", "Dairy", "Eggs", "Soy", "Fish", "None"];

const RECIPES = [
  {
    id: 1, name: "Iron-Boosted Lentil & Spinach Soup", time: "35 min", cal: 340, diff: "Easy",
    emoji: "🥣",
    synergies: ["Vitamin C + Iron ×3", "Turmeric + Black Pepper"],
    tags: ["High Iron", "Pregnancy-safe", "Anti-inflammatory"],
    nutrients: { Iron: 92, "Vitamin C": 78, Protein: 65, Fiber: 88 },
    tip: "Squeeze lemon just before serving — Vitamin C triples non-heme iron absorption.",
    steps: ["Sauté onion; let garlic rest 10 min before cooking to activate allicin", "Add lentils, turmeric + black pepper", "Finish with lemon juice to 3× iron absorption"],
    suitable: ["Iron Deficiency", "Pregnancy"],
    tagColors: ["coral","gold","accent"],
  },
  {
    id: 2, name: "Glycemic-Smart Chicken Rice Bowl", time: "30 min", cal: 420, diff: "Medium",
    emoji: "🍚",
    synergies: ["Resistant Starch", "Glycemic Retrogradation"],
    tags: ["Low GI", "Diabetic-Friendly", "High Protein"],
    nutrients: { Carbs: 45, Protein: 88, Fiber: 72, "Glycemic Impact": 38 },
    tip: "Cook rice, cool overnight — reheat to form resistant starch and lower GI by up to 50%.",
    steps: ["Cook rice, cool overnight (forms resistant starch)", "Reheat with colourful veggies", "Eat sequence: veggies → protein → rice last to blunt glucose spike by 73%"],
    suitable: ["Diabetes (Type 2)"],
    tagColors: ["sky","accent","gold"],
  },
  {
    id: 3, name: "Shellfish-Free Omega Salmon Salad", time: "20 min", cal: 380, diff: "Easy",
    emoji: "🥗",
    synergies: ["Fat-soluble Vitamins + Fats", "Quercetin + Resveratrol"],
    tags: ["Shellfish-Free", "Heart Health", "Anti-inflammatory"],
    nutrients: { "Omega-3": 95, "Vitamin D": 82, Antioxidants: 78, Protein: 91 },
    tip: "Fat-soluble vitamins A, D, E, K absorb up to 4× better paired with healthy dietary fats.",
    steps: ["Grill salmon with olive oil", "Layer with colourful bell peppers", "Dress with lemon-tahini (fat aids vitamin absorption)"],
    suitable: ["High Cholesterol"],
    tagColors: ["gold","accent","sky"],
  },
  {
    id: 4, name: "Pregnancy Power Buddha Bowl", time: "25 min", cal: 460, diff: "Easy",
    emoji: "🫙",
    synergies: ["Folate + B12", "Calcium + Vitamin D", "Iron + Vitamin C"],
    tags: ["Pregnancy-Safe", "High Folate", "Complete Protein"],
    nutrients: { Folate: 95, Calcium: 85, Iron: 78, Protein: 72 },
    tip: "Quinoa supplies all 9 essential amino acids — rare for plant proteins.",
    steps: ["Layer quinoa, edamame, roasted sweet potato", "Add nutritional yeast for B12", "Top with pumpkin seeds + lemon dressing"],
    suitable: ["Pregnancy", "Iron Deficiency"],
    tagColors: ["lavender","accent","gold"],
  },
];

const TAG_COLORS = {
  accent:   { bg: C.accentLight, color: C.accentDark, border: C.accent },
  gold:     { bg: C.goldLight,   color: C.gold,       border: "#F0B84A" },
  coral:    { bg: C.coralLight,  color: C.coral,      border: "#F08080" },
  sky:      { bg: C.skyLight,    color: C.sky,        border: "#60AFEE" },
  lavender: { bg: C.lavLight,    color: C.lavender,   border: "#B090E0" },
};

function getHeightParts(height) {
  const text = String(height || "").trim().toLowerCase();
  const feetMatch = text.match(/(\d+)\s*(?:ft|')/);
  const inchMatch = text.match(/(\d+)\s*(?:in|")/);
  return {
    feet: feetMatch?.[1] || "",
    inches: inchMatch?.[1] || "",
  };
}

function buildHeightValue(feet, inches) {
  const normalizedFeet = String(feet || "").trim();
  const normalizedInches = String(inches || "").trim();
  if (!normalizedFeet && !normalizedInches) return "";
  if (!normalizedFeet) return `${normalizedInches} in`;
  if (!normalizedInches) return `${normalizedFeet} ft`;
  return `${normalizedFeet} ft ${normalizedInches} in`;
}

function createInitialWeeklyPlannerState(anchorDate = new Date()) {
  const plannerAnchorDate = new Date(anchorDate);
  plannerAnchorDate.setHours(0, 0, 0, 0);
  const startOfWeek = new Date(plannerAnchorDate);
  startOfWeek.setDate(plannerAnchorDate.getDate() - plannerAnchorDate.getDay());
  const imageSet = {
    breakfast: "https://images.unsplash.com/photo-1517673400267-0251440c45dc?auto=format&fit=crop&w=1200&q=80",
    lunch: "https://images.unsplash.com/photo-1547592180-85f173990554?auto=format&fit=crop&w=1200&q=80",
    dinner: "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?auto=format&fit=crop&w=1200&q=80",
    snack: "https://images.unsplash.com/photo-1505253758473-96b7015fcd40?auto=format&fit=crop&w=1200&q=80",
  };
  const baseSlots = [["breakfast", "Breakfast"], ["lunch", "Lunch"], ["dinner", "Dinner"], ["snack", "Snack"]];
  const createMealEntry = (slotType, template, labelOverride) => ({
    ...template,
    slotType,
    label: labelOverride || (baseSlots.find(([slot]) => slot === slotType)?.[1] || "Meal"),
  });
  const calculateTotalCalories = (meals) => Object.values(meals).reduce((sum, meal) => sum + meal.calories, 0);
  const breakfastTemplates = [
    { name: "Berry oat bowl", calories: 350, protein: 12, image: imageSet.breakfast, tip: "Add seeds for extra fiber and better staying power.", nutrients: { Fiber: 82, Protein: 48, Antioxidants: 86 }, emoji: "🥣" },
    { name: "Avocado toast", calories: 340, protein: 14, image: imageSet.breakfast, tip: "Egg or yogurt on the side makes this more filling.", nutrients: { Fiber: 56, Protein: 54, Satiety: 88 }, emoji: "🍞" },
    { name: "Greek yogurt parfait", calories: 310, protein: 18, image: imageSet.breakfast, tip: "Lower-sugar granola keeps the protein-to-sugar balance stronger.", nutrients: { Protein: 72, Calcium: 70, Probiotics: 82 }, emoji: "🥛" },
    { name: "Green smoothie bowl", calories: 300, protein: 15, image: imageSet.breakfast, tip: "Use yogurt or protein milk to avoid a carb-only breakfast.", nutrients: { Hydration: 82, VitaminC: 90, Protein: 52 }, emoji: "🍓" },
    { name: "Chia pudding", calories: 280, protein: 11, image: imageSet.breakfast, tip: "Soak overnight for a smoother texture and easier digestion.", nutrients: { Fiber: 84, Omega3: 74, Calcium: 66 }, emoji: "🥄" },
    { name: "Protein waffles", calories: 360, protein: 17, image: imageSet.breakfast, tip: "Add yogurt and fruit to balance the plate.", nutrients: { Carbs: 70, Protein: 58, FamilyAppeal: 90 }, emoji: "🧇" },
    { name: "Fruit and nuts", calories: 240, protein: 9, image: imageSet.breakfast, tip: "Pair with milk or yogurt if you need more protein.", nutrients: { HealthyFats: 74, Fiber: 52, Energy: 60 }, emoji: "🍎" },
  ];
  const lunchTemplates = [
    { name: "Mediterranean chicken bowl", calories: 600, protein: 35, image: imageSet.lunch, tip: "Add extra greens for more fiber without much prep.", nutrients: { Protein: 84, Fiber: 64, Balance: 82 }, emoji: "🥗" },
    { name: "Protein wrap", calories: 540, protein: 32, image: imageSet.lunch, tip: "A bean or chickpea side can lift fiber quickly.", nutrients: { Protein: 74, Fiber: 56, Convenience: 86 }, emoji: "🌯" },
    { name: "Rice and veggie bowl", calories: 560, protein: 29, image: imageSet.lunch, tip: "Cool and reheat rice for a gentler glucose response.", nutrients: { Carbs: 68, Protein: 72, Fiber: 58 }, emoji: "🍚" },
    { name: "Lentil salad box", calories: 520, protein: 26, image: imageSet.lunch, tip: "Citrus dressing helps boost iron absorption.", nutrients: { Iron: 80, Fiber: 82, Protein: 58 }, emoji: "🥙" },
    { name: "Turkey sandwich plate", calories: 510, protein: 31, image: imageSet.lunch, tip: "Choose whole grain bread for better satiety.", nutrients: { Protein: 74, Fiber: 48, Satiety: 76 }, emoji: "🥪" },
    { name: "Paneer power bowl", calories: 580, protein: 28, image: imageSet.lunch, tip: "Pair paneer with fresh herbs and citrus for brighter flavor.", nutrients: { Protein: 68, Calcium: 72, Balance: 78 }, emoji: "🫓" },
    { name: "Chickpea crunch salad", calories: 500, protein: 24, image: imageSet.lunch, tip: "Roasted chickpeas keep the texture lively and satisfying.", nutrients: { Fiber: 80, Protein: 52, Energy: 70 }, emoji: "🥬" },
  ];
  const dinnerTemplates = [
    { name: "Salmon veggie skillet", calories: 520, protein: 30, image: imageSet.dinner, tip: "Pair with colorful veg to support antioxidant intake.", nutrients: { Protein: 82, Omega3: 90, VitaminD: 76 }, emoji: "🍲" },
    { name: "Tofu stir fry", calories: 500, protein: 27, image: imageSet.dinner, tip: "Use sesame and lime to add flavor without a heavy sauce.", nutrients: { Protein: 70, Fiber: 62, Balance: 80 }, emoji: "🥘" },
    { name: "Chicken tray bake", calories: 560, protein: 34, image: imageSet.dinner, tip: "Roast extra vegetables for tomorrow's lunch.", nutrients: { Protein: 84, Fiber: 54, FamilyAppeal: 88 }, emoji: "🍗" },
    { name: "Lentil pasta plate", calories: 540, protein: 25, image: "https://images.unsplash.com/photo-1622973536968-3ead9e780960?auto=format&fit=crop&w=1200&q=80", tip: "Add greens into the sauce for a fast nutrient boost.", nutrients: { Protein: 62, Fiber: 72, Iron: 58 }, emoji: "🍝" },
    { name: "Stuffed pepper tray", calories: 510, protein: 23, image: imageSet.dinner, tip: "Beans and quinoa make this filling without feeling heavy.", nutrients: { Fiber: 76, Protein: 56, Satiety: 78 }, emoji: "🫑" },
    { name: "Shrimp rice bowl", calories: 530, protein: 32, image: imageSet.dinner, tip: "Add cabbage slaw for crunch and extra fiber.", nutrients: { Protein: 82, Balance: 74, Energy: 72 }, emoji: "🍤" },
    { name: "Veggie taco night", calories: 550, protein: 22, image: imageSet.dinner, tip: "Add avocado and beans to round out the plate.", nutrients: { Fiber: 70, Protein: 50, FamilyAppeal: 90 }, emoji: "🌮" },
  ];
  const snackTemplates = [
    { name: "Apple and peanut butter", calories: 190, protein: 7, image: imageSet.snack, tip: "Fruit plus fat makes this snack more sustaining.", nutrients: { Fiber: 60, HealthyFats: 72, Energy: 58 }, emoji: "🍎" },
    { name: "Greek yogurt cup", calories: 140, protein: 15, image: imageSet.snack, tip: "Keep sugar lower so protein stays the star.", nutrients: { Protein: 78, Calcium: 64, Probiotics: 82 }, emoji: "🥛" },
    { name: "Trail mix", calories: 210, protein: 8, image: imageSet.snack, tip: "Pre-portion servings so the snack stays balanced.", nutrients: { HealthyFats: 78, Fiber: 42, Energy: 68 }, emoji: "🥜" },
    { name: "Hummus and carrots", calories: 160, protein: 6, image: imageSet.snack, tip: "A veggie snack helps spread produce through the day.", nutrients: { Fiber: 58, VitaminA: 84, Energy: 44 }, emoji: "🥕" },
    { name: "Cheese and crackers", calories: 200, protein: 10, image: imageSet.snack, tip: "Whole grain crackers hold the snack steadier than refined ones.", nutrients: { Protein: 48, Calcium: 62, Satiety: 60 }, emoji: "🧀" },
    { name: "Berry smoothie", calories: 220, protein: 14, image: imageSet.snack, tip: "Adding yogurt gives it a better protein profile.", nutrients: { Protein: 70, Hydration: 78, Antioxidants: 74 }, emoji: "🫐" },
    { name: "Banana oat bites", calories: 180, protein: 6, image: imageSet.snack, tip: "Batch prep these to avoid last-minute snack scrambles.", nutrients: { Energy: 58, Fiber: 46, Potassium: 72 }, emoji: "🍌" },
  ];

  const days = Array.from({ length: 7 }, (_, index) => {
    const date = new Date(startOfWeek);
    const meals = {
      breakfast: createMealEntry("breakfast", breakfastTemplates[index], "Breakfast"),
      lunch: createMealEntry("lunch", lunchTemplates[index], "Lunch"),
      dinner: createMealEntry("dinner", dinnerTemplates[index], "Dinner"),
      snack: createMealEntry("snack", snackTemplates[index], "Snack"),
    };
    date.setDate(startOfWeek.getDate() + index);
    return {
      key: date.toISOString(),
      shortDay: date.toLocaleDateString("en-US", { weekday: "short" }),
      longDay: date.toLocaleDateString("en-US", { weekday: "long" }),
      dayNumber: date.toLocaleDateString("en-US", { day: "numeric" }),
      monthLabel: date.toLocaleDateString("en-US", { month: "short" }),
      display: date.toLocaleDateString("en-US", { month: "short", day: "numeric" }),
      mealOrder: baseSlots.map(([slot]) => slot),
      totalCalories: calculateTotalCalories(meals),
      meals,
    };
  });

  return {
    anchorDate: plannerAnchorDate,
    days,
    selectedDayIndex: Math.min(Math.max(plannerAnchorDate.getDay(), 0), 6),
  };
}

// ─── SMALL COMPONENTS ─────────────────────────────────────────────────────────

function Logo({ size = 28, textColor = C.text }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <div style={{ width: size, height: size, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <svg width={size * 0.9} height={size * 0.9} viewBox="0 0 256 257" fill="none" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <linearGradient id="componentLogoGrad1" x1="-.828%" x2="57.636%" y1="7.652%" y2="78.411%">
              <stop offset="0%" stopColor="#41D1FF"/>
              <stop offset="100%" stopColor="#BD34FE"/>
            </linearGradient>
            <linearGradient id="componentLogoGrad2" x1="43.376%" x2="50.316%" y1="2.242%" y2="89.03%">
              <stop offset="0%" stopColor="#FFEA83"/>
              <stop offset="8.333%" stopColor="#FFDD35"/>
              <stop offset="100%" stopColor="#FFA800"/>
            </linearGradient>
          </defs>
          <path fill="url(#componentLogoGrad1)" d="M255.153 37.938L134.897 252.976c-2.483 4.44-8.862 4.466-11.382.048L.875 37.958c-2.746-4.814 1.371-10.646 6.827-9.67l120.385 21.517a6.537 6.537 0 0 0 2.322-.004l117.867-21.483c5.438-.991 9.574 4.796 6.877 9.62Z"/>
          <path fill="url(#componentLogoGrad2)" d="M185.432.063L96.44 17.501a3.268 3.268 0 0 0-2.634 3.014l-5.474 92.456a3.268 3.268 0 0 0 3.997 3.378l24.777-5.718c2.318-.535 4.413 1.507 3.936 3.838l-7.361 36.047c-.495 2.426 1.782 4.5 4.151 3.78l15.304-4.649c2.372-.72 4.652 1.36 4.15 3.788l-11.698 56.621c-.732 3.542 3.979 5.473 5.943 2.437l1.313-2.028l72.516-144.72c1.215-2.423-.88-5.186-3.54-4.672l-25.505 4.922c-2.396.462-4.435-1.77-3.759-4.114l16.646-57.705c.677-2.35-1.37-4.583-3.769-4.113Z"/>
        </svg>
      </div>
      <span style={{ fontFamily: "Plus Jakarta Sans", fontWeight: 800, fontSize: size * 0.85, color: textColor, letterSpacing: "-0.5px" }}>Mazimeal</span>
    </div>
  );
}

function SiteFooter({ compact = false, marginTop = 0 }) {
  const links = [
    { label: "Features", href: "/#features" },
    { label: "Pricing", href: "/#pricing" },
    { label: "Start Free", href: "/#pricing" },
    { label: "Contact", href: "mailto:hello@mazimeal.com" },
  ];

  return (
    <footer style={{ background: C.text, color: C.white, padding: compact ? "28px 24px" : "36px 32px", marginTop }}>
      <div style={{ maxWidth: 1200, margin: "0 auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 18, flexWrap: "wrap" }}>
          <Logo size={30} textColor={C.white} />
          <div style={{ display: "flex", gap: compact ? 14 : 18, flexWrap: "wrap", justifyContent: "center" }}>
            {links.map((link) => (
              <a
                key={link.label}
                href={link.href}
                style={{
                  color: "rgba(255, 255, 255, 0.68)",
                  textDecoration: "none",
                  fontSize: compact ? 13 : 14,
                  cursor: "pointer",
                }}
              >
                {link.label}
              </a>
            ))}
          </div>
          <p style={{ fontSize: 12, color: "rgba(255, 255, 255, 0.46)", margin: 0 }}>© 2026 Mazimeal</p>
        </div>
      </div>
    </footer>
  );
}

function CenteredPageShell({ children }) {
  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", background: C.bg }}>
      <main style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: "40px 20px" }}>
        {children}
      </main>
      <SiteFooter compact marginTop={40} />
    </div>
  );
}

function TopHeader({ user }) {
  const [showNotifications, setShowNotifications] = useState(false);
  const [showProfileMenu, setShowProfileMenu] = useState(false);
  const notifications = [
    { id: 1, icon: "📋", title: "Meal plan ready", message: "Your weekly meal plan for family is ready", time: "2 min ago", read: false },
    { id: 2, icon: "⚠️", title: "Allergen alert", message: "Dairy detected in today's lunch recommendation", time: "1 hour ago", read: false },
    { id: 3, icon: "📊", title: "Nutrition goal reached", message: "Your family hit 100% daily nutrients", time: "3 hours ago", read: true },
    { id: 4, icon: "👨‍👩‍👧", title: "Profile updated", message: "Noah's dietary preferences were updated", time: "1 day ago", read: true },
  ];

  // Close dropdowns when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (!event.target.closest('.notification-bell') && !event.target.closest('.profile-avatar')) {
        setShowNotifications(false);
        setShowProfileMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div className="glass-header" style={{ position: "fixed", top: 0, left: 0, right: 0, height: 64, background: C.white, borderBottom: `1px solid ${C.border}`, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 18px", zIndex: 100 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <div style={{ width: 40, height: 40, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <svg width="32" height="32" viewBox="0 0 256 257" fill="none" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <linearGradient id="logoGrad1" x1="-.828%" x2="57.636%" y1="7.652%" y2="78.411%">
                <stop offset="0%" stopColor="#41D1FF"/>
                <stop offset="100%" stopColor="#BD34FE"/>
              </linearGradient>
              <linearGradient id="logoGrad2" x1="43.376%" x2="50.316%" y1="2.242%" y2="89.03%">
                <stop offset="0%" stopColor="#FFEA83"/>
                <stop offset="8.333%" stopColor="#FFDD35"/>
                <stop offset="100%" stopColor="#FFA800"/>
              </linearGradient>
            </defs>
            <path fill="url(#logoGrad1)" d="M255.153 37.938L134.897 252.976c-2.483 4.44-8.862 4.466-11.382.048L.875 37.958c-2.746-4.814 1.371-10.646 6.827-9.67l120.385 21.517a6.537 6.537 0 0 0 2.322-.004l117.867-21.483c5.438-.991 9.574 4.796 6.877 9.62Z"/>
            <path fill="url(#logoGrad2)" d="M185.432.063L96.44 17.501a3.268 3.268 0 0 0-2.634 3.014l-5.474 92.456a3.268 3.268 0 0 0 3.997 3.378l24.777-5.718c2.318-.535 4.413 1.507 3.936 3.838l-7.361 36.047c-.495 2.426 1.782 4.5 4.151 3.78l15.304-4.649c2.372-.72 4.652 1.36 4.15 3.788l-11.698 56.621c-.732 3.542 3.979 5.473 5.943 2.437l1.313-2.028l72.516-144.72c1.215-2.423-.88-5.186-3.54-4.672l-25.505 4.922c-2.396.462-4.435-1.77-3.759-4.114l16.646-57.705c.677-2.35-1.37-4.583-3.769-4.113Z"/>
          </svg>
        </div>
        <div style={{ fontSize: 20, fontWeight: 700, color: C.text }}>Mazimeal</div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <input className="top-search" placeholder="Search recipes, meals..." style={{ width: 320, padding: "9px 14px", borderRadius: 20, border: `1px solid ${C.border}`, background: C.bg, fontSize: 14 }} />
        
        {/* NOTIFICATIONS BELL */}
        <div className="notification-bell" style={{ position: "relative" }}>
          <button onClick={() => setShowNotifications(!showNotifications)} style={{ background: "transparent", border: "none", fontSize: 20, cursor: "pointer", color: C.muted, position: "relative" }}>
            🔔
            {notifications.some(n => !n.read) && (
              <div style={{ position: "absolute", top: -2, right: -2, width: 8, height: 8, background: "#ef4444", borderRadius: "50%", border: `2px solid ${C.white}` }} />
            )}
          </button>
          
          {/* NOTIFICATIONS DROPDOWN */}
          {showNotifications && (
            <div style={{ position: "absolute", top: 56, right: 0, width: 380, background: C.white, borderRadius: 16, border: `1px solid ${C.border}`, boxShadow: "0 18px 44px rgba(0, 0, 0, 0.12)", zIndex: 200, overflow: "hidden" }}>
              <div style={{ padding: "16px 18px", borderBottom: `1px solid ${C.border}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <h3 style={{ fontSize: 16, fontWeight: 700, color: C.text, margin: 0 }}>Notifications</h3>
                <button onClick={() => setShowNotifications(false)} style={{ background: "transparent", border: "none", fontSize: 18, cursor: "pointer", color: C.muted }}>✕</button>
              </div>
              <div style={{ maxHeight: 400, overflowY: "auto" }}>
                {notifications.map(notif => (
                  <div key={notif.id} style={{ padding: "14px 18px", borderBottom: `1px solid ${C.border}`, display: "flex", gap: 12, background: !notif.read ? C.bg : "transparent", hover: { background: C.bg }, cursor: "pointer", transition: "background 0.2s" }} onMouseEnter={(e) => e.target.style.background = C.bg} onMouseLeave={(e) => e.target.style.background = !notif.read ? C.bg : "transparent"}>
                    <div style={{ fontSize: 24, minWidth: 32 }}>{notif.icon}</div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 14, fontWeight: 600, color: C.text, marginBottom: 2 }}>{notif.title}</div>
                      <div style={{ fontSize: 13, color: C.subtext, lineHeight: 1.4, marginBottom: 4 }}>{notif.message}</div>
                      <div style={{ fontSize: 11, color: C.muted }}>{notif.time}</div>
                    </div>
                    {!notif.read && (
                      <div style={{ width: 8, height: 8, background: C.accent, borderRadius: "50%", minWidth: 8, marginTop: 6 }} />
                    )}
                  </div>
                ))}
              </div>
              <div style={{ padding: "12px 18px", textAlign: "center", borderTop: `1px solid ${C.border}` }}>
                <a href="#" style={{ fontSize: 13, color: C.accent, textDecoration: "none", fontWeight: 600 }}>See all notifications</a>
              </div>
            </div>
          )}
        </div>

        <div className="profile-avatar" style={{ position: "relative" }}>
          <button 
            onClick={() => setShowProfileMenu(!showProfileMenu)} 
            style={{ background: "transparent", border: "none", cursor: "pointer", padding: 0 }}
          >
            <div style={{ width: 32, height: 32, background: C.accentLight, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, color: C.accent, fontSize: 16 }}>{user[0]}</div>
          </button>
          
          {/* PROFILE DROPDOWN */}
          {showProfileMenu && (
            <div style={{ position: "absolute", top: 48, right: 0, width: 220, background: C.white, borderRadius: 16, border: `1px solid ${C.border}`, boxShadow: "0 18px 44px rgba(0, 0, 0, 0.12)", zIndex: 200, overflow: "hidden" }}>
              <div style={{ padding: "16px 18px", borderBottom: `1px solid ${C.border}` }}>
                <div style={{ fontSize: 16, fontWeight: 700, color: C.text, marginBottom: 4 }}>{user}</div>
                <div style={{ fontSize: 13, color: C.subtext }}>Premium Member</div>
              </div>
              <div style={{ padding: "8px 0" }}>
                <button 
                  onClick={() => {
                    setShowProfileMenu(false);
                    // Add edit profile logic here
                    alert('Edit Profile clicked - you can implement navigation to profile page here');
                  }}
                  style={{ 
                    width: "100%", 
                    padding: "12px 18px", 
                    background: "transparent", 
                    border: "none", 
                    textAlign: "left", 
                    cursor: "pointer", 
                    fontSize: 14, 
                    color: C.text,
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    transition: "background 0.2s"
                  }}
                  onMouseEnter={(e) => e.target.style.background = C.bg}
                  onMouseLeave={(e) => e.target.style.background = "transparent"}
                >
                  <span>⚙️</span>
                  Edit Profile
                </button>
                <button 
                  onClick={() => {
                    setShowProfileMenu(false);
                    // Add settings logic here
                  }}
                  style={{ 
                    width: "100%", 
                    padding: "12px 18px", 
                    background: "transparent", 
                    border: "none", 
                    textAlign: "left", 
                    cursor: "pointer", 
                    fontSize: 14, 
                    color: C.text,
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    transition: "background 0.2s"
                  }}
                  onMouseEnter={(e) => e.target.style.background = C.bg}
                  onMouseLeave={(e) => e.target.style.background = "transparent"}
                >
                  <span>🔧</span>
                  Settings
                </button>
                <button 
                  onClick={() => {
                    setShowProfileMenu(false);
                    // Add logout logic here
                  }}
                  style={{ 
                    width: "100%", 
                    padding: "12px 18px", 
                    background: "transparent", 
                    border: "none", 
                    textAlign: "left", 
                    cursor: "pointer", 
                    fontSize: 14, 
                    color: C.coral,
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    transition: "background 0.2s"
                  }}
                  onMouseEnter={(e) => e.target.style.background = C.coralLight}
                  onMouseLeave={(e) => e.target.style.background = "transparent"}
                >
                  <span>🚪</span>
                  Sign Out
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function LeftSidebar({ step, setStep }) {
  const navItems = [
    { id: "homeClassic", label: "Home", icon: "🏠" },
    { id: "profile", label: "Profile", icon: "👤" },
    { id: "recipesClassic", label: "Recipes", icon: "🍽" },
    { id: "weeklyPlanner", label: "Weekly Planner", icon: "🗓️" },
    { id: "tracker", label: "Tracker", icon: "📊" },
    { id: "results", label: "Results", icon: "📈" },
  ];
  return (
    <div className="left-sidebar" style={{ width: 280, background: C.white, borderRight: `1px solid ${C.border}`, padding: "16px", position: "fixed", left: 0, top: 64, bottom: 0, overflowY: "auto", display: "none" }}>
      <div style={{ marginBottom: 24 }}>
        <h3 style={{ fontSize: 18, fontWeight: 600, color: C.text }}>Navigation</h3>
      </div>
      <div style={{ display: "grid", gap: 8 }}>
        {navItems.map(item => (
          <button key={item.id} onClick={() => setStep(item.id)} className={`nav-link ${step === item.id ? 'active' : ''}`}>
            <span>{item.icon}</span>
            {item.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function RightSidebar({ profiles, visible = false }) {
  if (!visible) return null;

  return (
    <div className="right-sidebar" style={{ width: 320, background: C.white, borderLeft: `1px solid ${C.border}`, padding: "16px", position: "fixed", right: 0, top: 64, bottom: 0, overflowY: "auto", display: "none" }}>
      <div style={{ marginBottom: 24 }}>
        <h3 style={{ fontSize: 18, fontWeight: 600, color: C.text }}>Family Members</h3>
      </div>
      <div style={{ display: "grid", gap: 12 }}>
        {profiles.map(p => (
          <div key={p.id} style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px", borderRadius: 8, background: C.bg }}>
            <div style={{ width: 40, height: 40, background: C.accentLight, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, color: C.accent, fontSize: 18 }}>{p.name[0]}</div>
            <div>
              <div style={{ fontWeight: 600, color: C.text }}>{p.name}</div>
              <div style={{ fontSize: 12, color: C.muted }}>{p.role}</div>
            </div>
          </div>
        ))}
      </div>
      <div style={{ marginTop: 24 }}>
        <h3 style={{ fontSize: 18, fontWeight: 600, color: C.text }}>Quick Stats</h3>
        <div style={{ display: "grid", gap: 8, marginTop: 12 }}>
          <div style={{ padding: "12px", background: C.bg, borderRadius: 8 }}>
            <div style={{ fontSize: 14, color: C.muted }}>Today's Meals</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: C.accent }}>4</div>
          </div>
          <div style={{ padding: "12px", background: C.bg, borderRadius: 8 }}>
            <div style={{ fontSize: 14, color: C.muted }}>Recipes Saved</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: C.accent }}>12</div>
          </div>
        </div>
      </div>
    </div>
  );
}

function NutrientBar({ label, value, color = C.accent }) {
  return (
    <div style={{ marginBottom: 9 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11.5, color: C.subtext, marginBottom: 4 }}>
        <span>{label}</span><span style={{ color, fontWeight: 600 }}>{value}%</span>
      </div>
      <div style={{ height: 5, background: C.bg, borderRadius: 3, overflow: "hidden", border: `1px solid ${C.border}` }}>
        <div style={{ height: "100%", width: `${value}%`, background: `linear-gradient(90deg, ${color}99, ${color})`, borderRadius: 3, transition: "width 1.2s ease" }} />
      </div>
    </div>
  );
}

function SynergyPill({ text }) {
  const cols = [C.accent, C.gold, C.sky, C.lavender, C.coral];
  const c = cols[text.length % cols.length];
  return (
    <span style={{ background: `${c}15`, border: `1px solid ${c}50`, color: c, borderRadius: 20, padding: "3px 10px", fontSize: 11, fontWeight: 600, display: "inline-block", margin: "2px 3px 2px 0" }}>⚡ {text}</span>
  );
}

function Tag({ label, colorKey = "accent" }) {
  const c = TAG_COLORS[colorKey] || TAG_COLORS.accent;
  return (
    <span style={{ background: c.bg, border: `1px solid ${c.border}`, color: c.color, borderRadius: 20, padding: "3px 10px", fontSize: 11, fontWeight: 500 }}>{label}</span>
  );
}

function StatCard({ icon, val, label, color = C.accent }) {
  return (
    <div className="card" style={{ padding: "16px 20px", textAlign: "center" }}>
      <div style={{ fontSize: 22, marginBottom: 4 }}>{icon}</div>
      <div style={{ fontWeight: 800, fontSize: 26, color, fontFamily: "'Lora'" }}>{val}</div>
      <div style={{ fontSize: 11, color: C.muted, marginTop: 2 }}>{label}</div>
    </div>
  );
}

const defaultProfileDraft = (role = "Adult") => ({
  name: "",
  age: "",
  sex: "Female",
  height: "",
  weight: "",
  activity: "Moderate",
  goal: "Maintain weight",
  allergies: "None",
  dislikes: "None",
  dietaryPattern: "None",
  preferences: "Chicken, Onion",
  cuisines: ["Mexican"],
  lifeStage: "None",
  pregnancyWeek: "",
  role,
  invited: false,
  permission: "Full profile access",
  inviteEmail: "",
});

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

function calculateDailyCalorieTarget(profile) {
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

function safeReadJson(storageKey, fallbackValue) {
  if (typeof window === "undefined") return fallbackValue;
  try {
    const rawValue = window.localStorage.getItem(storageKey);
    return rawValue ? JSON.parse(rawValue) : fallbackValue;
  } catch {
    return fallbackValue;
  }
}

function describeCalorieGoal(profile, calorieGoal) {
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

function formatNutrientLabel(label) {
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

// ═══════════════════════════════════════════════════════════════════════════════
// MODULE 1: LANDING
// ═══════════════════════════════════════════════════════════════════════════════
function LandingModule({ onTrial, onLogin }) {
  const [showPromoCodes, setShowPromoCodes] = useState(false);
  const [billingPeriod, setBillingPeriod] = useState('monthly');
  const [heroProgress, setHeroProgress] = useState(0);
  const heroRef = useRef(null);

  useEffect(() => {
    const handleScroll = () => {
      if (!heroRef.current) return;
      const rect = heroRef.current.getBoundingClientRect();
      const viewport = window.innerHeight || 1;
      const scrollY = window.scrollY || window.pageYOffset || 0;
      const heroTop = scrollY + rect.top;
      const start = heroTop;
      const end = heroTop + rect.height;
      const travel = Math.max(1, end - start);
      const raw = (scrollY - start) / travel;
      const clamped = Math.max(0, Math.min(1, raw));
      setHeroProgress(clamped);
    };
    handleScroll();
    window.addEventListener("scroll", handleScroll, { passive: true });
    window.addEventListener("resize", handleScroll);
    return () => {
      window.removeEventListener("scroll", handleScroll);
      window.removeEventListener("resize", handleScroll);
    };
  }, []);

  const floatTransform = `translate3d(${-heroProgress * 84}px, ${heroProgress * 176}px, 0) rotate(${heroProgress * 8 - 4}deg)`;
  const heroSequenceTitle = "Iron-smart lunch sequence";
  const heroSequenceDescription = "Mazimeal prioritizes iron-rich meals with vitamin C pairings to improve uptake during your busiest hours.";
  return (
    <div className="luxury-shell" style={{ minHeight: "100vh", display: "flex", flexDirection: "column", background: C.white }}>
      <a href="#main-content" className="skip-link">Skip to main content</a>
      {/* HEADER */}
      <header className="glass-header" style={{ position: "fixed", top: 0, left: 0, right: 0, height: 64, background: C.white, borderBottom: `1px solid ${C.border}`, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 32px", zIndex: 1000 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ width: 40, height: 40, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <svg width="32" height="32" viewBox="0 0 256 257" fill="none" xmlns="http://www.w3.org/2000/svg">
              <defs>
                <linearGradient id="landingLogoGrad1" x1="-.828%" x2="57.636%" y1="7.652%" y2="78.411%">
                  <stop offset="0%" stopColor="#41D1FF"/>
                  <stop offset="100%" stopColor="#BD34FE"/>
                </linearGradient>
                <linearGradient id="landingLogoGrad2" x1="43.376%" x2="50.316%" y1="2.242%" y2="89.03%">
                  <stop offset="0%" stopColor="#FFEA83"/>
                  <stop offset="8.333%" stopColor="#FFDD35"/>
                  <stop offset="100%" stopColor="#FFA800"/>
                </linearGradient>
              </defs>
              <path fill="url(#landingLogoGrad1)" d="M255.153 37.938L134.897 252.976c-2.483 4.44-8.862 4.466-11.382.048L.875 37.958c-2.746-4.814 1.371-10.646 6.827-9.67l120.385 21.517a6.537 6.537 0 0 0 2.322-.004l117.867-21.483c5.438-.991 9.574 4.796 6.877 9.62Z"/>
              <path fill="url(#landingLogoGrad2)" d="M185.432.063L96.44 17.501a3.268 3.268 0 0 0-2.634 3.014l-5.474 92.456a3.268 3.268 0 0 0 3.997 3.378l24.777-5.718c2.318-.535 4.413 1.507 3.936 3.838l-7.361 36.047c-.495 2.426 1.782 4.5 4.151 3.78l15.304-4.649c2.372-.72 4.652 1.36 4.15 3.788l-11.698 56.621c-.732 3.542 3.979 5.473 5.943 2.437l1.313-2.028l72.516-144.72c1.215-2.423-.88-5.186-3.54-4.672l-25.505 4.922c-2.396.462-4.435-1.77-3.759-4.114l16.646-57.705c.677-2.35-1.37-4.583-3.769-4.113Z"/>
            </svg>
          </div>
          <span style={{ fontSize: 22, fontWeight: 800, color: C.accent }}>Mazimeal</span>
        </div>
        <nav aria-label="Primary navigation" style={{ display: "flex", alignItems: "center", gap: 28 }}>
          <a href="#features" style={{ fontSize: 14, color: C.text, textDecoration: "none", fontWeight: 500, cursor: "pointer" }}>Features</a>
          <a href="#pricing" style={{ fontSize: 14, color: C.text, textDecoration: "none", fontWeight: 500, cursor: "pointer" }}>Pricing</a>
          <a
            href="#account-setup"
            style={{ fontSize: 14, color: C.text, textDecoration: "none", fontWeight: 500, cursor: "pointer" }}
            onClick={(e) => {
              e.preventDefault();
              onTrial();
            }}
          >
            Start Free
          </a>
          <button className="btn-ghost" style={{ padding: "8px 20px", fontSize: 14 }} onClick={onLogin}>Log In</button>
          <button className="btn-primary" style={{ padding: "8px 24px", fontSize: 14 }} onClick={onTrial}>Sign Up</button>
        </nav>
      </header>

      {/* MAIN CONTENT */}
      <main id="main-content" style={{ flex: 1, paddingTop: 64 }}>
        {/* HERO SECTION */}
        <section ref={heroRef} className="luxury-hero" style={{ padding: "110px 32px 96px" }}>
          <div style={{ maxWidth: 1240, margin: "0 auto" }}>
            <div className="luxury-hero-grid">
              <div>
                <div className="luxury-eyebrow">{heroSequenceTitle}</div>
                <h1 className="luxury-title" style={{ marginTop: 18, marginBottom: 22 }}>More calm, confidence and care in every family meal.</h1>
                <p className="luxury-copy">Mazimeal brings together allergy-aware planning, adaptive household profiles, and premium AI meal guidance so your kitchen runs with the same clarity as a concierge service.</p>
                <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginTop: 28 }}>
                  <button className="btn-primary" style={{ padding: "14px 32px", fontSize: 16, minWidth: 220 }} onClick={onTrial}>Get Started for Free</button>
                  <button className="btn-ghost" style={{ padding: "14px 32px", fontSize: 16, background: "rgba(255,255,255,0.9)" }} onClick={onLogin}>Explore the Experience</button>
                </div>
              </div>

              <div className="luxury-motion-stage">
                <svg className="luxury-route" viewBox="0 0 520 420" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                  <path d="M60 330C140 250 170 190 252 186C346 182 366 90 454 52" stroke="rgba(255,255,255,0.48)" strokeWidth="2.5" strokeDasharray="8 12" strokeLinecap="round" />
                  <circle cx="60" cy="330" r="6" fill="rgba(255,255,255,0.82)" />
                  <circle cx="454" cy="52" r="6" fill="rgba(255,255,255,0.82)" />
                </svg>

                <div className="luxury-float-card" style={{ transform: floatTransform }}>
                  <div className="luxury-float-image" />
                  <div className="luxury-float-content">
                    <div style={{ fontFamily: "'Fraunces', serif", fontSize: 26, lineHeight: 1.08, marginTop: 12, marginBottom: 8 }}>{heroSequenceTitle}</div>
                    <p style={{ color: "rgba(255,255,255,0.8)", lineHeight: 1.7, marginBottom: 14 }}>{heroSequenceDescription}</p>
                    <div className="luxury-stat-grid">
                      <div className="luxury-stat">
                        <div style={{ fontSize: 11, color: "rgba(255,255,255,0.72)", textTransform: "uppercase", letterSpacing: 1 }}>Profiles</div>
                        <div style={{ fontSize: 24, fontWeight: 800, color: C.white, marginTop: 8 }}>6+</div>
                      </div>
                      <div className="luxury-stat">
                        <div style={{ fontSize: 11, color: "rgba(255,255,255,0.72)", textTransform: "uppercase", letterSpacing: 1 }}>Planning Time</div>
                        <div style={{ fontSize: 24, fontWeight: 800, color: C.white, marginTop: 8 }}>5 min</div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* FEATURES SECTION */}
        <section id="features" className="luxury-section" style={{ background: C.white }}>
          <div style={{ maxWidth: 1200, margin: "0 auto" }}>
            <div style={{ marginBottom: 36 }}>
              <div style={{ fontSize: 12, color: C.accent, fontWeight: 700, letterSpacing: 1.4, textTransform: "uppercase", marginBottom: 12 }}>Why families love Mazimeal</div>
              <h2 className="luxury-heading" style={{ marginBottom: 14 }}>Everything you need for healthier family meals in one place</h2>
              <p className="luxury-subcopy">A more personal approach to meal planning means every recommendation feels tailored, safe, and genuinely useful across the whole household.</p>
            </div>

            <div className="luxury-services">
              <div className="luxury-service-card">
                <div style={{ fontSize: 12, color: C.accent, fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase", marginBottom: 12 }}>Flexible Services</div>
                <div className="luxury-list">
                  {[
                    ["01", "Multi-profile planning", "Create profiles for each family member with distinct allergies, goals, and preferences."],
                    ["02", "Smart nutrition engine", "Get meal guidance that balances nutrients, timing, and ingredient compatibility."],
                    ["03", "Live allergen safety", "Avoid unsafe recommendations with real-time household-aware checks."],
                    ["04", "Weekly meal flow", "Generate coordinated meals, shopping lists, and prep suggestions in minutes."],
                  ].map(([n, title, desc]) => (
                    <div key={title} className="luxury-list-item">
                      <div className="luxury-bullet">{n}</div>
                      <div>
                        <div style={{ fontWeight: 700, color: C.text, marginBottom: 4 }}>{title}</div>
                        <div style={{ color: C.subtext, lineHeight: 1.7 }}>{desc}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="luxury-service-card luxury-dark-card">
                <div style={{ fontSize: 12, color: "rgba(255,255,255,0.8)", fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase", marginBottom: 12 }}>Personal Nutrition Manager</div>
                <div style={{ fontFamily: "'Fraunces', serif", fontSize: 30, lineHeight: 1.1, marginBottom: 12 }}>A calmer, smarter way to run family meals.</div>
                <p style={{ color: "rgba(255,255,255,0.8)", lineHeight: 1.8, marginBottom: 18 }}>Mazimeal acts like a dedicated planning partner, helping you move from scattered decisions to one coherent weekly system.</p>
                <div className="luxury-stat-grid">
                  <div className="luxury-stat"><div style={{ fontSize: 11, color: "rgba(255,255,255,0.72)", textTransform: "uppercase" }}>Meal Matching</div><div style={{ color: C.white, fontWeight: 800, fontSize: 22, marginTop: 8 }}>Adaptive</div></div>
                  <div className="luxury-stat"><div style={{ fontSize: 11, color: "rgba(255,255,255,0.72)", textTransform: "uppercase" }}>Allergen Filter</div><div style={{ color: C.white, fontWeight: 800, fontSize: 22, marginTop: 8 }}>Live</div></div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="luxury-section" style={{ paddingTop: 0, background: C.white }}>
          <div style={{ maxWidth: 1200, margin: "0 auto" }}>
            <div style={{ fontSize: 12, color: C.accent, fontWeight: 700, letterSpacing: 1.4, textTransform: "uppercase", marginBottom: 12 }}>Popular Household Modes</div>
            <div className="luxury-destination-grid">
              {[
                ["Weeknight Rescue", "Fast, balanced dinners", "https://images.unsplash.com/photo-1547592180-85f173990554?auto=format&fit=crop&w=1400&q=80"],
                ["School Lunch Flow", "Portable, kid-friendly options", "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?auto=format&fit=crop&w=1400&q=80"],
                ["High-Protein Planning", "Meals aligned to active goals", "https://images.unsplash.com/photo-1490645935967-10de6ba17061?auto=format&fit=crop&w=1400&q=80"],
                ["Allergy-Safe Rotation", "Confident planning for everyone", "https://images.unsplash.com/photo-1482049016688-2d3e1b311543?auto=format&fit=crop&w=1400&q=80"],
              ].map(([title, subtitle, image]) => (
                <div key={title} className="luxury-destination" style={{ backgroundImage: `url("${image}")` }}>
                  <div className="luxury-destination-content">
                    <div style={{ fontSize: 22, fontWeight: 700, marginBottom: 6 }}>{title}</div>
                    <div style={{ color: "rgba(255,255,255,0.82)", fontSize: 14 }}>{subtitle}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* PRICING SECTION */}
        <section id="pricing" style={{ padding: "80px 32px", background: C.white }}>
          <div style={{ maxWidth: 1200, margin: "0 auto" }}>
            <h2 style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 42, color: C.text, textAlign: "center", marginBottom: 16 }}>Simple, transparent pricing</h2>
            <p style={{ fontSize: 17, color: C.subtext, textAlign: "center", marginBottom: 56, maxWidth: 600, margin: "0 auto 56px" }}>Choose the plan that works best for your family. Always flexible, always fair.</p>

            {/* PRICING TOGGLE */}
            <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 20, marginBottom: 48 }}>
              <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}>
                <input 
                  type="radio" 
                  name="billing" 
                  checked={billingPeriod === 'monthly'}
                  onChange={() => setBillingPeriod('monthly')}
                  style={{ cursor: "pointer" }} 
                />
                <span style={{ fontSize: 15, fontWeight: 600, color: C.text }}>Monthly</span>
              </label>
              <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}>
                <input 
                  type="radio" 
                  name="billing" 
                  checked={billingPeriod === 'yearly'}
                  onChange={() => setBillingPeriod('yearly')}
                  style={{ cursor: "pointer" }} 
                />
                <span style={{ fontSize: 15, fontWeight: 600, color: C.text }}>Yearly</span>
                <span style={{ background: C.accent, color: C.white, padding: "4px 10px", borderRadius: 20, fontSize: 12, fontWeight: 700 }}>Save 20%</span>
              </label>
            </div>

            {/* PRICING CARDS */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 24, marginBottom: 48 }}>
              {[
                {
                  name: "Starter",
                  desc: "For individuals",
                  monthlyPrice: 9.99,
                  yearlyPrice: 95.88,
                  features: [
                    "1 family profile",
                    "Basic meal plans",
                    "Recipe suggestions",
                    "Allergen tracking",
                    "Email support",
                  ],
                  highlighted: false,
                },
                {
                  name: "Family",
                  desc: "Most popular",
                  monthlyPrice: 24.99,
                  yearlyPrice: 239.88,
                  features: [
                    "Up to 6 family profiles",
                    "Personalized meal plans",
                    "AI recipe matching",
                    "Full allergen safety",
                    "Nutrition tracking",
                    "Weekly reports",
                    "Phone & email support",
                  ],
                  highlighted: true,
                },
                {
                  name: "Premium",
                  desc: "For health-conscious families",
                  monthlyPrice: 49.99,
                  yearlyPrice: 479.88,
                  features: [
                    "Unlimited profiles",
                    "Advanced meal planning",
                    "Food synergy analysis",
                    "Complete allergen mapping",
                    "Real-time nutrition tracking",
                    "Daily personalized reports",
                    "Priority support 24/7",
                    "Dietician consultation",
                  ],
                  highlighted: false,
                },
              ].map(plan => (
                <div
                  key={plan.name}
                  style={{
                    background: plan.highlighted ? C.accent : C.bg,
                    border: `2px solid ${plan.highlighted ? "transparent" : C.border}`,
                    borderRadius: 16,
                    padding: 32,
                    display: "flex",
                    flexDirection: "column",
                    gap: 20,
                    position: "relative",
                    transform: plan.highlighted ? "scale(1.05)" : "scale(1)",
                    transition: "transform 0.2s",
                  }}
                >
                  {plan.highlighted && (
                    <div style={{ position: "absolute", top: -12, left: "50%", transform: "translateX(-50%)", background: C.white, color: C.accent, padding: "4px 14px", borderRadius: 20, fontSize: 12, fontWeight: 700 }}>
                      RECOMMENDED
                    </div>
                  )}
                  <div>
                    <h3 style={{ fontSize: 20, fontWeight: 700, color: plan.highlighted ? C.white : C.text, marginBottom: 4 }}>
                      {plan.name}
                    </h3>
                    <p style={{ fontSize: 13, color: plan.highlighted ? "rgba(255,255,255,0.8)" : C.subtext }}>
                      {plan.desc}
                    </p>
                  </div>
                  <div style={{ borderTop: `1px solid ${plan.highlighted ? "rgba(255,255,255,0.2)" : C.border}`, paddingTop: 20 }}>
                    <div style={{ fontSize: 36, fontWeight: 800, color: plan.highlighted ? C.white : C.text, marginBottom: 4 }}>
                      ${billingPeriod === 'monthly' ? plan.monthlyPrice : (plan.yearlyPrice / 12).toFixed(2)}
                      <span style={{ fontSize: 16, fontWeight: 600, color: plan.highlighted ? "rgba(255,255,255,0.8)" : C.subtext }}>
                        /month
                      </span>
                    </div>
                    <p style={{ fontSize: 12, color: plan.highlighted ? "rgba(255,255,255,0.7)" : C.muted }}>
                      {billingPeriod === 'monthly' 
                        ? `or ${(plan.yearlyPrice / 12).toFixed(2)}/month billed yearly` 
                        : `billed $${plan.yearlyPrice} yearly (save $${((plan.monthlyPrice * 12) - plan.yearlyPrice).toFixed(2)})`}
                    </p>
                  </div>
                  <button
                    className="btn-primary"
                    style={{
                      width: "100%",
                      padding: "12px",
                      fontSize: 15,
                      fontWeight: 700,
                      background: plan.highlighted ? C.white : C.accent,
                      color: plan.highlighted ? C.accent : C.white,
                      border: "none",
                      borderRadius: 10,
                      cursor: "pointer",
                    }}
                  >
                    Get Started
                  </button>
                  <ul style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                    {plan.features.map(feature => (
                      <li
                        key={feature}
                        style={{
                          fontSize: 14,
                          color: plan.highlighted ? "rgba(255,255,255,0.9)" : C.text,
                          display: "flex",
                          alignItems: "center",
                          gap: 10,
                        }}
                      >
                        <span style={{ fontSize: 18 }}>✓</span>
                        {feature}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>

            {/* PROMO CODES SECTION */}
            <div style={{ background: C.bg, borderRadius: 16, padding: 32, border: `1px solid ${C.border}` }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 12, marginBottom: 12 }}>
                <h3 style={{ fontSize: 20, fontWeight: 700, color: C.text }}>💰 Special Promo Codes</h3>
                <button
                  onClick={() => setShowPromoCodes(!showPromoCodes)}
                  style={{
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    fontSize: 16,
                    color: C.accent,
                    fontWeight: 600,
                    padding: "4px 8px",
                    borderRadius: 6,
                    transition: "background 0.2s",
                  }}
                  onMouseOver={(e) => e.target.style.background = C.bg}
                  onMouseOut={(e) => e.target.style.background = "none"}
                >
                  {showPromoCodes ? "Hide" : "Show"} Codes
                </button>
              </div>
              {showPromoCodes && (
                <>
                  <p style={{ fontSize: 15, color: C.subtext, marginBottom: 24, textAlign: "center" }}>Get extra savings with our exclusive promo codes</p>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 16 }}>
                    {[
                      { code: "FAMILY20", discount: "20% off", desc: "For new families", color: "#10B981" },
                      { code: "YEARLY25", discount: "25% off", desc: "Yearly plans", color: "#3B82F6" },
                      { code: "HEALTH15", discount: "15% off", desc: "Health professionals", color: "#8B5CF6" },
                      { code: "FRIEND10", discount: "10% off", desc: "Refer a friend", color: "#F59E0B" },
                    ].map(promo => (
                      <div
                        key={promo.code}
                        style={{
                          background: C.white,
                          border: `2px solid ${promo.color}`,
                          borderRadius: 12,
                          padding: 18,
                          textAlign: "center",
                          display: "flex",
                          flexDirection: "column",
                          gap: 10,
                        }}
                      >
                        <div style={{ fontSize: 18, fontWeight: 800, color: promo.color }}>
                          {promo.discount}
                        </div>
                        <div
                          style={{
                            fontSize: 14,
                            fontFamily: "monospace",
                            fontWeight: 700,
                            color: C.text,
                            background: C.bg,
                            padding: "8px 12px",
                            borderRadius: 8,
                            letterSpacing: 1,
                          }}
                        >
                          {promo.code}
                        </div>
                        <p style={{ fontSize: 12, color: C.muted }}>{promo.desc}</p>
                      </div>
                    ))}
                  </div>
                  <p style={{ fontSize: 12, color: C.muted, textAlign: "center", marginTop: 20 }}>
                    * Promo codes cannot be combined. Valid for new subscriptions only.
                  </p>
                </>
              )}
            </div>
          </div>
        </section>

        {/* CTA SECTION */}
        <section style={{ padding: "80px 32px", background: `linear-gradient(135deg, ${C.accent} 0%, #006640 100%)` }}>
          <div style={{ maxWidth: 700, margin: "0 auto", textAlign: "center" }}>
            <h2 style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 44, color: C.white, marginBottom: 18 }}>Ready to transform your family's nutrition?</h2>
            <p style={{ fontSize: 18, color: "rgba(255, 255, 255, 0.9)", lineHeight: 1.6, marginBottom: 32 }}>Start your 14-day free trial. No credit card required.</p>
            <button className="btn-primary" style={{ padding: "14px 32px", fontSize: 16, background: C.white, color: C.accent, fontWeight: 700, minWidth: 240 }} onClick={onTrial}>Get Started Free</button>
          </div>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MODULE 2: LOGIN
// ═══════════════════════════════════════════════════════════════════════════════
function LoginModule({ onLogin, initialTab = "login", onBack, onNavigateToSection }) {
  const [tab, setTab] = useState(initialTab);
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [name, setName] = useState("");
  const [username, setUsername] = useState("");
  const [captcha, setCaptcha] = useState(false);

  const handleNavClick = (section) => {
    if (onNavigateToSection) {
      onNavigateToSection(section);
    } else if (onBack) {
      onBack();
    }
  };
  const derivedName = name.trim() || (email.includes("@") ? email.split("@")[0] : "Mazimeal User");

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", background: C.bg }}>
      <header className="glass-header" style={{ position: "fixed", top: 0, left: 0, right: 0, height: 64, background: C.white, borderBottom: `1px solid ${C.border}`, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 32px", zIndex: 1000 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {onBack && (
            <button onClick={onBack} style={{ background: "transparent", border: "none", fontSize: 20, cursor: "pointer", color: C.text, marginRight: 8 }}>←</button>
          )}
          <div style={{ width: 40, height: 40, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <svg width="32" height="32" viewBox="0 0 256 257" fill="none" xmlns="http://www.w3.org/2000/svg">
              <defs>
                <linearGradient id="loginLogoGrad1" x1="-.828%" x2="57.636%" y1="7.652%" y2="78.411%">
                  <stop offset="0%" stopColor="#41D1FF"/>
                  <stop offset="100%" stopColor="#BD34FE"/>
                </linearGradient>
                <linearGradient id="loginLogoGrad2" x1="43.376%" x2="50.316%" y1="2.242%" y2="89.03%">
                  <stop offset="0%" stopColor="#FFEA83"/>
                  <stop offset="8.333%" stopColor="#FFDD35"/>
                  <stop offset="100%" stopColor="#FFA800"/>
                </linearGradient>
              </defs>
              <path fill="url(#loginLogoGrad1)" d="M255.153 37.938L134.897 252.976c-2.483 4.44-8.862 4.466-11.382.048L.875 37.958c-2.746-4.814 1.371-10.646 6.827-9.67l120.385 21.517a6.537 6.537 0 0 0 2.322-.004l117.867-21.483c5.438-.991 9.574 4.796 6.877 9.62Z"/>
              <path fill="url(#loginLogoGrad2)" d="M185.432.063L96.44 17.501a3.268 3.268 0 0 0-2.634 3.014l-5.474 92.456a3.268 3.268 0 0 0 3.997 3.378l24.777-5.718c2.318-.535 4.413 1.507 3.936 3.838l-7.361 36.047c-.495 2.426 1.782 4.5 4.151 3.78l15.304-4.649c2.372-.72 4.652 1.36 4.15 3.788l-11.698 56.621c-.732 3.542 3.979 5.473 5.943 2.437l1.313-2.028l72.516-144.72c1.215-2.423-.88-5.186-3.54-4.672l-25.505 4.922c-2.396.462-4.435-1.77-3.759-4.114l16.646-57.705c.677-2.35-1.37-4.583-3.769-4.113Z"/>
            </svg>
          </div>
          <span style={{ fontSize: 22, fontWeight: 800, color: C.accent }}>Mazimeal</span>
        </div>
        <nav className="marketing-nav" style={{ display: "flex", alignItems: "center", gap: 20 }}>
          <button onClick={() => handleNavClick('features')} style={{ fontSize: 14, color: C.text, textDecoration: "none", fontWeight: 500, cursor: "pointer", background: "transparent", border: "none" }}>Features</button>
          <button onClick={() => handleNavClick('how-it-works')} style={{ fontSize: 14, color: C.text, textDecoration: "none", fontWeight: 500, cursor: "pointer", background: "transparent", border: "none" }}>How it Works</button>
          <button onClick={() => handleNavClick('pricing')} style={{ fontSize: 14, color: C.text, textDecoration: "none", fontWeight: 500, cursor: "pointer", background: "transparent", border: "none" }}>Pricing</button>
        </nav>
      </header>

      <main style={{ flex: 1, paddingTop: 64, display: "flex", alignItems: "center", justifyContent: "center", paddingBottom: 28 }}>
        <div className="card fade-up" style={{ width: "100%", maxWidth: 1140, margin: "28px 20px 0", padding: 0, overflow: "hidden" }}>
          <div className="login-grid" style={{ minHeight: 640, gap: 0 }}>
            <div
              style={{
                position: "relative",
                padding: "44px 34px",
                display: "grid",
                alignContent: "space-between",
                backgroundImage:
                  "linear-gradient(125deg, rgba(44,82,63,0.42), rgba(91,133,109,0.24)), url('https://images.unsplash.com/photo-1490645935967-10de6ba17061?auto=format&fit=crop&w=1800&q=80')",
                backgroundSize: "cover",
                backgroundPosition: "center",
              }}
            >
              <div style={{ display: "grid", gap: 18, position: "relative", zIndex: 1 }}>
                <div style={{ fontSize: 12, color: "rgba(255,255,255,0.86)", fontWeight: 700, letterSpacing: 1.4, textTransform: "uppercase" }}>
                  Smart Family Nutrition
                </div>
                <h1 style={{ fontFamily: "'Fraunces', serif", fontWeight: 700, fontSize: 42, lineHeight: 1.05, color: C.white, margin: 0 }}>
                  Your kitchen command center, now one login away.
                </h1>
                <p style={{ fontSize: 15, color: "rgba(255,255,255,0.88)", lineHeight: 1.72, maxWidth: 440, margin: 0 }}>
                  Coordinate household goals, track nutrition patterns, and activate recipe intelligence designed for real family routines.
                </p>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                {[
                  ["Realtime planning", "Adaptive weekly meal flow", "linear-gradient(180deg, rgba(125, 190, 117, 0.36), rgba(255,255,255,0.12))", "rgba(197, 241, 190, 0.48)"],
                  ["Allergen safety", "Household-aware protections", "linear-gradient(180deg, rgba(255, 196, 107, 0.34), rgba(255,255,255,0.12))", "rgba(255, 223, 162, 0.46)"],
                  ["Profile routing", "Personalized recommendations", "linear-gradient(180deg, rgba(120, 182, 255, 0.34), rgba(255,255,255,0.12))", "rgba(190, 221, 255, 0.46)"],
                  ["Nutrition insights", "Progress you can trust", "linear-gradient(180deg, rgba(191, 150, 255, 0.32), rgba(255,255,255,0.12))", "rgba(219, 198, 255, 0.44)"],
                ].map(([title, subtitle, cardBackground, borderColor]) => (
                  <button
                    key={title}
                    type="button"
                    aria-label={`${title}: ${subtitle}`}
                    role="button"
                    tabIndex={0}
                    style={{
                      background: cardBackground,
                      border: `1.5px solid ${borderColor}`,
                      borderRadius: 16,
                      padding: "20px 18px",
                      boxShadow: "0 8px 24px rgba(0,0,0,0.12), inset 0 1px 0 rgba(255,255,255,0.4)",
                      backdropFilter: "blur(8px)",
                      cursor: "pointer",
                      transition: "all 0.25s ease",
                      textAlign: "left",
                      outline: "none",
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.transform = "translateY(-4px)";
                      e.currentTarget.style.boxShadow = "0 12px 32px rgba(0,0,0,0.18), inset 0 1px 0 rgba(255,255,255,0.4)";
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.transform = "translateY(0)";
                      e.currentTarget.style.boxShadow = "0 8px 24px rgba(0,0,0,0.12), inset 0 1px 0 rgba(255,255,255,0.4)";
                    }}
                    onFocus={(e) => {
                      e.currentTarget.style.outline = "2px solid rgba(255,255,255,0.8)";
                      e.currentTarget.style.outlineOffset = "2px";
                    }}
                    onBlur={(e) => {
                      e.currentTarget.style.outline = "none";
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        e.currentTarget.click();
                      }
                    }}
                  >
                    <div style={{ fontWeight: 800, color: C.white, fontSize: 16, lineHeight: 1.3 }}>{title}</div>
                    <div style={{ fontSize: 14, color: "rgba(255,255,255,0.95)", marginTop: 8, fontWeight: 500 }}>{subtitle}</div>
                  </button>
                ))}
              </div>
            </div>

            <div
              style={{
                padding: "38px 32px",
                display: "grid",
                alignContent: "center",
                position: "relative",
                backgroundImage:
                  "linear-gradient(150deg, rgba(255,252,246,0.92), rgba(247,241,228,0.86)), url('https://images.unsplash.com/photo-1466637574441-749b8f19452f?auto=format&fit=crop&w=1400&q=80')",
                backgroundSize: "cover",
                backgroundPosition: "center",
              }}
            >
              <div
                aria-hidden="true"
                style={{
                  position: "absolute",
                  inset: 0,
                  pointerEvents: "none",
                  background:
                    "radial-gradient(circle at 18% 22%, rgba(248,210,142,0.26), transparent 42%), radial-gradient(circle at 82% 78%, rgba(47,106,79,0.12), transparent 44%)",
                }}
              />
              <div style={{ display: "grid", gap: 18, position: "relative", zIndex: 1 }}>
                <div>
                  <div style={{ fontSize: 12, color: C.accent, fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase" }}>
                    Secure Access
                  </div>
                  <h2 className="hero-title" style={{ fontSize: 34, color: C.text, marginTop: 8 }}>
                    {tab === "login" ? "Welcome back to Mazimeal" : "Create your Mazimeal account"}
                  </h2>
                  <p style={{ color: C.subtext, lineHeight: 1.7, marginTop: 8 }}>
                    {tab === "login"
                      ? "Sign in to continue managing your family nutrition hub with live profile insights."
                      : "Use the same account setup details to start your personalized meal intelligence workspace."}
                  </p>
                </div>

                <div style={{ display: "flex", background: C.bg, borderRadius: 11, padding: 4, border: `1px solid ${C.border}` }}>
                  {["login", "signup"].map((t) => (
                    <button
                      key={t}
                      onClick={() => setTab(t)}
                      style={{
                        flex: 1,
                        border: "none",
                        borderRadius: 8,
                        padding: "9px 10px",
                        background: tab === t ? C.white : "transparent",
                        color: tab === t ? C.accent : C.muted,
                        fontWeight: tab === t ? 700 : 500,
                        fontSize: 13.5,
                        cursor: "pointer",
                        boxShadow: tab === t ? "0 2px 8px rgba(20,45,31,0.12)" : "none",
                      }}
                    >
                      {t === "login" ? "Log In" : "Sign Up"}
                    </button>
                  ))}
                </div>

                <div style={{ display: "grid", gap: 14 }}>
                  <div>
                    <label>{tab === "signup" ? "Full Name" : "Display Name"}</label>
                    <input placeholder="e.g. Maya Johnson" value={name} onChange={(e) => setName(e.target.value)} />
                  </div>
                  <div>
                    <label>Email Address</label>
                    <input type="email" placeholder="you@family.com" value={email} onChange={(e) => setEmail(e.target.value)} />
                  </div>
                  {tab === "signup" && (
                    <div>
                      <label>Username</label>
                      <input placeholder="mazimeal.user" value={username} onChange={(e) => setUsername(e.target.value)} />
                    </div>
                  )}
                  <div>
                    <label>Password</label>
                    <input type="password" placeholder="••••••••" value={pw} onChange={(e) => setPw(e.target.value)} />
                  </div>
                  {tab === "signup" && (
                    <div className="captcha-mock">
                      <label htmlFor="login-captcha" className="captcha-main">
                        <input
                          id="login-captcha"
                          type="checkbox"
                          className="captcha-input"
                          checked={captcha}
                          onChange={(e) => setCaptcha(e.target.checked)}
                        />
                        <span className={`captcha-box ${captcha ? "checked" : ""}`} aria-hidden="true">
                          {captcha ? "✓" : ""}
                        </span>
                        <span className="captcha-label">I'm not a robot</span>
                      </label>
                      <div className="captcha-brand" aria-hidden="true">
                        <div className="captcha-logo">
                          <svg width="30" height="30" viewBox="0 0 30 30" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <circle cx="15" cy="15" r="13" stroke="#DADCE0" strokeWidth="2" />
                            <path d="M23 15a8 8 0 1 1-2.1-5.4" stroke="#1A73E8" strokeWidth="2.6" strokeLinecap="round" />
                            <path d="M22.2 9.4l1.8 4.7-4.9-.7" fill="#1A73E8" />
                          </svg>
                        </div>
                        <div className="captcha-brand-text">reCAPTCHA</div>
                        <div className="captcha-meta">Privacy - Terms</div>
                      </div>
                    </div>
                  )}
                  <button className="btn-primary" style={{ width: "100%", padding: "13px", fontSize: 15, marginTop: 6 }} onClick={() => onLogin(derivedName)}>
                    {tab === "login" ? "Enter Nutrition Hub →" : "Create Access & Continue →"}
                  </button>
                </div>

                <div style={{ display: "flex", justifyContent: "space-between", gap: 10, color: C.muted, fontSize: 12 }}>
                  <span>Protected account flow</span>
                  <span>Demo-ready access</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>

      <SiteFooter compact />
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MODULE 2: ONBOARDING FLOW
// ═══════════════════════════════════════════════════════════════════════════════
function CreateAccountModule({ onNext, onBack }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [pw, setPw] = useState("");
  const [captcha, setCaptcha] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [submitSuccess, setSubmitSuccess] = useState("");

  const handleCreateAccount = async () => {
    setSubmitError("");
    setSubmitSuccess("");

    if (!name.trim() || !email.trim() || !username.trim() || !pw.trim()) {
      setSubmitError("Please complete all required account fields.");
      return;
    }

    if (!captcha) {
      setSubmitError("Please complete the captcha check before continuing.");
      return;
    }

    setIsSubmitting(true);
    try {
      // Email sending is temporarily disabled.
      // await sendAccountSetupEmail({
      //   name: name.trim(),
      //   email: email.trim(),
      //   username: username.trim(),
      // });
      setSubmitSuccess("Account created successfully. Email delivery is currently disabled.");
      onNext({
        name: name.trim(),
        email: email.trim(),
        username: username.trim(),
      });
    } catch (error) {
      setSubmitError(error?.message || "Unable to send account email right now. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", background: C.bg }}>
      <header className="glass-header" style={{ position: "fixed", top: 0, left: 0, right: 0, height: 64, background: C.white, borderBottom: `1px solid ${C.border}`, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 28px", zIndex: 1000 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <button onClick={onBack} style={{ background: "transparent", border: "none", fontSize: 20, cursor: "pointer", color: C.text, marginRight: 8 }}>←</button>
          <div style={{ width: 40, height: 40, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <svg width="32" height="32" viewBox="0 0 256 257" fill="none" xmlns="http://www.w3.org/2000/svg">
              <defs>
                <linearGradient id="profileLogoGrad1" x1="-.828%" x2="57.636%" y1="7.652%" y2="78.411%">
                  <stop offset="0%" stopColor="#41D1FF"/>
                  <stop offset="100%" stopColor="#BD34FE"/>
                </linearGradient>
                <linearGradient id="profileLogoGrad2" x1="43.376%" x2="50.316%" y1="2.242%" y2="89.03%">
                  <stop offset="0%" stopColor="#FFEA83"/>
                  <stop offset="8.333%" stopColor="#FFDD35"/>
                  <stop offset="100%" stopColor="#FFA800"/>
                </linearGradient>
              </defs>
              <path fill="url(#profileLogoGrad1)" d="M255.153 37.938L134.897 252.976c-2.483 4.44-8.862 4.466-11.382.048L.875 37.958c-2.746-4.814 1.371-10.646 6.827-9.67l120.385 21.517a6.537 6.537 0 0 0 2.322-.004l117.867-21.483c5.438-.991 9.574 4.796 6.877 9.62Z"/>
              <path fill="url(#profileLogoGrad2)" d="M185.432.063L96.44 17.501a3.268 3.268 0 0 0-2.634 3.014l-5.474 92.456a3.268 3.268 0 0 0 3.997 3.378l24.777-5.718c2.318-.535 4.413 1.507 3.936 3.838l-7.361 36.047c-.495 2.426 1.782 4.5 4.151 3.78l15.304-4.649c2.372-.72 4.652 1.36 4.15 3.788l-11.698 56.621c-.732 3.542 3.979 5.473 5.943 2.437l1.313-2.028l72.516-144.72c1.215-2.423-.88-5.186-3.54-4.672l-25.505 4.922c-2.396.462-4.435-1.77-3.759-4.114l16.646-57.705c.677-2.35-1.37-4.583-3.769-4.113Z"/>
            </svg>
          </div>
          <span style={{ fontSize: 22, fontWeight: 800, color: C.accent }}>Mazimeal</span>
        </div>
        <div style={{ fontSize: 12, color: C.muted, fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase" }}>Step 1 of 6</div>
      </header>

      <main style={{ flex: 1, paddingTop: 64, display: "flex", alignItems: "center", justifyContent: "center", padding: "88px 20px 28px" }}>
        <div
          className="card fade-up"
          style={{
            width: "100%",
            maxWidth: 1120,
            padding: 0,
            overflow: "hidden",
            backgroundImage:
            "linear-gradient(145deg, rgba(255,252,246,0.92), rgba(248,243,233,0.88)), url('https://images.unsplash.com/photo-1495546968767-f0573cca821e?auto=format&fit=crop&w=1600&q=80')"
          }}
        >
          <div className="login-grid" style={{ minHeight: 640, gap: 0 }}>
            <div
              style={{
                position: "relative",
                padding: "42px 34px",
                display: "grid",
                alignContent: "space-between",
                backgroundImage:
                  "linear-gradient(120deg, rgba(16,34,26,0.68), rgba(33,74,57,0.56)), url('https://images.unsplash.com/photo-1482049016688-2d3e1b311543?auto=format&fit=crop&w=1600&q=80')",
                backgroundSize: "cover",
                backgroundPosition: "center",
              }}
            >
              <div>
                <div style={{ fontSize: 12, color: "rgba(255,255,255,0.84)", fontWeight: 700, letterSpacing: 1.3, textTransform: "uppercase" }}>Get Started For Free</div>
                <h2 style={{ fontFamily: "'Fraunces', serif", fontSize: 42, lineHeight: 1.08, color: C.white, marginTop: 10 }}>Build your family nutrition hub in minutes.</h2>
                <p style={{ color: "rgba(255,255,255,0.88)", lineHeight: 1.7, marginTop: 12, maxWidth: 430 }}>
                  Start with account creation now. After you receive your confirmation email, you will continue with Household and Nutrition details to activate your personalized meal system.
                </p>
              </div>
              <div style={{ display: "grid", gap: 10 }}>
                {[
                  "Step 1: Account setup (this page)",
                  "Step 2: Household details (after email confirmation)",
                  "Step 3: Nutrition preferences (final personalization)",
                ].map((line) => (
                  <div key={line} style={{ background: "rgba(255,255,255,0.16)", border: "1px solid rgba(255,255,255,0.26)", borderRadius: 14, padding: "12px 14px", color: C.white, fontSize: 14 }}>
                    {line}
                  </div>
                ))}
              </div>
            </div>

            <div
              style={{
                padding: "38px 32px",
                display: "grid",
                alignContent: "center",
                position: "relative",
                backgroundImage:
                  "linear-gradient(145deg, rgba(255,252,246,0.92), rgba(248,243,233,0.88)), url('https://images.unsplash.com/photo-1495546968767-f0573cca821e?auto=format&fit=crop&w=1600&q=80')",
                backgroundSize: "cover",
                backgroundPosition: "center",
              }}
            >
              <div
                aria-hidden="true"
                style={{
                  position: "absolute",
                  inset: 0,
                  pointerEvents: "none",
                  background:
                    "radial-gradient(circle at 18% 24%, rgba(248,210,142,0.18), transparent 40%), radial-gradient(circle at 84% 76%, rgba(47,106,79,0.1), transparent 42%)",
                }}
              />
              <div style={{ display: "grid", gap: 18, position: "relative", zIndex: 1 }}>
                {submitError && (
                  <div
                    role="alert"
                    style={{
                      background: "#FCE7E0",
                      border: `1px solid ${C.coral}`,
                      color: "#8A2D20",
                      borderRadius: 10,
                      padding: "10px 12px",
                      fontSize: 13,
                      fontWeight: 600,
                    }}
                  >
                    {submitError}
                  </div>
                )}
                <div>
                  <div style={{ fontSize: 12, color: C.accent, fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase" }}>Account Setup</div>
                  <h3 className="hero-title" style={{ fontSize: 34, color: C.text, marginTop: 8 }}>Create your Mazimeal account</h3>
                  <p style={{ color: C.subtext, lineHeight: 1.7, marginTop: 8 }}>A quick setup keeps your household, preferences, and meal plans ready to go.</p>
                </div>

                <div className="bento-grid" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
                  {["Account", "Household", "Nutrition"].map((label, i) => (
                    <div key={label} className="bento-card" style={{ padding: 12, textAlign: "center", background: i === 0 ? C.accentLight : "rgba(255,252,246,0.9)" }}>
                      <div style={{ fontSize: 12, fontWeight: 700, color: i === 0 ? C.accent : C.muted }}>{label}</div>
                    </div>
                  ))}
                </div>

                <div style={{ display: "grid", gap: 14 }}>
                  <div><label>Full Name</label><input placeholder="e.g. Maya Patel" value={name} onChange={e => setName(e.target.value)} /></div>
                  <div><label>Email Address</label><input type="email" placeholder="you@family.com" value={email} onChange={e => setEmail(e.target.value)} /></div>
                  <div><label>Username</label><input placeholder="mazimeal.user" value={username} onChange={e => setUsername(e.target.value)} /></div>
                  <div><label>Password</label><input type="password" placeholder="At least 8 characters" value={pw} onChange={e => setPw(e.target.value)} /></div>
                  <div className="captcha-mock">
                    <label htmlFor="captcha" className="captcha-main">
                      <input
                        id="captcha"
                        type="checkbox"
                        className="captcha-input"
                        checked={captcha}
                        onChange={e => setCaptcha(e.target.checked)}
                      />
                      <span className={`captcha-box ${captcha ? "checked" : ""}`} aria-hidden="true">
                        {captcha ? "✓" : ""}
                      </span>
                      <span className="captcha-label">I'm not a robot</span>
                    </label>
                    <div className="captcha-brand" aria-hidden="true">
                      <div className="captcha-logo">
                        <svg width="30" height="30" viewBox="0 0 30 30" fill="none" xmlns="http://www.w3.org/2000/svg">
                          <circle cx="15" cy="15" r="13" stroke="#DADCE0" strokeWidth="2" />
                          <path d="M23 15a8 8 0 1 1-2.1-5.4" stroke="#1A73E8" strokeWidth="2.6" strokeLinecap="round" />
                          <path d="M22.2 9.4l1.8 4.7-4.9-.7" fill="#1A73E8" />
                        </svg>
                      </div>
                      <div className="captcha-brand-text">reCAPTCHA</div>
                      <div className="captcha-meta">Privacy - Terms</div>
                    </div>
                  </div>
                </div>

                <div style={{ display: "flex", justifyContent: "space-between", gap: 12, marginTop: 8 }}>
                  <button className="btn-ghost" style={{ flex: 1 }} onClick={onBack}>Back</button>
                  <button className="btn-primary" style={{ flex: 1 }} onClick={handleCreateAccount} disabled={isSubmitting}>
                    {isSubmitting ? "Sending..." : "Create Account"}
                  </button>
                </div>

                {submitSuccess && <p style={{ color: C.accent, fontSize: 12, textAlign: "center", margin: 0 }}>{submitSuccess}</p>}
                <p style={{ color: C.subtext, fontSize: 12, textAlign: "center", margin: 0 }}>
                  Next after email: complete <strong>Household</strong> and <strong>Nutrition</strong> to finish onboarding.
                </p>

                <p style={{ color: C.muted, fontSize: 12, textAlign: "center" }}>
                  Free trial starts after setup. No payment required today.
                </p>
              </div>
            </div>
          </div>
        </div>
      </main>

      <SiteFooter compact marginTop={40} />
    </div>
  );
}

function EmailVerificationModule({ email, onVerified, onBack }) {
  const [sent, setSent] = useState(true);

  return (
    <CenteredPageShell>
      <div className="card" style={{ width: "100%", maxWidth: 560, padding: "40px 38px", textAlign: "center" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div style={{ fontSize: 12, color: C.accent, fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase" }}>Step 2 of 6 · Email Verification</div>
          <span style={{ fontSize: 50 }}>📧</span>
          <h2 style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 28, color: C.text }}>Verify your email</h2>
          <p style={{ color: C.subtext, fontSize: 14, lineHeight: 1.7 }}>We sent a verification link to <strong>{email}</strong>. Click the link in your inbox to continue.</p>
          <button className="btn-primary" style={{ width: "100%" }} onClick={onVerified}>I clicked the link</button>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 12, marginTop: 8 }}>
            <button className="btn-ghost" onClick={onBack}>Back</button>
            <button className="btn-ghost" onClick={() => setSent(true)}>Resend email</button>
          </div>
          {sent && <p style={{ color: C.accent, fontSize: 13, marginTop: 8 }}>Verification email sent.</p>}
        </div>
      </div>
    </CenteredPageShell>
  );
}

function LegalModule({ onAgree, onBack }) {
  const [agree, setAgree] = useState(false);

  return (
    <CenteredPageShell>
      <div className="card" style={{ width: "100%", maxWidth: 640, padding: "42px 40px" }}>
        <div style={{ fontSize: 12, color: C.accent, fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase", marginBottom: 12 }}>Step 3 of 6 · Legal</div>
        <h2 style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 28, marginBottom: 18 }}>Legal & privacy</h2>
        <div style={{ display: "grid", gap: 14, marginBottom: 24 }}>
          <div style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: 14, padding: 18 }}>
            <div style={{ fontWeight: 700, marginBottom: 8 }}>Disclaimer</div>
            <p style={{ color: C.subtext, fontSize: 14, lineHeight: 1.7 }}>Mazimeal provides nutritional guidance and meal planning suggestions. It is not a substitute for professional medical advice, diagnosis, or treatment.</p>
          </div>
          <div style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: 14, padding: 18 }}>
            <div style={{ fontWeight: 700, marginBottom: 8 }}>Privacy Policy</div>
            <p style={{ color: C.subtext, fontSize: 14, lineHeight: 1.7 }}>We collect household and nutrition preferences to personalize meals. Data is protected and used only to improve your experience.</p>
          </div>
          <div style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: 14, padding: 18 }}>
            <div style={{ fontWeight: 700, marginBottom: 8 }}>Liability Agreement</div>
            <p style={{ color: C.subtext, fontSize: 14, lineHeight: 1.7 }}>You agree that Mazimeal is not liable for medical decisions made using this guidance. Always consult a healthcare professional for clinical concerns.</p>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 24 }}>
          <input id="agree" type="checkbox" checked={agree} onChange={e => setAgree(e.target.checked)} />
          <label htmlFor="agree" style={{ fontSize: 14, color: C.text }}>I have read and agree to the terms.</label>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
          <button className="btn-ghost" onClick={onBack}>Back</button>
          <button className="btn-primary" disabled={!agree} onClick={onAgree}>Agree & Continue</button>
        </div>
      </div>
    </CenteredPageShell>
  );
}

function HouseholdSetupModule({ onNext, onBack, household, setHousehold }) {
  return (
    <CenteredPageShell>
      <div className="card" style={{ width: "100%", maxWidth: 640, padding: "42px 40px" }}>
        <div style={{ display: "grid", gap: 20 }}>
          <div>
            <div style={{ fontSize: 12, color: C.accent, fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase", marginBottom: 10 }}>Step 4 of 6 · Household</div>
            <h2 style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 28 }}>Household setup</h2>
            <p style={{ color: C.subtext, fontSize: 14, lineHeight: 1.7 }}>Add your household details so Mazimeal can personalize the plan for your family.</p>
          </div>
          <div style={{ display: "grid", gap: 16 }}>
            <div><label>Household name (optional)</label><input placeholder="Family name or household" value={household.name} onChange={e => setHousehold(h => ({ ...h, name: e.target.value }))} /></div>
            <div><label>Country / Region</label><select value={household.country} onChange={e => setHousehold(h => ({ ...h, country: e.target.value }))}>
              <option value="US">United States</option>
              <option value="CA">Canada</option>
              <option value="UK">United Kingdom</option>
              <option value="AU">Australia</option>
              <option value="Other">Other</option>
            </select></div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
              <div><label>Number of family members</label><input type="number" min="1" value={household.members} onChange={e => setHousehold(h => ({ ...h, members: Number(e.target.value) }))} /></div>
              <div style={{ display: "grid", gap: 8 }}>
                <label>Pets in household</label>
                <div style={{ display: "flex", gap: 12 }}>
                  <button type="button" className={`btn-ghost ${household.pets.cat ? "active" : ""}`} style={{ flex: 1, borderColor: household.pets.cat ? C.accent : C.border }} onClick={() => setHousehold(h => ({ ...h, pets: { ...h.pets, cat: !h.pets.cat } }))}>Cat</button>
                  <button type="button" className={`btn-ghost ${household.pets.dog ? "active" : ""}`} style={{ flex: 1, borderColor: household.pets.dog ? C.accent : C.border }} onClick={() => setHousehold(h => ({ ...h, pets: { ...h.pets, dog: !h.pets.dog } }))}>Dog</button>
                </div>
              </div>
            </div>
            <div style={{ display: "flex", gap: 14, alignItems: "center" }}>
              <span>Do pets receive food scraps?</span>
              <button className={`btn-ghost ${household.scraps ? "active" : ""}`} onClick={() => setHousehold(h => ({ ...h, scraps: true }))}>Yes</button>
              <button className={`btn-ghost ${!household.scraps ? "active" : ""}`} onClick={() => setHousehold(h => ({ ...h, scraps: false }))}>No</button>
            </div>
          </div>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, marginTop: 30 }}>
          <button className="btn-ghost" onClick={onBack}>Back</button>
          <button className="btn-primary" onClick={onNext}>Continue →</button>
        </div>
      </div>
    </CenteredPageShell>
  );
}

function ProfileBasicsModule({ profile, updateProfile, onNext, onBack }) {
  const heightParts = getHeightParts(profile.height);

  return (
    <CenteredPageShell>
      <div className="card" style={{ width: "100%", maxWidth: 640, padding: "42px 40px" }}>
        <div style={{ display: "grid", gap: 20 }}>
          <div>
            <div style={{ fontSize: 12, color: C.accent, fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase", marginBottom: 10 }}>Step 5 of 6 · Profile Basics</div>
            <h2 style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 28 }}>Primary profile</h2>
            <p style={{ color: C.subtext, fontSize: 14, lineHeight: 1.7 }}>Tell us about the main member so we can calculate nutrition needs accurately.</p>
          </div>
          <div style={{ display: "grid", gap: 16 }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
              <div><label>Role</label><select value={profile.role} onChange={e => updateProfile({ ...profile, role: e.target.value })}>
                <option>Adult</option>
                <option>Child</option>
              </select></div>
              <div><label>Sex at birth</label><select value={profile.sex} onChange={e => updateProfile({ ...profile, sex: e.target.value })}>
                <option>Female</option>
                <option>Male</option>
                <option>Other</option>
              </select></div>
            </div>
            <div><label>Name</label><input value={profile.name} onChange={e => updateProfile({ ...profile, name: e.target.value })} /></div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
              <div><label>Age</label><input type="number" min="1" value={profile.age} onChange={e => updateProfile({ ...profile, age: e.target.value })} /></div>
              <div>
                <label>Height</label>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                  <input
                    placeholder="ft"
                    value={heightParts.feet}
                    onChange={e => updateProfile({ ...profile, height: buildHeightValue(e.target.value, heightParts.inches) })}
                  />
                  <input
                    placeholder="in"
                    value={heightParts.inches}
                    onChange={e => updateProfile({ ...profile, height: buildHeightValue(heightParts.feet, e.target.value) })}
                  />
                </div>
              </div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
              <div><label>Weight</label><input placeholder="lb" value={profile.weight} onChange={e => updateProfile({ ...profile, weight: e.target.value })} /></div>
              <div>
                <label>Activity level</label>
                <select value={profile.activity} onChange={e => updateProfile({ ...profile, activity: e.target.value })}>
                  <option>Sedentary</option>
                  <option>Moderate</option>
                  <option>Active</option>
                </select></div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
              <div>
                <label>Activity level</label>
                <select value={profile.activity} onChange={e => updateProfile({ ...profile, activity: e.target.value })}>
                  <option>Sedentary</option>
                  <option>Moderate</option>
                  <option>Active</option>
                </select>
              </div>
              <div>
                <label>Health goal</label>
                <select value={profile.goal} onChange={e => updateProfile({ ...profile, goal: e.target.value })}>
                  <option>Maintain weight</option>
                  <option>Weight loss</option>
                  <option>Weight gain</option>
                  <option>Improve health</option>
                </select>
              </div>
            </div>
          </div>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, marginTop: 30 }}>
          <button className="btn-ghost" onClick={onBack}>Back</button>
          <button className="btn-primary" onClick={onNext}>Continue →</button>
        </div>
      </div>
    </CenteredPageShell>
  );
}

function DietPreferencesModule({ profile, updateProfile, onNext, onBack }) {
  return (
    <CenteredPageShell>
      <div className="card" style={{ width: "100%", maxWidth: 640, padding: "42px 40px" }}>
        <div style={{ display: "grid", gap: 20 }}>
          <div>
            <div style={{ fontSize: 12, color: C.accent, fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase", marginBottom: 10 }}>Step 6 of 6 · Nutrition Preferences (1/3)</div>
            <h2 style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 28 }}>Food & diet preferences</h2>
            <p style={{ color: C.subtext, fontSize: 14, lineHeight: 1.7 }}>Select allergies, dislikes, dietary patterns, and favorite ingredients.</p>
          </div>
          <div style={{ display: "grid", gap: 16 }}>
            <div><label>Allergies</label><input placeholder="Type an allergy or None" value={profile.allergies} onChange={e => updateProfile({ ...profile, allergies: e.target.value })} /></div>
            <div><label>Food dislikes</label><input placeholder="Type dislikes or None" value={profile.dislikes} onChange={e => updateProfile({ ...profile, dislikes: e.target.value })} /></div>
            <div>
              <label>Dietary pattern</label>
              <select value={profile.dietaryPattern} onChange={e => updateProfile({ ...profile, dietaryPattern: e.target.value })}>
                <option>None</option>
                <option>Vegan</option>
                <option>Vegetarian</option>
                <option>Mediterranean</option>
                <option>Low glycemic / low carb</option>
                <option>Other</option>
              </select>
            </div>
            <div><label>Food preferences</label><input placeholder="e.g. Chicken, Onion" value={profile.preferences} onChange={e => updateProfile({ ...profile, preferences: e.target.value })} /></div>
          </div>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, marginTop: 30 }}>
          <button className="btn-ghost" onClick={onBack}>Back</button>
          <button className="btn-primary" onClick={onNext}>Continue →</button>
        </div>
      </div>
    </CenteredPageShell>
  );
}

function CulinaryPreferencesModule({ profile, updateProfile, onNext, onBack }) {
  const cuisines = ["Mexican", "Asian", "Mediterranean", "American", "Other"];
  const toggleCuisine = value => {
    const next = profile.cuisines.includes(value) ? profile.cuisines.filter(item => item !== value) : [...profile.cuisines, value];
    updateProfile({ ...profile, cuisines: next });
  };

  return (
    <CenteredPageShell>
      <div className="card" style={{ width: "100%", maxWidth: 640, padding: "42px 40px" }}>
        <div style={{ display: "grid", gap: 20 }}>
          <div>
            <div style={{ fontSize: 12, color: C.accent, fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase", marginBottom: 10 }}>Step 6 of 6 · Nutrition Preferences (2/3)</div>
            <h2 style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 28 }}>Culinary preferences</h2>
            <p style={{ color: C.subtext, fontSize: 14, lineHeight: 1.7 }}>Pick the regional cuisines your household loves.</p>
          </div>
          <div style={{ display: "grid", gap: 12 }}>
            {cuisines.map(cuisine => (
              <button key={cuisine} type="button" className={`btn-ghost ${profile.cuisines.includes(cuisine) ? "active" : ""}`} style={{ textAlign: "left", justifyContent: "flex-start", borderColor: profile.cuisines.includes(cuisine) ? C.accent : C.border }} onClick={() => toggleCuisine(cuisine)}>{cuisine}</button>
            ))}
          </div>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, marginTop: 30 }}>
          <button className="btn-ghost" onClick={onBack}>Back</button>
          <button className="btn-primary" onClick={onNext}>Continue →</button>
        </div>
      </div>
    </CenteredPageShell>
  );
}

function LifeStageModule({ profile, updateProfile, onNext, onBack }) {
  const stages = ["Pregnant", "Lactating", "Menstruating", "Menopause", "None"];
  return (
    <CenteredPageShell>
      <div className="card" style={{ width: "100%", maxWidth: 640, padding: "42px 40px" }}>
        <div style={{ display: "grid", gap: 20 }}>
          <div>
            <div style={{ fontSize: 12, color: C.accent, fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase", marginBottom: 10 }}>Step 6 of 6 · Nutrition Preferences (3/3)</div>
            <h2 style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 28 }}>Women’s life stage</h2>
            <p style={{ color: C.subtext, fontSize: 14, lineHeight: 1.7 }}>Select the option that best matches the primary profile.</p>
          </div>
          <div style={{ display: "grid", gap: 12 }}>
            {stages.map(stage => (
              <button key={stage} type="button" className={`btn-ghost ${profile.lifeStage === stage ? "active" : ""}`} style={{ textAlign: "left", justifyContent: "flex-start", borderColor: profile.lifeStage === stage ? C.accent : C.border }} onClick={() => updateProfile({ ...profile, lifeStage: stage })}>{stage}</button>
            ))}
          </div>
          {profile.lifeStage === "Pregnant" && (
            <div><label>Pregnancy week</label><input type="number" min="1" max="42" placeholder="Week" value={profile.pregnancyWeek} onChange={e => updateProfile({ ...profile, pregnancyWeek: e.target.value })} /></div>
          )}
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, marginTop: 30 }}>
          <button className="btn-ghost" onClick={onBack}>Back</button>
          <button className="btn-primary" onClick={onNext}>Finish Profile</button>
        </div>
      </div>
    </CenteredPageShell>
  );
}

function AdditionalProfilesModule({ profiles, onAddAdult, onAddChild, onInvite, onContinue, onBack }) {
  return (
    <CenteredPageShell>
      <div className="card" style={{ width: "100%", maxWidth: 760, padding: "42px 40px" }}>
        <div style={{ display: "grid", gap: 24 }}>
          <div>
            <div style={{ fontSize: 12, color: C.accent, fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase", marginBottom: 10 }}>Setup Complete · Optional</div>
            <h2 style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 28 }}>Add additional household profiles</h2>
            <p style={{ color: C.subtext, fontSize: 14, lineHeight: 1.7 }}>Add another family member, or invite an adult by email to join and set permissions.</p>
          </div>
          <div style={{ display: "grid", gap: 16 }}>
            {profiles.length > 0 && (
              <div>
                <div style={{ fontWeight: 700, marginBottom: 12 }}>Current profiles</div>
                <div style={{ display: "grid", gap: 10 }}>
                  {profiles.map((p, index) => (
                    <div key={index} className="card" style={{ padding: 14, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <div>
                        <div style={{ fontWeight: 700 }}>{p.name || p.inviteEmail || `Household member ${index + 1}`}</div>
                        <div style={{ color: C.subtext, fontSize: 13 }}>{p.role} {p.invited ? `• Invited (${p.permission})` : `• ${p.age || "Unset"}`}</div>
                      </div>
                      {p.invited && <span style={{ color: C.accent, fontWeight: 700 }}>Invite pending</span>}
                    </div>
                  ))}
                </div>
              </div>
            )}
            <div style={{ display: "grid", gap: 12, gridTemplateColumns: "1fr 1fr" }}>
              <button className="btn-primary" style={{ width: "100%" }} onClick={onAddAdult}>Add Adult</button>
              <button className="btn-primary" style={{ width: "100%" }} onClick={onAddChild}>Add Child</button>
            </div>
            <button className="btn-ghost" style={{ width: "100%" }} onClick={onInvite}>Invite adult by email</button>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
            <button className="btn-ghost" onClick={onBack}>Back</button>
            <button className="btn-ghost" onClick={onContinue}>Continue to app</button>
          </div>
        </div>
      </div>
    </CenteredPageShell>
  );
}

function InviteAdultModule({ onSend, onBack }) {
  const [email, setEmail] = useState("");
  const [permission, setPermission] = useState("Full profile access");

  return (
    <CenteredPageShell>
      <div className="card" style={{ width: "100%", maxWidth: 560, padding: "42px 40px" }}>
        <div style={{ display: "grid", gap: 20 }}>
          <div>
            <h2 style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 28 }}>Invite an adult</h2>
            <p style={{ color: C.subtext, fontSize: 14, lineHeight: 1.7 }}>Send a household access link and set their permission level.</p>
          </div>
          <div style={{ display: "grid", gap: 16 }}>
            <div><label>Email address</label><input type="email" placeholder="invitee@family.com" value={email} onChange={e => setEmail(e.target.value)} /></div>
            <div>
              <label>Permission level</label>
              <select value={permission} onChange={e => setPermission(e.target.value)}>
                <option>Full profile access</option>
                <option>Meal planning only</option>
                <option>Track access only</option>
              </select>
            </div>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
            <button className="btn-ghost" onClick={onBack}>Back</button>
            <button className="btn-primary" disabled={!email} onClick={() => onSend(email, permission)}>Send invite</button>
          </div>
        </div>
      </div>
    </CenteredPageShell>
  );
}

function HomeDashboard({ user, setStep, plannerDay }) {
  const items = plannerDay
    ? plannerDay.mealOrder.map((slot) => {
        const meal = plannerDay.meals[slot];
        return {
          id: slot,
          meal: meal.label || meal.slotType || "Meal",
          name: meal.name,
          calories: meal.calories,
          protein: meal.protein,
        };
      })
    : [
        { id: "breakfast", meal: "Breakfast", name: "Avocado Toast + Berry Smoothie", calories: 340, protein: 14 },
        { id: "lunch", meal: "Lunch", name: "Chicken + Veggie Bowl", calories: 520, protein: 30 },
        { id: "dinner", meal: "Dinner", name: "Salmon Mediterranean Plate", calories: 540, protein: 32 },
        { id: "snack", meal: "Snack", name: "Hummus & Veggies", calories: 160, protein: 6 },
      ];
  const totalMeals = items.length;
  const totalCalories = plannerDay ? plannerDay.totalCalories : items.reduce((sum, item) => sum + item.calories, 0);
  const calorieAlignment = Math.min(Math.round((totalCalories / 2000) * 100), 100);

  return (
    <div style={{ padding: "26px 20px 92px", maxWidth: 1160, margin: "0 auto", position: "relative" }}>
      <div className="card home-hero-image" style={{ padding: 28, marginBottom: 22, position: "relative", overflow: "hidden" }}>
        <span className="orb" style={{ width: 140, height: 140, top: -20, right: -20, background: "rgba(47,106,79,0.24)" }} />
        <span className="orb" style={{ width: 120, height: 120, bottom: -30, left: "42%", background: "rgba(183,134,45,0.2)", animationDelay: "0.8s" }} />
        <div className="home-hero-content" style={{ position: "relative", display: "grid", gap: 18 }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
            <div>
              <div style={{ color: C.accent, fontSize: 12, fontWeight: 700, letterSpacing: 1.4, textTransform: "uppercase" }}>Daily Command Center</div>
              <h1 className="hero-title" style={{ fontSize: 42, color: C.text, marginTop: 8 }}>Welcome back, {user || "Mazimeal"}</h1>
              <p style={{ color: C.subtext, marginTop: 10, maxWidth: 620 }}>Your household has a strong week in progress. Keep momentum with today’s smart meal blocks and adaptive suggestions.</p>
            </div>
            <div className="bento-card" style={{ minWidth: 210 }}>
              <div style={{ fontSize: 12, color: C.muted, textTransform: "uppercase", letterSpacing: 1 }}>Today’s Plan</div>
              <div style={{ fontWeight: 800, fontSize: 38, color: C.accent, lineHeight: 1.1, marginTop: 10 }}>{totalMeals} meals</div>
              <div style={{ color: C.subtext, marginTop: 6, fontSize: 13 }}>{totalCalories} kcal planned</div>
              <div style={{ color: C.subtext, marginTop: 4, fontSize: 13 }}>{calorieAlignment}% daily calorie target aligned</div>
            </div>
          </div>
          <div className="bento-grid">
            <div className="bento-card">
              <div style={{ fontSize: 12, color: C.muted, textTransform: "uppercase", letterSpacing: 1 }}>Prep Window</div>
              <div style={{ fontWeight: 700, fontSize: 18, marginTop: 8 }}>52 min total prep</div>
              <div style={{ color: C.subtext, marginTop: 6 }}>Batch lunch items now to save 18 minutes tonight.</div>
            </div>
            <div className="bento-card">
              <div style={{ fontSize: 12, color: C.muted, textTransform: "uppercase", letterSpacing: 1 }}>Focus Nutrient</div>
              <div style={{ fontWeight: 700, fontSize: 18, marginTop: 8 }}>Iron + Vitamin C synergy</div>
              <div style={{ color: C.subtext, marginTop: 6 }}>Lunch pairing boosts absorption by 2.8x.</div>
            </div>
          </div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))", gap: 16, marginBottom: 22 }}>
        {items.map(item => (
          <div key={item.id} className="card meal-card" style={{ padding: 20, cursor: "pointer" }} onClick={() => setStep("cook")}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 14 }}>
              <div>
                <div style={{ fontSize: 11, color: C.muted, textTransform: "uppercase", letterSpacing: 1 }}>{item.meal}</div>
                <div style={{ fontWeight: 700, marginTop: 7, lineHeight: 1.35 }}>{item.name}</div>
              </div>
              <div style={{ fontSize: 12, color: C.accent, fontWeight: 700 }}>{item.calories} kcal</div>
            </div>
            <div style={{ color: C.subtext, fontSize: 13, marginBottom: 14 }}>{item.protein}g protein</div>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
              <button className="btn-ghost" onClick={e => { e.stopPropagation(); }} style={{ flex: "1 1 30%", minWidth: 96 }}>Add</button>
              <button className="btn-primary" onClick={e => { e.stopPropagation(); setStep("cook"); }} style={{ flex: "1 1 30%", minWidth: 96, padding: "9px 14px" }}>Cook</button>
              <button className="btn-ghost" onClick={e => { e.stopPropagation(); }} style={{ flex: "1 1 30%", minWidth: 96 }}>Track</button>
            </div>
          </div>
        ))}
      </div>

      <div className="dashboard-grid">
        <div className="dashboard-stack">
          <div className="card" style={{ padding: 20 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
              <strong>AI Suggestions</strong>
              <button className="btn-ghost">Refresh</button>
            </div>
            <div style={{ display: "grid", gap: 10 }}>
              <div style={{ color: C.text }}>Try a crunchy chickpea snack this afternoon for steadier energy.</div>
              <div style={{ color: C.text }}>Add leafy greens to dinner for stronger iron absorption and fiber.</div>
            </div>
          </div>
        </div>
        <div className="dashboard-stack">
          <div className="card" style={{ padding: 20 }}>
            <strong style={{ display: "block", marginBottom: 12 }}>Execution Snapshot</strong>
            <div className="bento-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
              <div className="bento-card" style={{ padding: 14 }}>
                <div style={{ fontSize: 11, color: C.muted, textTransform: "uppercase" }}>Hydration</div>
                <div style={{ fontWeight: 800, marginTop: 6 }}>6 / 8 cups</div>
              </div>
              <div className="bento-card" style={{ padding: 14 }}>
                <div style={{ fontSize: 11, color: C.muted, textTransform: "uppercase" }}>Prep streak</div>
                <div style={{ fontWeight: 800, marginTop: 6 }}>5 days</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function HomeDashboardClassic({
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
  const smartTips = [
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

function RecipesClassicPage({ user, setStep, plannerDay, plannerState, setPlannerState, selectedDayIndex }) {
  const [search, setSearch] = useState("");
  const [selectedPrep, setSelectedPrep] = useState("Prep Time");
  const [selectedMealType, setSelectedMealType] = useState("Meal Type");
  const [selectedDietary, setSelectedDietary] = useState("Dietary Needs");
  const [selectedCalories, setSelectedCalories] = useState("Calories");
  const [selectedDifficulty, setSelectedDifficulty] = useState("Difficulty");
  const [selectedCuisine, setSelectedCuisine] = useState("Cuisine");
  const [selectedRecipe, setSelectedRecipe] = useState(null);
  const [selectedCategory, setSelectedCategory] = useState("Salads");
  const [activeRecipeSection, setActiveRecipeSection] = useState(null);
  const [showAddToPlanModal, setShowAddToPlanModal] = useState(false);
  const [selectedPlanMealSlot, setSelectedPlanMealSlot] = useState("dinner");
  const [selectedPlanStartDayIndex, setSelectedPlanStartDayIndex] = useState(0);
  const [selectedSmartPick, setSelectedSmartPick] = useState(null);
  const [showSmartPickMealChooser, setShowSmartPickMealChooser] = useState(false);
  const [selectedSmartPickMealSlot, setSelectedSmartPickMealSlot] = useState("dinner");
  const [smartPickToast, setSmartPickToast] = useState("");
  const [frequentlyUsedRecipes, setFrequentlyUsedRecipes] = useState(() => {
    try {
      const stored = localStorage.getItem(`mazimeal:frequently-used-recipes:${user || "guest"}`);
      return stored ? JSON.parse(stored) : ["salmon", "stir-fry", "quinoa"];
    } catch {
      return ["salmon", "stir-fry", "quinoa"];
    }
  });

  const [favoriteRecipes, setFavoriteRecipes] = useState(() => {
    try {
      const stored = localStorage.getItem(`mazimeal:favorite-recipes:${user || "guest"}`);
      return stored ? JSON.parse(stored) : [];
    } catch {
      return [];
    }
  });

  const plannerInspiredShell = {
    position: "relative",
    overflow: "hidden",
    borderRadius: 24,
    background: "linear-gradient(180deg, rgba(255,253,248,0.96), rgba(248,245,238,0.94))",
    border: `1.5px solid ${C.border}`,
    boxShadow: "0 18px 38px rgba(72, 88, 120, 0.08)",
  };

  const plannerInspiredGlass = {
    borderRadius: 22,
    border: `1px solid ${C.border}`,
    background: "rgba(255,255,255,0.88)",
    backdropFilter: "blur(10px)",
    boxShadow: "0 12px 26px rgba(72, 88, 120, 0.1)",
  };

  const recipeCollections = [
    {
      id: "salmon",
      title: "Grilled Lemon Herb Salmon",
      subtitle: "Light and zesty, perfect for a healthy dinner.",
      cuisine: "Mediterranean",
      prep: "20 min",
      calories: 350,
      difficulty: "Easy",
      mealType: "Dinner",
      dietary: "High Protein",
      categories: ["Asian"],
      badge: "AI Recommended for You",
      badgeTone: { bg: "#F1F8DF", border: "#D4E7A8", color: "#6B9634" },
      image: "https://images.unsplash.com/photo-1467003909585-2f8a72700288?auto=format&fit=crop&w=1400&q=80",
      cardTag: { label: "Family Friendly", color: "#4B8CCC" },
      ingredients: ["4 salmon fillets", "2 lemons", "1 tbsp olive oil", "2 tbsp chopped parsley", "Steamed greens"],
      steps: [
        "Pat salmon dry and season with olive oil, lemon zest, parsley, salt, and pepper.",
        "Sear skin-side down until crisp, then finish gently until flaky.",
        "Plate with steamed greens and fresh lemon wedges.",
      ],
      swapInsight: "If you're out of parsley, dill gives the same bright finish.",
      reflection: "A clean, protein-forward dinner that supports energy without feeling heavy.",
      nutrientStory: ["Protein Next", "Omega Support", "Light Carbs"],
      macro: { protein: 34, carbs: 16, fats: 18 },
    },
    {
      id: "stir-fry",
      title: "Chicken Stir-Fry",
      subtitle: "Quick and protein-packed with crisp vegetables.",
      cuisine: "Asian",
      prep: "20 min",
      calories: 420,
      difficulty: "Easy",
      mealType: "Dinner",
      dietary: "High Protein",
      categories: ["Asian", "Quick Meals"],
      badge: "High Protein",
      badgeTone: { bg: "#FFF4D9", border: "#F0D38A", color: "#C58A15" },
      image: "https://images.unsplash.com/photo-1512058564366-18510be2db19?auto=format&fit=crop&w=1400&q=80",
      cardTag: { label: "High Protein", color: "#F0B23D" },
      ingredients: ["Chicken breast", "Broccoli florets", "Bell peppers", "Brown rice", "Garlic ginger sauce"],
      steps: [
        "Saute chicken until golden and just cooked through.",
        "Add broccoli and peppers with ginger-garlic sauce.",
        "Serve over rice and finish with sesame seeds.",
      ],
      swapInsight: "Use tofu instead of chicken for a vegetarian version with similar satisfaction.",
      reflection: "A dependable weeknight choice that balances protein, crunch, and comfort.",
      nutrientStory: ["Fiber First", "Protein Next", "Steady Carbs"],
      macro: { protein: 31, carbs: 33, fats: 12 },
    },
    {
      id: "quinoa",
      title: "Veggie Quinoa Bowl",
      subtitle: "Hearty and nutritious with a light citrus finish.",
      cuisine: "Mediterranean",
      prep: "15 min",
      calories: 320,
      difficulty: "Easy",
      mealType: "Lunch",
      dietary: "Low Carb",
      categories: ["Bowls"],
      badge: "Low Carb",
      badgeTone: { bg: "#EAF7E0", border: "#C8E7AF", color: "#5F9A2E" },
      image: "https://images.unsplash.com/photo-1547592180-85f173990554?auto=format&fit=crop&w=1400&q=80",
      cardTag: { label: "Low Carb", color: "#58A63D" },
      ingredients: ["Cooked quinoa", "Roasted zucchini", "Spinach", "Chickpeas", "Lemon tahini drizzle"],
      steps: [
        "Layer quinoa with spinach, zucchini, and chickpeas.",
        "Spoon over lemon tahini and finish with herbs.",
        "Serve warm or chilled for meal prep.",
      ],
      swapInsight: "Swap quinoa with cauliflower rice for an even lighter bowl.",
      reflection: "A balanced lunch that keeps energy steady without an afternoon crash.",
      nutrientStory: ["Fiber First", "Protein Next", "Carbs Last"],
      macro: { protein: 17, carbs: 33, fats: 9 },
    },
    {
      id: "wrap",
      title: "Turkey Avocado Wrap",
      subtitle: "Easy and satisfying lunch built for busy afternoons.",
      cuisine: "American",
      prep: "5 min",
      calories: 280,
      difficulty: "Easy",
      mealType: "Lunch",
      dietary: "Quick Meal",
      categories: ["Quick Meals"],
      badge: "Quick Meal",
      badgeTone: { bg: "#FFF1D9", border: "#F6D087", color: "#D9911E" },
      image: "https://images.unsplash.com/photo-1534939561126-855b8675edd7?auto=format&fit=crop&w=1400&q=80",
      cardTag: { label: "Quick Meal", color: "#F0A52D" },
      ingredients: ["Turkey slices", "Whole wheat wrap", "Avocado", "Tomato", "Baby spinach"],
      steps: [
        "Spread avocado across the wrap and layer turkey and vegetables.",
        "Roll tightly and slice in half.",
        "Pair with fruit or crunchy vegetables.",
      ],
      swapInsight: "Use hummus if you want a dairy-free creamy layer.",
      reflection: "A fast lunch that still feels filling and put together.",
      nutrientStory: ["Protein First", "Healthy Fats", "Portable Carbs"],
      macro: { protein: 20, carbs: 24, fats: 11 },
    },
    {
      id: "pasta",
      title: "Pasta Primavera",
      subtitle: "Fresh and veggie-filled comfort in one bowl.",
      cuisine: "Italian",
      prep: "20 min",
      calories: 350,
      difficulty: "Medium",
      mealType: "Dinner",
      dietary: "Family Friendly",
      categories: ["Pasta"],
      badge: "Family Friendly",
      badgeTone: { bg: "#EAF2FC", border: "#BED4F1", color: "#4E86C0" },
      image: "https://images.unsplash.com/photo-1621996346565-e3dbc646d9a9?auto=format&fit=crop&w=1400&q=80",
      cardTag: { label: "Family Friendly", color: "#4B8CCC" },
      ingredients: ["Pasta", "Cherry tomatoes", "Peas", "Zucchini", "Parmesan"],
      steps: [
        "Cook pasta until al dente and reserve a splash of pasta water.",
        "Saute vegetables until tender-crisp.",
        "Toss everything together with parmesan and herbs.",
      ],
      swapInsight: "Gluten-free pasta works well here without changing the overall feel.",
      reflection: "A softer comfort dinner with extra vegetables folded in naturally.",
      nutrientStory: ["Fiber Build", "Veggie Lift", "Comfort Carbs"],
      macro: { protein: 15, carbs: 44, fats: 10 },
    },
    {
      id: "salad",
      title: "Cucumber Mint Quinoa Salad",
      subtitle: "Hydrating and energizing, perfect for a warm day.",
      cuisine: "Mediterranean",
      prep: "15 min",
      calories: 280,
      difficulty: "Easy",
      mealType: "Lunch",
      dietary: "Vegetarian",
      categories: ["Salads"],
      badge: "Vegetarian",
      badgeTone: { bg: "#E8F4D8", border: "#C8E09A", color: "#5B922A" },
      image: "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?auto=format&fit=crop&w=1400&q=80",
      cardTag: { label: "Hydration Boost", color: "#67A94B" },
      ingredients: ["1 cup cooked quinoa", "1 cup chopped cucumber", "1/2 cup canned chickpeas", "1/4 cup fresh mint leaves", "1/2 cup cherry tomatoes"],
      steps: [
        "Combine quinoa, cucumber, chickpeas, and mint in a large bowl.",
        "Drizzle with lemon juice and olive oil, then top with cherry tomatoes and toss gently.",
      ],
      swapInsight: "Out of mint? Try basil for a similar freshness.",
      reflection: "You've chosen a balanced meal-light, hydrating, and energizing. Perfect for your rhythm today.",
      nutrientStory: ["Fiber First", "Protein Next", "Carbs Last"],
      macro: { protein: 17, carbs: 33, fats: 9 },
    },
    {
      id: "parfait",
      title: "Berry Yogurt Parfait",
      subtitle: "Refreshing, protein-forward breakfast with fruit and crunch.",
      cuisine: "American",
      prep: "10 min",
      calories: 260,
      difficulty: "Easy",
      mealType: "Breakfast",
      dietary: "High Protein",
      categories: ["Quick Meals"],
      badge: "Breakfast Favorite",
      badgeTone: { bg: "#EEF4FF", border: "#D3E0F8", color: "#4B78B6" },
      image: "https://images.unsplash.com/photo-1488477181946-6428a0291777?auto=format&fit=crop&w=1400&q=80",
      cardTag: { label: "High Protein", color: "#4B8CCC" },
      ingredients: ["Greek yogurt", "Mixed berries", "Granola", "Chia seeds", "Honey drizzle"],
      steps: [
        "Layer yogurt, berries, and granola in a glass.",
        "Top with chia seeds and a light honey drizzle.",
        "Serve chilled for a quick balanced breakfast.",
      ],
      swapInsight: "Use unsweetened coconut yogurt if you want a dairy-free option.",
      reflection: "A light breakfast that still gives protein, color, and a steady start.",
      nutrientStory: ["Protein First", "Antioxidant Lift", "Light Carbs"],
      macro: { protein: 19, carbs: 27, fats: 7 },
    },
    {
      id: "energy-bites",
      title: "Peanut Oat Energy Bites",
      subtitle: "Small but satisfying snack for a quick lift between meals.",
      cuisine: "American",
      prep: "10 min",
      calories: 190,
      difficulty: "Easy",
      mealType: "Snack",
      dietary: "Quick Meal",
      categories: ["Quick Meals"],
      badge: "Snack Ready",
      badgeTone: { bg: "#FFF4E3", border: "#F2D29D", color: "#C8841A" },
      image: "https://images.unsplash.com/photo-1515003197210-e0cd71810b5f?auto=format&fit=crop&w=1400&q=80",
      cardTag: { label: "Quick Meal", color: "#F0A52D" },
      ingredients: ["Rolled oats", "Peanut butter", "Ground flax", "Dates", "Dark chocolate chips"],
      steps: [
        "Mix oats, peanut butter, and chopped dates until combined.",
        "Fold in flax and a few chocolate chips.",
        "Roll into bite-sized pieces and chill briefly before serving.",
      ],
      swapInsight: "Sunflower seed butter works well if you need a peanut-free version.",
      reflection: "A compact snack that helps energy stay steady without much prep.",
      nutrientStory: ["Healthy Fats", "Fiber Boost", "Portable Energy"],
      macro: { protein: 8, carbs: 18, fats: 9 },
    },
    {
      id: "ratatouille",
      title: "Herbed Ratatouille Bake",
      subtitle: "Layered vegetables with a slower oven finish and deeper flavor.",
      cuisine: "Mediterranean",
      prep: "30 min+",
      calories: 340,
      difficulty: "Advanced",
      mealType: "Dinner",
      dietary: "Vegetarian",
      categories: ["Salads"],
      badge: "Slow Cook Favorite",
      badgeTone: { bg: "#EEF7E5", border: "#CBE2AB", color: "#5B922A" },
      image: "https://images.unsplash.com/photo-1473093295043-cdd812d0e601?auto=format&fit=crop&w=1400&q=80",
      cardTag: { label: "Family Friendly", color: "#67A94B" },
      ingredients: ["Eggplant", "Zucchini", "Tomatoes", "Herbed sauce", "Olive oil"],
      steps: [
        "Slice vegetables evenly and layer over herbed tomato sauce.",
        "Brush lightly with olive oil and bake until tender.",
        "Rest briefly before serving so the layers hold together.",
      ],
      swapInsight: "Add white beans between layers if you want a little more protein.",
      reflection: "A slower, more hands-on dinner that still feels vibrant and nourishing.",
      nutrientStory: ["Fiber Build", "Veggie Density", "Comfort Carbs"],
      macro: { protein: 11, carbs: 29, fats: 14 },
    },
    {
      id: "lentil-soup",
      title: "Roasted Tomato Lentil Soup",
      subtitle: "Comforting, hearty, and easy to batch for the week.",
      cuisine: "Mediterranean",
      prep: "30 min+",
      calories: 310,
      difficulty: "Medium",
      mealType: "Lunch",
      dietary: "Vegetarian",
      categories: ["Soups"],
      badge: "Cozy Bowl",
      badgeTone: { bg: "#FFF4E3", border: "#F2D29D", color: "#C8841A" },
      image: "https://images.unsplash.com/photo-1547592166-23ac45744acd?auto=format&fit=crop&w=1400&q=80",
      cardTag: { label: "Fiber Rich", color: "#D28A2D" },
      ingredients: ["Red lentils", "Roasted tomatoes", "Garlic", "Vegetable stock", "Fresh basil"],
      steps: [
        "Roast tomatoes and garlic until softened and fragrant.",
        "Simmer with lentils and stock until the soup turns rich and silky.",
        "Blend lightly and finish with basil before serving.",
      ],
      swapInsight: "Add white beans if you want the soup to feel even more filling.",
      reflection: "A steady, cozy meal that works well for lunch or a lighter dinner.",
      nutrientStory: ["Fiber First", "Slow Energy", "Comfort Carbs"],
      macro: { protein: 16, carbs: 38, fats: 7 },
    },
    {
      id: "greek-salad",
      title: "Greek Chickpea Salad",
      subtitle: "Bright, briny, and filling enough for an easy lunch.",
      cuisine: "Mediterranean",
      prep: "10 min",
      calories: 290,
      difficulty: "Easy",
      mealType: "Lunch",
      dietary: "Vegetarian",
      categories: ["Salads", "Quick Meals"],
      badge: "Fresh Favorite",
      badgeTone: { bg: "#E8F4D8", border: "#C8E09A", color: "#5B922A" },
      image: "https://images.unsplash.com/photo-1540420773420-3366772f4999?auto=format&fit=crop&w=1400&q=80",
      cardTag: { label: "Fresh Pick", color: "#67A94B" },
      ingredients: ["Chickpeas", "Cucumber", "Tomato", "Olives", "Feta"],
      steps: ["Toss chopped vegetables with chickpeas and olives.", "Add feta and herbs.", "Dress lightly with lemon and olive oil."],
      swapInsight: "Skip feta and add avocado for a dairy-free version.",
      reflection: "A clean lunch with crunch, brightness, and staying power.",
      nutrientStory: ["Fiber First", "Hydration Boost", "Light Protein"],
      macro: { protein: 14, carbs: 25, fats: 12 },
    },
    {
      id: "kale-salad",
      title: "Citrus Kale Crunch Salad",
      subtitle: "Leafy, crisp, and lifted with orange and seeds.",
      cuisine: "American",
      prep: "15 min",
      calories: 260,
      difficulty: "Easy",
      mealType: "Lunch",
      dietary: "Low Carb",
      categories: ["Salads"],
      badge: "Fiber Lift",
      badgeTone: { bg: "#EEF7E5", border: "#CBE2AB", color: "#5B922A" },
      image: "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?auto=format&fit=crop&w=1400&q=80",
      cardTag: { label: "Low Carb", color: "#58A63D" },
      ingredients: ["Kale", "Orange", "Pumpkin seeds", "Parmesan", "Light vinaigrette"],
      steps: ["Massage kale with dressing.", "Top with orange segments and seeds.", "Finish with parmesan just before serving."],
      swapInsight: "Sunflower seeds work well if pumpkin seeds are unavailable.",
      reflection: "A sharper, more vibrant salad that still feels substantial.",
      nutrientStory: ["Fiber First", "Vitamin C", "Crunchy Fats"],
      macro: { protein: 11, carbs: 18, fats: 13 },
    },
    {
      id: "southwest-salad",
      title: "Southwest Chicken Salad",
      subtitle: "Smoky chicken, crisp romaine, and creamy avocado.",
      cuisine: "American",
      prep: "15 min",
      calories: 360,
      difficulty: "Easy",
      mealType: "Lunch",
      dietary: "High Protein",
      categories: ["Salads"],
      badge: "Protein Packed",
      badgeTone: { bg: "#FFF4D9", border: "#F0D38A", color: "#C58A15" },
      image: "https://images.unsplash.com/photo-1551248429-40975aa4de74?auto=format&fit=crop&w=1400&q=80",
      cardTag: { label: "High Protein", color: "#F0B23D" },
      ingredients: ["Chicken", "Romaine", "Corn", "Black beans", "Avocado"],
      steps: ["Slice cooked chicken.", "Layer over romaine with beans and corn.", "Top with avocado and lime dressing."],
      swapInsight: "Use grilled tofu for a plant-forward protein option.",
      reflection: "A fuller salad that still keeps lunch feeling fresh.",
      nutrientStory: ["Protein First", "Fiber Boost", "Balanced Carbs"],
      macro: { protein: 28, carbs: 24, fats: 14 },
    },
    {
      id: "pasta-salad",
      title: "Caprese Pasta Salad",
      subtitle: "A chilled pasta option with tomatoes, basil, and mozzarella.",
      cuisine: "Italian",
      prep: "10 min",
      calories: 330,
      difficulty: "Easy",
      mealType: "Lunch",
      dietary: "Family Friendly",
      categories: ["Salads", "Pasta", "Quick Meals"],
      badge: "Easy Lunch",
      badgeTone: { bg: "#EAF2FC", border: "#BED4F1", color: "#4E86C0" },
      image: "https://images.unsplash.com/photo-1529042410759-befb1204b468?auto=format&fit=crop&w=1400&q=80",
      cardTag: { label: "Family Friendly", color: "#4B8CCC" },
      ingredients: ["Cooked pasta", "Cherry tomatoes", "Mozzarella", "Basil", "Olive oil"],
      steps: ["Toss cooled pasta with tomatoes and mozzarella.", "Add basil and olive oil.", "Chill briefly before serving."],
      swapInsight: "Use chickpea pasta if you want a little more protein.",
      reflection: "A familiar lunch with softer comfort and bright flavor.",
      nutrientStory: ["Comfort Carbs", "Fresh Herbs", "Light Protein"],
      macro: { protein: 13, carbs: 39, fats: 11 },
    },
    {
      id: "teriyaki-bowl",
      title: "Teriyaki Tofu Bowl",
      subtitle: "Fast tofu, rice, and vegetables with a sweet-savory glaze.",
      cuisine: "Asian",
      prep: "15 min",
      calories: 370,
      difficulty: "Easy",
      mealType: "Dinner",
      dietary: "Vegetarian",
      categories: ["Bowls", "Asian"],
      badge: "Weeknight Bowl",
      badgeTone: { bg: "#EEF7E5", border: "#CBE2AB", color: "#5B922A" },
      image: "https://images.unsplash.com/photo-1512058564366-18510be2db19?auto=format&fit=crop&w=1400&q=80",
      cardTag: { label: "Vegetarian", color: "#67A94B" },
      ingredients: ["Tofu", "Rice", "Broccoli", "Carrots", "Teriyaki sauce"],
      steps: ["Sear tofu until golden.", "Cook vegetables until crisp-tender.", "Serve over rice with teriyaki glaze."],
      swapInsight: "Brown rice makes the bowl a little steadier and nuttier.",
      reflection: "A fast dinner bowl with satisfying texture and flavor.",
      nutrientStory: ["Protein First", "Veggie Lift", "Steady Carbs"],
      macro: { protein: 19, carbs: 42, fats: 10 },
    },
    {
      id: "salmon-bowl",
      title: "Sesame Salmon Rice Bowl",
      subtitle: "Tender salmon over rice with crunchy cucumber and cabbage.",
      cuisine: "Asian",
      prep: "20 min",
      calories: 410,
      difficulty: "Medium",
      mealType: "Dinner",
      dietary: "High Protein",
      categories: ["Bowls", "Asian"],
      badge: "Omega Bowl",
      badgeTone: { bg: "#EEF4FF", border: "#D3E0F8", color: "#4B78B6" },
      image: "https://images.unsplash.com/photo-1519708227418-c8fd9a32b7a2?auto=format&fit=crop&w=1400&q=80",
      cardTag: { label: "High Protein", color: "#4B8CCC" },
      ingredients: ["Salmon", "Rice", "Cucumber", "Cabbage", "Sesame dressing"],
      steps: ["Roast or sear salmon until flaky.", "Build the bowl with rice and vegetables.", "Finish with sesame dressing."],
      swapInsight: "Try farro for a chewier grain base.",
      reflection: "A richer bowl with strong protein and crunch.",
      nutrientStory: ["Omega Support", "Protein First", "Crisp Veg"],
      macro: { protein: 30, carbs: 32, fats: 16 },
    },
    {
      id: "burrito-bowl",
      title: "Harvest Burrito Bowl",
      subtitle: "Beans, rice, roasted corn, and avocado in one filling bowl.",
      cuisine: "American",
      prep: "15 min",
      calories: 390,
      difficulty: "Easy",
      mealType: "Lunch",
      dietary: "Family Friendly",
      categories: ["Bowls"],
      badge: "Lunch Bowl",
      badgeTone: { bg: "#FFF4E3", border: "#F2D29D", color: "#C8841A" },
      image: "https://images.unsplash.com/photo-1547592180-85f173990554?auto=format&fit=crop&w=1400&q=80",
      cardTag: { label: "Family Friendly", color: "#F0A52D" },
      ingredients: ["Rice", "Black beans", "Corn", "Avocado", "Salsa"],
      steps: ["Warm rice and beans.", "Add corn and avocado.", "Top with salsa and herbs."],
      swapInsight: "Greek yogurt can replace sour cream for extra protein.",
      reflection: "A familiar bowl that works well for lunch or dinner.",
      nutrientStory: ["Fiber First", "Comfort Carbs", "Healthy Fats"],
      macro: { protein: 14, carbs: 46, fats: 12 },
    },
    {
      id: "green-goddess-bowl",
      title: "Green Goddess Grain Bowl",
      subtitle: "Herby dressing, greens, and grains with a creamy finish.",
      cuisine: "Mediterranean",
      prep: "20 min",
      calories: 340,
      difficulty: "Easy",
      mealType: "Lunch",
      dietary: "Vegetarian",
      categories: ["Bowls"],
      badge: "Green Bowl",
      badgeTone: { bg: "#E8F4D8", border: "#C8E09A", color: "#5B922A" },
      image: "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?auto=format&fit=crop&w=1400&q=80",
      cardTag: { label: "Vegetarian", color: "#67A94B" },
      ingredients: ["Farro", "Greens", "Cucumber", "Herb dressing", "Edamame"],
      steps: ["Cook grains and cool slightly.", "Layer with greens and cucumber.", "Finish with herb dressing."],
      swapInsight: "Quinoa works well if you want a softer bowl base.",
      reflection: "A calmer, green-forward bowl that still feels complete.",
      nutrientStory: ["Fiber First", "Green Density", "Light Protein"],
      macro: { protein: 15, carbs: 35, fats: 11 },
    },
    {
      id: "miso-soup",
      title: "Miso Veggie Soup",
      subtitle: "Light broth with tofu, greens, and umami depth.",
      cuisine: "Asian",
      prep: "10 min",
      calories: 180,
      difficulty: "Easy",
      mealType: "Lunch",
      dietary: "Quick Meal",
      categories: ["Soups", "Asian", "Quick Meals"],
      badge: "Light Soup",
      badgeTone: { bg: "#EEF4FF", border: "#D3E0F8", color: "#4B78B6" },
      image: "https://images.unsplash.com/photo-1547928576-b822bc410bdf?auto=format&fit=crop&w=1400&q=80",
      cardTag: { label: "Quick Meal", color: "#4B8CCC" },
      ingredients: ["Miso paste", "Tofu", "Scallions", "Spinach", "Mushrooms"],
      steps: ["Warm broth gently.", "Add tofu and vegetables.", "Stir in miso off heat."],
      swapInsight: "Add noodles if you want the soup to feel more meal-like.",
      reflection: "A lighter option when you want something warm but not heavy.",
      nutrientStory: ["Hydration Boost", "Light Protein", "Warm Umami"],
      macro: { protein: 10, carbs: 14, fats: 6 },
    },
    {
      id: "chicken-noodle",
      title: "Chicken Noodle Soup",
      subtitle: "Comforting broth with vegetables and tender chicken.",
      cuisine: "American",
      prep: "30 min+",
      calories: 330,
      difficulty: "Medium",
      mealType: "Dinner",
      dietary: "Family Friendly",
      categories: ["Soups"],
      badge: "Comfort Classic",
      badgeTone: { bg: "#FFF4E3", border: "#F2D29D", color: "#C8841A" },
      image: "https://images.unsplash.com/photo-1603105037880-880cd4edfb0d?auto=format&fit=crop&w=1400&q=80",
      cardTag: { label: "Family Friendly", color: "#F0A52D" },
      ingredients: ["Chicken", "Noodles", "Carrots", "Celery", "Broth"],
      steps: ["Simmer chicken and vegetables.", "Add noodles near the end.", "Finish with herbs."],
      swapInsight: "Use whole grain noodles for a steadier carb base.",
      reflection: "A familiar soup that feels restorative and easy to share.",
      nutrientStory: ["Comfort Carbs", "Warm Protein", "Broth Hydration"],
      macro: { protein: 24, carbs: 29, fats: 8 },
    },
    {
      id: "curry-soup",
      title: "Coconut Curry Vegetable Soup",
      subtitle: "Silky coconut broth with vegetables and warm spice.",
      cuisine: "Asian",
      prep: "20 min",
      calories: 320,
      difficulty: "Medium",
      mealType: "Dinner",
      dietary: "Vegetarian",
      categories: ["Soups", "Asian"],
      badge: "Warm Spice",
      badgeTone: { bg: "#FFF4D9", border: "#F0D38A", color: "#C58A15" },
      image: "https://images.unsplash.com/photo-1455619452474-d2be8b1e70cd?auto=format&fit=crop&w=1400&q=80",
      cardTag: { label: "Vegetarian", color: "#F0B23D" },
      ingredients: ["Coconut milk", "Carrots", "Peppers", "Broth", "Curry paste"],
      steps: ["Saute aromatics.", "Simmer with broth and vegetables.", "Finish with coconut milk."],
      swapInsight: "Add tofu cubes if you want a stronger protein base.",
      reflection: "A warmer, richer soup that still keeps vegetables at the center.",
      nutrientStory: ["Warm Spice", "Veggie Lift", "Silky Broth"],
      macro: { protein: 9, carbs: 26, fats: 18 },
    },
    {
      id: "minestrone",
      title: "Minestrone Pasta Soup",
      subtitle: "Tomato broth, beans, vegetables, and pasta in one pot.",
      cuisine: "Italian",
      prep: "20 min",
      calories: 300,
      difficulty: "Easy",
      mealType: "Lunch",
      dietary: "Vegetarian",
      categories: ["Soups", "Pasta"],
      badge: "Pantry Hero",
      badgeTone: { bg: "#EAF2FC", border: "#BED4F1", color: "#4E86C0" },
      image: "https://images.unsplash.com/photo-1476718406336-bb5a9690ee2a?auto=format&fit=crop&w=1400&q=80",
      cardTag: { label: "Vegetarian", color: "#4B8CCC" },
      ingredients: ["Beans", "Small pasta", "Tomato broth", "Carrots", "Celery"],
      steps: ["Simmer vegetables in tomato broth.", "Add beans and pasta.", "Cook until tender and finish with herbs."],
      swapInsight: "Use whole wheat pasta for more fiber.",
      reflection: "A pantry-friendly soup that feels generous and balanced.",
      nutrientStory: ["Fiber First", "Comfort Carbs", "Plant Protein"],
      macro: { protein: 13, carbs: 41, fats: 5 },
    },
    {
      id: "ricotta-pasta",
      title: "Spinach Ricotta Pasta",
      subtitle: "Creamy but fresh pasta with wilted greens.",
      cuisine: "Italian",
      prep: "15 min",
      calories: 360,
      difficulty: "Easy",
      mealType: "Dinner",
      dietary: "Vegetarian",
      categories: ["Pasta"],
      badge: "Creamy Favorite",
      badgeTone: { bg: "#EAF2FC", border: "#BED4F1", color: "#4E86C0" },
      image: "https://images.unsplash.com/photo-1555949258-eb67b1ef0ceb?auto=format&fit=crop&w=1400&q=80",
      cardTag: { label: "Vegetarian", color: "#4B8CCC" },
      ingredients: ["Pasta", "Ricotta", "Spinach", "Garlic", "Parmesan"],
      steps: ["Cook pasta until al dente.", "Stir ricotta with a splash of pasta water.", "Fold in spinach and parmesan."],
      swapInsight: "Cottage cheese can lighten the sauce while keeping protein up.",
      reflection: "A softer pasta option that still brings in greens.",
      nutrientStory: ["Comfort Carbs", "Creamy Protein", "Greens Lift"],
      macro: { protein: 18, carbs: 43, fats: 11 },
    },
    {
      id: "pesto-penne",
      title: "Pesto Penne with Peas",
      subtitle: "Bright basil pesto with peas for a quick weeknight dinner.",
      cuisine: "Italian",
      prep: "15 min",
      calories: 340,
      difficulty: "Easy",
      mealType: "Dinner",
      dietary: "Family Friendly",
      categories: ["Pasta", "Quick Meals"],
      badge: "Fast Pasta",
      badgeTone: { bg: "#EEF7E5", border: "#CBE2AB", color: "#5B922A" },
      image: "https://images.unsplash.com/photo-1473093295043-cdd812d0e601?auto=format&fit=crop&w=1400&q=80",
      cardTag: { label: "Family Friendly", color: "#67A94B" },
      ingredients: ["Penne", "Pesto", "Peas", "Parmesan", "Lemon zest"],
      steps: ["Cook pasta and peas together.", "Toss with pesto and parmesan.", "Finish with lemon zest."],
      swapInsight: "Use arugula pesto for a pepperier finish.",
      reflection: "A quicker pasta that still tastes lively and fresh.",
      nutrientStory: ["Quick Carbs", "Green Herbs", "Family Appeal"],
      macro: { protein: 14, carbs: 42, fats: 10 },
    },
    {
      id: "sesame-noodles",
      title: "Sesame Noodle Toss",
      subtitle: "Cold noodles with crunchy vegetables and a savory sauce.",
      cuisine: "Asian",
      prep: "10 min",
      calories: 320,
      difficulty: "Easy",
      mealType: "Lunch",
      dietary: "Quick Meal",
      categories: ["Pasta", "Asian", "Quick Meals"],
      badge: "Fast Lunch",
      badgeTone: { bg: "#FFF4E3", border: "#F2D29D", color: "#C8841A" },
      image: "https://images.unsplash.com/photo-1617093727343-374698b1b08d?auto=format&fit=crop&w=1400&q=80",
      cardTag: { label: "Quick Meal", color: "#F0A52D" },
      ingredients: ["Noodles", "Cucumber", "Carrots", "Sesame sauce", "Scallions"],
      steps: ["Cook and cool noodles.", "Toss with vegetables and sauce.", "Top with scallions before serving."],
      swapInsight: "Add edamame if you want extra protein.",
      reflection: "A chilled noodle dish that works well for a quick lunch.",
      nutrientStory: ["Quick Carbs", "Crunchy Veg", "Savory Sauce"],
      macro: { protein: 11, carbs: 44, fats: 9 },
    },
  ];

  const filterOptions = {
    prep: ["Prep Time", "5 min", "10 min", "15 min", "20 min", "30 min+"],
    mealType: ["Meal Type", "Breakfast", "Lunch", "Dinner", "Snack"],
    dietary: ["Dietary Needs", "High Protein", "Low Carb", "Vegetarian", "Family Friendly", "Quick Meal"],
    calories: ["Calories", "< 300", "300-400", "400+"],
    difficulty: ["Difficulty", "Easy", "Medium", "Advanced"],
    cuisine: ["Cuisine", "Mediterranean", "Asian", "American", "Italian"],
  };

  const smartPicks = [
    {
      icon: "🍑",
      label: "Boost Your Protein",
      hint: "Keep the plate fuller and more satisfying.",
      sideAddOn: "Optional side: Greek yogurt dip",
    },
    {
      icon: "🧊",
      label: "Stay Hydrated Today",
      hint: "A lighter meal pairs well with extra fluids.",
      sideAddOn: "Optional side: Lemon-mint water",
    },
    {
      icon: "🥗",
      label: "Need More Fiber?",
      hint: "Add something crisp and colorful on the side.",
      sideAddOn: "Optional side: Cucumber salad cup",
    },
    {
      icon: "🍅",
      label: "Energize Your Lunch",
      hint: "Round it out with a fresh, simple add-on.",
      sideAddOn: "Optional side: Citrus tomato bowl",
    },
  ];

  const categories = [
    {
      icon: "🥗",
      label: "Salads",
      description: "Fresh, crisp, and lighter options for energized meals.",
    },
    {
      icon: "🥣",
      label: "Bowls",
      description: "Balanced bowls with grains, protein, and vegetables.",
    },
    {
      icon: "🍲",
      label: "Soups",
      description: "Comforting, spoonable recipes that still feel nourishing.",
    },
    {
      icon: "🍝",
      label: "Pasta",
      description: "Comfort meals with a little more warmth and familiarity.",
    },
    {
      icon: "🥡",
      label: "Asian",
      description: "Fast savory dishes with bold sauces and crisp vegetables.",
    },
    {
      icon: "🍱",
      label: "Quick Meals",
      description: "Fast recipes for busy moments and lighter prep windows.",
    },
  ];

  useEffect(() => {
    if (!smartPickToast) return undefined;
    const timer = setTimeout(() => setSmartPickToast(""), 2200);
    return () => clearTimeout(timer);
  }, [smartPickToast]);

  const applyRecipeFilters = (recipe) => {
    const matchesSearch =
      !search ||
      recipe.title.toLowerCase().includes(search.toLowerCase()) ||
      recipe.subtitle.toLowerCase().includes(search.toLowerCase()) ||
      recipe.dietary.toLowerCase().includes(search.toLowerCase()) ||
      recipe.cuisine.toLowerCase().includes(search.toLowerCase());
    const matchesPrep = selectedPrep === "Prep Time" || recipe.prep === selectedPrep;
    const matchesMealType = selectedMealType === "Meal Type" || recipe.mealType === selectedMealType;
    const matchesDietary = selectedDietary === "Dietary Needs" || recipe.dietary === selectedDietary;
    const matchesDifficulty = selectedDifficulty === "Difficulty" || recipe.difficulty === selectedDifficulty;
    const matchesCuisine = selectedCuisine === "Cuisine" || recipe.cuisine === selectedCuisine;
    const matchesCalories =
      selectedCalories === "Calories" ||
      (selectedCalories === "< 300" && recipe.calories < 300) ||
      (selectedCalories === "300-400" && recipe.calories >= 300 && recipe.calories <= 400) ||
      (selectedCalories === "400+" && recipe.calories > 400);

    return matchesSearch && matchesPrep && matchesMealType && matchesDietary && matchesDifficulty && matchesCuisine && matchesCalories;
  };

  const filteredRecipes = recipeCollections.filter(applyRecipeFilters);
  const activeCategory = categories.find((category) => category.label === selectedCategory) || categories[0];
  const categoryRecipes = recipeCollections.filter((recipe) => (recipe.categories || []).includes(activeCategory.label));
  const activeFilterEntries = [
    selectedPrep !== "Prep Time" ? { key: "prep", icon: "⏱", label: selectedPrep, clear: () => setSelectedPrep("Prep Time") } : null,
    selectedMealType !== "Meal Type" ? { key: "mealType", icon: "🍽", label: selectedMealType, clear: () => setSelectedMealType("Meal Type") } : null,
    selectedDietary !== "Dietary Needs" ? { key: "dietary", icon: "🥬", label: selectedDietary, clear: () => setSelectedDietary("Dietary Needs") } : null,
    selectedCalories !== "Calories" ? { key: "calories", icon: "🔥", label: selectedCalories, clear: () => setSelectedCalories("Calories") } : null,
    selectedDifficulty !== "Difficulty" ? { key: "difficulty", icon: "⭐", label: selectedDifficulty, clear: () => setSelectedDifficulty("Difficulty") } : null,
    selectedCuisine !== "Cuisine" ? { key: "cuisine", icon: "🌍", label: selectedCuisine, clear: () => setSelectedCuisine("Cuisine") } : null,
  ].filter(Boolean);
  const hasCuratedRecipeFilters = activeFilterEntries.length > 0;
  const featuredRecipe = filteredRecipes[0] || recipeCollections[0];
  const plannerDays = plannerState?.days || [];
  const defaultPlannerStartIndex = Math.min(Math.max(selectedDayIndex ?? 0, 0), Math.max(plannerDays.length - 1, 0));
  const plannerStartIndex = Math.min(Math.max(selectedPlanStartDayIndex ?? defaultPlannerStartIndex, 0), Math.max(plannerDays.length - 1, 0));
  const plannerStartDay = plannerDays[plannerStartIndex];
  const plannerEndDay = plannerDays[plannerDays.length - 1];
  const plannerRangeLabel =
    plannerStartDay && plannerEndDay ? `${plannerStartDay.display} to ${plannerEndDay.display}` : "this week";
  const recipeOfTheDay = plannerDay?.meals?.dinner
    ? {
        ...featuredRecipe,
        title: plannerDay.meals.dinner.name,
        calories: plannerDay.meals.dinner.calories,
        image: plannerDay.meals.dinner.image,
      }
    : featuredRecipe;

  const showRecipeDetails = (recipe) => {
    trackRecipeUsage(recipe.id);
    setSelectedRecipe(recipe);
  };
  const getRecipeSuggestedSlot = (recipe) => {
    const mealType = String(recipe?.mealType || "").toLowerCase();
    if (mealType.includes("breakfast")) return "breakfast";
    if (mealType.includes("lunch")) return "lunch";
    if (mealType.includes("snack")) return "snack";
    return "dinner";
  };
  const openAddToPlanModal = () => {
    setSelectedPlanMealSlot(getRecipeSuggestedSlot(selectedRecipe));
    setSelectedPlanStartDayIndex(defaultPlannerStartIndex);
    setShowAddToPlanModal(true);
  };
  const closeAddToPlanModal = () => setShowAddToPlanModal(false);
  const closeSmartPickModal = () => {
    setSelectedSmartPick(null);
    setShowSmartPickMealChooser(false);
    setSelectedSmartPickMealSlot("dinner");
  };
  const saveRecipeToPlanner = () => {
    if (!selectedRecipe || !setPlannerState || !plannerDays.length) return;
    const slotLabels = {
      breakfast: "Breakfast",
      lunch: "Lunch",
      dinner: "Dinner",
      snack: "Snack",
    };
    const slotEmojis = {
      breakfast: "🥣",
      lunch: "🥗",
      dinner: "🍽",
      snack: "🍎",
    };
    const buildRecipeMealEntry = (slot, existingMeal) => ({
      ...existingMeal,
      name: selectedRecipe.title,
      calories: selectedRecipe.calories,
      protein: selectedRecipe.macro?.protein ?? existingMeal?.protein ?? 0,
      image: selectedRecipe.image,
      tip: selectedRecipe.swapInsight || selectedRecipe.reflection,
      nutrients: {
        Protein: Math.min(100, Math.round(((selectedRecipe.macro?.protein || 0) / 40) * 100)),
        Carbs: Math.min(100, Math.round(((selectedRecipe.macro?.carbs || 0) / 50) * 100)),
        Fats: Math.min(100, Math.round(((selectedRecipe.macro?.fats || 0) / 25) * 100)),
      },
      emoji: slotEmojis[slot],
      slotType: slot,
      label: existingMeal?.label || slotLabels[slot],
      prep: selectedRecipe.prep,
      dietary: selectedRecipe.dietary,
      subtitle: selectedRecipe.subtitle,
      cuisine: selectedRecipe.cuisine,
    });

    setPlannerState((current) => {
      const days = (current.days || []).map((day, index) => {
        if (index < plannerStartIndex) return day;
        const updatedMeals = {
          ...day.meals,
          [selectedPlanMealSlot]: buildRecipeMealEntry(selectedPlanMealSlot, day.meals[selectedPlanMealSlot]),
        };
        const totalCalories = Object.values(updatedMeals).reduce((sum, meal) => sum + (meal?.calories || 0), 0);
        return {
          ...day,
          meals: updatedMeals,
          totalCalories,
        };
      });
      return {
        ...current,
        days,
        selectedDayIndex: plannerStartIndex,
      };
    });

    setShowAddToPlanModal(false);
    setSelectedRecipe(null);
    setStep("weeklyPlanner");
  };
  const saveSmartPickToPlanner = () => {
    if (!selectedSmartPick || !setPlannerState) return;
    const sideSuggestion = selectedSmartPick.sideAddOn.replace("Optional side: ", "");
    const slotLabels = {
      breakfast: "Breakfast",
      lunch: "Lunch",
      dinner: "Dinner",
      snack: "Snack",
    };

    setPlannerState((current) => {
      const nextSelectedDayIndex = Math.min(Math.max(selectedDayIndex ?? 0, 0), Math.max((current.days || []).length - 1, 0));
      const days = (current.days || []).map((day, index) => {
        if (index !== nextSelectedDayIndex) return day;
        const currentMeal = day.meals?.[selectedSmartPickMealSlot];
        if (!currentMeal) return day;
        const updatedMeals = {
          ...day.meals,
          [selectedSmartPickMealSlot]: {
            ...currentMeal,
            sideSuggestion,
            sideSuggestionSource: selectedSmartPick.label,
          },
        };
        return {
          ...day,
          meals: updatedMeals,
        };
      });
      return {
        ...current,
        days,
        selectedDayIndex: nextSelectedDayIndex,
      };
    });

    setSmartPickToast(`${sideSuggestion} saved to ${slotLabels[selectedSmartPickMealSlot].toLowerCase()} for ${plannerDay?.longDay || "today"}.`);
    closeSmartPickModal();
  };

  const filterSelectStyle = {
    appearance: "none",
    WebkitAppearance: "none",
    MozAppearance: "none",
    border: "1px solid #C9D8EE",
    borderRadius: 16,
    background: "linear-gradient(180deg, #FFFFFF, #EEF5FF)",
    padding: "12px 44px 12px 42px",
    color: "#234A80",
    fontSize: 14,
    fontWeight: 800,
    outline: "none",
    cursor: "pointer",
    minWidth: 156,
    boxShadow: "0 10px 22px rgba(72, 88, 120, 0.08)",
  };

  const renderFilterSelect = (value, options, onChange, icon) => (
    <label
      style={{
        position: "relative",
        display: "inline-flex",
        alignItems: "center",
      }}
    >
      <span
        style={{
          position: "absolute",
          left: 14,
          width: 20,
          height: 20,
          borderRadius: 999,
          background: "linear-gradient(180deg, #EAF3FF, #D5E6FB)",
          color: "#3C6698",
          display: "grid",
          placeItems: "center",
          fontSize: 11,
          boxShadow: "inset 0 1px 0 rgba(255,255,255,0.85)",
          pointerEvents: "none",
        }}
      >
        {icon}
      </span>
      <select value={value} onChange={(event) => onChange(event.target.value)} style={filterSelectStyle}>
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
      <span style={{ position: "absolute", right: 16, pointerEvents: "none", color: "#6F89AB", fontSize: 12 }}>⌄</span>
    </label>
  );

  const clearAllRecipeFilters = () => {
    setSelectedPrep("Prep Time");
    setSelectedMealType("Meal Type");
    setSelectedDietary("Dietary Needs");
    setSelectedCalories("Calories");
    setSelectedDifficulty("Difficulty");
    setSelectedCuisine("Cuisine");
  };

  const trackRecipeUsage = (recipeId) => {
    const updated = [recipeId, ...frequentlyUsedRecipes.filter(id => id !== recipeId)].slice(0, 6);
    setFrequentlyUsedRecipes(updated);
    try {
      localStorage.setItem(`mazimeal:frequently-used-recipes:${user || "guest"}`, JSON.stringify(updated));
    } catch {}
  };

  const toggleFavorite = (recipeId) => {
    const isFavorite = favoriteRecipes.includes(recipeId);
    const updated = isFavorite
      ? favoriteRecipes.filter(id => id !== recipeId)
      : [...favoriteRecipes, recipeId];
    setFavoriteRecipes(updated);
    try {
      localStorage.setItem(`mazimeal:favorite-recipes:${user || "guest"}`, JSON.stringify(updated));
    } catch {}
  };

  const recipeSectionTabMeta = {
    explore: {
      icon: "🍽",
      accent: "#D58A18",
      ribbon: "Search, filter, and discover",
      helper: "Find recipes that fit your prep time, meal type, and calorie rhythm.",
    },
    smartPicks: {
      icon: "✨",
      accent: "#5A9A39",
      ribbon: "Quick personalized boosts",
      helper: "Surface simple add-ons and meal ideas that support today's goals.",
    },
    categories: {
      icon: "🥗",
      accent: "#3E78B7",
      ribbon: "Browse by cooking mood",
      helper: "Jump into salads, bowls, soups, pasta, and more in one place.",
    },
  };

  const renderRecipeSectionTab = (title, sectionKey) => {
    const isActive = activeRecipeSection === sectionKey;
    const meta = recipeSectionTabMeta[sectionKey];

    return (
    <button
      type="button"
      onClick={() => {
        const newSection = activeRecipeSection === sectionKey ? null : sectionKey;
        setActiveRecipeSection(newSection);
        if (newSection === "explore" || newSection === "categories") {
          setTimeout(() => {
            const element = document.querySelector(`[data-recipe-section="${newSection}"]`);
            if (element) {
              element.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
          }, 100);
        }
      }}
      style={{
        width: "100%",
        border: isActive ? `1px solid ${meta.accent}55` : "1px solid #D7DFEB",
        borderRadius: 24,
        background: isActive
          ? `linear-gradient(180deg, ${meta.accent}12, rgba(255,255,255,0.98) 48%, rgba(248,250,255,0.94))`
          : "linear-gradient(180deg, rgba(255,255,255,0.98), rgba(246,250,255,0.9))",
        padding: "18px 18px 16px",
        display: "flex",
        flexDirection: "column",
        alignItems: "flex-start",
        justifyContent: "space-between",
        gap: 16,
        cursor: "pointer",
        boxShadow: isActive ? `0 18px 34px ${meta.accent}20` : "0 10px 24px rgba(72, 88, 120, 0.06)",
        textAlign: "left",
        minHeight: 148,
        transition: "all 160ms ease",
        position: "relative",
        overflow: "hidden",
      }}
    >
      <span
        style={{
          position: "absolute",
          inset: "0 auto auto 0",
          width: "100%",
          height: 4,
          background: isActive
            ? `linear-gradient(90deg, ${meta.accent}, ${meta.accent}99)`
            : "linear-gradient(90deg, #DCE7F6, #EEF3FB)",
        }}
      />
      <span style={{ display: "grid", gap: 10, width: "100%" }}>
        <span style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span
            style={{
              width: 42,
              height: 42,
              borderRadius: 14,
              display: "grid",
              placeItems: "center",
              fontSize: 22,
              background: isActive
                ? `linear-gradient(180deg, ${meta.accent}22, ${meta.accent}10)`
                : "linear-gradient(180deg, #EEF4FF, #E3ECFA)",
              boxShadow: "inset 0 1px 0 rgba(255,255,255,0.9)",
            }}
          >
            {meta.icon}
          </span>
          <span style={{ display: "grid", gap: 4 }}>
            <span style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 22, color: "#214A86" }}>{title}</span>
            <span style={{ color: isActive ? meta.accent : "#6E819E", fontSize: 12, fontWeight: 800, letterSpacing: "0.04em", textTransform: "uppercase" }}>
              {meta.ribbon}
            </span>
          </span>
        </span>
        <span style={{ color: "#60738F", fontSize: 14, lineHeight: 1.5, maxWidth: 320 }}>{meta.helper}</span>
      </span>
      {isActive && (
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 8,
            padding: "7px 12px",
            borderRadius: 999,
            background: `linear-gradient(180deg, ${meta.accent}, ${meta.accent}CC)`,
            color: "#FFFFFF",
            fontSize: 13,
            fontWeight: 700,
            boxShadow: "inset 0 1px 0 rgba(255,255,255,0.85)",
          }}
        >
          Now viewing
        </span>
      )}
    </button>
    );
  };

  return (
    <>
      <div style={{ padding: "26px 20px 40px", maxWidth: 1180, margin: "0 auto", display: "grid", gap: 22 }}>

        <div className="card" style={{ ...plannerInspiredShell, minHeight: 0 }}>
          <div style={{ position: "absolute", inset: 0, backgroundImage: `linear-gradient(180deg, rgba(255,253,248,0.92), rgba(255,253,248,0.74)), url('${recipeOfTheDay.image}')`, backgroundSize: "cover", backgroundPosition: "center" }} />
          <div style={{ position: "absolute", inset: 0, background: "linear-gradient(180deg, rgba(255,255,255,0.18), rgba(245,241,232,0.74))" }} />
          <div style={{ position: "relative", zIndex: 1, padding: "22px 24px 24px", display: "grid", gap: 18 }}>
            <div style={{ color: C.accent, fontSize: 13, fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase" }}>Recipes</div>
            <div style={{ textAlign: "center", marginBottom: 12 }}>
              <h1 style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 28, color: "#214A86", margin: 0 }}>
                Find meals that fit your rhythm, {user || "Nav"}.
              </h1>
              <p style={{ color: "#5E6E86", marginTop: 8, fontSize: 15 }}>
                Personalized suggestions update daily based on your habits.
              </p>
            </div>
            <div className="card" style={{ ...plannerInspiredGlass, position: "relative", padding: "28px 28px 24px" }}>
              <div style={{ position: "absolute", top: -18, left: "50%", transform: "translateX(-50%)", background: "rgba(255,249,236,0.96)", border: "1px solid #E6DCC2", borderRadius: 16, padding: "8px 20px", color: "#3C6698", fontFamily: "'Lora'", fontSize: 16, fontWeight: 700 }}>
                - Featured Recipe of the Day -
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "260px minmax(0, 1fr) 170px", gap: 22, alignItems: "center" }}>
                <div style={{ height: 154, borderRadius: 10, backgroundImage: `url('${recipeOfTheDay.image}')`, backgroundSize: "cover", backgroundPosition: "center", boxShadow: "0 8px 20px rgba(72, 88, 120, 0.12)" }} />
                <div>
                  <div style={{ fontFamily: "'Lora'", fontSize: 32, fontWeight: 700, color: "#214A86" }}>{recipeOfTheDay.title}</div>
                  <div style={{ color: "#5D6D83", marginTop: 10, fontSize: 17 }}>{recipeOfTheDay.subtitle}</div>
                  <div style={{ color: "#344D71", marginTop: 18, fontSize: 18 }}>{recipeOfTheDay.prep} | {recipeOfTheDay.calories} kcal</div>
                  <div style={{ marginTop: 14, display: "inline-flex", alignItems: "center", gap: 8, background: recipeOfTheDay.badgeTone.bg, border: `1px solid ${recipeOfTheDay.badgeTone.border}`, borderRadius: 10, padding: "8px 12px", color: recipeOfTheDay.badgeTone.color, fontWeight: 700 }}>
                    <span style={{ width: 10, height: 10, borderRadius: 999, background: recipeOfTheDay.badgeTone.color, opacity: 0.8 }} />
                    {recipeOfTheDay.badge}
                  </div>
                </div>
                <button className="btn-primary" style={{ background: "linear-gradient(180deg, #4E8DD0, #2E67A4)", borderColor: "#2E67A4", minWidth: 150, justifySelf: "end" }} onClick={() => showRecipeDetails(recipeOfTheDay)}>
                  View Recipe ›
                </button>
              </div>
            </div>

            <div style={{ display: "grid", gap: 14 }}>
              <div style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 20, color: "#214A86" }}>⭐ Your Frequently Used Recipes</div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 12 }}>
                {recipeCollections
                  .filter(recipe => frequentlyUsedRecipes.includes(recipe.id))
                  .map((recipe) => (
                    <div key={recipe.id} className="card" style={{ ...plannerInspiredGlass, padding: 12, display: "grid", gap: 10, position: "relative" }}>
                      <button
                        style={{
                          position: "absolute",
                          top: 12,
                          right: 12,
                          background: "rgba(255, 255, 255, 0.9)",
                          border: "1px solid #E6DCC2",
                          borderRadius: 20,
                          width: 36,
                          height: 36,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          fontSize: 18,
                          cursor: "pointer",
                          zIndex: 10,
                          transition: "all 0.2s ease",
                        }}
                        onClick={() => toggleFavorite(recipe.id)}
                        onMouseEnter={(e) => { e.target.style.background = "rgba(255, 255, 255, 1)"; e.target.style.boxShadow = "0 2px 8px rgba(72, 88, 120, 0.15)"; }}
                        onMouseLeave={(e) => { e.target.style.background = "rgba(255, 255, 255, 0.9)"; e.target.style.boxShadow = "none"; }}
                        title={favoriteRecipes.includes(recipe.id) ? "Remove from favorites" : "Add to favorites"}
                      >
                        {favoriteRecipes.includes(recipe.id) ? "♥" : "🤍"}
                      </button>
                      <div style={{ height: 100, borderRadius: 10, backgroundImage: `url('${recipe.image}')`, backgroundSize: "cover", backgroundPosition: "center" }} />
                      <div style={{ fontWeight: 700, fontSize: 14, color: "#214A86", lineHeight: 1.3 }}>{recipe.title}</div>
                      <div style={{ color: "#5D6D83", fontSize: 12 }}>{recipe.prep} | {recipe.calories} kcal</div>
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                        <button
                          className="btn-primary"
                          style={{ flex: 1, minWidth: 70, padding: "6px 8px", fontSize: 12, background: "linear-gradient(180deg, #4E8DD0, #2E67A4)", borderColor: "#2E67A4" }}
                          onClick={() => { trackRecipeUsage(recipe.id); showRecipeDetails(recipe); }}
                        >
                          View
                        </button>
                        <button
                          className="btn-ghost"
                          style={{ flex: 1, minWidth: 70, padding: "6px 8px", fontSize: 12, background: "#F9FBFF", borderColor: "#CCD5E5", color: "#24487B" }}
                          onClick={() => { trackRecipeUsage(recipe.id); setSelectedRecipe(recipe); setShowAddToPlanModal(true); }}
                        >
                          Add to Plan
                        </button>
                      </div>
                    </div>
                  ))}
              </div>
            </div>

            <div style={{ display: "grid", gap: 16 }}>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 12 }}>
                {renderRecipeSectionTab("Explore Recipes", "explore")}
                {renderRecipeSectionTab("Smart Picks for Your Day", "smartPicks")}
                {renderRecipeSectionTab("Browse by Category", "categories")}
              </div>

              {activeRecipeSection && (
                <div className="card" style={{ ...plannerInspiredGlass, padding: 18 }}>
              {activeRecipeSection === "explore" && (
              <div data-recipe-section="explore" style={{ display: "grid", gap: 12 }}>
              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: 10,
                  justifyContent: "center",
                  alignItems: "center",
                  border: `1px solid ${C.border}`,
                  borderRadius: 18,
                  padding: "14px 16px",
                  background: "rgba(255,255,255,0.78)",
                  backdropFilter: "blur(8px)",
                  boxShadow: "0 10px 24px rgba(72, 88, 120, 0.06)",
                }}
              >
                {renderFilterSelect(selectedPrep, filterOptions.prep, setSelectedPrep, "⏱")}
                {renderFilterSelect(selectedMealType, filterOptions.mealType, setSelectedMealType, "🍽")}
                {renderFilterSelect(selectedDietary, filterOptions.dietary, setSelectedDietary, "🥬")}
                {renderFilterSelect(selectedCalories, filterOptions.calories, setSelectedCalories, "🔥")}
                {renderFilterSelect(selectedDifficulty, filterOptions.difficulty, setSelectedDifficulty, "⭐")}
                {renderFilterSelect(selectedCuisine, filterOptions.cuisine, setSelectedCuisine, "🌍")}
              </div>
              {hasCuratedRecipeFilters ? (
                <>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
                    <div style={{ color: "#4E678B", fontSize: 15 }}>
                      Curated for you: <strong style={{ color: "#214A86" }}>{filteredRecipes.length}</strong> matching recipe{filteredRecipes.length === 1 ? "" : "s"}
                    </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "flex-end" }}>
                    {activeFilterEntries.map((entry) => (
                      <button
                        type="button"
                        onClick={entry.clear}
                        key={entry.key}
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 8,
                          padding: "7px 12px",
                          borderRadius: 999,
                          background: "linear-gradient(180deg, #EEF7E5, #E1F0D0)",
                          border: "1px solid #C9E0A8",
                          color: "#5A892C",
                          fontWeight: 700,
                          boxShadow: "0 8px 18px rgba(90, 137, 44, 0.12)",
                          cursor: "pointer",
                        }}
                      >
                        <span style={{ fontSize: 15 }}>{entry.icon}</span>
                        <span>{entry.label}</span>
                        <span style={{ fontSize: 14, lineHeight: 1, paddingLeft: 2 }}>×</span>
                      </button>
                    ))}
                    <button
                      type="button"
                      onClick={clearAllRecipeFilters}
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 8,
                        padding: "7px 12px",
                        borderRadius: 999,
                        border: "1px solid #D7DFEB",
                        background: "linear-gradient(180deg, #FFFFFF, #F6F9FF)",
                        color: "#49627E",
                        fontWeight: 700,
                        boxShadow: "0 8px 18px rgba(72, 88, 120, 0.08)",
                        cursor: "pointer",
                      }}
                    >
                      Clear all
                    </button>
                  </div>
                  </div>
                  {filteredRecipes.length === 0 ? (
                    <div className="card" style={{ ...plannerInspiredGlass, padding: 28, textAlign: "center" }}>
                      <div style={{ fontFamily: "'Lora'", fontSize: 24, fontWeight: 700, color: "#214A86" }}>No recipes match this filter set yet</div>
                      <div style={{ marginTop: 10, color: "#5D6D83", fontSize: 16 }}>
                        Try a different prep time, meal type, calorie range, or cuisine to broaden the results.
                      </div>
                    </div>
                  ) : (
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 16 }}>
                      {filteredRecipes.slice(0, 10).map((recipe) => (
                        <div key={recipe.id} className="card" style={{ ...plannerInspiredGlass, padding: 14, position: "relative" }}>
                          <button
                            style={{
                              position: "absolute",
                              top: 10,
                              right: 10,
                              background: "rgba(255, 255, 255, 0.9)",
                              border: "1px solid #E6DCC2",
                              borderRadius: 20,
                              width: 36,
                              height: 36,
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              fontSize: 18,
                              cursor: "pointer",
                              zIndex: 10,
                              transition: "all 0.2s ease",
                            }}
                            onClick={() => toggleFavorite(recipe.id)}
                            onMouseEnter={(e) => { e.target.style.background = "rgba(255, 255, 255, 1)"; e.target.style.boxShadow = "0 2px 8px rgba(72, 88, 120, 0.15)"; }}
                            onMouseLeave={(e) => { e.target.style.background = "rgba(255, 255, 255, 0.9)"; e.target.style.boxShadow = "none"; }}
                            title={favoriteRecipes.includes(recipe.id) ? "Remove from favorites" : "Add to favorites"}
                          >
                            {favoriteRecipes.includes(recipe.id) ? "♥" : "🤍"}
                          </button>
                          <div style={{ fontWeight: 700, fontSize: 17, color: "#214A86", paddingBottom: 6, borderBottom: "1px solid #E5EAF3" }}>{recipe.title}</div>
                          <div style={{ color: "#5D6D83", marginTop: 8 }}>{recipe.subtitle}</div>
                          <div style={{ color: "#344D71", marginTop: 8, fontSize: 14 }}>Prep: {recipe.prep} | {recipe.calories} kcal</div>
                          <div style={{ color: "#6A7C96", marginTop: 6, fontSize: 13 }}>
                            {recipe.mealType} • {recipe.dietary} • {recipe.difficulty} • {recipe.cuisine}
                          </div>
                          <button
                            className="btn-primary"
                            style={{ marginTop: 14, width: "100%", background: `linear-gradient(180deg, ${recipe.cardTag.color}, ${recipe.cardTag.color}CC)`, borderColor: recipe.cardTag.color }}
                            onClick={() => showRecipeDetails(recipe)}
                          >
                            {recipe.cardTag.label} ›
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              ) : (
                <div className="card" style={{ ...plannerInspiredGlass, padding: "28px 30px", display: "grid", gap: 16 }}>
                  <div style={{ display: "grid", gap: 8 }}>
                    <div style={{ fontFamily: "'Lora'", fontSize: 26, fontWeight: 700, color: "#214A86" }}>Choose a few filters to unlock curated recipes</div>
                    <div style={{ color: "#5D6D83", fontSize: 16, maxWidth: 720, lineHeight: 1.6 }}>
                      Pick the prep time, meal type, dietary needs, calories, difficulty, or cuisine you want. We'll narrow the list and show a more personal, easier-to-browse recipe set.
                    </div>
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
                    {[
                      { icon: "⏱", text: "Fast 10-15 min meals" },
                      { icon: "🍽", text: "Lunch and dinner ideas" },
                      { icon: "🥬", text: "Vegetarian or high protein" },
                      { icon: "🌍", text: "Mediterranean and Asian picks" },
                    ].map((idea) => (
                      <span
                        key={idea.text}
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 8,
                          padding: "8px 12px",
                          borderRadius: 999,
                          background: "linear-gradient(180deg, #EEF4FF, #E2ECFB)",
                          border: "1px solid #D3DEEF",
                          color: "#48698E",
                          fontWeight: 700,
                          fontSize: 14,
                        }}
                      >
                        <span>{idea.icon}</span>
                        <span>{idea.text}</span>
                      </span>
                    ))}
                  </div>
                </div>
              )}
              </div>
            )}

              {activeRecipeSection === "smartPicks" && (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: 12 }}>
              {smartPicks.map((pick) => (
                <button
                  type="button"
                  key={pick.label}
                  className="card"
                  onClick={() => setSelectedSmartPick(pick)}
                  style={{
                    ...plannerInspiredGlass,
                    padding: "14px 16px",
                    display: "grid",
                    gap: 8,
                    textAlign: "left",
                    cursor: "pointer",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 12, color: "#2E5A8B", fontWeight: 700 }}>
                    <span style={{ fontSize: 22 }}>{pick.icon}</span>
                    <span>{pick.label}</span>
                  </div>
                  <div style={{ color: "#6A7C96", fontSize: 14, lineHeight: 1.5 }}>{pick.hint}</div>
                </button>
              ))}
              </div>
            )}

              {activeRecipeSection === "categories" && (
              <>
              <div data-recipe-section="categories" className="card" style={{ ...plannerInspiredGlass, padding: 0, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", overflow: "hidden" }}>
                {categories.map((category, index) => (
                  <button
                    key={category.label}
                    type="button"
                    onClick={() => setSelectedCategory(category.label)}
                    style={{
                      border: "none",
                      borderRight: index < categories.length - 1 ? "1px solid #E4E8F0" : "none",
                      background: selectedCategory === category.label ? "linear-gradient(180deg, #EEF7E5, #E1F0D0)" : "transparent",
                      padding: "16px 12px",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      gap: 10,
                      color: selectedCategory === category.label ? "#4F7C22" : "#2E5A8B",
                      fontWeight: 700,
                      cursor: "pointer",
                    }}
                  >
                    <span style={{ fontSize: 24 }}>{category.icon}</span>
                    <span>{category.label}</span>
                  </button>
                ))}
              </div>
              <div style={{ display: "grid", gap: 12 }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", alignItems: "baseline" }}>
                  <div>
                    <div style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 22, color: "#214A86" }}>
                      {activeCategory.icon} {activeCategory.label}
                    </div>
                    <div style={{ marginTop: 6, color: "#5D6D83", fontSize: 15 }}>{activeCategory.description}</div>
                  </div>
                  <div style={{ color: "#4E678B", fontSize: 14 }}>
                    <strong style={{ color: "#214A86" }}>{categoryRecipes.length}</strong> recipe{categoryRecipes.length === 1 ? "" : "s"} in this category
                  </div>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 16 }}>
                  {categoryRecipes.map((recipe) => (
                    <div key={`${activeCategory.label}-${recipe.id}`} className="card" style={{ ...plannerInspiredGlass, padding: 14, position: "relative" }}>
                      <button
                        style={{
                          position: "absolute",
                          top: 10,
                          right: 10,
                          background: "rgba(255, 255, 255, 0.9)",
                          border: "1px solid #E6DCC2",
                          borderRadius: 20,
                          width: 36,
                          height: 36,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          fontSize: 18,
                          cursor: "pointer",
                          zIndex: 10,
                          transition: "all 0.2s ease",
                        }}
                        onClick={() => toggleFavorite(recipe.id)}
                        onMouseEnter={(e) => { e.target.style.background = "rgba(255, 255, 255, 1)"; e.target.style.boxShadow = "0 2px 8px rgba(72, 88, 120, 0.15)"; }}
                        onMouseLeave={(e) => { e.target.style.background = "rgba(255, 255, 255, 0.9)"; e.target.style.boxShadow = "none"; }}
                        title={favoriteRecipes.includes(recipe.id) ? "Remove from favorites" : "Add to favorites"}
                      >
                        {favoriteRecipes.includes(recipe.id) ? "♥" : "🤍"}
                      </button>
                      <div style={{ height: 108, borderRadius: 12, backgroundImage: `url('${recipe.image}')`, backgroundSize: "cover", backgroundPosition: "center" }} />
                      <div style={{ fontWeight: 700, fontSize: 17, color: "#214A86", marginTop: 10 }}>{recipe.title}</div>
                      <div style={{ color: "#5D6D83", marginTop: 8 }}>{recipe.subtitle}</div>
                      <div style={{ color: "#344D71", marginTop: 8, fontSize: 14 }}>Prep: {recipe.prep} | {recipe.calories} kcal</div>
                      <div style={{ color: "#6A7C96", marginTop: 6, fontSize: 13 }}>
                        {recipe.mealType} • {recipe.dietary} • {recipe.cuisine}
                      </div>
                      <button
                        className="btn-primary"
                        style={{ marginTop: 14, width: "100%", background: `linear-gradient(180deg, ${recipe.cardTag.color}, ${recipe.cardTag.color}CC)`, borderColor: recipe.cardTag.color }}
                        onClick={() => showRecipeDetails(recipe)}
                      >
                        View Recipe ›
                      </button>
                    </div>
                  ))}
                </div>
              </div>
              </>
              )}
                </div>
              )}
            </div>
          </div>
        </div>

      </div>

      {selectedRecipe && (
        <div
          onClick={() => setSelectedRecipe(null)}
          style={{
            position: "fixed",
            inset: 0,
            background: "linear-gradient(180deg, rgba(186, 215, 245, 0.88), rgba(231, 241, 252, 0.9))",
            display: "grid",
            placeItems: "center",
            padding: "84px 24px 24px",
            zIndex: 230,
            backdropFilter: "blur(4px)",
          }}
        >
          <div
            onClick={(event) => event.stopPropagation()}
            className="card"
            style={{
              width: "min(980px, calc(100vw - 48px))",
              maxHeight: "calc(100vh - 64px)",
              marginTop: 12,
              overflowY: "auto",
              border: "1px solid #D7DFEB",
              background: "linear-gradient(180deg, rgba(255,255,255,0.97), rgba(246,249,253,0.98))",
              boxShadow: "0 30px 80px rgba(55, 88, 138, 0.24)",
            }}
          >
            <div style={{ padding: "20px 28px 16px", borderBottom: "1px solid #E4E8F0", position: "relative" }}>
              <div style={{ position: "absolute", right: 18, top: 16, display: "flex", alignItems: "center", gap: 12 }}>
                <button
                  style={{
                    background: "rgba(255, 255, 255, 0.9)",
                    border: "1px solid #E6DCC2",
                    borderRadius: 20,
                    width: 40,
                    height: 40,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 20,
                    cursor: "pointer",
                    zIndex: 10,
                    transition: "all 0.2s ease",
                  }}
                  onClick={() => toggleFavorite(selectedRecipe.id)}
                  onMouseEnter={(e) => { e.target.style.background = "rgba(255, 255, 255, 1)"; e.target.style.boxShadow = "0 2px 8px rgba(72, 88, 120, 0.15)"; }}
                  onMouseLeave={(e) => { e.target.style.background = "rgba(255, 255, 255, 0.9)"; e.target.style.boxShadow = "none"; }}
                  title={favoriteRecipes.includes(selectedRecipe.id) ? "Remove from favorites" : "Add to favorites"}
                >
                  {favoriteRecipes.includes(selectedRecipe.id) ? "♥" : "🤍"}
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedRecipe(null)}
                  style={{ border: "none", background: "transparent", fontSize: 32, color: "#8A9AB0", cursor: "pointer" }}
                >
                  ×
                </button>
              </div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 14, flexWrap: "wrap" }}>
                <h2 style={{ margin: 0, fontFamily: "'Lora'", fontWeight: 700, fontSize: 34, color: "#214A86" }}>{selectedRecipe.title}</h2>
                <span style={{ background: selectedRecipe.badgeTone.bg, border: `1px solid ${selectedRecipe.badgeTone.border}`, borderRadius: 999, padding: "8px 14px", color: selectedRecipe.badgeTone.color, fontWeight: 700 }}>
                  {selectedRecipe.dietary}
                </span>
              </div>
              <div style={{ textAlign: "center", color: "#5D6D83", marginTop: 12, fontSize: 18 }}>{selectedRecipe.subtitle}</div>
              <div style={{ textAlign: "center", color: "#344D71", marginTop: 14, fontSize: 17 }}>
                ⓘ Prep: {selectedRecipe.prep} · {selectedRecipe.calories} kcal · {selectedRecipe.cardTag.label} 🍃
              </div>
            </div>

            <div style={{ padding: 24, display: "grid", gap: 18 }}>
              <div style={{ border: "1px solid #DBE8BF", background: "linear-gradient(180deg, #F8FDEB, #EEF8D3)", borderRadius: 10, padding: "14px 16px", color: "#4E7C1F", fontWeight: 700 }}>
                💧 {selectedRecipe.title.includes("Cucumber") ? "This salad will help keep you refreshed and hydrated!" : "A balanced plate that supports energy and steadier meals."}
              </div>

              <div style={{ textAlign: "center", fontFamily: "'Lora'", color: "#5A6B86", fontSize: 17, fontWeight: 700 }}>
                •• Nutrient Breakdown ••
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 0, overflow: "hidden", borderRadius: 12, boxShadow: "0 8px 18px rgba(72, 88, 120, 0.12)" }}>
                {selectedRecipe.nutrientStory.map((item, index) => (
                  <div
                    key={item}
                    style={{
                      padding: "14px 18px",
                      color: C.white,
                      background: index === 0 ? "linear-gradient(180deg, #5C9D31, #427320)" : index === 1 ? "linear-gradient(180deg, #4C8FD8, #2B62AA)" : "linear-gradient(180deg, #E2A124, #BB7C0D)",
                    }}
                  >
                    <div style={{ fontSize: 28 }}>{index === 0 ? "🥬" : index === 1 ? "🥗" : "🍅"}</div>
                    <div style={{ fontWeight: 800, fontSize: 15, marginTop: 8 }}>{item}</div>
                    <div style={{ fontSize: 13, marginTop: 6, opacity: 0.94 }}>
                      {index === 0 ? "Start with greens and crisp vegetables." : index === 1 ? "Let protein anchor the plate." : "Finish with the lighter carb portion."}
                    </div>
                  </div>
                ))}
              </div>

              <div className="card" style={{ padding: 20, border: "1px solid #D7DFEB" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", color: "#214A86", fontSize: 16 }}>
                  <span style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 18 }}>Nutrient Breakdown</span>
                  <span style={{ color: "#6AA33F" }}>•</span>
                  <span style={{ color: "#5D6D83" }}>Per serving snapshot</span>
                </div>
                <div style={{ marginTop: 16, display: "grid", gridTemplateColumns: "1.15fr 1.15fr 1.15fr 0.9fr", overflow: "hidden", borderRadius: 8, border: "1px solid #D7DFEB" }}>
                  <div style={{ background: "linear-gradient(180deg, #5A9C33, #3F7420)", color: C.white, padding: "12px 14px", fontWeight: 800 }}>Protein {selectedRecipe.macro.protein}g ⓘ</div>
                  <div style={{ background: "linear-gradient(180deg, #3B7EDA, #245EA7)", color: C.white, padding: "12px 14px", fontWeight: 800 }}>Carbs {selectedRecipe.macro.carbs}g ⓘ</div>
                  <div style={{ background: "linear-gradient(180deg, #D9A11E, #B17A09)", color: C.white, padding: "12px 14px", fontWeight: 800 }}>Fats {selectedRecipe.macro.fats}g ⓘ</div>
                  <div style={{ background: "#F3F5F7", color: "#324C71", padding: "12px 14px", fontWeight: 800 }}>{selectedRecipe.calories} kcal Total</div>
                </div>
                <div style={{ textAlign: "center", color: "#526883", marginTop: 14, fontSize: 17 }}>
                  Low glycemic load • Helps maintain steady energy.
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 0.95fr) minmax(0, 1.05fr)", gap: 24, alignItems: "start", borderTop: "1px solid #D7DFEB", paddingTop: 12 }}>
                <div>
                  <div style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 18, color: "#214A86" }}>•• Ingredients ••</div>
                  <div style={{ display: "grid", gap: 10, marginTop: 14, color: "#2F4A70", fontSize: 17 }}>
                    {selectedRecipe.ingredients.map((ingredient, index) => (
                      <div key={ingredient} style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                        <span>•</span>
                        <span>{ingredient}</span>
                        {index === 2 && <span style={{ background: "#EEF6D8", border: "1px solid #C8E09A", borderRadius: 999, padding: "4px 10px", color: "#5B922A", fontSize: 14, fontWeight: 700 }}>Non-GMO ✓</span>}
                        {index === 3 && <span style={{ background: "#EEF6D8", border: "1px solid #C8E09A", borderRadius: 999, padding: "4px 10px", color: "#5B922A", fontSize: 14, fontWeight: 700 }}>Organic ✓</span>}
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <div style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 18, color: "#214A86" }}>•• Instructions ••</div>
                  <div style={{ display: "grid", gap: 14, marginTop: 14, color: "#2F2F2F", fontSize: 17 }}>
                    {selectedRecipe.steps.map((step, index) => (
                      <div key={step} style={{ display: "flex", gap: 12 }}>
                        <strong>{index + 1}.</strong>
                        <span>{step}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              <div style={{ border: "1px solid #DBE8BF", background: "linear-gradient(180deg, #F8FDEB, #EEF8D3)", borderRadius: 10, overflow: "hidden" }}>
                <div style={{ padding: "12px 16px", borderBottom: "1px solid #DBE8BF", color: "#4E7C1F", fontWeight: 800 }}>🌿 Ingredient Swap Insight ••</div>
                <div style={{ padding: "12px 16px", color: "#4C5E37", fontSize: 17 }}>{selectedRecipe.swapInsight}</div>
              </div>

              <div style={{ border: "1px solid #F0D8A2", background: "linear-gradient(180deg, #FFF8E7, #FBEEC8)", borderRadius: 10, overflow: "hidden" }}>
                <div style={{ padding: "12px 16px", borderBottom: "1px solid #F0D8A2", color: "#9C4D27", fontWeight: 800 }}>❤️ Today's Reflection ••</div>
                <div style={{ padding: "12px 16px", color: "#6E5431", fontSize: 17 }}>{selectedRecipe.reflection}</div>
              </div>

              <div style={{ display: "flex", justifyContent: "center", gap: 16, flexWrap: "wrap", paddingBottom: 4 }}>
                <button className="btn-primary" style={{ minWidth: 198, background: "linear-gradient(180deg, #5AA132, #3E7A1D)", borderColor: "#3E7A1D" }} onClick={openAddToPlanModal}>
                  Add to Plan
                </button>
                <button className="btn-ghost" style={{ minWidth: 198, background: "linear-gradient(180deg, #F8E8B1, #E9D182)", borderColor: "#D6BE74", color: "#5B4A24" }} onClick={() => setSelectedRecipe(null)}>
                  Keep Browsing
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {selectedRecipe && showAddToPlanModal && (
        <div
          onClick={closeAddToPlanModal}
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(32, 52, 86, 0.38)",
            display: "grid",
            placeItems: "center",
            padding: "88px 24px 24px",
            zIndex: 260,
            backdropFilter: "blur(3px)",
          }}
        >
          <div
            onClick={(event) => event.stopPropagation()}
            className="card"
            style={{
              width: "min(520px, calc(100vw - 48px))",
              maxHeight: "calc(100vh - 120px)",
              border: "1px solid #D7DFEB",
              background: "linear-gradient(180deg, #FFFFFF, #F7FAFF)",
              boxShadow: "0 24px 52px rgba(55, 88, 138, 0.22)",
              padding: 24,
              display: "grid",
              gap: 18,
              overflowY: "auto",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "flex-start" }}>
              <div>
                <div style={{ fontFamily: "'Lora'", fontSize: 28, fontWeight: 700, color: "#214A86" }}>Add to Plan</div>
                <div style={{ marginTop: 8, color: "#5D6D83", fontSize: 16 }}>
                  We&apos;ll add <strong>{selectedRecipe.title}</strong> from <strong>{plannerRangeLabel}</strong>, through the weekend.
                </div>
              </div>
              <button type="button" onClick={closeAddToPlanModal} style={{ border: "none", background: "transparent", color: "#8A9AB0", fontSize: 30, cursor: "pointer", lineHeight: 1 }}>
                ×
              </button>
            </div>

            <div style={{ border: "1px solid #DDE6F3", borderRadius: 14, background: "linear-gradient(180deg, #F9FBFF, #F2F7FF)", padding: 16 }}>
              <div style={{ color: "#214A86", fontWeight: 800, marginBottom: 12 }}>Choose which meal of the day to update</div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 10 }}>
                {[
                  ["breakfast", "Breakfast", "🥣"],
                  ["lunch", "Lunch", "🥗"],
                  ["dinner", "Dinner", "🍽"],
                  ["snack", "Snack", "🍎"],
                ].map(([slot, label, icon]) => {
                  const isActive = selectedPlanMealSlot === slot;
                  return (
                    <button
                      key={slot}
                      type="button"
                      onClick={() => setSelectedPlanMealSlot(slot)}
                      style={{
                        border: isActive ? "1px solid #5AA132" : "1px solid #D7DFEB",
                        background: isActive ? "linear-gradient(180deg, #EFF8E4, #DFF0C9)" : "linear-gradient(180deg, #FFFFFF, #F8FBFF)",
                        color: isActive ? "#427320" : "#325170",
                        borderRadius: 14,
                        padding: "14px 12px",
                        textAlign: "left",
                        cursor: "pointer",
                        boxShadow: isActive ? "0 10px 22px rgba(90, 161, 50, 0.12)" : "0 6px 14px rgba(72, 88, 120, 0.06)",
                      }}
                    >
                      <div style={{ fontSize: 18 }}>{icon}</div>
                      <div style={{ marginTop: 8, fontWeight: 800 }}>{label}</div>
                    </button>
                  );
                })}
              </div>
            </div>

            <div style={{ border: "1px solid #DDE6F3", borderRadius: 14, background: "linear-gradient(180deg, #FFFFFF, #F6FAFF)", padding: 16 }}>
              <div style={{ color: "#214A86", fontWeight: 800, marginBottom: 12 }}>Choose the day to start adding this recipe</div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(92px, 1fr))", gap: 10 }}>
                {plannerDays.map((day, index) => {
                  const isActive = plannerStartIndex === index;
                  return (
                    <button
                      key={day.key}
                      type="button"
                      onClick={() => setSelectedPlanStartDayIndex(index)}
                      style={{
                        border: isActive ? "1px solid #4E8DD0" : "1px solid #D7DFEB",
                        background: isActive ? "linear-gradient(180deg, #EAF3FF, #DCEBFF)" : "linear-gradient(180deg, #FFFFFF, #F8FBFF)",
                        color: isActive ? "#214A86" : "#49627E",
                        borderRadius: 14,
                        padding: "12px 10px",
                        cursor: "pointer",
                        textAlign: "center",
                        boxShadow: isActive ? "0 10px 22px rgba(78, 141, 208, 0.14)" : "0 6px 14px rgba(72, 88, 120, 0.05)",
                      }}
                    >
                      <div style={{ fontSize: 12, fontWeight: 800, letterSpacing: "0.04em", textTransform: "uppercase", opacity: 0.8 }}>{day.shortDay}</div>
                      <div style={{ marginTop: 6, fontFamily: "'Lora'", fontSize: 20, fontWeight: 700 }}>{day.dayNumber}</div>
                      <div style={{ marginTop: 4, fontSize: 12 }}>{day.monthLabel}</div>
                    </button>
                  );
                })}
              </div>
            </div>

            <div style={{ padding: "14px 16px", borderRadius: 12, background: "linear-gradient(180deg, #FFF8E7, #FCEFCF)", border: "1px solid #F0D8A2", color: "#6E5431", fontSize: 15 }}>
              This will replace the <strong>{selectedPlanMealSlot}</strong> slot for each planner day from <strong>{plannerStartDay?.longDay || "today"} {plannerStartDay?.monthLabel} {plannerStartDay?.dayNumber || ""}</strong> through <strong>{plannerEndDay?.longDay || "Sunday"} {plannerEndDay?.monthLabel} {plannerEndDay?.dayNumber || ""}</strong>.
            </div>

            <div style={{ display: "flex", justifyContent: "center", gap: 12, flexWrap: "wrap" }}>
              <button className="btn-primary" style={{ minWidth: 190, background: "linear-gradient(180deg, #5AA132, #3E7A1D)", borderColor: "#3E7A1D" }} onClick={saveRecipeToPlanner}>
                Add to Planner
              </button>
              <button className="btn-ghost" style={{ minWidth: 160 }} onClick={closeAddToPlanModal}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {selectedSmartPick && (
        <div
          onClick={closeSmartPickModal}
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(32, 52, 86, 0.34)",
            display: "grid",
            placeItems: "center",
            padding: "96px 24px 24px",
            zIndex: 250,
            backdropFilter: "blur(3px)",
          }}
        >
          <div
            onClick={(event) => event.stopPropagation()}
            className="card"
            style={{
              width: "min(460px, calc(100vw - 48px))",
              maxHeight: "calc(100vh - 120px)",
              overflowY: "auto",
              border: "1px solid #D7DFEB",
              background: "linear-gradient(180deg, #FFFFFF, #F7FAFF)",
              boxShadow: "0 24px 52px rgba(55, 88, 138, 0.22)",
              padding: 24,
              display: "grid",
              gap: 16,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "flex-start" }}>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 10, color: "#214A86" }}>
                  <span style={{ fontSize: 24 }}>{selectedSmartPick.icon}</span>
                  <div style={{ fontFamily: "'Lora'", fontSize: 28, fontWeight: 700 }}>{selectedSmartPick.label}</div>
                </div>
                <div style={{ marginTop: 8, color: "#5D6D83", fontSize: 16 }}>{selectedSmartPick.hint}</div>
              </div>
              <button type="button" onClick={closeSmartPickModal} style={{ border: "none", background: "transparent", color: "#8A9AB0", fontSize: 30, cursor: "pointer", lineHeight: 1 }}>
                ×
              </button>
            </div>

            {!showSmartPickMealChooser ? (
              <>
                <div style={{ border: "1px solid #F0D8A2", background: "linear-gradient(180deg, #FFF8E7, #FCEFCF)", borderRadius: 14, padding: 16, color: "#6E5431" }}>
                  <div style={{ fontWeight: 800, color: "#9C4D27", marginBottom: 8 }}>Suggested side dish</div>
                  <div style={{ fontSize: 18, fontWeight: 700 }}>{selectedSmartPick.sideAddOn.replace("Optional side: ", "")}</div>
                  <div style={{ marginTop: 8, fontSize: 14 }}>A simple add-on that pairs naturally with the meal and keeps the plate more balanced.</div>
                </div>

                <div style={{ display: "flex", justifyContent: "center", gap: 12, flexWrap: "wrap" }}>
                  <button
                    className="btn-primary"
                    style={{ minWidth: 180, background: "linear-gradient(180deg, #5AA132, #3E7A1D)", borderColor: "#3E7A1D" }}
                    onClick={() => {
                      setSelectedSmartPickMealSlot("dinner");
                      setShowSmartPickMealChooser(true);
                    }}
                  >
                    Add to meal
                  </button>
                  <button className="btn-ghost" style={{ minWidth: 140 }} onClick={closeSmartPickModal}>
                    Close
                  </button>
                </div>
              </>
            ) : (
              <>
                <div style={{ border: "1px solid #DDE6F3", borderRadius: 14, background: "linear-gradient(180deg, #FFFFFF, #F6FAFF)", padding: 16 }}>
                  <div style={{ color: "#214A86", fontWeight: 800, marginBottom: 12 }}>Add this suggestion for which meal today?</div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 10 }}>
                    {[
                      ["breakfast", "Breakfast", "🥣"],
                      ["lunch", "Lunch", "🥗"],
                      ["dinner", "Dinner", "🍽"],
                      ["snack", "Snack", "🍎"],
                    ].map(([slot, label, icon]) => (
                      <button
                        key={slot}
                        type="button"
                        onClick={() => setSelectedSmartPickMealSlot(slot)}
                        style={{
                          border: selectedSmartPickMealSlot === slot ? "1px solid #5AA132" : "1px solid #D7DFEB",
                          background: selectedSmartPickMealSlot === slot ? "linear-gradient(180deg, #EFF8E4, #DFF0C9)" : "linear-gradient(180deg, #FFFFFF, #F8FBFF)",
                          color: selectedSmartPickMealSlot === slot ? "#427320" : "#325170",
                          borderRadius: 14,
                          padding: "14px 12px",
                          textAlign: "left",
                          cursor: "pointer",
                          boxShadow: selectedSmartPickMealSlot === slot ? "0 10px 22px rgba(90, 161, 50, 0.12)" : "0 6px 14px rgba(72, 88, 120, 0.06)",
                        }}
                      >
                        <div style={{ fontSize: 18 }}>{icon}</div>
                        <div style={{ marginTop: 8, fontWeight: 800 }}>{label}</div>
                      </button>
                    ))}
                  </div>
                </div>

                <div style={{ display: "flex", justifyContent: "center", gap: 12, flexWrap: "wrap" }}>
                  <button
                    className="btn-primary"
                    style={{ minWidth: 180, background: "linear-gradient(180deg, #5AA132, #3E7A1D)", borderColor: "#3E7A1D" }}
                    onClick={saveSmartPickToPlanner}
                  >
                    Save
                  </button>
                  <button className="btn-ghost" style={{ minWidth: 140 }} onClick={() => setShowSmartPickMealChooser(false)}>
                    Back
                  </button>
                  <button className="btn-ghost" style={{ minWidth: 140 }} onClick={closeSmartPickModal}>
                    Close
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {smartPickToast && (
        <div
          style={{
            position: "fixed",
            right: 20,
            bottom: 108,
            zIndex: 280,
            padding: "12px 16px",
            borderRadius: 14,
            background: "linear-gradient(180deg, #EFF8E4, #DFF0C9)",
            border: "1px solid #C9E0A8",
            color: "#427320",
            fontWeight: 700,
            boxShadow: "0 14px 28px rgba(90, 161, 50, 0.18)",
          }}
        >
          {smartPickToast}
        </div>
      )}

      <FloatingSousMazi message="How can I assist you today?" />
    </>
  );
}

function FloatingSousMazi({ message = "How can I assist you today?", right = 18, bottom = 18 }) {
  return (
    <div style={{ position: "fixed", right, bottom, zIndex: 205, display: "grid", justifyItems: "end", gap: 10 }}>
      <div
        style={{
          background: "#F7FBFF",
          border: "1px solid #C9D3E3",
          color: "#24487B",
          borderRadius: 16,
          padding: "8px 14px",
          boxShadow: "0 8px 18px rgba(72, 88, 120, 0.14)",
          fontWeight: 600,
          fontSize: 12.5,
        }}
      >
        {message}
      </div>
      <button
        type="button"
        aria-label="Ask Sous Mazi"
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
  );
}

function RecipesTab({ setStep }) {
  const [search, setSearch] = useState("");
  const [useAi, setUseAi] = useState(false);
  const [view, setView] = useState("search");
  const [selectedFilters, setSelectedFilters] = useState([]);
  const recipeBackdrop = "https://images.unsplash.com/photo-1490645935967-10de6ba17061?auto=format&fit=crop&w=1400&q=80";
  const filters = ["Under 30 min", "Beginner", "Kid friendly", "Breakfast", "Lunch", "Dinner", "Snack", "Dessert", "Soup", "Appetizer"];
  const recipeData = [
    { title: "Lentil Tacos", description: "High fiber, family favorite", time: "28 min", tags: ["Under 30 min", "Kid friendly", "Dinner"] },
    { title: "Rainbow Buddha Bowl", description: "Veggies + protein balance", time: "22 min", tags: ["Under 30 min", "Lunch", "Healthy"] },
    { title: "Chicken Stir-Fry", description: "Quick Asian-inspired meal", time: "18 min", tags: ["Under 30 min", "Dinner", "Kid friendly"] },
    { title: "Berry Yogurt Parfait", description: "Light and refreshing breakfast", time: "10 min", tags: ["Breakfast", "Kid friendly"] },
    { title: "Mushroom Soup", description: "Comforting savory starter", time: "35 min", tags: ["Soup", "Beginner"] },
  ];

  const toggleFilter = (filter) => {
    setSelectedFilters(prev => 
      prev.includes(filter) 
        ? prev.filter(f => f !== filter)
        : [...prev, filter]
    );
    setUseAi(false);
  };

  const displayed = useAi 
    ? recipeData.slice(0, 3) 
    : recipeData.filter(r => {
        const matchesSearch = !search || r.title.toLowerCase().includes(search.toLowerCase()) || r.description.toLowerCase().includes(search.toLowerCase());
        const matchesFilters = selectedFilters.length === 0 || selectedFilters.some(filter => r.tags.includes(filter));
        return matchesSearch && matchesFilters;
      });
  const weekDays = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];
  const calendarPlan = weekDays.map((day, index) => ({
    day,
    meal: recipeData[index % recipeData.length].title,
    time: recipeData[index % recipeData.length].time,
    note: index % 2 === 0 ? "Family dinner" : "Kid-friendly lunch",
  }));

  return (
    <div style={{ padding: "24px 20px 92px", maxWidth: 1120, margin: "0 auto", display: "grid", gap: 20 }}>
      <div className="card" style={{ position: "relative", overflow: "hidden", padding: 0, background: "linear-gradient(180deg, rgba(255,253,248,0.96), rgba(248,245,238,0.94))", border: `1.5px solid ${C.border}` }}>
        <div style={{ position: "absolute", inset: 0, backgroundImage: `linear-gradient(180deg, rgba(255,253,248,0.92), rgba(255,253,248,0.78)), url('${recipeBackdrop}')`, backgroundSize: "cover", backgroundPosition: "center" }} />
        <div style={{ position: "absolute", inset: 0, background: "linear-gradient(180deg, rgba(255,255,255,0.16), rgba(245,241,232,0.7))" }} />
        <div style={{ position: "relative", zIndex: 1, padding: "22px 24px 26px", display: "grid", gap: 16 }}>
          <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 16, alignItems: "center" }}>
            <div>
              <div style={{ color: C.accent, fontSize: 13, fontWeight: 700, letterSpacing: 1.3, textTransform: "uppercase" }}>Search Recipes</div>
              <h2 style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 30, color: C.text, marginTop: 8 }}>Find meals, schedule them, or review the weekly calendar</h2>
              <p style={{ color: C.subtext, marginTop: 8, maxWidth: 720 }}>Browse recipe ideas in the same planner-inspired workspace, with softer surfaces, live filters, and a cleaner weekly scheduling view.</p>
            </div>
            <div style={{ display: "grid", gap: 10, minWidth: 290, flex: "1 1 320px", maxWidth: 360 }}>
              <input value={search} onChange={e => { setSearch(e.target.value); setUseAi(false); }} placeholder="Search recipes" style={{ width: "100%", padding: "12px 14px", border: `1px solid ${C.border}`, borderRadius: 14, background: "rgba(255,255,255,0.88)" }} />
              <button className="btn-primary" style={{ justifySelf: "start", background: "#3B67B0", borderColor: "#3B67B0", padding: "10px 18px" }} onClick={() => { setUseAi(true); setSearch(""); setView("search"); }}>Ask AI</button>
            </div>
          </div>

          <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
            {filters.map(filter => (
              <button
                key={filter}
                type="button"
                onClick={() => toggleFilter(filter)}
                style={{
                  border: `1px solid ${selectedFilters.includes(filter) ? "#214A86" : C.border}`,
                  background: selectedFilters.includes(filter) ? "#214A86" : "rgba(255,255,255,0.82)",
                  color: selectedFilters.includes(filter) ? C.white : C.text,
                  borderRadius: 999,
                  padding: "8px 13px",
                  fontSize: 12,
                  fontWeight: 700,
                }}
              >
                {filter}
              </button>
            ))}
          </div>

          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {[["search","Search"],["calendar","Calendar"]].map(([id,label]) => (
              <button
                key={id}
                type="button"
                onClick={() => setView(id)}
                style={{
                  border: `1px solid ${view === id ? "#214A86" : C.border}`,
                  background: view === id ? "#214A86" : "rgba(255,255,255,0.82)",
                  color: view === id ? C.white : C.text,
                  borderRadius: 999,
                  padding: "8px 14px",
                  fontSize: 12,
                  fontWeight: 700,
                }}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {view === "search" && (
        <div className="card" style={{ padding: 20, background: "rgba(255,255,255,0.84)", backdropFilter: "blur(8px)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
            <div>
              <div style={{ fontSize: 13, color: C.accent, textTransform: "uppercase", letterSpacing: 1.5, fontWeight: 700 }}>Top picks</div>
              <div style={{ fontWeight: 700, fontSize: 24, color: "#214A86" }}>{useAi ? "AI-inspired choices" : "Search results"}</div>
            </div>
            {useAi && <span style={{ color: C.accent, fontWeight: 700, background: C.accentLight, border: `1px solid ${C.accent}`, borderRadius: 999, padding: "7px 12px", fontSize: 12 }}>Top 3</span>}
          </div>
          <div style={{ display: "grid", gap: 14 }}>
            {displayed.map(recipe => (
              <div key={recipe.title} className="card" style={{ padding: 18, display: "grid", gap: 12, background: "rgba(255,255,255,0.84)", backdropFilter: "blur(8px)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16 }}>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 18, color: C.text }}>{recipe.title}</div>
                    <div style={{ color: C.subtext, fontSize: 13 }}>{recipe.description}</div>
                  </div>
                  <div style={{ textAlign: "right", color: "#214A86", fontWeight: 700 }}>{recipe.time}</div>
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
                  {recipe.tags.map(tag => <span key={tag} style={{ background: "rgba(255,255,255,0.86)", border: `1px solid ${C.border}`, borderRadius: 999, padding: "6px 10px", fontSize: 12, color: C.text }}>{tag}</span>)}
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
                  <button className="btn-primary" style={{ background: "#3B67B0", borderColor: "#3B67B0" }} onClick={() => setStep("cook")}>Cook</button>
                  <button className="btn-ghost" style={{ background: C.white }}>Add to calendar</button>
                  <button className="btn-ghost" style={{ background: C.white }}>Track</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {view === "calendar" && (
        <div className="card" style={{ padding: 20, background: "rgba(255,255,255,0.84)", backdropFilter: "blur(8px)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
            <div>
              <div style={{ fontSize: 13, color: C.accent, textTransform: "uppercase", letterSpacing: 1.5, fontWeight: 700 }}>Calendar view</div>
              <div style={{ fontWeight: 700, fontSize: 24, color: "#214A86" }}>Weekly recipe schedule</div>
            </div>
            <button className="btn-ghost" style={{ background: C.white }}>Export Planner</button>
          </div>
          <div style={{ display: "grid", gap: 16 }}>
            {calendarPlan.map(slot => (
              <div key={slot.day} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: 16, borderRadius: 18, background: "rgba(255,255,255,0.82)", border: `1px solid ${C.border}` }}>
                <div>
                  <div style={{ fontSize: 13, color: C.accent, fontWeight: 700 }}>{slot.day}</div>
                  <div style={{ fontWeight: 700, marginTop: 4, color: C.text }}>{slot.meal}</div>
                  <div style={{ color: C.subtext, fontSize: 13, marginTop: 4 }}>{slot.note}</div>
                </div>
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                  <button className="btn-ghost" style={{ background: C.white }}>Edit</button>
                  <button className="btn-ghost" style={{ background: C.white }}>View</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function TrackerTab({ plannerDay, plannerState, setPlannerState, profile }) {
  const [showManualLog, setShowManualLog] = useState(false);
  const [manualLog, setManualLog] = useState({
    mealName: "",
    mealSlot: "snack",
    calories: "",
    protein: "",
    note: "",
  });

  const plannerInspiredShell = {
    position: "relative",
    overflow: "hidden",
    borderRadius: 24,
    background: "linear-gradient(180deg, rgba(255,253,248,0.96), rgba(248,245,238,0.94))",
    border: `1.5px solid ${C.border}`,
    boxShadow: "0 18px 38px rgba(72, 88, 120, 0.08)",
  };

  const plannerInspiredGlass = {
    borderRadius: 22,
    border: `1px solid ${C.border}`,
    background: "rgba(255,255,255,0.88)",
    backdropFilter: "blur(10px)",
    boxShadow: "0 12px 26px rgba(72, 88, 120, 0.1)",
  };
  const trackerMeals = plannerDay
    ? plannerDay.mealOrder.map((slot) => {
        const meal = plannerDay.meals[slot];
        return {
          id: slot,
          slot,
          label: meal.label || meal.slotType || "Meal",
          name: meal.name,
          calories: meal.calories || 0,
          protein: meal.protein || 0,
          nutrients: meal.nutrients || {},
          note: meal.sideSuggestion || meal.tip || "",
        };
      })
    : [];
  const todayCalories = trackerMeals.reduce((sum, meal) => sum + meal.calories, 0);
  const todayProtein = trackerMeals.reduce((sum, meal) => sum + meal.protein, 0);
  const todayFiber = trackerMeals.reduce((sum, meal) => sum + (Number(meal.nutrients?.Fiber) || 0), 0);
  const calorieGoal = calculateDailyCalorieTarget(profile);
  const weeklyCalories = (plannerState?.days || []).reduce((sum, day) => sum + (day.totalCalories || 0), 0);
  const weeklyAvgCalories = plannerState?.days?.length ? Math.round(weeklyCalories / plannerState.days.length) : todayCalories;
  const monthlyConsistency = Math.min(100, Math.round((trackerMeals.filter((meal) => meal.calories > 0).length / Math.max(trackerMeals.length, 1)) * 100));
  const topTrackerMeals = [...trackerMeals].sort((a, b) => b.calories - a.calories).slice(0, 4);
  const trackerDays = (plannerState?.days || []).slice(0, 7);
  const dateRangeLabel = trackerDays.length
    ? `${trackerDays[0].monthLabel} ${trackerDays[0].dayNumber} - ${trackerDays[Math.min(trackerDays.length - 1, 6)].monthLabel} ${trackerDays[Math.min(trackerDays.length - 1, 6)].dayNumber}`
    : "Apr 1 - Apr 21";
  const hydrationTrend = trackerDays.map((day, index) => {
    const baseValue = 54 + index * 5;
    return Math.min(94, baseValue + (index % 2 === 0 ? 4 : -2));
  });
  const mealConsistencyTrend = trackerDays.map((day) => {
    const filledMeals = day?.mealOrder?.filter((slot) => (day.meals?.[slot]?.calories || 0) > 0).length || 0;
    return Math.round((filledMeals / Math.max(day?.mealOrder?.length || 1, 1)) * 100);
  });
  const activityTrend = trackerDays.map((day, index) => 36 + index * 8 + (index % 2 === 0 ? 3 : -1));
  const sleepTrend = trackerDays.map((day, index) => 58 + index * 5 + (index > 3 ? 10 : 0));
  const mealConsistencyChange = Math.max(0, mealConsistencyTrend[mealConsistencyTrend.length - 1] - mealConsistencyTrend[0]);
  const hydrationSteadyDays = hydrationTrend.filter((value) => value >= 64).length;
  const activityMinutes = trackerDays.reduce((sum, day, index) => sum + 48 + index * 9, 0);
  const activityLift = 12;
  const averageSleepHours = (7.2).toFixed(1);
  const sleepChange = 3;
  const nutrientBalanceLift = Math.min(18, Math.max(8, Math.round(todayFiber / 2)));
  const fatigueRiskDrop = 22;
  const nutrientAbsorptionLift = 18;
  const roiMeter = 88;
  const rhythmSummary = `${profile?.name || "Nav"}'s balance is becoming habitual.`;
  const nextFocus = "Sleep Consistency | Mindful Hydration";
  const insightRows = [
    `Hydration consistency ↑ ${Math.max(12, hydrationSteadyDays + 10)}% — Linked to improved sleep quality.`,
    `Nutrient balance ↑ ${nutrientBalanceLift}% — Enhanced recovery efficiency.`,
    `Energy uptrend — Your active minutes increased by ${activityLift}%.`,
    "Optimize sleep — Consider a lighter dinner for better rest.",
  ];

  const createLinePath = (values, width = 250, height = 88) => {
    if (!values.length) return "";
    const maxValue = Math.max(...values);
    const minValue = Math.min(...values);
    const range = maxValue - minValue || 1;
    return values
      .map((value, index) => {
        const x = (index / Math.max(values.length - 1, 1)) * width;
        const y = height - ((value - minValue) / range) * (height - 10) - 5;
        return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
      })
      .join(" ");
  };

  const createAreaPath = (values, width = 250, height = 88) => {
    if (!values.length) return "";
    const linePath = createLinePath(values, width, height);
    return `${linePath} L ${width} ${height} L 0 ${height} Z`;
  };

  const trackerChartCard = ({ title, value, suffix = "", accent, values, footer, trendLabel }) => (
    <div
      className="card"
      style={{
        ...plannerInspiredGlass,
        padding: 22,
        display: "grid",
        gap: 14,
      }}
    >
      <div>
        <div style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 17, color: "#163F77" }}>{title}</div>
        <div style={{ marginTop: 8, display: "flex", alignItems: "baseline", gap: 6, flexWrap: "wrap" }}>
          <span style={{ fontSize: 28, fontWeight: 800, color: "#163F77" }}>{value}</span>
          {suffix && <span style={{ fontSize: 15, color: "#5E6E86" }}>{suffix}</span>}
          {trendLabel && <span style={{ fontSize: 13, color: accent, fontWeight: 700 }}>{trendLabel}</span>}
        </div>
      </div>
      <div style={{ borderTop: "1px solid rgba(91, 109, 132, 0.14)", paddingTop: 14 }}>
        <svg viewBox="0 0 250 88" style={{ width: "100%", height: 90, display: "block" }}>
          <defs>
            <linearGradient id={`tracker-fill-${title.replace(/\s+/g, "-")}`} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor={accent} stopOpacity="0.32" />
              <stop offset="100%" stopColor={accent} stopOpacity="0.04" />
            </linearGradient>
          </defs>
          <path d={createAreaPath(values)} fill={`url(#tracker-fill-${title.replace(/\s+/g, "-")})`} />
          <path d={createLinePath(values)} fill="none" stroke={accent} strokeWidth="3" strokeLinecap="round" />
          {values.map((value, index) => {
            const maxValue = Math.max(...values);
            const minValue = Math.min(...values);
            const range = maxValue - minValue || 1;
            const x = (index / Math.max(values.length - 1, 1)) * 250;
            const y = 88 - ((value - minValue) / range) * 78 - 5;
            return <circle key={`${title}-${index}`} cx={x} cy={y} r={index === values.length - 1 ? 5 : 3.5} fill="#F8FBFF" stroke={accent} strokeWidth="2" />;
          })}
        </svg>
      </div>
      <div style={{ borderTop: "1px solid rgba(91, 109, 132, 0.14)", paddingTop: 14, color: "#5E6E86", fontSize: 14 }}>{footer}</div>
    </div>
  );

  const saveManualLog = () => {
    if (!manualLog.mealName.trim() || !setPlannerState) return;
    const nextCalories = Number(manualLog.calories) || 0;
    const nextProtein = Number(manualLog.protein) || 0;
    setPlannerState((current) => {
      const selectedDayIndex = Math.min(Math.max(current.selectedDayIndex ?? 0, 0), Math.max((current.days || []).length - 1, 0));
      const days = (current.days || []).map((day, index) => {
        if (index !== selectedDayIndex) return day;
        const existingMeal = day.meals?.[manualLog.mealSlot];
        if (!existingMeal) return day;
        const updatedMeals = {
          ...day.meals,
          [manualLog.mealSlot]: {
            ...existingMeal,
            name: manualLog.mealName.trim(),
            calories: nextCalories || existingMeal.calories,
            protein: nextProtein || existingMeal.protein,
            tip: manualLog.note.trim() || existingMeal.tip,
            sideSuggestion: manualLog.note.trim() || existingMeal.sideSuggestion || "",
          },
        };
        const totalCalories = Object.values(updatedMeals).reduce((sum, meal) => sum + (meal?.calories || 0), 0);
        return {
          ...day,
          meals: updatedMeals,
          totalCalories,
        };
      });
      return {
        ...current,
        days,
      };
    });
    setManualLog({ mealName: "", mealSlot: "snack", calories: "", protein: "", note: "" });
    setShowManualLog(false);
  };

  return (
    <>
    <div style={{ padding: "26px 20px 40px", maxWidth: 1180, margin: "0 auto", display: "grid", gap: 22 }}>
      <div className="card" style={{ ...plannerInspiredShell, minHeight: 0 }}>
        <div style={{ position: "absolute", inset: 0, backgroundImage: `linear-gradient(180deg, rgba(255,253,248,0.92), rgba(255,253,248,0.74))`, backgroundSize: "cover", backgroundPosition: "center" }} />
        <div style={{ position: "absolute", inset: 0, background: "linear-gradient(180deg, rgba(255,255,255,0.18), rgba(245,241,232,0.74))" }} />
        <div style={{ position: "relative", zIndex: 1, padding: "22px 24px 24px", display: "grid", gap: 18 }}>
          <div style={{ color: C.accent, fontSize: 13, fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase" }}>Tracker</div>
          <div style={{ textAlign: "center", marginBottom: 12 }}>
            <h1 style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 28, color: "#214A86", margin: 0 }}>
              Wellness Intelligence, {profile?.name || "Nav"}.
            </h1>
            <p style={{ color: "#5E6E86", marginTop: 8, fontSize: 15 }}>
              Your nutrition and wellness patterns over time.
            </p>
          </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(12, minmax(0, 1fr))", gap: 16 }}>
        <div style={{ gridColumn: "span 3" }}>
          {trackerChartCard({
            title: "Meals Consistency",
            value: `+${mealConsistencyChange}%`,
            accent: "#8FC26C",
            values: mealConsistencyTrend,
            footer: "Balanced choices this week.",
          })}
        </div>
        <div style={{ gridColumn: "span 3" }}>
          {trackerChartCard({
            title: "Hydration Rhythm",
            value: "Steady",
            suffix: `${hydrationSteadyDays} Days`,
            accent: "#4A83C4",
            values: hydrationTrend,
            footer: "Hydration on track.",
          })}
        </div>
        <div style={{ gridColumn: "span 3" }}>
          {trackerChartCard({
            title: "Activity Level",
            value: activityMinutes,
            suffix: "min Weekly",
            accent: "#90BC59",
            values: activityTrend,
            footer: "Energy curve improving.",
            trendLabel: `↑${activityLift}%`,
          })}
        </div>
        <div
          className="card"
          style={{
            ...plannerInspiredShell,
            gridColumn: "span 3",
            padding: 0,
            overflow: "hidden",
            height: 292,
            display: "grid",
            gridTemplateRows: "auto 1fr",
          }}
        >
          <div style={{ padding: "18px 22px", borderBottom: "1px solid rgba(91, 109, 132, 0.14)", fontFamily: "'Lora'", fontWeight: 700, fontSize: 17, color: "#163F77" }}>
            Insights & Recommendations
          </div>
          <div style={{ display: "grid", overflowY: "auto" }}>
            {insightRows.map((row, index) => (
              <div key={row} style={{ padding: "16px 22px", borderBottom: index < insightRows.length - 1 ? "1px solid rgba(91, 109, 132, 0.14)" : "none", color: "#314457", lineHeight: 1.4, fontSize: 15 }}>
                • {row}
              </div>
            ))}
          </div>
        </div>

        <div
          className="card"
          style={{
            ...plannerInspiredGlass,
            gridColumn: "span 5",
            padding: 22,
            display: "grid",
            gap: 14,
          }}
        >
          <div style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 17, color: "#163F77" }}>Sleep Quality</div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
            <span style={{ fontSize: 44, lineHeight: 1, fontWeight: 800, color: "#163F77" }}>{averageSleepHours}</span>
            <span style={{ fontSize: 18, color: "#5E6E86" }}>hrs</span>
            <span style={{ fontSize: 15, color: "#768697" }}>↘{sleepChange}%</span>
          </div>
          <div style={{ borderTop: "1px solid rgba(91, 109, 132, 0.14)", paddingTop: 12 }}>
            <svg viewBox="0 0 520 110" style={{ width: "100%", height: 110, display: "block" }}>
              <defs>
                <linearGradient id="tracker-sleep-fill-wide" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="#5BA4C9" stopOpacity="0.32" />
                  <stop offset="100%" stopColor="#5BA4C9" stopOpacity="0.04" />
                </linearGradient>
              </defs>
              <path d={createAreaPath(sleepTrend, 520, 110)} fill="url(#tracker-sleep-fill-wide)" />
              <path d={createLinePath(sleepTrend, 520, 110)} fill="none" stroke="#5BA4C9" strokeWidth="3.5" strokeLinecap="round" />
            </svg>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", color: "#7C8798", fontSize: 13 }}>
            <span>Mods 1</span>
            <span>Week 2</span>
          </div>
        </div>

        <div
          className="card"
          style={{
            gridColumn: "span 7",
            padding: 0,
            overflow: "hidden",
            border: `1px solid ${C.border}`,
            background: "rgba(255,255,255,0.84)",
            backdropFilter: "blur(8px)",
            boxShadow: "0 10px 24px rgba(72, 88, 120, 0.08)",
            borderRadius: 18,
          }}
        >
          <div style={{ display: "grid", gridTemplateColumns: "220px minmax(0, 1fr)" }}>
            <div style={{ padding: "28px 22px", borderRight: "1px solid rgba(91, 109, 132, 0.1)", background: "linear-gradient(180deg, rgba(234,242,255,0.78), rgba(248,250,252,0.8))" }}>
              <div style={{ fontWeight: 800, fontSize: 18, color: "#32485F" }}>Wellness ROI:</div>
              <div style={{ marginTop: 28, display: "flex", alignItems: "end", gap: 10, fontSize: 36 }}>
                <span>🥝</span>
                <span>🍋</span>
                <span>🍎</span>
                <span>🫐</span>
              </div>
            </div>
            <div style={{ display: "grid" }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", borderBottom: "1px solid rgba(91, 109, 132, 0.12)" }}>
                <div style={{ padding: "22px 20px", display: "flex", alignItems: "center", gap: 12, borderRight: "1px solid rgba(91, 109, 132, 0.12)" }}>
                  <span style={{ fontSize: 28 }}>🖤</span>
                  <span style={{ color: "#314457", fontSize: 18 }}>Fatigue Risk <strong>↓ {fatigueRiskDrop}%</strong></span>
                </div>
                <div style={{ padding: "22px 20px", display: "flex", alignItems: "center", gap: 12 }}>
                  <span style={{ color: "#314457", fontSize: 18 }}>Nutrient Absorption <strong style={{ color: "#76B74A" }}>↑ {nutrientAbsorptionLift}%</strong></span>
                </div>
              </div>
              <div style={{ padding: "18px 20px", display: "grid", gap: 16 }}>
                <div style={{ color: "#4B5D72", fontSize: 16 }}>3-week improvement leads to better energy and resilience.</div>
                <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 8 }}>
                  <div style={{ width: 210, height: 12, borderRadius: 999, background: "#DCE4EA", overflow: "hidden" }}>
                    <div style={{ width: `${roiMeter}%`, height: "100%", background: "linear-gradient(90deg, #7AB25B, #456E5A 78%, #D6B140)" }} />
                  </div>
                  <span style={{ color: "#D6B140", fontSize: 18 }}>▶</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div
          className="card"
          style={{
            ...plannerInspiredGlass,
            gridColumn: "1 / -1",
            padding: "22px 24px",
            display: "grid",
            gap: 18,
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", gap: 18, alignItems: "center", flexWrap: "wrap" }}>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline", color: "#314457" }}>
              <span style={{ fontWeight: 800, fontSize: 22 }}>{profile?.name || "Nav"}'s Rhythm Summary</span>
              <span style={{ fontSize: 18 }}>— 21 days of consistent tracking • {rhythmSummary}</span>
            </div>
            <button className="btn-primary" style={{ minWidth: 220, background: "linear-gradient(180deg, #4D5B69, #2F3E4C)", borderColor: "#2F3E4C" }} onClick={() => alert("Trajectory view coming soon! Track your long-term wellness improvements here.")}>
              View Trajectory
            </button>
          </div>
          <div style={{ borderTop: "1px solid rgba(91, 109, 132, 0.14)", paddingTop: 14, display: "flex", justifyContent: "center", flexWrap: "wrap", gap: 10, color: "#314457", fontSize: 18 }}>
            <strong>Next Focus:</strong>
            <span>{nextFocus}</span>
          </div>
        </div>

      </div>
        </div>
      </div>
    </div>

      <FloatingSousMazi message="How can I assist you today?" />

      {showManualLog && (
        <div
          onClick={() => setShowManualLog(false)}
          style={{ position: "fixed", inset: 0, background: "rgba(16, 31, 23, 0.45)", display: "grid", placeItems: "center", padding: "92px 20px 24px", zIndex: 1000 }}
        >
          <div
            className="card"
            onClick={(event) => event.stopPropagation()}
            style={{ ...plannerInspiredGlass, width: "min(560px, 100%)", maxHeight: "calc(100vh - 128px)", overflowY: "auto", padding: 24, display: "grid", gap: 16 }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "start" }}>
              <div>
                <div style={{ color: C.accent, fontSize: 12, fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase" }}>Manual Log</div>
                <div style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 28, color: C.text, marginTop: 8 }}>Update today&apos;s tracker</div>
              </div>
              <button className="btn-ghost" onClick={() => setShowManualLog(false)}>Close</button>
            </div>
            <div style={{ display: "grid", gap: 14 }}>
              <div>
                <label>Meal name</label>
                <input value={manualLog.mealName} onChange={(event) => setManualLog((current) => ({ ...current, mealName: event.target.value }))} placeholder="Ex: Restaurant salmon bowl" />
              </div>
              <div>
                <label>Meal slot</label>
                <select value={manualLog.mealSlot} onChange={(event) => setManualLog((current) => ({ ...current, mealSlot: event.target.value }))}>
                  <option value="breakfast">Breakfast</option>
                  <option value="lunch">Lunch</option>
                  <option value="dinner">Dinner</option>
                  <option value="snack">Snack</option>
                </select>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 14 }}>
                <div>
                  <label>Calories</label>
                  <input value={manualLog.calories} onChange={(event) => setManualLog((current) => ({ ...current, calories: event.target.value }))} placeholder="420" />
                </div>
                <div>
                  <label>Protein (g)</label>
                  <input value={manualLog.protein} onChange={(event) => setManualLog((current) => ({ ...current, protein: event.target.value }))} placeholder="28" />
                </div>
              </div>
              <div>
                <label>Note</label>
                <textarea value={manualLog.note} onChange={(event) => setManualLog((current) => ({ ...current, note: event.target.value }))} placeholder="Optional note or side suggestion for this meal" rows={4} style={{ width: "100%", borderRadius: 14, border: `1px solid ${C.border}`, padding: 14, resize: "vertical", font: "inherit", color: C.text, background: C.white }} />
              </div>
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 12, flexWrap: "wrap" }}>
              <button className="btn-ghost" onClick={() => setShowManualLog(false)}>Cancel</button>
              <button className="btn-primary" onClick={saveManualLog}>Save to tracker</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function ProfileTab({ user, profiles, profile, profileCount, setProfiles, setStep }) {
  const primary = profile || { name: "Not set", goal: "Not set" };
  const [editingIndex, setEditingIndex] = useState(null);
  const [editDraft, setEditDraft] = useState(defaultProfileDraft());
  const invitedCount = profiles.filter((p) => p.invited).length;
  const activeCount = Math.max(0, profileCount - invitedCount);
  const editHeightParts = getHeightParts(editDraft.height);

  useEffect(() => {
    if (editingIndex !== null && profiles[editingIndex]) {
      setEditDraft(profiles[editingIndex]);
    }
  }, [editingIndex, profiles]);

  const saveEdit = () => {
    if (editingIndex === null) return;
    setProfiles(profiles.map((p, index) => index === editingIndex ? editDraft : p));
    setEditingIndex(null);
  };

  const removeProfile = (index) => {
    setProfiles(profiles.filter((_, i) => i !== index));
    if (editingIndex === index) setEditingIndex(null);
  };

  return (
    <div style={{ padding: "24px 20px 92px", maxWidth: 1120, margin: "0 auto", display: "grid", gap: 20 }}>
      <div className="card" style={{
        padding: 0,
        overflow: "hidden",
        border: "1px solid rgba(74, 95, 78, 0.2)",
        background:
          "linear-gradient(125deg, rgba(18,43,33,0.95), rgba(38,82,63,0.86)), url('https://images.unsplash.com/photo-1547592166-23ac45744acd?auto=format&fit=crop&w=1600&q=80')",
        backgroundSize: "cover",
        backgroundPosition: "center",
        color: C.white,
      }}>
        <div style={{ padding: "28px 24px", display: "grid", gap: 14 }}>
          <div style={{ color: "rgba(255,255,255,0.82)", fontSize: 12, fontWeight: 700, letterSpacing: 1.3, textTransform: "uppercase" }}>Profile</div>
          <h2 style={{ fontFamily: "'Fraunces', serif", fontWeight: 700, fontSize: 34, lineHeight: 1.08, margin: 0 }}>Account & household</h2>
          <p style={{ color: "rgba(255,255,255,0.86)", maxWidth: 620, lineHeight: 1.7, margin: 0 }}>
            Keep your family nutrition setup clear and coordinated with live profile management, permissions, and household-level controls.
          </p>
        </div>
      </div>

      <div className="card" style={{ padding: 20, display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <div>
          <div style={{ fontWeight: 700, color: C.text }}>Household command center</div>
          <div style={{ color: C.subtext, fontSize: 14, marginTop: 4 }}>Primary goal: {primary.goal || "Not set"} · Active members: {activeCount}</div>
        </div>
        <button className="btn-primary" style={{ minWidth: 190 }} onClick={() => setStep("manage")}>Manage household</button>
      </div>

      {editingIndex !== null && (
        <div className="card" style={{ padding: 0, overflow: "hidden", border: `1px solid ${C.border}`, background: "linear-gradient(180deg, rgba(255,253,248,0.96), rgba(248,245,238,0.94))" }}>
          <div style={{ padding: "22px 24px", display: "grid", gap: 18 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "start", flexWrap: "wrap" }}>
              <div>
                <div style={{ color: C.accent, fontSize: 12, fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase" }}>Edit Profile</div>
                <h3 style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 28, color: C.text, marginTop: 8 }}>{editDraft.name || "Household member"} profile details</h3>
                <p style={{ color: C.subtext, fontSize: 14, lineHeight: 1.7, marginTop: 8, maxWidth: 720 }}>
                  These values are carried from onboarding and can be refined anytime for better meal planning, nutrition guidance, and profile personalization.
                </p>
              </div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 16 }}>
              <div><label>Name</label><input value={editDraft.name} onChange={e => setEditDraft({ ...editDraft, name: e.target.value })} /></div>
              <div><label>Age</label><input type="number" min="1" value={editDraft.age} onChange={e => setEditDraft({ ...editDraft, age: e.target.value })} /></div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 16 }}>
              <div>
                <label>Height</label>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                  <input
                    placeholder="ft"
                    value={editHeightParts.feet}
                    onChange={e => setEditDraft({ ...editDraft, height: buildHeightValue(e.target.value, editHeightParts.inches) })}
                  />
                  <input
                    placeholder="in"
                    value={editHeightParts.inches}
                    onChange={e => setEditDraft({ ...editDraft, height: buildHeightValue(editHeightParts.feet, e.target.value) })}
                  />
                </div>
              </div>
              <div><label>Weight</label><input placeholder="lb" value={editDraft.weight || ""} onChange={e => setEditDraft({ ...editDraft, weight: e.target.value })} /></div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 16 }}>
              <div><label>Activity level</label><select value={editDraft.activity} onChange={e => setEditDraft({ ...editDraft, activity: e.target.value })}>
                <option>Sedentary</option>
                <option>Moderate</option>
                <option>Active</option>
              </select></div>
              <div><label>Health goal</label><select value={editDraft.goal} onChange={e => setEditDraft({ ...editDraft, goal: e.target.value })}>
                <option>Maintain weight</option>
                <option>Weight loss</option>
                <option>Weight gain</option>
                <option>Improve health</option>
              </select></div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 16 }}>
              <div><label>Dietary pattern</label><select value={editDraft.dietaryPattern} onChange={e => setEditDraft({ ...editDraft, dietaryPattern: e.target.value })}>
                <option>None</option>
                <option>Vegan</option>
                <option>Vegetarian</option>
                <option>Mediterranean</option>
                <option>Low glycemic / low carb</option>
                <option>Other</option>
              </select></div>
              <div><label>Food preferences</label><input value={editDraft.preferences} onChange={e => setEditDraft({ ...editDraft, preferences: e.target.value })} /></div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 16 }}>
              <div><label>Allergy</label><input value={editDraft.allergies || ""} onChange={e => setEditDraft({ ...editDraft, allergies: e.target.value })} /></div>
              <div><label>Food dislikes</label><input value={editDraft.dislikes || ""} onChange={e => setEditDraft({ ...editDraft, dislikes: e.target.value })} /></div>
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 12, marginTop: 4 }}>
              <button className="btn-ghost" onClick={() => setEditingIndex(null)}>Cancel</button>
              <button className="btn-primary" onClick={saveEdit}>Save changes</button>
            </div>
          </div>
        </div>
      )}

      <div style={{ display: "grid", gap: 14 }}>
        {profiles.length === 0 && (
          <div className="card" style={{ padding: 20, color: C.subtext }}>No household profiles created yet.</div>
        )}
        {profiles.map((p, index) => (
          <div key={index} className="card" style={{ padding: 20, display: "grid", gap: 12, borderLeft: `4px solid ${p.invited ? "#c3b8a3" : C.accent}` }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div>
                <div style={{ fontWeight: 700, fontSize: 16 }}>{p.name || p.inviteEmail || `Member ${index + 1}`}</div>
                <div style={{ color: C.subtext, fontSize: 13 }}>{p.role}{p.age ? ` · Age ${p.age}` : ""}{p.invited ? " · Invited" : ""}</div>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                {!p.invited && <button className="btn-ghost" onClick={() => setEditingIndex(index)}>Edit</button>}
                <button className="btn-ghost" onClick={() => removeProfile(index)}>Remove</button>
              </div>
            </div>
            <div style={{ display: "grid", gap: 6, color: C.muted, fontSize: 13, background: C.bg, borderRadius: 12, border: `1px solid ${C.border}`, padding: 12 }}>
              <div><strong>Goal:</strong> {p.goal || "Not set"}</div>
              <div><strong>Activity:</strong> {p.activity || "Not set"}</div>
              <div><strong>Height:</strong> {p.height || "Not set"}</div>
              <div><strong>Weight:</strong> {p.weight ? `${p.weight} lb` : "Not set"}</div>
              <div><strong>Diet:</strong> {p.dietaryPattern || "Not set"}</div>
              <div><strong>Allergy:</strong> {p.allergies || "None"}</div>
              <div><strong>Preferences:</strong> {p.preferences || "None"}</div>
              {p.invited && <div><strong>Permission:</strong> {p.permission}</div>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ManageHouseholdModule({ profiles, setProfiles, onBack }) {
  const [dragIndex, setDragIndex] = useState(null);
  const [dragOverIndex, setDragOverIndex] = useState(null);

  const moveProfile = (from, to) => {
    if (to < 0 || to >= profiles.length) return;
    const next = [...profiles];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    setProfiles(next);
  };

  const updatePermission = (index, permission) => {
    setProfiles(profiles.map((p, i) => i === index ? { ...p, permission } : p));
  };

  const removeProfile = (index) => {
    setProfiles(profiles.filter((_, i) => i !== index));
  };

  const handleDragStart = (index) => (event) => {
    setDragIndex(index);
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", String(index));
  };

  const handleDragOver = (index) => (event) => {
    event.preventDefault();
    setDragOverIndex(index);
  };

  const handleDrop = (index) => (event) => {
    event.preventDefault();
    const sourceIndex = Number(event.dataTransfer.getData("text/plain"));
    if (!Number.isNaN(sourceIndex) && sourceIndex !== index) {
      moveProfile(sourceIndex, index);
    }
    setDragIndex(null);
    setDragOverIndex(null);
  };

  const handleDragEnd = () => {
    setDragIndex(null);
    setDragOverIndex(null);
  };

  return (
    <div style={{ padding: "24px 20px 92px", maxWidth: 1120, margin: "0 auto", display: "grid", gap: 20 }}>
      <div>
        <div style={{ color: C.accent, fontSize: 13, fontWeight: 700, letterSpacing: 1.3, textTransform: "uppercase" }}>Household</div>
        <h2 style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 28, marginTop: 8 }}>Manage household profiles</h2>
        <p style={{ color: C.subtext, fontSize: 14, lineHeight: 1.7 }}>Drag and drop profiles to reorder them, update invite permissions, or remove household members.</p>
      </div>

      {profiles.length === 0 && (
        <div className="card" style={{ padding: 20, color: C.subtext }}>No household profiles saved yet.</div>
      )}

      {profiles.map((p, index) => {
        const isDragging = dragIndex === index;
        const isDragOver = dragOverIndex === index && dragIndex !== null;
        return (
          <div
            key={index}
            className="card"
            draggable
            onDragStart={handleDragStart(index)}
            onDragOver={handleDragOver(index)}
            onDrop={handleDrop(index)}
            onDragEnd={handleDragEnd}
            style={{
              padding: 20,
              display: "grid",
              gap: 12,
              opacity: isDragging ? 0.4 : 1,
              border: isDragOver ? `2px dashed ${C.accent}` : "1px solid transparent",
              background: isDragOver ? `${C.accentLight}33` : C.white,
              transition: "background 0.2s, opacity 0.2s, border 0.2s",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div>
                <div style={{ fontWeight: 700, fontSize: 16 }}>{p.name || p.inviteEmail || `Member ${index + 1}`}</div>
                <div style={{ color: C.subtext, fontSize: 13 }}>{p.role}{p.age ? ` · Age ${p.age}` : ""}{p.invited ? " · Invited" : ""}</div>
              </div>
              <button className="btn-ghost" onClick={() => removeProfile(index)}>Remove</button>
            </div>
            <div style={{ display: "grid", gap: 8, color: C.muted, fontSize: 13 }}>
              <div><strong>Goal:</strong> {p.goal || "Not set"}</div>
              <div><strong>Activity:</strong> {p.activity || "Not set"}</div>
              <div><strong>Diet:</strong> {p.dietaryPattern || "Not set"}</div>
              <div><strong>Preferences:</strong> {p.preferences || "None"}</div>
              {p.invited && <div><strong>Permission:</strong> {p.permission}</div>}
            </div>
            <div style={{ display: "grid", gap: 10 }}>
              <label style={{ fontSize: 13, fontWeight: 600, color: C.text }}>Permission level</label>
              <select value={p.permission || "Full profile access"} onChange={e => updatePermission(index, e.target.value)}>
                <option>Full profile access</option>
                <option>Meal planning only</option>
                <option>Track access only</option>
              </select>
            </div>
          </div>
        );
      })}

      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <button className="btn-ghost" style={{ width: 180 }} onClick={onBack}>Back to profile</button>
      </div>
    </div>
  );
}

function CookModeTab() {
  return (
    <div style={{ padding: "24px 20px 92px", maxWidth: 1120, margin: "0 auto", display: "grid", gap: 20 }}>
      <div>
        <div style={{ color: C.accent, fontSize: 13, fontWeight: 700, letterSpacing: 1.3, textTransform: "uppercase" }}>Cook Mode</div>
        <h2 style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 28, marginTop: 8 }}>Recipe step-by-step</h2>
      </div>
      <div className="card" style={{ padding: 20 }}>
        <div style={{ display: "grid", gap: 12 }}>
          <div style={{ fontWeight: 700 }}>Mediterranean Salmon Plate</div>
          <div style={{ color: C.subtext }}>Ingredients</div>
          <ul style={{ paddingLeft: 18, color: C.text }}><li>Salmon</li><li>Olive oil</li><li>Tomatoes</li></ul>
          <div style={{ color: C.subtext }}>Steps</div>
          <ol style={{ paddingLeft: 18, color: C.text }}><li>Season salmon and roast 18 minutes.</li><li>Sear veggies in olive oil.</li><li>Plate and enjoy.</li></ol>
          <button className="btn-primary">Start timer</button>
        </div>
      </div>
    </div>
  );
}

function MvpPlannerTab() {
  return null;
}

function BottomNav({ step, setStep }) {
  const tabs = [
    ["homeClassic", "Home"],
    ["profile", "Profile"],
    ["recipesClassic", "Recipes"],
    ["weeklyPlanner", "Planner"],
    ["tracker", "Tracker"],
    ["results", "Results"],
  ];
  return (
    <div className="bottom-nav-modern" style={{ position: "fixed", bottom: 0, left: 0, right: 0, background: C.white, borderTop: `1px solid ${C.border}`, display: "flex", justifyContent: "space-around", alignItems: "center", height: 72, zIndex: 100 }}>
      {tabs.map(([id,label]) => (
        <button key={id} onClick={() => setStep(id)} style={{ background: "transparent", border: "none", color: step === id ? C.accent : C.subtext, fontSize: 12, fontWeight: step === id ? 700 : 500, display: "flex", flexDirection: "column", alignItems: "center", gap: 4, cursor: "pointer" }}>
          <span style={{ width: 34, height: 34, borderRadius: 12, display: "grid", placeItems: "center", background: step === id ? C.accentLight : C.bg, border: step === id ? `1px solid ${C.accent}` : `1px solid ${C.border}` }}>{label[0]}</span>
          {label}
        </button>
      ))}
    </div>
  );
}

function OnboardingModule({ user, profiles, profile, profileCount, setProfiles, step, setStep, plannerDay, plannerState, setPlannerState }) {
  const showRightSidebar = step === "profile";
  const [showIntro, setShowIntro] = useState(true);
  const classicMealLogStorageKey = `mazimeal:classic-meal-log:${user || "guest"}`;
  const classicHydrationStorageKey = `mazimeal:classic-hydration-log:${user || "guest"}`;
  const [classicMealLogByDay, setClassicMealLogByDay] = useState(() => safeReadJson(classicMealLogStorageKey, {}));
  const [classicHydrationByDay, setClassicHydrationByDay] = useState(() => safeReadJson(classicHydrationStorageKey, {}));

  useEffect(() => {
    const timer = setTimeout(() => setShowIntro(false), 1200);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    setClassicMealLogByDay(safeReadJson(classicMealLogStorageKey, {}));
    setClassicHydrationByDay(safeReadJson(classicHydrationStorageKey, {}));
  }, [classicMealLogStorageKey, classicHydrationStorageKey]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(classicMealLogStorageKey, JSON.stringify(classicMealLogByDay));
  }, [classicMealLogByDay, classicMealLogStorageKey]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(classicHydrationStorageKey, JSON.stringify(classicHydrationByDay));
  }, [classicHydrationByDay, classicHydrationStorageKey]);

  return (
    <>
      {showIntro && (
        <div className="intro-overlay">
          <div className="intro-core">
            <div className="intro-logo">M</div>
            <div className="intro-title">Mazimeal</div>
            <div className="intro-sub">Preparing Your Nutrition Workspace</div>
          </div>
        </div>
      )}
      <TopHeader user={user} />
      <LeftSidebar step={step} setStep={setStep} />
      <div className={`main-content app-backdrop theme-${step} ${showIntro ? "app-entering" : ""}`} style={{ minHeight: "100vh", paddingBottom: 92, background: C.bg, paddingTop: 64, marginRight: showRightSidebar ? 320 : 0, transition: "margin-right 0.2s ease" }}>
        {step === "home" && <HomeDashboard user={user} setStep={setStep} plannerDay={plannerDay} />}
        {step === "homeClassic" && (
          <HomeDashboardClassic
            user={user}
            setStep={setStep}
            plannerDay={plannerDay}
            profile={profile}
            mealLogByDay={classicMealLogByDay}
            setMealLogByDay={setClassicMealLogByDay}
            hydrationByDay={classicHydrationByDay}
            setHydrationByDay={setClassicHydrationByDay}
          />
        )}
        {step === "recipes" && <RecipesTab setStep={setStep} />}
        {step === "recipesClassic" && (
          <RecipesClassicPage
            user={user}
            setStep={setStep}
            plannerDay={plannerDay}
            plannerState={plannerState}
            setPlannerState={setPlannerState}
            selectedDayIndex={Math.min(Math.max(plannerState.selectedDayIndex ?? new Date().getDay(), 0), 6)}
          />
        )}
        {step === "weeklyPlan" && <WeeklyPlanTab profiles={profiles} />}
        {step === "weeklyPlanner" && (
          <WeeklyPlannerShowcase
            profiles={profiles}
            plannerDays={plannerState.days}
            setPlannerDays={(daysOrUpdater) =>
              setPlannerState((current) => ({
                ...current,
                days: typeof daysOrUpdater === "function" ? daysOrUpdater(current.days) : daysOrUpdater,
              }))
            }
            plannerAnchorDate={plannerState.anchorDate}
            setPlannerAnchorDate={(anchorDateOrUpdater) =>
              setPlannerState((current) => ({
                ...current,
                anchorDate: typeof anchorDateOrUpdater === "function" ? anchorDateOrUpdater(current.anchorDate) : anchorDateOrUpdater,
              }))
            }
            selectedDayIndex={Math.min(Math.max(plannerState.selectedDayIndex ?? new Date().getDay(), 0), 6)}
            setSelectedDayIndex={(selectedDayIndexOrUpdater) =>
              setPlannerState((current) => ({
                ...current,
                selectedDayIndex: Math.min(
                  Math.max(
                    typeof selectedDayIndexOrUpdater === "function"
                      ? selectedDayIndexOrUpdater(current.selectedDayIndex ?? new Date().getDay())
                      : selectedDayIndexOrUpdater,
                    0
                  ),
                  6
                ),
              }))
            }
          />
        )}
        {step === "tracker" && <TrackerTab plannerDay={plannerDay} plannerState={plannerState} setPlannerState={setPlannerState} profile={profile} />}
        {step === "results" && <ResultsModule profiles={profiles} onBack={() => setStep("profile")} />}
        {step === "manage" && <ManageHouseholdModule profiles={profiles} setProfiles={setProfiles} onBack={() => setStep("profile")} />}
        {step === "profile" && <ProfileTab user={user} profiles={profiles} profile={profile} profileCount={profileCount} setProfiles={setProfiles} setStep={setStep} />}
        {step === "cook" && <CookModeTab />}
      </div>
      <RightSidebar profiles={profiles} visible={showRightSidebar} />
      <div className="app-desktop-footer">
        <SiteFooter compact />
      </div>
      <BottomNav step={step} setStep={setStep} />
    </>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MODULE 3: PROFILES
// ═══════════════════════════════════════════════════════════════════════════════
function ProfileModule({ profiles, setProfiles, onContinue }) {
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ name: "", age: "", role: "Adult", conditions: [], allergies: [] });

  const toggle = (arr, v) => arr.includes(v) ? arr.filter(x => x !== v) : [...arr, v];

  const addProfile = () => {
    if (!form.name) return;
    setProfiles(p => [...p, { ...form, id: Date.now() }]);
    setForm({ name: "", age: "", role: "Adult", conditions: [], allergies: [] });
    setAdding(false);
  };

  const roleStyle = { Adult: { bg: C.skyLight, color: C.sky, border: "#90CFEE" }, Child: { bg: C.accentLight, color: C.accent, border: C.accent }, Infant: { bg: C.goldLight, color: C.gold, border: "#F0B84A" }, Elderly: { bg: C.lavLight, color: C.lavender, border: "#B090E0" } };

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "36px 24px" }} className="fade-up">
      <div style={{ marginBottom: 32 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 6 }}>
          <div style={{ width: 38, height: 38, background: C.accentLight, border: `1.5px solid ${C.accent}`, borderRadius: 10, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 20 }}>👨‍👩‍👧</div>
          <h2 style={{ fontFamily: "'Lora'", fontWeight: 600, fontSize: 24, color: C.text }}>Family Profiles</h2>
        </div>
        <p style={{ color: C.muted, fontSize: 13.5, marginLeft: 50 }}>Build your household's nutrition map. Mazimeal personalizes every meal recommendation around each person's needs.</p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px,1fr))", gap: 16, marginBottom: 20 }}>
        {profiles.map(p => {
          const rs = roleStyle[p.role] || roleStyle.Adult;
          return (
            <div key={p.id} className="card" style={{ padding: 20 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 14 }}>
                <div style={{ width: 42, height: 42, background: C.accentLight, border: `1.5px solid ${C.accent}`, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "'Plus Jakarta Sans'", fontWeight: 800, fontSize: 18, color: C.accent }}>
                  {p.name[0]}
                </div>
                <span style={{ background: rs.bg, color: rs.color, border: `1px solid ${rs.border}`, borderRadius: 6, padding: "2px 9px", fontSize: 11, fontWeight: 600 }}>{p.role}</span>
              </div>
              <div style={{ fontWeight: 700, fontSize: 15.5, color: C.text, marginBottom: 2 }}>{p.name}</div>
              {p.age && <div style={{ fontSize: 12, color: C.muted, marginBottom: 10 }}>Age {p.age}</div>}
              {p.conditions.filter(c => c !== "None").length > 0 && (
                <div style={{ marginBottom: 8 }}>
                  <div style={{ fontSize: 10.5, color: C.muted, fontWeight: 600, letterSpacing: 0.5, marginBottom: 5, textTransform: "uppercase" }}>Conditions</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                    {p.conditions.filter(c => c !== "None").map(c => <span key={c} style={{ background: C.coralLight, color: C.coral, border: `1px solid #F08080`, borderRadius: 4, padding: "2px 7px", fontSize: 11 }}>{c}</span>)}
                  </div>
                </div>
              )}
              {p.allergies.filter(a => a !== "None").length > 0 && (
                <div>
                  <div style={{ fontSize: 10.5, color: C.muted, fontWeight: 600, letterSpacing: 0.5, marginBottom: 5, textTransform: "uppercase" }}>Allergies</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                    {p.allergies.filter(a => a !== "None").map(a => <span key={a} style={{ background: C.goldLight, color: C.gold, border: `1px solid #F0C060`, borderRadius: 4, padding: "2px 7px", fontSize: 11 }}>⚠ {a}</span>)}
                  </div>
                </div>
              )}
            </div>
          );
        })}

        {!adding && (
          <button onClick={() => setAdding(true)} style={{ background: "transparent", border: `2px dashed ${C.border}`, borderRadius: 16, padding: 20, cursor: "pointer", minHeight: 160, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 8, color: C.muted, transition: "all 0.2s" }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = C.accent; e.currentTarget.style.color = C.accent; e.currentTarget.style.background = C.accentLight; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = C.border; e.currentTarget.style.color = C.muted; e.currentTarget.style.background = "transparent"; }}>
            <span style={{ fontSize: 28, lineHeight: 1 }}>+</span>
            <span style={{ fontSize: 13, fontWeight: 600 }}>Add Family Member</span>
          </button>
        )}
      </div>

      {adding && (
        <div className="card" style={{ padding: 28, marginBottom: 20 }}>
          <h3 style={{ fontFamily: "'Lora'", fontWeight: 600, fontSize: 18, color: C.text, marginBottom: 20 }}>New Profile</h3>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16, marginBottom: 20 }}>
            <div><label>Name</label><input placeholder="e.g. Emma" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} /></div>
            <div><label>Age</label><input type="number" placeholder="e.g. 8" value={form.age} onChange={e => setForm(f => ({ ...f, age: e.target.value }))} /></div>
            <div><label>Role</label>
              <select value={form.role} onChange={e => setForm(f => ({ ...f, role: e.target.value }))}>
                {["Adult","Child","Infant","Elderly"].map(r => <option key={r}>{r}</option>)}
              </select>
            </div>
          </div>
          <div style={{ marginBottom: 16 }}>
            <label style={{ marginBottom: 8 }}>Health Conditions</label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 7 }}>
              {CONDITIONS.map(c => <button key={c} onClick={() => setForm(f => ({ ...f, conditions: toggle(f.conditions, c) }))} className={`chip ${form.conditions.includes(c) ? "active" : ""}`}>{c}</button>)}
            </div>
          </div>
          <div style={{ marginBottom: 22 }}>
            <label style={{ marginBottom: 8 }}>Allergies / Intolerances</label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 7 }}>
              {ALLERGIES.map(a => <button key={a} onClick={() => setForm(f => ({ ...f, allergies: toggle(f.allergies, a) }))} className={`chip ${form.allergies.includes(a) ? "active" : ""}`} style={form.allergies.includes(a) ? { background: C.goldLight, borderColor: "#F0B84A", color: C.gold } : {}}>⚠ {a}</button>)}
            </div>
          </div>
          <div style={{ display: "flex", gap: 12 }}>
            <button className="btn-primary" onClick={addProfile}>Add Profile</button>
            <button className="btn-ghost" onClick={() => setAdding(false)}>Cancel</button>
          </div>
        </div>
      )}

      {profiles.length > 0 && !adding && (
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <button className="btn-primary" onClick={onContinue} style={{ fontSize: 15, padding: "13px 32px" }}>
            Generate AI Meal Plan →
          </button>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MODULE 3: ENGINE
// ═══════════════════════════════════════════════════════════════════════════════
function EngineModule({ profiles, onResults }) {
  const [stage, setStage] = useState(0);
  const stages = [
    { icon: "🔍", label: "Scanning 847 open-source nutrition databases...",   color: C.accent },
    { icon: "⚗️", label: "Mapping food synergy combination pairs...",          color: C.gold },
    { icon: "🧬", label: "Computing bioavailability enhancement scores...",    color: C.sky },
    { icon: "👨‍👩‍👧", label: "Cross-referencing all family member profiles...",   color: C.lavender },
    { icon: "🛡️", label: "Filtering allergens & health contraindications...", color: C.coral },
    { icon: "✦",  label: "Sequencing and finalizing optimized meal plan...",  color: C.accent },
  ];

  useEffect(() => {
    const t = setInterval(() => setStage(s => {
      if (s >= stages.length - 1) { clearInterval(t); setTimeout(onResults, 700); return s; }
      return s + 1;
    }), 700);
    return () => clearInterval(t);
  }, []);

  const allC = [...new Set(profiles.flatMap(p => p.conditions).filter(c => c !== "None"))];
  const allA = [...new Set(profiles.flatMap(p => p.allergies).filter(a => a !== "None"))];

  return (
    <div style={{ minHeight: "80vh", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: 28 }} className="fade-up">
      <div style={{ width: "100%", maxWidth: 500 }}>
        <div style={{ textAlign: "center", marginBottom: 36 }}>
          <div style={{ width: 72, height: 72, background: `linear-gradient(135deg, ${C.accent}, #00D98B)`, borderRadius: 20, margin: "0 auto 18px", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 36, boxShadow: `0 8px 32px ${C.accentGlow}`, animation: "pulse 2s ease-in-out infinite" }}>✦</div>
          <h2 style={{ fontFamily: "'Lora'", fontWeight: 600, fontSize: 26, color: C.text, marginBottom: 8 }}>Mazimeal Engine Running</h2>
          <p style={{ color: C.muted, fontSize: 13.5 }}>Building your family's personalized nutrition blueprint</p>
        </div>

        <div className="card" style={{ padding: 6, marginBottom: 20 }}>
          {stages.map((st, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 14, padding: "12px 16px", borderRadius: 10, background: i === stage ? `${st.color}0D` : "transparent", transition: "background 0.3s", opacity: i <= stage ? 1 : 0.35 }}>
              <span style={{ fontSize: 18, minWidth: 26 }}>{st.icon}</span>
              <span style={{ fontSize: 13, color: i === stage ? st.color : C.muted, fontWeight: i === stage ? 600 : 400, flex: 1 }}>{st.label}</span>
              {i < stage && <span style={{ color: C.accent, fontSize: 16, fontWeight: 700 }}>✓</span>}
              {i === stage && <div className="spinner" style={{ width: 18, height: 18, borderWidth: 2.5, borderTopColor: st.color, flexShrink: 0 }} />}
            </div>
          ))}
        </div>

        {(allC.length > 0 || allA.length > 0) && (
          <div className="card" style={{ padding: 16 }}>
            <div style={{ fontSize: 10.5, color: C.muted, fontWeight: 700, letterSpacing: 1, textTransform: "uppercase", marginBottom: 10 }}>Optimization Parameters</div>
            {allC.length > 0 && <div style={{ marginBottom: 7 }}><span style={{ fontSize: 12, color: C.subtext }}>Conditions: </span>{allC.map(c => <span key={c} style={{ background: C.coralLight, color: C.coral, borderRadius: 4, padding: "2px 8px", fontSize: 11, marginRight: 4 }}>{c}</span>)}</div>}
            {allA.length > 0 && <div><span style={{ fontSize: 12, color: C.subtext }}>Excluded allergens: </span>{allA.map(a => <span key={a} style={{ background: C.goldLight, color: C.gold, borderRadius: 4, padding: "2px 8px", fontSize: 11, marginRight: 4 }}>⚠ {a}</span>)}</div>}
          </div>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MODULE 4: RESULTS
// ═══════════════════════════════════════════════════════════════════════════════
function ResultsModule({ profiles, onBack }) {
  const [selected, setSelected] = useState(null);
  const [tab, setTab] = useState("recipes");
  const [saved, setSaved] = useState([]);

  const allA = [...new Set(profiles.flatMap(p => p.allergies).filter(a => a !== "None"))];
  const allC = [...new Set(profiles.flatMap(p => p.conditions).filter(c => c !== "None"))];
  const filtered = RECIPES.filter(r => !allA.some(a => r.tags.some(t => t.toLowerCase().includes(a.toLowerCase()))));

  const weekDays = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];
  const plan = weekDays.map((day, i) => ({
    day,
    breakfast: ["Oat bowl + berries","Eggs & avocado toast","Greek yoghurt + granola","Smoothie bowl","Chia seed pudding","Whole grain waffles","Fruit & nut mix"][i],
    lunch: filtered[i % filtered.length]?.name || "Quinoa salad",
    dinner: filtered[(i + 1) % filtered.length]?.name || "Salmon bowl",
    calories: [420, 510, 380, 455, 430, 500, 390][i],
    balance: ["Good","Excellent","Good","Balanced","Strong","Excellent","Good"][i],
  }));

  const mealAnalytics = plan.map(row => ({
    day: row.day,
    breakfast: { meal: row.breakfast, calories: Math.round(row.calories * 0.28), quality: "High protein" },
    lunch: { meal: row.lunch, calories: Math.round(row.calories * 0.36), quality: "Balanced" },
    dinner: { meal: row.dinner, calories: Math.round(row.calories * 0.34), quality: "Light & nutrient-dense" },
  }));

  const nutrientColors = [C.accent, C.sky, C.gold, C.lavender, C.coral, C.accent];

  const tabs = [["recipes","🍽 Recipes"], ["analytics","📊 Analytics"], ["nutrition","📈 Nutrition Map"]];

  return (
    <div style={{ maxWidth: 980, margin: "0 auto", padding: "32px 24px" }} className="fade-up">
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 28 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5 }}>
            <div style={{ width: 8, height: 8, background: C.accent, borderRadius: "50%", animation: "pulse 2s ease-in-out infinite" }} />
            <span style={{ fontSize: 11.5, color: C.accent, fontWeight: 700, letterSpacing: 0.5 }}>MEAL PLAN READY</span>
          </div>
          <h2 style={{ fontFamily: "'Lora'", fontWeight: 600, fontSize: 26, color: C.text }}>Your Family's Nutrition Plan</h2>
          <p style={{ color: C.muted, fontSize: 13.5, marginTop: 4 }}>{filtered.length} recipes · {profiles.length} family members · {allC.length} condition{allC.length !== 1 ? "s" : ""} optimised</p>
          <div style={{ marginTop: 12, display: "inline-flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6, background: C.accentLight, border: `1px solid ${C.accent}`, borderRadius: 999, padding: "8px 14px", color: C.accent, fontSize: 12, fontWeight: 700 }}>
              👨‍👩‍👧‍👦 {profiles.length} household members
            </span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6, background: C.bg, border: `1px solid ${C.border}`, borderRadius: 999, padding: "8px 14px", color: C.text, fontSize: 12 }}>
              📆 Daily meal analytics available
            </span>
          </div>
        </div>
        <button className="btn-ghost" onClick={onBack}>← Edit Profiles</button>
      </div>

      {/* Summary stats */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12, marginBottom: 28 }}>
        <StatCard icon="🍽" val={filtered.length} label="Recipes Generated" color={C.accent} />
        <StatCard icon="⚡" val={filtered.reduce((a,r) => a + r.synergies.length, 0)} label="Synergy Combos" color={C.gold} />
        <StatCard icon="🛡" val={allA.length} label="Allergens Excluded" color={C.coral} />
        <StatCard icon="💊" val={allC.length} label="Conditions Managed" color={C.sky} />
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 3, marginBottom: 24, background: C.white, padding: 4, borderRadius: 12, border: `1.5px solid ${C.border}`, width: "fit-content", boxShadow: "0 1px 4px rgba(0,80,40,0.06)" }}>
        {tabs.map(([id, label]) => (
          <button key={id} onClick={() => setTab(id)} className={`nav-link ${tab === id ? "active" : ""}`} style={{ fontFamily: "'Plus Jakarta Sans'" }}>
            {label}
          </button>
        ))}
      </div>

      {/* RECIPES */}
      {tab === "recipes" && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(285px,1fr))", gap: 18 }}>
          {filtered.map(r => (
            <div key={r.id} className="card" style={{ padding: 22, cursor: "pointer", transition: "all 0.2s", borderColor: selected?.id === r.id ? C.accent : C.border, background: selected?.id === r.id ? C.accentLight : C.white }}
              onClick={() => setSelected(selected?.id === r.id ? null : r)}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 14 }}>
                <div style={{ width: 52, height: 52, background: C.bg, border: `1.5px solid ${C.border}`, borderRadius: 14, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 28 }}>{r.emoji}</div>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <span style={{ fontSize: 11.5, color: C.muted, background: C.bg, border: `1px solid ${C.border}`, borderRadius: 6, padding: "3px 8px" }}>⏱ {r.time}</span>
                  <button onClick={e => { e.stopPropagation(); setSaved(s => s.includes(r.id) ? s.filter(x => x !== r.id) : [...s, r.id]); }}
                    style={{ background: "none", border: "none", cursor: "pointer", fontSize: 20, color: saved.includes(r.id) ? C.coral : C.dim }}>
                    {saved.includes(r.id) ? "♥" : "♡"}
                  </button>
                </div>
              </div>

              <h3 style={{ fontWeight: 700, fontSize: 15, color: C.text, marginBottom: 10, lineHeight: 1.35 }}>{r.name}</h3>
              <div style={{ marginBottom: 10 }}>
                {r.synergies.map(s => <SynergyPill key={s} text={s} />)}
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginBottom: 14 }}>
                {r.tags.slice(0,2).map((t,i) => <Tag key={t} label={t} colorKey={r.tagColors[i]} />)}
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: C.muted, paddingTop: 12, borderTop: `1.5px solid ${C.border}` }}>
                <span style={{ fontWeight: 500 }}>{r.cal} kcal</span>
                <span style={{ color: r.diff === "Easy" ? C.accent : C.gold, fontWeight: 600 }}>{r.diff}</span>
              </div>

              {selected?.id === r.id && (
                <div style={{ marginTop: 18, paddingTop: 18, borderTop: `1.5px solid ${C.border}` }}>
                  <div style={{ fontSize: 10.5, color: C.muted, fontWeight: 700, letterSpacing: 0.8, textTransform: "uppercase", marginBottom: 10 }}>Nutrient Optimisation</div>
                  {Object.entries(r.nutrients).map(([k, v], i) => (
                    <NutrientBar key={k} label={k} value={v} color={nutrientColors[i % nutrientColors.length]} />
                  ))}
                  <div style={{ background: C.accentLight, border: `1.5px solid ${C.accent}`, borderRadius: 10, padding: 13, marginTop: 14 }}>
                    <div style={{ fontSize: 11, color: C.accent, fontWeight: 700, marginBottom: 4 }}>💡 Bioavailability Tip</div>
                    <p style={{ fontSize: 12, color: C.text, lineHeight: 1.65 }}>{r.tip}</p>
                  </div>
                  <div style={{ marginTop: 14 }}>
                    <div style={{ fontSize: 10.5, color: C.muted, fontWeight: 700, letterSpacing: 0.8, textTransform: "uppercase", marginBottom: 10 }}>Preparation Steps</div>
                    {r.steps.map((step, i) => (
                      <div key={i} style={{ display: "flex", gap: 10, marginBottom: 9 }}>
                        <span style={{ minWidth: 22, height: 22, background: C.accentLight, border: `1.5px solid ${C.accent}`, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, color: C.accent, fontWeight: 700, flexShrink: 0 }}>{i + 1}</span>
                        <span style={{ fontSize: 12.5, color: C.subtext, lineHeight: 1.6 }}>{step}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {tab === "analytics" && (
        <div style={{ display: "grid", gap: 18 }}>
          {mealAnalytics.map(day => (
            <div key={day.day} className="card" style={{ padding: 20 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 18 }}>
                <div>
                  <div style={{ fontSize: 14, color: C.muted, textTransform: "uppercase", letterSpacing: 1.3, fontWeight: 700 }}>Daily Analytics</div>
                  <div style={{ fontWeight: 700, fontSize: 20 }}>{day.day}</div>
                </div>
                <span style={{ color: C.accent, fontWeight: 700 }}>{plan.find(p => p.day === day.day)?.balance}</span>
              </div>
              <div style={{ display: "grid", gap: 14 }}>
                {Object.entries(day).filter(([key]) => key !== "day").map(([meal, details]) => (
                  <div key={meal} style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 12, alignItems: "center", padding: 18, background: C.bg, borderRadius: 16 }}>
                    <div>
                      <div style={{ textTransform: "capitalize", fontWeight: 700, color: C.text, marginBottom: 6 }}>{meal}</div>
                      <div style={{ fontSize: 14, color: C.subtext }}>{details.meal}</div>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <div style={{ fontWeight: 700, color: C.accent }}>{details.calories} kcal</div>
                      <div style={{ fontSize: 12, color: C.muted }}>{details.quality}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* NUTRITION MAP */}
      {tab === "nutrition" && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px,1fr))", gap: 18 }}>
          {profiles.map(p => (
            <div key={p.id} className="card" style={{ padding: 24 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 16.5, color: C.text }}>{p.name}</div>
                  <div style={{ fontSize: 12, color: C.muted, marginTop: 2 }}>{p.role}{p.age ? ` · Age ${p.age}` : ""}</div>
                </div>
                <div style={{ width: 46, height: 46, background: C.accentLight, border: `2px solid ${C.accent}`, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 800, fontSize: 20, color: C.accent }}>
                  {p.name[0]}
                </div>
              </div>
              {[
                { label: "Iron",       value: p.conditions.includes("Iron Deficiency") ? 45 : 82, color: C.coral },
                { label: "Vitamin C",  value: 91,  color: C.accent },
                { label: "Vitamin D",  value: p.role === "Child" ? 88 : 62, color: C.gold },
                { label: "Omega-3",    value: 74,  color: C.sky },
                { label: "Fiber",      value: p.conditions.includes("Diabetes (Type 2)") ? 55 : 79, color: C.lavender },
                { label: "Folate",     value: p.conditions.includes("Pregnancy") ? 95 : 71, color: C.accent },
              ].map(n => <NutrientBar key={n.label} {...n} />)}
              {p.conditions.filter(c => c !== "None").length > 0 && (
                <div style={{ marginTop: 14, padding: 12, background: C.coralLight, border: `1px solid #F08080`, borderRadius: 8 }}>
                  <div style={{ fontSize: 10.5, color: C.coral, fontWeight: 700, marginBottom: 3 }}>CLINICAL FOCUS</div>
                  <p style={{ fontSize: 12, color: C.subtext }}>Optimised for: {p.conditions.filter(c => c !== "None").join(", ")}</p>
                </div>
              )}
            </div>
          ))}

          {/* Family synergy score */}
          <div className="card" style={{ padding: 24 }}>
            <h3 style={{ fontWeight: 700, fontSize: 16, color: C.text, marginBottom: 18 }}>Family Synergy Score</h3>
            <div style={{ display: "flex", alignItems: "center", gap: 20, marginBottom: 20 }}>
              <div style={{ position: "relative", width: 88, height: 88, flexShrink: 0 }}>
                <svg viewBox="0 0 88 88" style={{ transform: "rotate(-90deg)" }}>
                  <circle cx="44" cy="44" r="36" fill="none" stroke={C.border} strokeWidth="8" />
                  <circle cx="44" cy="44" r="36" fill="none" stroke={C.accent} strokeWidth="8"
                    strokeDasharray={`${2 * Math.PI * 36 * 0.87} ${2 * Math.PI * 36}`} strokeLinecap="round" />
                </svg>
                <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 800, fontSize: 22, color: C.accent, fontFamily: "'Lora'" }}>87</div>
              </div>
              <div>
                <div style={{ fontWeight: 700, fontSize: 15, color: C.text, marginBottom: 4 }}>Excellent Optimisation</div>
                <p style={{ fontSize: 12.5, color: C.muted, lineHeight: 1.6 }}>Your plan scores 87% nutrient synergy — significantly above the 52% average for unplanned family diets.</p>
              </div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              {[
                ["Synergy Combos",   "12 active", C.accent],
                ["Allergen Safety",  "100%",      C.sky],
                ["Conditions Covered", `${allC.length} mgd`, C.gold],
                ["Bioavailability",  "+34%",      C.lavender],
              ].map(([k, v, c]) => (
                <div key={k} style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: 10, padding: "10px 13px" }}>
                  <div style={{ fontSize: 10.5, color: C.muted, fontWeight: 600 }}>{k}</div>
                  <div style={{ fontWeight: 800, color: c, fontSize: 16, marginTop: 2 }}>{v}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function WeeklyPlanTab({ profiles }) {
  const allA = [...new Set(profiles.flatMap(p => p.allergies).filter(a => a !== "None"))];
  const filtered = RECIPES.filter(r => !allA.some(a => r.tags.some(t => t.toLowerCase().includes(a.toLowerCase()))));
  const weekDays = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];
  const today = new Date();
  const startOfWeek = new Date(today);
  startOfWeek.setHours(0, 0, 0, 0);
  startOfWeek.setDate(today.getDate() - today.getDay());
  const currentWeekDates = weekDays.map((_, index) => {
    const date = new Date(startOfWeek);
    date.setDate(startOfWeek.getDate() + index);
    return {
      shortDay: date.toLocaleDateString("en-US", { weekday: "short" }),
      dayNumber: date.toLocaleDateString("en-US", { day: "numeric" }),
      monthLabel: date.toLocaleDateString("en-US", { month: "short" }),
      fullLabel: date.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" }),
    };
  });
  const weekRangeLabel = `${currentWeekDates[0].monthLabel} ${currentWeekDates[0].dayNumber} - ${currentWeekDates[currentWeekDates.length - 1].monthLabel} ${currentWeekDates[currentWeekDates.length - 1].dayNumber}`;
  const nutrientColors = [C.accent, C.sky, C.gold, C.lavender, C.coral, C.accent];
  const breakfastMeals = [
    {
      name: "Oat bowl + berries",
      time: "10 min",
      cal: 290,
      diff: "Easy",
      emoji: "🥣",
      synergies: ["Fiber + Antioxidants", "Slow-release energy"],
      tags: ["Breakfast", "High Fiber", "Quick"],
      nutrients: { Fiber: 82, Antioxidants: 88, Protein: 42, "Steady Energy": 76 },
      tip: "Adding berries to oats supports a slower glucose rise while boosting polyphenol intake.",
      steps: ["Warm oats with your milk of choice", "Fold in berries and seeds", "Top with cinnamon for extra flavor and blood sugar support"],
      tagColors: ["accent", "lavender", "gold"],
    },
    {
      name: "Eggs & avocado toast",
      time: "12 min",
      cal: 340,
      diff: "Easy",
      emoji: "🍳",
      synergies: ["Protein + Healthy Fats", "Satiety support"],
      tags: ["Breakfast", "High Protein", "Quick"],
      nutrients: { Protein: 74, "Healthy Fats": 86, Fiber: 46, "Satiety": 90 },
      tip: "Pairing eggs with avocado helps extend fullness and improves absorption of fat-soluble nutrients.",
      steps: ["Toast whole grain bread", "Cook eggs to preference", "Mash avocado with lemon and spread before topping with eggs"],
      tagColors: ["accent", "sky", "gold"],
    },
    {
      name: "Greek yoghurt + granola",
      time: "8 min",
      cal: 310,
      diff: "Easy",
      emoji: "🥛",
      synergies: ["Protein + Probiotics", "Crunch + Cream balance"],
      tags: ["Breakfast", "Protein", "Gut Friendly"],
      nutrients: { Protein: 68, Calcium: 72, Probiotics: 80, Fiber: 44 },
      tip: "Choose lower-sugar granola to keep this breakfast protein-forward without a sugar spike.",
      steps: ["Spoon yoghurt into a bowl", "Add granola and fruit", "Finish with nuts or seeds for more staying power"],
      tagColors: ["accent", "lavender", "gold"],
    },
    {
      name: "Smoothie bowl",
      time: "10 min",
      cal: 320,
      diff: "Easy",
      emoji: "🍓",
      synergies: ["Fruit + Seeds", "Hydration + Micronutrients"],
      tags: ["Breakfast", "Refreshing", "Micronutrient-rich"],
      nutrients: { Hydration: 84, "Vitamin C": 86, Fiber: 58, Protein: 40 },
      tip: "Blend fruit with a protein base like Greek yoghurt to avoid a carb-only breakfast.",
      steps: ["Blend fruit, greens, and protein base", "Pour into a bowl", "Top with seeds, nuts, and sliced fruit"],
      tagColors: ["sky", "accent", "gold"],
    },
    {
      name: "Chia seed pudding",
      time: "5 min prep",
      cal: 260,
      diff: "Easy",
      emoji: "🥄",
      synergies: ["Omega-3 + Fiber", "Prep-ahead convenience"],
      tags: ["Breakfast", "Meal Prep", "Fiber"],
      nutrients: { Fiber: 85, "Omega-3": 74, Calcium: 61, Protein: 36 },
      tip: "Let chia soak overnight so the gel texture forms and digestion feels easier.",
      steps: ["Whisk chia seeds with milk", "Refrigerate overnight", "Top with fruit and nuts before serving"],
      tagColors: ["lavender", "accent", "gold"],
    },
    {
      name: "Whole grain waffles",
      time: "15 min",
      cal: 350,
      diff: "Medium",
      emoji: "🧇",
      synergies: ["Whole grains + Fruit", "Weekend fuel"],
      tags: ["Breakfast", "Whole Grain", "Family Favorite"],
      nutrients: { Carbs: 72, Fiber: 49, Protein: 38, "Family Appeal": 88 },
      tip: "Use a protein-rich topping like Greek yoghurt or nut butter to balance the waffles.",
      steps: ["Toast or cook waffles", "Top with fruit", "Add a protein topping before serving"],
      tagColors: ["gold", "accent", "sky"],
    },
    {
      name: "Fruit & nut mix",
      time: "5 min",
      cal: 240,
      diff: "Easy",
      emoji: "🍎",
      synergies: ["Healthy Fats + Fruit", "Portable breakfast"],
      tags: ["Breakfast", "Portable", "Quick"],
      nutrients: { "Healthy Fats": 72, Fiber: 54, Antioxidants: 63, Protein: 30 },
      tip: "Pair the mix with yoghurt or milk if you want more protein and longer fullness.",
      steps: ["Slice fresh fruit", "Combine with mixed nuts", "Add yoghurt on the side for a fuller meal"],
      tagColors: ["accent", "gold", "lavender"],
    },
  ];
  const snackMeals = [
    {
      name: "Apple slices + peanut butter",
      time: "5 min",
      cal: 190,
      diff: "Easy",
      emoji: "🍎",
      synergies: ["Fiber + Healthy Fats", "Snack satiety"],
      tags: ["Snack", "Quick", "Kid Friendly"],
      nutrients: { Fiber: 64, "Healthy Fats": 72, Protein: 28, Energy: 58 },
      tip: "Pairing fruit with nut butter slows digestion and helps the snack feel more filling.",
      steps: ["Slice an apple", "Add peanut or almond butter on the side", "Sprinkle cinnamon if you want extra flavor"],
      tagColors: ["accent", "gold", "sky"],
    },
    {
      name: "Greek yogurt cup",
      time: "2 min",
      cal: 140,
      diff: "Easy",
      emoji: "🥛",
      synergies: ["Protein + Probiotics", "Simple recovery snack"],
      tags: ["Snack", "High Protein", "Gut Friendly"],
      nutrients: { Protein: 70, Calcium: 66, Probiotics: 78, Energy: 46 },
      tip: "A plain or low-sugar yogurt keeps the snack higher in protein without extra sugar.",
      steps: ["Open yogurt cup", "Top with fruit or seeds if desired", "Serve chilled"],
      tagColors: ["accent", "lavender", "gold"],
    },
    {
      name: "Trail mix",
      time: "1 min",
      cal: 210,
      diff: "Easy",
      emoji: "🥜",
      synergies: ["Healthy Fats + Crunch", "Portable energy"],
      tags: ["Snack", "Portable", "Energy Boost"],
      nutrients: { "Healthy Fats": 78, Protein: 34, Fiber: 40, Energy: 68 },
      tip: "Portion trail mix ahead of time so it stays convenient without becoming too calorie-dense.",
      steps: ["Measure a serving", "Mix nuts, seeds, and dried fruit", "Pack for grab-and-go access"],
      tagColors: ["gold", "accent", "sky"],
    },
    {
      name: "Hummus + carrots",
      time: "5 min",
      cal: 160,
      diff: "Easy",
      emoji: "🥕",
      synergies: ["Fiber + Plant Protein", "Crunchy savory snack"],
      tags: ["Snack", "Vegetarian", "Fiber"],
      nutrients: { Fiber: 61, Protein: 30, "Vitamin A": 84, Energy: 44 },
      tip: "A veggie-and-dip snack adds produce earlier in the day without needing much prep.",
      steps: ["Spoon hummus into a small bowl", "Slice carrots or use baby carrots", "Serve immediately or pack ahead"],
      tagColors: ["accent", "sky", "gold"],
    },
    {
      name: "Cheese + whole grain crackers",
      time: "3 min",
      cal: 200,
      diff: "Easy",
      emoji: "🧀",
      synergies: ["Protein + Whole Grains", "Balanced savory bite"],
      tags: ["Snack", "Savory", "Balanced"],
      nutrients: { Protein: 42, Calcium: 62, Carbs: 46, Energy: 60 },
      tip: "Choosing whole grain crackers helps this snack stay steadier than refined snack options.",
      steps: ["Plate crackers", "Add sliced cheese", "Pair with fruit if you want more fiber"],
      tagColors: ["gold", "accent", "lavender"],
    },
    {
      name: "Berry protein smoothie",
      time: "6 min",
      cal: 220,
      diff: "Easy",
      emoji: "🫐",
      synergies: ["Protein + Antioxidants", "Post-school refill"],
      tags: ["Snack", "Protein", "Refreshing"],
      nutrients: { Protein: 64, Antioxidants: 76, Hydration: 72, Energy: 62 },
      tip: "Adding protein powder or Greek yogurt makes the smoothie more sustaining as a snack.",
      steps: ["Blend berries, milk, and protein base", "Pour into a glass", "Serve cold"],
      tagColors: ["lavender", "accent", "sky"],
    },
    {
      name: "Banana oat bites",
      time: "8 min",
      cal: 180,
      diff: "Easy",
      emoji: "🍌",
      synergies: ["Fruit + Whole Grains", "Naturally sweet snack"],
      tags: ["Snack", "Meal Prep", "Family Favorite"],
      nutrients: { Carbs: 58, Fiber: 44, Potassium: 72, Energy: 56 },
      tip: "These work well prepped ahead so snacks are ready without reaching for ultra-processed options.",
      steps: ["Mash banana with oats", "Shape into small bites", "Bake or chill until set"],
      tagColors: ["accent", "gold", "sky"],
    },
  ];

  const createMealFromRecipe = (recipe, fallbackName, emoji = "🍽") => {
    if (recipe) return { ...recipe };
    return {
      name: fallbackName,
      time: "20 min",
      cal: 360,
      diff: "Easy",
      emoji,
      synergies: ["Balanced plate"],
      tags: ["Household Plan"],
      nutrients: { Protein: 58, Fiber: 52, Energy: 68, Balance: 74 },
      tip: "Keep a protein, produce, and fiber source on the plate for steadier energy.",
      steps: ["Prep the main ingredients", "Cook until tender and balanced", "Serve with a vegetable or salad on the side"],
      tagColors: ["accent"],
    };
  };

  const [plan, setPlan] = useState(() =>
    weekDays.map((day, i) => ({
      day,
      date: currentWeekDates[i],
      breakfast: { ...breakfastMeals[i] },
      lunch: createMealFromRecipe(filtered[i % filtered.length], "Quinoa salad", "🥗"),
      dinner: createMealFromRecipe(filtered[(i + 1) % filtered.length], "Salmon bowl", "🍲"),
      snack: { ...snackMeals[i] },
    }))
  );
  const [activeMeal, setActiveMeal] = useState(null);

  const openMealEditor = (dayIndex, slot) => {
    setActiveMeal({ dayIndex, slot });
  };

  const updateMealName = (value) => {
    if (!activeMeal) return;
    setPlan((current) =>
      current.map((row, rowIndex) =>
        rowIndex === activeMeal.dayIndex
          ? {
              ...row,
              [activeMeal.slot]: {
                ...row[activeMeal.slot],
                name: value,
              },
            }
          : row
      )
    );
  };

  const selectedMeal = activeMeal ? plan[activeMeal.dayIndex][activeMeal.slot] : null;

  return (
    <>
      <div style={{ padding: "24px 20px 92px", maxWidth: 1120, margin: "0 auto", display: "grid", gap: 20 }}>
        <div>
          <div style={{ color: C.accent, fontSize: 13, fontWeight: 700, letterSpacing: 1.3, textTransform: "uppercase" }}>Weekly Plan</div>
          <h2 style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 28, marginTop: 8 }}>Household meal schedule for the week</h2>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center", marginTop: 10 }}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6, background: C.accentLight, border: `1px solid ${C.accent}`, borderRadius: 999, padding: "7px 12px", color: C.accent, fontSize: 12, fontWeight: 700 }}>
              Week of {weekRangeLabel}
            </span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6, background: C.bg, border: `1px solid ${C.border}`, borderRadius: 999, padding: "7px 12px", color: C.subtext, fontSize: 12, fontWeight: 600 }}>
              Dynamic dates
            </span>
          </div>
          <p style={{ color: C.subtext, marginTop: 10, maxWidth: 720 }}>Click any meal or snack to edit its name and review the nutrient details, bioavailability tip, and preparation steps.</p>
        </div>
        <div style={{ overflowX: "auto", borderRadius: 16, border: `1.5px solid ${C.border}`, background: C.white, boxShadow: "0 1px 4px rgba(0,80,40,0.06)" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: C.bg }}>
                {["Date","Breakfast","Lunch","Dinner","Snack"].map((h, i) => (
                  <th key={h} style={{ textAlign: "left", padding: "13px 16px", fontSize: 11, color: C.muted, fontWeight: 700, letterSpacing: 0.8, textTransform: "uppercase", borderBottom: `1.5px solid ${C.border}`, minWidth: i === 0 ? 70 : 220 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {plan.map((row, i) => (
                <tr key={row.day} style={{ borderBottom: i < plan.length - 1 ? `1px solid ${C.border}` : "none" }}>
                  <td style={{ padding: "13px 16px", verticalAlign: "top" }}>
                    <div style={{ display: "grid", gap: 2 }}>
                      <span style={{ fontWeight: 800, fontSize: 13.5, color: i === 0 ? C.accent : C.text }}>{row.date.shortDay}</span>
                      <span style={{ fontSize: 18, lineHeight: 1.1, fontWeight: 800, color: C.text }}>{row.date.dayNumber}</span>
                      <span style={{ fontSize: 12, color: C.muted, fontWeight: 600 }}>{row.date.monthLabel}</span>
                    </div>
                  </td>
                  {["breakfast", "lunch", "dinner", "snack"].map((slot) => (
                    <td key={slot} style={{ padding: "10px 12px" }}>
                      <button
                        type="button"
                        onClick={() => openMealEditor(i, slot)}
                        style={{ width: "100%", textAlign: "left", padding: "14px 14px", borderRadius: 14, border: `1px solid ${C.border}`, background: C.bg, cursor: "pointer" }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "start" }}>
                          <div>
                            <div style={{ fontWeight: 700, color: C.text }}>{row[slot].name}</div>
                            <div style={{ fontSize: 12, color: C.subtext, marginTop: 4 }}>{row[slot].time} · {row[slot].cal} kcal</div>
                          </div>
                          <span style={{ color: C.accent, fontSize: 12, fontWeight: 700 }}>Edit</span>
                        </div>
                      </button>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card" style={{ padding: 20, display: "flex", gap: 14, alignItems: "flex-start" }}>
          <div style={{ width: 40, height: 40, background: C.accentLight, border: `1.5px solid ${C.accent}`, borderRadius: 10, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 20, flexShrink: 0 }}>💡</div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 14, color: C.text, marginBottom: 4 }}>Smart Sequencing Applied</div>
            <p style={{ fontSize: 12.5, color: C.muted, lineHeight: 1.65 }}>Vitamin C-rich breakfasts prime iron absorption for iron-rich lunches. Evening meals are lower glycaemic index to support overnight metabolic recovery.</p>
          </div>
        </div>
      </div>

      {activeMeal && selectedMeal && (
        <div
          onClick={() => setActiveMeal(null)}
          style={{ position: "fixed", inset: 0, background: "rgba(16, 31, 23, 0.55)", display: "grid", alignItems: "start", justifyItems: "center", overflowY: "auto", padding: "88px 20px 104px", zIndex: 1000 }}
        >
          <div
            className="card"
            onClick={(e) => e.stopPropagation()}
            style={{ width: "min(760px, 100%)", maxHeight: "calc(100vh - 192px)", overflowY: "auto", padding: 24, background: C.white, borderRadius: 24, boxShadow: "0 24px 80px rgba(13, 28, 21, 0.22)", margin: "0 auto" }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "flex-start", marginBottom: 20 }}>
              <div>
                <div style={{ color: C.accent, fontSize: 12, fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase" }}>
                  {plan[activeMeal.dayIndex].day} · {activeMeal.slot}
                </div>
                <h3 style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 28, marginTop: 8, color: C.text }}>Edit planned meal</h3>
              </div>
              <button className="btn-ghost" onClick={() => setActiveMeal(null)}>Close</button>
            </div>

            <div style={{ display: "grid", gap: 18 }}>
              <div>
                <label>Meal name</label>
                <input value={selectedMeal.name} onChange={(e) => updateMealName(e.target.value)} />
              </div>

              <div className="card" style={{ padding: 22, background: C.card }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, marginBottom: 14 }}>
                  <div style={{ display: "flex", gap: 14, alignItems: "center" }}>
                    <div style={{ width: 54, height: 54, background: C.bg, border: `1.5px solid ${C.border}`, borderRadius: 16, display: "grid", placeItems: "center", fontSize: 28 }}>{selectedMeal.emoji}</div>
                    <div>
                      <div style={{ fontWeight: 700, fontSize: 18, color: C.text }}>{selectedMeal.name}</div>
                      <div style={{ fontSize: 13, color: C.subtext, marginTop: 4 }}>{selectedMeal.time} · {selectedMeal.cal} kcal · {selectedMeal.diff}</div>
                    </div>
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "flex-end" }}>
                    {selectedMeal.tags.slice(0, 3).map((tag, index) => (
                      <Tag key={tag} label={tag} colorKey={selectedMeal.tagColors?.[index] || "accent"} />
                    ))}
                  </div>
                </div>

                <div style={{ marginBottom: 12 }}>
                  {selectedMeal.synergies.map((item) => <SynergyPill key={item} text={item} />)}
                </div>

                <div style={{ marginTop: 18 }}>
                  <div style={{ fontSize: 10.5, color: C.muted, fontWeight: 700, letterSpacing: 0.8, textTransform: "uppercase", marginBottom: 10 }}>Nutrient Optimisation</div>
                  {Object.entries(selectedMeal.nutrients).map(([k, v], index) => (
                    <NutrientBar key={k} label={k} value={v} color={nutrientColors[index % nutrientColors.length]} />
                  ))}
                </div>

                <div style={{ background: C.accentLight, border: `1.5px solid ${C.accent}`, borderRadius: 10, padding: 13, marginTop: 14 }}>
                  <div style={{ fontSize: 11, color: C.accent, fontWeight: 700, marginBottom: 4 }}>💡 Bioavailability Tip</div>
                  <p style={{ fontSize: 12, color: C.text, lineHeight: 1.65 }}>{selectedMeal.tip}</p>
                </div>

                <div style={{ marginTop: 14 }}>
                  <div style={{ fontSize: 10.5, color: C.muted, fontWeight: 700, letterSpacing: 0.8, textTransform: "uppercase", marginBottom: 10 }}>Preparation Steps</div>
                  {selectedMeal.steps.map((step, index) => (
                    <div key={index} style={{ display: "flex", gap: 10, marginBottom: 9 }}>
                      <span style={{ minWidth: 22, height: 22, background: C.accentLight, border: `1.5px solid ${C.accent}`, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, color: C.accent, fontWeight: 700, flexShrink: 0 }}>{index + 1}</span>
                      <span style={{ fontSize: 12.5, color: C.subtext, lineHeight: 1.6 }}>{step}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function WeeklyPlannerShowcase({
  profiles,
  plannerDays,
  setPlannerDays,
  plannerAnchorDate,
  setPlannerAnchorDate,
  selectedDayIndex,
  setSelectedDayIndex,
}) {
  const nutrientColors = [C.accent, C.sky, C.gold, C.lavender, C.coral, C.accent];
  const baseSlots = [["breakfast", "Breakfast"], ["lunch", "Lunch"], ["dinner", "Dinner"], ["snack", "Snack"]];
  const [showWeekPicker, setShowWeekPicker] = useState(false);
  const [weekPickerView, setWeekPickerView] = useState("weeks");
  const [pickerCursorDate, setPickerCursorDate] = useState(() => new Date());
  const startOfWeek = new Date(plannerAnchorDate);
  startOfWeek.setHours(0, 0, 0, 0);
  startOfWeek.setDate(plannerAnchorDate.getDate() - plannerAnchorDate.getDay());
  const imageSet = {
    breakfast: "https://images.unsplash.com/photo-1517673400267-0251440c45dc?auto=format&fit=crop&w=1200&q=80",
    lunch: "https://images.unsplash.com/photo-1547592180-85f173990554?auto=format&fit=crop&w=1200&q=80",
    dinner: "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?auto=format&fit=crop&w=1200&q=80",
    snack: "https://images.unsplash.com/photo-1505253758473-96b7015fcd40?auto=format&fit=crop&w=1200&q=80",
  };
  const breakfastTemplates = [
    { name: "Berry oat bowl", calories: 350, protein: 12, image: imageSet.breakfast, tip: "Add seeds for extra fiber and better staying power.", nutrients: { Fiber: 82, Protein: 48, Antioxidants: 86 }, emoji: "🥣" },
    { name: "Avocado toast", calories: 340, protein: 14, image: imageSet.breakfast, tip: "Egg or yogurt on the side makes this more filling.", nutrients: { Fiber: 56, Protein: 54, Satiety: 88 }, emoji: "🍞" },
    { name: "Greek yogurt parfait", calories: 310, protein: 18, image: imageSet.breakfast, tip: "Lower-sugar granola keeps the protein-to-sugar balance stronger.", nutrients: { Protein: 72, Calcium: 70, Probiotics: 82 }, emoji: "🥛" },
    { name: "Green smoothie bowl", calories: 300, protein: 15, image: imageSet.breakfast, tip: "Use yogurt or protein milk to avoid a carb-only breakfast.", nutrients: { Hydration: 82, VitaminC: 90, Protein: 52 }, emoji: "🍓" },
    { name: "Chia pudding", calories: 280, protein: 11, image: imageSet.breakfast, tip: "Soak overnight for a smoother texture and easier digestion.", nutrients: { Fiber: 84, Omega3: 74, Calcium: 66 }, emoji: "🥄" },
    { name: "Protein waffles", calories: 360, protein: 17, image: imageSet.breakfast, tip: "Add yogurt and fruit to balance the plate.", nutrients: { Carbs: 70, Protein: 58, FamilyAppeal: 90 }, emoji: "🧇" },
    { name: "Fruit and nuts", calories: 240, protein: 9, image: imageSet.breakfast, tip: "Pair with milk or yogurt if you need more protein.", nutrients: { HealthyFats: 74, Fiber: 52, Energy: 60 }, emoji: "🍎" },
  ];
  const lunchTemplates = [
    { name: "Mediterranean chicken bowl", calories: 600, protein: 35, image: imageSet.lunch, tip: "Add extra greens for more fiber without much prep.", nutrients: { Protein: 84, Fiber: 64, Balance: 82 }, emoji: "🥗" },
    { name: "Protein wrap", calories: 540, protein: 32, image: imageSet.lunch, tip: "A bean or chickpea side can lift fiber quickly.", nutrients: { Protein: 74, Fiber: 56, Convenience: 86 }, emoji: "🌯" },
    { name: "Rice and veggie bowl", calories: 560, protein: 29, image: imageSet.lunch, tip: "Cool and reheat rice for a gentler glucose response.", nutrients: { Carbs: 68, Protein: 72, Fiber: 58 }, emoji: "🍚" },
    { name: "Lentil salad box", calories: 520, protein: 26, image: imageSet.lunch, tip: "Citrus dressing helps boost iron absorption.", nutrients: { Iron: 80, Fiber: 82, Protein: 58 }, emoji: "🥙" },
    { name: "Turkey sandwich plate", calories: 510, protein: 31, image: imageSet.lunch, tip: "Choose whole grain bread for better satiety.", nutrients: { Protein: 74, Fiber: 48, Satiety: 76 }, emoji: "🥪" },
    { name: "Paneer power bowl", calories: 580, protein: 28, image: imageSet.lunch, tip: "Pair paneer with fresh herbs and citrus for brighter flavor.", nutrients: { Protein: 68, Calcium: 72, Balance: 78 }, emoji: "🫓" },
    { name: "Chickpea crunch salad", calories: 500, protein: 24, image: imageSet.lunch, tip: "Roasted chickpeas keep the texture lively and satisfying.", nutrients: { Fiber: 80, Protein: 52, Energy: 70 }, emoji: "🥬" },
  ];
  const dinnerTemplates = [
    { name: "Salmon veggie skillet", calories: 520, protein: 30, image: imageSet.dinner, tip: "Pair with colorful veg to support antioxidant intake.", nutrients: { Protein: 82, Omega3: 90, VitaminD: 76 }, emoji: "🍲" },
    { name: "Tofu stir fry", calories: 500, protein: 27, image: imageSet.dinner, tip: "Use sesame and lime to add flavor without a heavy sauce.", nutrients: { Protein: 70, Fiber: 62, Balance: 80 }, emoji: "🥘" },
    { name: "Chicken tray bake", calories: 560, protein: 34, image: imageSet.dinner, tip: "Roast extra vegetables for tomorrow's lunch.", nutrients: { Protein: 84, Fiber: 54, FamilyAppeal: 88 }, emoji: "🍗" },
    { name: "Lentil pasta plate", calories: 540, protein: 25, image: "https://images.unsplash.com/photo-1622973536968-3ead9e780960?auto=format&fit=crop&w=1200&q=80", tip: "Add greens into the sauce for a fast nutrient boost.", nutrients: { Protein: 62, Fiber: 72, Iron: 58 }, emoji: "🍝" },
    { name: "Stuffed pepper tray", calories: 510, protein: 23, image: imageSet.dinner, tip: "Beans and quinoa make this filling without feeling heavy.", nutrients: { Fiber: 76, Protein: 56, Satiety: 78 }, emoji: "🫑" },
    { name: "Shrimp rice bowl", calories: 530, protein: 32, image: imageSet.dinner, tip: "Add cabbage slaw for crunch and extra fiber.", nutrients: { Protein: 82, Balance: 74, Energy: 72 }, emoji: "🍤" },
    { name: "Veggie taco night", calories: 550, protein: 22, image: imageSet.dinner, tip: "Add avocado and beans to round out the plate.", nutrients: { Fiber: 70, Protein: 50, FamilyAppeal: 90 }, emoji: "🌮" },
  ];
  const snackTemplates = [
    { name: "Apple and peanut butter", calories: 190, protein: 7, image: imageSet.snack, tip: "Fruit plus fat makes this snack more sustaining.", nutrients: { Fiber: 60, HealthyFats: 72, Energy: 58 }, emoji: "🍎" },
    { name: "Greek yogurt cup", calories: 140, protein: 15, image: imageSet.snack, tip: "Keep sugar lower so protein stays the star.", nutrients: { Protein: 78, Calcium: 64, Probiotics: 82 }, emoji: "🥛" },
    { name: "Trail mix", calories: 210, protein: 8, image: imageSet.snack, tip: "Pre-portion servings so the snack stays balanced.", nutrients: { HealthyFats: 78, Fiber: 42, Energy: 68 }, emoji: "🥜" },
    { name: "Hummus and carrots", calories: 160, protein: 6, image: imageSet.snack, tip: "A veggie snack helps spread produce through the day.", nutrients: { Fiber: 58, VitaminA: 84, Energy: 44 }, emoji: "🥕" },
    { name: "Cheese and crackers", calories: 200, protein: 10, image: imageSet.snack, tip: "Whole grain crackers hold the snack steadier than refined ones.", nutrients: { Protein: 48, Calcium: 62, Satiety: 60 }, emoji: "🧀" },
    { name: "Berry smoothie", calories: 220, protein: 14, image: imageSet.snack, tip: "Adding yogurt gives it a better protein profile.", nutrients: { Protein: 70, Hydration: 78, Antioxidants: 74 }, emoji: "🫐" },
    { name: "Banana oat bites", calories: 180, protein: 6, image: imageSet.snack, tip: "Batch prep these to avoid last-minute snack scrambles.", nutrients: { Energy: 58, Fiber: 46, Potassium: 72 }, emoji: "🍌" },
  ];
  const templateGroups = { breakfast: breakfastTemplates, lunch: lunchTemplates, dinner: dinnerTemplates, snack: snackTemplates };
  const addMealCategories = [
    { key: "breakfast", label: "Breakfast", description: "Morning meal ideas with more staying power." },
    { key: "lunch", label: "Lunch", description: "Balanced mid-day options for home or on the go." },
    { key: "dinner", label: "Dinner", description: "Main meals with fuller portions and protein focus." },
    { key: "snack", label: "Snack", description: "Short meals, mini plates, and smaller bites." },
  ];
  const getMealLabel = (meal, fallbackSlot) => {
    if (meal?.label) return meal.label;
    return baseSlots.find(([slot]) => slot === (meal?.slotType || fallbackSlot))?.[1] || "Meal";
  };
  const createMealEntry = (slotType, template, labelOverride) => ({
    ...template,
    slotType,
    label: labelOverride || (baseSlots.find(([slot]) => slot === slotType)?.[1] || "Meal"),
  });
  const calculateTotalCalories = (meals) => Object.values(meals).reduce((sum, meal) => sum + meal.calories, 0);

  const weekEntries = Array.from({ length: 7 }, (_, index) => {
    const date = new Date(startOfWeek);
    const meals = {
      breakfast: createMealEntry("breakfast", breakfastTemplates[index], "Breakfast"),
      lunch: createMealEntry("lunch", lunchTemplates[index], "Lunch"),
      dinner: createMealEntry("dinner", dinnerTemplates[index], "Dinner"),
      snack: createMealEntry("snack", snackTemplates[index], "Snack"),
    };
    date.setDate(startOfWeek.getDate() + index);
    return {
      key: date.toISOString(),
      shortDay: date.toLocaleDateString("en-US", { weekday: "short" }),
      longDay: date.toLocaleDateString("en-US", { weekday: "long" }),
      dayNumber: date.toLocaleDateString("en-US", { day: "numeric" }),
      monthLabel: date.toLocaleDateString("en-US", { month: "short" }),
      display: date.toLocaleDateString("en-US", { month: "short", day: "numeric" }),
      mealOrder: baseSlots.map(([slot]) => slot),
      totalCalories: calculateTotalCalories(meals),
      meals,
    };
  });

  const [activeRecipeSlot, setActiveRecipeSlot] = useState(null);
  const [activeSwapSlot, setActiveSwapSlot] = useState(null);
  const [showAddMealModal, setShowAddMealModal] = useState(false);
  const [addMealCategory, setAddMealCategory] = useState("snack");
  const [pendingAddMeal, setPendingAddMeal] = useState(null);
  const [addMealQuery, setAddMealQuery] = useState("");
  const [swapQuery, setSwapQuery] = useState("");
  const [pendingSwapMeal, setPendingSwapMeal] = useState(null);
  const [toastMessage, setToastMessage] = useState("");
  const currentDay = plannerDays[selectedDayIndex];
  const activeRecipe = activeRecipeSlot ? currentDay.meals[activeRecipeSlot] : null;
  const activeSwapMeal = activeSwapSlot ? currentDay.meals[activeSwapSlot] : null;
  const weekRangeLabel = `${plannerDays[0].monthLabel} ${plannerDays[0].dayNumber} - ${plannerDays[plannerDays.length - 1].monthLabel} ${plannerDays[plannerDays.length - 1].dayNumber}`;
  const calorieTarget = 2000;
  const calendarMonthLabel = pickerCursorDate.toLocaleDateString("en-US", { month: "long", year: "numeric" });
  const calendarMonthStart = new Date(pickerCursorDate.getFullYear(), pickerCursorDate.getMonth(), 1);
  const calendarGridStart = new Date(calendarMonthStart);
  calendarGridStart.setDate(calendarMonthStart.getDate() - calendarMonthStart.getDay());
  const calendarDays = Array.from({ length: 35 }, (_, index) => {
    const date = new Date(calendarGridStart);
    date.setDate(calendarGridStart.getDate() + index);
    return date;
  });
  const weekOptions = Array.from({ length: 5 }, (_, weekIndex) => {
    const weekStart = new Date(calendarGridStart);
    weekStart.setDate(calendarGridStart.getDate() + weekIndex * 7);
    const weekEnd = new Date(weekStart);
    weekEnd.setDate(weekStart.getDate() + 6);
    return {
      key: weekStart.toISOString(),
      start: weekStart,
      end: weekEnd,
      label: `${weekStart.toLocaleDateString("en-US", { month: "short", day: "numeric" })} - ${weekEnd.toLocaleDateString("en-US", { month: "short", day: "numeric" })}`,
      days: Array.from({ length: 7 }, (_, dayIndex) => {
        const day = new Date(weekStart);
        day.setDate(weekStart.getDate() + dayIndex);
        return day;
      }),
    };
  });
  const pickerYearLabel = pickerCursorDate.getFullYear();
  const monthOptions = Array.from({ length: 12 }, (_, monthIndex) => {
    const monthDate = new Date(pickerCursorDate.getFullYear(), monthIndex, 1);
    return {
      key: monthDate.toISOString(),
      label: monthDate.toLocaleDateString("en-US", { month: "short" }),
      monthIndex,
    };
  });
  const getPreparationSteps = (slot, mealName) => {
    const stepMap = {
      breakfast: [
        `Prep ingredients for ${mealName.toLowerCase()}.`,
        "Assemble the base and add the main protein or grain component.",
        "Finish with toppings just before serving for the best texture.",
      ],
      lunch: [
        `Cook and portion the main components for ${mealName.toLowerCase()}.`,
        "Layer vegetables, grains, and protein for a balanced plate.",
        "Add dressing or finishing flavors right before eating.",
      ],
      dinner: [
        `Start the main cook for ${mealName.toLowerCase()}.`,
        "Build the meal with vegetables and a balanced protein source.",
        "Plate warm and finish with herbs, citrus, or sauce for brightness.",
      ],
      snack: [
        `Portion ${mealName.toLowerCase()} for the day.`,
        "Pair it with fiber, protein, or healthy fats where possible.",
        "Serve fresh or pack ahead for a quick grab-and-go option.",
      ],
    };

    return stepMap[slot] || [
      `Prepare ${mealName.toLowerCase()}.`,
      "Assemble the meal components.",
      "Serve and adjust seasoning if needed.",
    ];
  };

  const applySwapMeal = (slot, nextMeal) => {
    setPlannerDays((days) =>
      days.map((day, index) => {
        if (index !== selectedDayIndex) return day;
        const existingMeal = day.meals[slot];
        const updatedMeals = {
          ...day.meals,
          [slot]: createMealEntry(existingMeal?.slotType || "snack", nextMeal, existingMeal?.label || getMealLabel(existingMeal, slot)),
        };
        return {
          ...day,
          meals: updatedMeals,
          totalCalories: calculateTotalCalories(updatedMeals),
        };
      })
    );
  };

  const openSwapModal = (slot) => {
    setActiveRecipeSlot(null);
    setSwapQuery("");
    setPendingSwapMeal(null);
    setActiveSwapSlot(slot);
  };

  const openAddMealModal = () => {
    setAddMealCategory("snack");
    setPendingAddMeal(null);
    setAddMealQuery("");
    setShowAddMealModal(true);
  };

  const saveAddedMeal = () => {
    if (!pendingAddMeal) return;
    setPlannerDays((days) =>
      days.map((day, index) => {
        if (index !== selectedDayIndex) return day;
        const extraCount = day.mealOrder.filter((mealKey) => mealKey.startsWith("extra-")).length;
        const nextMealKey = `extra-${extraCount + 1}`;
        const nextLabel = extraCount === 0 ? "Mini Meal" : `Mini Meal ${extraCount + 1}`;
        const updatedMeals = {
          ...day.meals,
          [nextMealKey]: createMealEntry(addMealCategory, pendingAddMeal, nextLabel),
        };
        return {
          ...day,
          meals: updatedMeals,
          mealOrder: [...day.mealOrder, nextMealKey],
          totalCalories: calculateTotalCalories(updatedMeals),
        };
      })
    );
    setShowAddMealModal(false);
    setPendingAddMeal(null);
    setAddMealQuery("");
    setToastMessage(`${currentDay.longDay} now includes an extra ${addMealCategories.find((category) => category.key === addMealCategory)?.label.toLowerCase() || "meal"}.`);
  };

  const saveSwapSelection = () => {
    if (!activeSwapSlot || !pendingSwapMeal) return;
    const slotLabel = getMealLabel(activeSwapMeal, activeSwapSlot);
    applySwapMeal(activeSwapSlot, pendingSwapMeal);
    setActiveSwapSlot(null);
    setPendingSwapMeal(null);
    setSwapQuery("");
    setToastMessage(`${slotLabel} updated. Your weekly plan is now saved.`);
  };

  const swapOptions = activeSwapSlot
    ? templateGroups[activeSwapMeal?.slotType || "snack"].filter((item) =>
        item.name.toLowerCase().includes(swapQuery.trim().toLowerCase())
      )
    : [];
  const addMealOptions = templateGroups[addMealCategory].filter((item) =>
    item.name.toLowerCase().includes(addMealQuery.trim().toLowerCase())
  );

  useEffect(() => {
    if (!toastMessage) return;
    const timer = setTimeout(() => setToastMessage(""), 2000);
    return () => clearTimeout(timer);
  }, [toastMessage]);

  return (
    <>
      <div style={{ padding: "26px 20px 92px", maxWidth: 1180, margin: "0 auto", display: "grid", gap: 22 }}>
        <div className="card" style={{ position: "relative", overflow: "hidden", minHeight: 760, padding: 0, background: "linear-gradient(180deg, rgba(255,253,248,0.96), rgba(248,245,238,0.94))", border: `1.5px solid ${C.border}` }}>
          <div style={{ position: "absolute", inset: 0, backgroundImage: `linear-gradient(180deg, rgba(255,253,248,0.92), rgba(255,253,248,0.74)), url('${imageSet.dinner}')`, backgroundSize: "cover", backgroundPosition: "center" }} />
          <div style={{ position: "absolute", inset: 0, background: "linear-gradient(180deg, rgba(255,255,255,0.18), rgba(245,241,232,0.74))" }} />
          <div style={{ position: "relative", zIndex: 1, padding: "22px 24px 28px", display: "grid", gap: 20 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
              <div>
                <div style={{ color: C.accent, fontSize: 13, fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase" }}>Weekly Planner</div>
                <h2 style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 30, color: C.text, marginTop: 6 }}>Interactive meal banner for the current week</h2>
                <p style={{ color: C.subtext, marginTop: 8, maxWidth: 720 }}>Inspired by your attached banner, this version stays dynamic with a live Sunday-to-Saturday schedule, swap actions, and a focused meal pop-up.</p>
              </div>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                <button
                  type="button"
                  onClick={() => {
                    setPickerCursorDate(new Date(plannerAnchorDate));
                    setWeekPickerView("weeks");
                    setShowWeekPicker(true);
                  }}
                  style={{ display: "inline-flex", alignItems: "center", gap: 6, background: "rgba(255,255,255,0.82)", border: `1px solid ${C.border}`, borderRadius: 999, padding: "8px 14px", color: C.subtext, fontWeight: 700, fontSize: 12 }}
                >
                  Week of {weekRangeLabel}
                </button>
              </div>
            </div>

            <div style={{ display: "grid", gap: 14 }}>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(7, minmax(88px, 1fr))", gap: 8 }}>
                {plannerDays.map((day, index) => {
                  const ringRadius = 18;
                  const ringCircumference = 2 * Math.PI * ringRadius;
                  const ringRatio = Math.min(day.totalCalories / calorieTarget, 1);
                  const ringOffset = ringCircumference * (1 - ringRatio);
                  const ringColor = selectedDayIndex === index ? "#BFD4FF" : "#214A86";

                  return (
                  <button key={day.key} type="button" onClick={() => setSelectedDayIndex(index)} style={{ border: `1px solid ${selectedDayIndex === index ? "#214A86" : C.border}`, background: selectedDayIndex === index ? "#214A86" : "rgba(255,255,255,0.82)", color: selectedDayIndex === index ? C.white : "#214A86", borderRadius: 16, padding: "14px 10px", fontWeight: 700, position: "relative", cursor: "pointer", boxShadow: selectedDayIndex === index ? "0 10px 24px rgba(33,74,134,0.22)" : "none" }}>
                    <div>{day.shortDay}</div>
                    <div style={{ fontSize: 12, opacity: 0.85, marginTop: 4 }}>{day.display}</div>
                    <div style={{ display: "grid", placeItems: "center", marginTop: 8 }}>
                      <div style={{ position: "relative", width: 52, height: 52 }}>
                        <svg viewBox="0 0 52 52" style={{ width: 52, height: 52, transform: "rotate(-90deg)" }}>
                          <circle cx="26" cy="26" r={ringRadius} fill="none" stroke={selectedDayIndex === index ? "rgba(255,255,255,0.22)" : "#D7E2F5"} strokeWidth="6" />
                          <circle
                            cx="26"
                            cy="26"
                            r={ringRadius}
                            fill="none"
                            stroke={ringColor}
                            strokeWidth="6"
                            strokeLinecap="round"
                            strokeDasharray={`${ringCircumference} ${ringCircumference}`}
                            strokeDashoffset={ringOffset}
                          />
                        </svg>
                        <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", fontSize: 10, lineHeight: 1.05 }}>
                          <span style={{ fontWeight: 800 }}>{Math.round(day.totalCalories / 10) / 100}k</span>
                        </div>
                      </div>
                    </div>
                    <div style={{ fontSize: 11, opacity: 0.9, marginTop: 6 }}>{day.totalCalories} kcal</div>
                    {selectedDayIndex === index && <div style={{ position: "absolute", left: "50%", bottom: -9, transform: "translateX(-50%)", width: 0, height: 0, borderLeft: "9px solid transparent", borderRight: "9px solid transparent", borderTop: "9px solid #214A86" }} />}
                  </button>
                )})}
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 18, marginTop: 8 }}>
                {currentDay.mealOrder.map((slot) => {
                  const meal = currentDay.meals[slot];
                  const label = getMealLabel(meal, slot);
                  return (
                    <div key={slot} className="card" style={{ overflow: "hidden", background: "rgba(255,255,255,0.84)", backdropFilter: "blur(8px)" }}>
                      <div style={{ height: 150, backgroundImage: `linear-gradient(180deg, rgba(0,0,0,0.08), rgba(0,0,0,0.18)), url('${meal.image}')`, backgroundSize: "cover", backgroundPosition: "center" }} />
                      <div style={{ padding: 16, display: "grid", gap: 10 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
                          <div>
                            <div style={{ fontSize: 12, color: C.muted, textTransform: "uppercase", fontWeight: 700, letterSpacing: 1 }}>{label}</div>
                            <div style={{ fontWeight: 700, fontSize: 18, color: C.text, marginTop: 6 }}>{meal.name}</div>
                          </div>
                          <div style={{ color: "#214A86", fontWeight: 700 }}>{meal.calories} kcal</div>
                        </div>
                        <div style={{ color: C.subtext, fontSize: 13 }}>{meal.protein}g protein</div>
                        {meal.sideSuggestion && (
                          <div style={{ display: "inline-flex", alignItems: "center", gap: 8, width: "fit-content", maxWidth: "100%", padding: "7px 10px", borderRadius: 999, background: "linear-gradient(180deg, #FFF8E7, #FCEFCF)", border: "1px solid #F0D8A2", color: "#7A5B20", fontSize: 12, fontWeight: 700 }}>
                            <span>+</span>
                            <span>{meal.sideSuggestion}</span>
                          </div>
                        )}
                        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                          <button className="btn-primary" style={{ background: "#3B67B0", borderColor: "#3B67B0", padding: "10px 18px" }} onClick={() => openSwapModal(slot)}>Swap</button>
                          <button className="btn-ghost" style={{ padding: "10px 18px", background: C.white }} onClick={() => setActiveRecipeSlot(slot)}>View Recipe</button>
                        </div>
                      </div>
                    </div>
                  );
                })}
                <button
                  type="button"
                  onClick={openAddMealModal}
                  className="card"
                  style={{ borderStyle: "dashed", borderWidth: 2, borderColor: "#9FB7E5", background: "rgba(255,255,255,0.62)", minHeight: 286, display: "grid", placeItems: "center", padding: 22, textAlign: "center", backdropFilter: "blur(6px)" }}
                >
                  <div style={{ display: "grid", gap: 10, justifyItems: "center" }}>
                    <div style={{ width: 58, height: 58, borderRadius: "50%", background: "linear-gradient(135deg, #214A86, #6B9B2F)", color: C.white, display: "grid", placeItems: "center", fontSize: 34, fontWeight: 500 }}>+</div>
                    <div style={{ fontWeight: 800, fontSize: 18, color: "#214A86" }}>Add another meal</div>
                    <div style={{ maxWidth: 220, color: C.subtext, fontSize: 13, lineHeight: 1.6 }}>
                      Add a fifth or sixth short meal for days that need extra flexibility, energy, or family-specific planning.
                    </div>
                  </div>
                </button>
              </div>

            </div>
          </div>
        </div>
      </div>

      {activeRecipe && currentDay && (
        <div onClick={() => setActiveRecipeSlot(null)} style={{ position: "fixed", inset: 0, background: "rgba(11, 18, 33, 0.56)", display: "grid", alignItems: "start", justifyItems: "center", overflowY: "auto", padding: "86px 20px 104px", zIndex: 1000 }}>
          <div className="card" onClick={(e) => e.stopPropagation()} style={{ width: "min(880px, 100%)", background: C.white, borderRadius: 28, overflow: "hidden", boxShadow: "0 32px 80px rgba(11,18,33,0.24)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "center", padding: "20px 24px", borderBottom: `1px solid ${C.border}` }}>
              <div>
                <div style={{ fontSize: 12, color: C.muted, fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase" }}>{currentDay.display}</div>
                <h3 style={{ fontSize: 28, color: "#214A86", fontWeight: 700, marginTop: 6 }}>{currentDay.longDay}'s {getMealLabel(activeRecipe, activeRecipeSlot)} Recipe</h3>
              </div>
              <button className="btn-ghost" onClick={() => setActiveRecipeSlot(null)}>Close</button>
            </div>
            <div style={{ padding: 22, display: "grid", gap: 16 }}>
              <div style={{ border: `1px solid ${C.border}`, borderRadius: 18, padding: 14, display: "grid", gridTemplateColumns: "180px 1fr", gap: 18, alignItems: "center", background: C.white }}>
                <div style={{ height: 156, borderRadius: 16, backgroundImage: `url('${activeRecipe.image}')`, backgroundSize: "cover", backgroundPosition: "center" }} />
                <div style={{ display: "grid", gap: 12 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "start" }}>
                    <div>
                      <div style={{ fontWeight: 700, fontSize: 18, color: C.text }}>{getMealLabel(activeRecipe, activeRecipeSlot)}</div>
                      <div style={{ fontWeight: 700, fontSize: 22, color: "#214A86", marginTop: 4 }}>{activeRecipe.name}</div>
                    </div>
                    <div style={{ textAlign: "right", color: C.subtext }}>
                      <div style={{ fontWeight: 700, fontSize: 17 }}>{activeRecipe.calories} kcal</div>
                      <div style={{ marginTop: 4 }}>{activeRecipe.protein}g Protein</div>
                    </div>
                  </div>
                  <div style={{ display: "grid", gap: 8, marginTop: 2 }}>
                    {Object.entries(activeRecipe.nutrients).map(([key, value], index) => <NutrientBar key={key} label={key} value={value} color={nutrientColors[index % nutrientColors.length]} />)}
                  </div>
                  <div style={{ background: C.accentLight, border: `1px solid ${C.accent}`, borderRadius: 12, padding: 12 }}>
                    <div style={{ fontSize: 11, color: C.accent, fontWeight: 700, marginBottom: 4 }}>Bioavailability Tip</div>
                    <div style={{ color: C.text, fontSize: 13 }}>{activeRecipe.tip}</div>
                  </div>
                  {activeRecipe.sideSuggestion && (
                    <div style={{ background: "linear-gradient(180deg, #FFF8E7, #FCEFCF)", border: "1px solid #F0D8A2", borderRadius: 12, padding: 12 }}>
                      <div style={{ fontSize: 11, color: "#9C4D27", fontWeight: 700, marginBottom: 4 }}>
                        Saved Side Suggestion{activeRecipe.sideSuggestionSource ? ` · ${activeRecipe.sideSuggestionSource}` : ""}
                      </div>
                      <div style={{ color: C.text, fontSize: 13 }}>{activeRecipe.sideSuggestion}</div>
                    </div>
                  )}
                  <div style={{ display: "grid", gap: 10 }}>
                    <div style={{ fontSize: 11, color: C.muted, fontWeight: 700, letterSpacing: 0.8, textTransform: "uppercase" }}>Preparation Steps</div>
                    {getPreparationSteps(activeRecipeSlot, activeRecipe.name).map((step, index) => (
                      <div key={index} style={{ display: "flex", gap: 10, alignItems: "start" }}>
                        <span style={{ minWidth: 22, height: 22, background: C.accentLight, border: `1px solid ${C.accent}`, borderRadius: "50%", display: "grid", placeItems: "center", fontSize: 11, color: C.accent, fontWeight: 700 }}>{index + 1}</span>
                        <span style={{ fontSize: 13, color: C.subtext, lineHeight: 1.6 }}>{step}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
            <div style={{ padding: "0 22px 22px" }}>
              <button className="btn-primary" style={{ width: "100%", background: "#6B9B2F", borderColor: "#6B9B2F", padding: "14px 18px", fontSize: 16 }} onClick={() => setActiveRecipeSlot(null)}>Close Recipe</button>
            </div>
          </div>
        </div>
      )}

      {activeSwapSlot && currentDay && (
        <div onClick={() => setActiveSwapSlot(null)} style={{ position: "fixed", inset: 0, background: "rgba(11, 18, 33, 0.56)", display: "grid", alignItems: "start", justifyItems: "center", overflowY: "auto", padding: "86px 20px 104px", zIndex: 1000 }}>
          <div className="card" onClick={(e) => e.stopPropagation()} style={{ width: "min(760px, 100%)", background: C.white, borderRadius: 28, overflow: "hidden", boxShadow: "0 32px 80px rgba(11,18,33,0.24)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "center", padding: "20px 24px", borderBottom: `1px solid ${C.border}` }}>
              <div>
                <div style={{ fontSize: 12, color: C.muted, fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase" }}>{currentDay.display}</div>
                <h3 style={{ fontSize: 28, color: "#214A86", fontWeight: 700, marginTop: 6 }}>Swap {getMealLabel(activeSwapMeal, activeSwapSlot)}</h3>
              </div>
              <button className="btn-ghost" onClick={() => setActiveSwapSlot(null)}>Close</button>
            </div>
            <div style={{ padding: 22, display: "grid", gap: 16 }}>
              <div>
                <label>Search recipes</label>
                <input value={swapQuery} onChange={(e) => setSwapQuery(e.target.value)} placeholder={`Search ${getMealLabel(activeSwapMeal, activeSwapSlot).toLowerCase()} options`} />
              </div>
              <div style={{ display: "grid", gap: 12 }}>
                {swapOptions.map((meal) => (
                  <button
                    key={meal.name}
                    type="button"
                    onClick={() => {
                      setPendingSwapMeal(meal);
                    }}
                    style={{ display: "grid", gridTemplateColumns: "112px 1fr auto", gap: 14, alignItems: "center", padding: 14, borderRadius: 18, border: `1px solid ${pendingSwapMeal?.name === meal.name ? C.accent : C.border}`, background: pendingSwapMeal?.name === meal.name ? C.accentLight : C.white, textAlign: "left" }}
                  >
                    <div style={{ height: 82, borderRadius: 14, backgroundImage: `url('${meal.image}')`, backgroundSize: "cover", backgroundPosition: "center" }} />
                    <div>
                      <div style={{ fontWeight: 700, fontSize: 18, color: "#214A86" }}>{meal.name}</div>
                      <div style={{ color: C.subtext, fontSize: 13, marginTop: 4 }}>{meal.calories} kcal · {meal.protein}g protein</div>
                      <div style={{ color: C.subtext, fontSize: 13, marginTop: 6 }}>{meal.tip}</div>
                    </div>
                    <span style={{ color: C.accent, fontWeight: 700 }}>{pendingSwapMeal?.name === meal.name ? "Selected" : "Select"}</span>
                  </button>
                ))}
                {swapOptions.length === 0 && (
                  <div className="card" style={{ padding: 18, textAlign: "center", color: C.subtext }}>
                    No matching recipes found.
                  </div>
                )}
              </div>
              <div style={{ display: "flex", gap: 12, justifyContent: "flex-end", flexWrap: "wrap" }}>
                <button className="btn-ghost" onClick={() => setActiveSwapSlot(null)}>Cancel</button>
                <button
                  className="btn-primary"
                  style={{ background: "#6B9B2F", borderColor: "#6B9B2F", padding: "12px 20px" }}
                  disabled={!pendingSwapMeal}
                  onClick={saveSwapSelection}
                >
                  Save
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {showAddMealModal && currentDay && (
        <div onClick={() => setShowAddMealModal(false)} style={{ position: "fixed", inset: 0, background: "rgba(11, 18, 33, 0.56)", display: "grid", alignItems: "start", justifyItems: "center", overflowY: "auto", padding: "86px 20px 104px", zIndex: 1000 }}>
          <div className="card" onClick={(e) => e.stopPropagation()} style={{ width: "min(820px, 100%)", background: C.white, borderRadius: 28, overflow: "hidden", boxShadow: "0 32px 80px rgba(11,18,33,0.24)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "center", padding: "20px 24px", borderBottom: `1px solid ${C.border}` }}>
              <div>
                <div style={{ fontSize: 12, color: C.muted, fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase" }}>{currentDay.display}</div>
                <h3 style={{ fontSize: 28, color: "#214A86", fontWeight: 700, marginTop: 6 }}>Add an extra meal</h3>
              </div>
              <button className="btn-ghost" onClick={() => setShowAddMealModal(false)}>Close</button>
            </div>
            <div style={{ padding: 22, display: "grid", gap: 18 }}>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 10 }}>
                {addMealCategories.map((category) => (
                  <button
                    key={category.key}
                    type="button"
                    onClick={() => {
                      setAddMealCategory(category.key);
                      setPendingAddMeal(null);
                      setAddMealQuery("");
                    }}
                    style={{
                      border: `1px solid ${addMealCategory === category.key ? "#214A86" : C.border}`,
                      background: addMealCategory === category.key ? "#214A86" : C.white,
                      color: addMealCategory === category.key ? C.white : C.text,
                      borderRadius: 16,
                      padding: "14px 12px",
                      textAlign: "left",
                    }}
                  >
                    <div style={{ fontWeight: 800 }}>{category.label}</div>
                    <div style={{ fontSize: 12, opacity: 0.82, marginTop: 6, lineHeight: 1.5 }}>{category.description}</div>
                  </button>
                ))}
              </div>
              <div>
                <label>Search ideas</label>
                <input value={addMealQuery} onChange={(e) => setAddMealQuery(e.target.value)} placeholder={`Search ${addMealCategories.find((category) => category.key === addMealCategory)?.label.toLowerCase()} ideas`} />
              </div>
              <div style={{ display: "grid", gap: 12, maxHeight: 340, overflowY: "auto", paddingRight: 2 }}>
                {addMealOptions.map((meal) => (
                  <button
                    key={`${addMealCategory}-${meal.name}`}
                    type="button"
                    onClick={() => setPendingAddMeal(meal)}
                    style={{ display: "grid", gridTemplateColumns: "112px 1fr auto", gap: 14, alignItems: "center", padding: 14, borderRadius: 18, border: `1px solid ${pendingAddMeal?.name === meal.name ? C.accent : C.border}`, background: pendingAddMeal?.name === meal.name ? C.accentLight : C.white, textAlign: "left" }}
                  >
                    <div style={{ height: 82, borderRadius: 14, backgroundImage: `url('${meal.image}')`, backgroundSize: "cover", backgroundPosition: "center" }} />
                    <div>
                      <div style={{ fontWeight: 700, fontSize: 18, color: "#214A86" }}>{meal.name}</div>
                      <div style={{ color: C.subtext, fontSize: 13, marginTop: 4 }}>{meal.calories} kcal · {meal.protein}g protein</div>
                      <div style={{ color: C.subtext, fontSize: 13, marginTop: 6 }}>{meal.tip}</div>
                    </div>
                    <span style={{ color: C.accent, fontWeight: 700 }}>{pendingAddMeal?.name === meal.name ? "Selected" : "Select"}</span>
                  </button>
                ))}
                {addMealOptions.length === 0 && (
                  <div className="card" style={{ padding: 18, textAlign: "center", color: C.subtext }}>
                    No matching meal ideas found.
                  </div>
                )}
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
                <div style={{ color: C.subtext, fontSize: 13 }}>
                  Build days with 5 or 6 smaller meals by adding flexible mini meal slots as needed.
                </div>
                <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                  <button className="btn-ghost" onClick={() => setShowAddMealModal(false)}>Cancel</button>
                  <button
                    className="btn-primary"
                    style={{ background: "#6B9B2F", borderColor: "#6B9B2F", padding: "12px 20px" }}
                    disabled={!pendingAddMeal}
                    onClick={saveAddedMeal}
                  >
                    Add Meal
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {toastMessage && (
        <div style={{ position: "fixed", inset: 0, display: "grid", placeItems: "center", pointerEvents: "none", zIndex: 1100 }}>
          <div className="card" style={{ padding: "16px 20px", background: "rgba(255, 252, 246, 0.96)", border: `1px solid ${C.accent}`, boxShadow: "0 24px 60px rgba(24, 42, 31, 0.18)", minWidth: 320, maxWidth: 420, textAlign: "center" }}>
            <div style={{ color: C.accent, fontWeight: 800, fontSize: 16 }}>Plan updated</div>
            <div style={{ color: C.subtext, marginTop: 6, lineHeight: 1.5 }}>{toastMessage}</div>
          </div>
        </div>
      )}

      <FloatingSousMazi message="How can I assist you today?" />

      {showWeekPicker && (
        <div onClick={() => setShowWeekPicker(false)} style={{ position: "fixed", inset: 0, background: "rgba(11, 18, 33, 0.4)", display: "grid", placeItems: "center", zIndex: 1050, padding: 20 }}>
          <div className="card" onClick={(e) => e.stopPropagation()} style={{ width: "min(440px, 100%)", padding: 22, background: C.white }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 18 }}>
              <div>
                <div style={{ color: C.accent, fontSize: 12, fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase" }}>Pick A Week</div>
                <div style={{ fontWeight: 700, fontSize: 24, color: "#214A86", marginTop: 4 }}>
                  {weekPickerView === "weeks" ? calendarMonthLabel : pickerYearLabel}
                </div>
              </div>
              <button className="btn-ghost" onClick={() => setShowWeekPicker(false)}>Close</button>
            </div>
            <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
              <button
                type="button"
                className="btn-ghost"
                style={{ flex: 1, borderColor: weekPickerView === "weeks" ? "#214A86" : C.border, background: weekPickerView === "weeks" ? C.accentLight : C.white }}
                onClick={() => setWeekPickerView("weeks")}
              >
                Weeks
              </button>
              <button
                type="button"
                className="btn-ghost"
                style={{ flex: 1, borderColor: weekPickerView === "year" ? "#214A86" : C.border, background: weekPickerView === "year" ? C.accentLight : C.white }}
                onClick={() => setWeekPickerView("year")}
              >
                Year
              </button>
            </div>

            {weekPickerView === "weeks" && (
              <>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 10, marginBottom: 14 }}>
                  <button
                    type="button"
                    className="btn-ghost"
                    onClick={() => setPickerCursorDate(new Date(pickerCursorDate.getFullYear(), pickerCursorDate.getMonth() - 1, 1))}
                  >
                    Previous
                  </button>
                  <button
                    type="button"
                    className="btn-ghost"
                    onClick={() => setWeekPickerView("year")}
                  >
                    Browse Year
                  </button>
                  <button
                    type="button"
                    className="btn-ghost"
                    onClick={() => setPickerCursorDate(new Date(pickerCursorDate.getFullYear(), pickerCursorDate.getMonth() + 1, 1))}
                  >
                    Next
                  </button>
                </div>
                <div style={{ display: "grid", gap: 10 }}>
                  {weekOptions.map((week) => {
                    const isSelectedWeek = plannerAnchorDate >= week.start && plannerAnchorDate <= week.end;
                    return (
                      <button
                        key={week.key}
                        type="button"
                        onClick={() => {
                          const nextPlannerState = createInitialWeeklyPlannerState(new Date(week.start));
                          setPlannerAnchorDate(nextPlannerState.anchorDate);
                          setPlannerDays(nextPlannerState.days);
                          setSelectedDayIndex(Math.min(Math.max(selectedDayIndex, 0), 6));
                          setShowWeekPicker(false);
                        }}
                        style={{
                          border: `1px solid ${isSelectedWeek ? "#214A86" : C.border}`,
                          background: isSelectedWeek ? "#214A86" : C.white,
                          color: isSelectedWeek ? C.white : C.text,
                          borderRadius: 18,
                          padding: "14px 16px",
                          textAlign: "left",
                        }}
                      >
                        <div style={{ fontWeight: 800, fontSize: 16 }}>Week of {week.label}</div>
                        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8, color: isSelectedWeek ? "rgba(255,255,255,0.86)" : C.subtext, fontSize: 12 }}>
                          {week.days.map((day) => (
                            <span key={day.toISOString()}>{day.toLocaleDateString("en-US", { weekday: "short", day: "numeric" })}</span>
                          ))}
                        </div>
                      </button>
                    );
                  })}
                </div>
              </>
            )}

            {weekPickerView === "year" && (
              <>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 10, marginBottom: 14 }}>
                  <button
                    type="button"
                    className="btn-ghost"
                    onClick={() => setPickerCursorDate(new Date(pickerCursorDate.getFullYear() - 1, pickerCursorDate.getMonth(), 1))}
                  >
                    Previous Year
                  </button>
                  <button
                    type="button"
                    className="btn-ghost"
                    onClick={() => setPickerCursorDate(new Date())}
                  >
                    This Year
                  </button>
                  <button
                    type="button"
                    className="btn-ghost"
                    onClick={() => setPickerCursorDate(new Date(pickerCursorDate.getFullYear() + 1, pickerCursorDate.getMonth(), 1))}
                  >
                    Next Year
                  </button>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
                  {monthOptions.map((month) => {
                    const isSelectedMonth =
                      plannerAnchorDate.getFullYear() === pickerCursorDate.getFullYear() &&
                      plannerAnchorDate.getMonth() === month.monthIndex;
                    return (
                      <button
                        key={month.key}
                        type="button"
                        onClick={() => {
                          setPickerCursorDate(new Date(pickerCursorDate.getFullYear(), month.monthIndex, 1));
                          setWeekPickerView("weeks");
                        }}
                        style={{
                          border: `1px solid ${isSelectedMonth ? "#214A86" : C.border}`,
                          background: isSelectedMonth ? "#214A86" : C.white,
                          color: isSelectedMonth ? C.white : C.text,
                          borderRadius: 16,
                          padding: "14px 10px",
                          fontWeight: 700,
                        }}
                      >
                        {month.label}
                      </button>
                    );
                  })}
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}

// ─── NAV BAR ──────────────────────────────────────────────────────────────────
function Nav({ user, step, setStep }) {
  const steps = [["profiles","👨‍👩‍👧","Profiles"],["engine","⚙","Engine"],["results","✦","Results"]];
  return (
    <div style={{ background: C.white, borderBottom: `1.5px solid ${C.border}`, padding: "0 24px", display: "flex", alignItems: "center", justifyContent: "space-between", height: 58, position: "sticky", top: 0, zIndex: 100, boxShadow: "0 1px 8px rgba(0,80,40,0.06)" }}>
      <Logo size={24} />
      <div style={{ display: "flex", gap: 2, background: C.bg, padding: 4, borderRadius: 10, border: `1.5px solid ${C.border}` }}>
        {steps.map(([id, icon, label], i) => (
          <button key={id} onClick={() => step !== "engine" && setStep(id)} className={`nav-link ${step === id ? "active" : ""}`}>
            <span style={{ width: 18, height: 18, background: step === id ? C.accent : C.dim, borderRadius: "50%", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 10, color: step === id ? C.white : C.subtext, fontWeight: 700, flexShrink: 0 }}>{i + 1}</span>
            {label}
          </button>
        ))}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div style={{ width: 34, height: 34, background: C.accentLight, border: `2px solid ${C.accent}`, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 800, color: C.accent, fontSize: 15 }}>{user[0]}</div>
        <span style={{ fontSize: 13.5, color: C.subtext, fontWeight: 500 }}>{user}</span>
      </div>
    </div>
  );
}

// ─── ROOT ─────────────────────────────────────────────────────────────────────
export default function App() {
  const [screen, setScreen] = useState("landing");
  const [user, setUser] = useState("");
  const [loginTab, setLoginTab] = useState("login");
  const [step, setStep] = useState("homeClassic");
  const [plannerState, setPlannerState] = useState(() => createInitialWeeklyPlannerState(new Date()));
  const [plannerHydrated, setPlannerHydrated] = useState(false);
  const [accountEmail, setAccountEmail] = useState("");
  const [household, setHousehold] = useState({ name: "", country: "US", members: 4, pets: { cat: false, dog: false }, scraps: false });
  const [profiles, setProfiles] = useState([
    { id: 1, name: "Maya", age: "34", height: "5 ft 6 in", weight: "141", role: "Adult", sex: "Female", activity: "Moderate", goal: "Maintain weight", allergies: "None", dislikes: "None", dietaryPattern: "Mediterranean", preferences: "Chicken, Onion", cuisines: ["Mexican"], lifeStage: "None", pregnancyWeek: "" },
    { id: 2, name: "Noah", age: "8", height: "4 ft 2 in", weight: "62", role: "Child", sex: "Male", activity: "Active", goal: "Grow strong", allergies: "None", dislikes: "Brussels sprouts", dietaryPattern: "None", preferences: "Pasta, Fruit", cuisines: ["American"], lifeStage: "None", pregnancyWeek: "" },
    { id: 3, name: "Ava", age: "12", height: "4 ft 11 in", weight: "90", role: "Child", sex: "Female", activity: "Moderate", goal: "Stay energized", allergies: "Dairy", dislikes: "Mushrooms", dietaryPattern: "None", preferences: "Rice, Berries", cuisines: ["Asian"], lifeStage: "None", pregnancyWeek: "" },
    { id: 4, name: "Mia", age: "67", height: "5 ft 3 in", weight: "130", role: "Adult", sex: "Female", activity: "Sedentary", goal: "Heart health", allergies: "Gluten", dislikes: "Spicy", dietaryPattern: "Low glycemic / low carb", preferences: "Fish, Greens", cuisines: ["Mediterranean"], lifeStage: "None", pregnancyWeek: "" },
  ]);
  const [setupProfiles, setSetupProfiles] = useState([]);
  const [profileDraft, setProfileDraft] = useState(defaultProfileDraft());
  const plannerDay = plannerState.days[Math.min(Math.max(plannerState.selectedDayIndex ?? new Date().getDay(), 0), 6)];
  const plannerSaveTimerRef = useRef(null);

  useEffect(() => {
    let cancelled = false;

    if (!user) {
      setPlannerHydrated(true);
      return undefined;
    }

    setPlannerHydrated(false);

    loadPlannerState(user).then((storedPlannerState) => {
      if (cancelled) return;
      const normalizedState = normalizePlannerState(storedPlannerState);
      if (normalizedState) {
        setPlannerState(normalizedState);
      }
      setPlannerHydrated(true);
    });

    return () => {
      cancelled = true;
    };
  }, [user]);

  useEffect(() => {
    if (!plannerHydrated || !user) return undefined;

    if (plannerSaveTimerRef.current) {
      clearTimeout(plannerSaveTimerRef.current);
    }

    plannerSaveTimerRef.current = setTimeout(() => {
      savePlannerState(user, plannerState);
    }, 350);

    return () => {
      if (plannerSaveTimerRef.current) {
        clearTimeout(plannerSaveTimerRef.current);
      }
    };
  }, [plannerState, plannerHydrated, user]);

  if (screen === "landing") return (
    <LandingModule onTrial={() => { setLoginTab("signup"); setSetupProfiles([]); setProfileDraft(defaultProfileDraft()); setScreen("account"); }} onLogin={() => { setLoginTab("login"); setScreen("login"); }} />
  );

  if (screen === "login") return (
    <LoginModule 
      initialTab={loginTab} 
      onLogin={n => { setUser(n); setScreen("app"); setStep("homeClassic"); }} 
      onBack={() => setScreen("landing")}
      onNavigateToSection={(section) => {
        setScreen("landing");
        // Scroll to section after a brief delay to allow navigation
        setTimeout(() => {
          const element = document.getElementById(section);
          if (element) {
            element.scrollIntoView({ behavior: 'smooth' });
          }
        }, 100);
      }}
    />
  );

  if (screen === "account") return (
    <CreateAccountModule onBack={() => setScreen("landing")} onNext={({ name, email }) => { setUser(name || "Mazimeal User"); setAccountEmail(email); setScreen("verify"); }} />
  );

  if (screen === "verify") return (
    <EmailVerificationModule email={accountEmail} onVerified={() => setScreen("legal")} onBack={() => setScreen("account")} />
  );

  if (screen === "legal") return (
    <LegalModule onBack={() => setScreen("verify")} onAgree={() => setScreen("household")} />
  );

  if (screen === "household") return (
    <HouseholdSetupModule household={household} setHousehold={setHousehold} onBack={() => setScreen("legal")} onNext={() => setScreen("profileBasics")} />
  );

  if (screen === "profileBasics") return (
    <ProfileBasicsModule profile={profileDraft} updateProfile={setProfileDraft} onBack={() => setScreen("household")} onNext={() => setScreen("dietPreferences")} />
  );

  if (screen === "dietPreferences") return (
    <DietPreferencesModule profile={profileDraft} updateProfile={setProfileDraft} onBack={() => setScreen("profileBasics")} onNext={() => setScreen("cuisinePreferences")} />
  );

  if (screen === "cuisinePreferences") return (
    <CulinaryPreferencesModule
      profile={profileDraft}
      updateProfile={setProfileDraft}
      onBack={() => setScreen("dietPreferences")}
      onNext={() => {
        if (profileDraft.sex === "Male") {
          setSetupProfiles(p => [...p, profileDraft]);
          setProfileDraft(defaultProfileDraft());
          setScreen("additionalProfiles");
          return;
        }
        setScreen("lifeStage");
      }}
    />
  );

  if (screen === "lifeStage") return (
    <LifeStageModule profile={profileDraft} updateProfile={setProfileDraft} onBack={() => setScreen("cuisinePreferences")} onNext={() => { setSetupProfiles(p => [...p, profileDraft]); setProfileDraft(defaultProfileDraft()); setScreen("additionalProfiles"); }} />
  );

  if (screen === "additionalProfiles") return (
    <AdditionalProfilesModule
      profiles={setupProfiles}
      onAddAdult={() => { setProfileDraft(defaultProfileDraft("Adult")); setScreen("profileBasics"); }}
      onAddChild={() => { setProfileDraft(defaultProfileDraft("Child")); setScreen("profileBasics"); }}
      onInvite={() => setScreen("inviteAdult")}
      onBack={() => setScreen("lifeStage")}
      onContinue={() => {
        if (setupProfiles.length > 0) {
          setProfiles(setupProfiles);
        }
        setScreen("app");
      }}
    />
  );

  if (screen === "inviteAdult") return (
    <InviteAdultModule onBack={() => setScreen("additionalProfiles")} onSend={(email, permission) => { setSetupProfiles(p => [...p, { invited: true, role: "Adult", inviteEmail: email, permission, name: "Invited Adult", age: "", lifeStage: "None" }]); setScreen("additionalProfiles"); }} />
  );

  if (screen === "app") return (
    <OnboardingModule
      user={user}
      profiles={profiles}
      profile={profiles[0] || profileDraft}
      profileCount={profiles.length}
      setProfiles={setProfiles}
      step={step}
      setStep={setStep}
      plannerDay={plannerDay}
      plannerState={plannerState}
      setPlannerState={setPlannerState}
    />
  );

  return null;
}
