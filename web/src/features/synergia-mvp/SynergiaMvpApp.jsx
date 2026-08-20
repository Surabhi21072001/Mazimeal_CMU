import { useState, useEffect, useRef } from "react";

// ─── DESIGN TOKENS ───────────────────────────────────────────────────────────
const C = {
  bg: "#0A0F0D",
  surface: "#111A14",
  card: "#16221A",
  border: "#1E3028",
  accent: "#3DFF8F",
  accentDim: "#2ACC72",
  accentGlow: "rgba(61,255,143,0.15)",
  gold: "#F0C060",
  coral: "#FF6B6B",
  sky: "#60BFFF",
  lavender: "#B48AFF",
  text: "#E8F4EC",
  muted: "#7A9E85",
  dim: "#3A5444",
};

const styles = `
  @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:ital,wght@0,300;0,400;0,500;1,300&display=swap');
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: ${C.bg}; color: ${C.text}; font-family: 'DM Sans', sans-serif; }
  ::-webkit-scrollbar { width: 4px; } ::-webkit-scrollbar-track { background: ${C.bg}; }
  ::-webkit-scrollbar-thumb { background: ${C.dim}; border-radius: 2px; }
  @keyframes fadeUp { from { opacity:0; transform:translateY(16px); } to { opacity:1; transform:translateY(0); } }
  @keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.5; } }
  @keyframes glow { 0%,100% { box-shadow: 0 0 20px ${C.accentGlow}; } 50% { box-shadow: 0 0 40px rgba(61,255,143,0.3); } }
  @keyframes spin { to { transform: rotate(360deg); } }
  .fade-up { animation: fadeUp 0.5s ease forwards; }
  .card { background: ${C.card}; border: 1px solid ${C.border}; border-radius: 16px; }
  .btn-primary { background: ${C.accent}; color: ${C.bg}; border: none; border-radius: 10px; padding: 12px 24px; font-family: 'Syne', sans-serif; font-weight: 700; font-size: 14px; cursor: pointer; transition: all 0.2s; letter-spacing: 0.5px; }
  .btn-primary:hover { background: ${C.accentDim}; transform: translateY(-1px); box-shadow: 0 8px 24px ${C.accentGlow}; }
  .btn-ghost { background: transparent; color: ${C.muted}; border: 1px solid ${C.border}; border-radius: 10px; padding: 10px 20px; font-family: 'DM Sans', sans-serif; font-size: 14px; cursor: pointer; transition: all 0.2s; }
  .btn-ghost:hover { border-color: ${C.accent}; color: ${C.accent}; }
  input, select, textarea { background: ${C.surface}; border: 1px solid ${C.border}; border-radius: 10px; padding: 12px 16px; color: ${C.text}; font-family: 'DM Sans', sans-serif; font-size: 14px; width: 100%; transition: border 0.2s; outline: none; }
  input:focus, select:focus, textarea:focus { border-color: ${C.accent}; box-shadow: 0 0 0 3px ${C.accentGlow}; }
  label { font-size: 13px; color: ${C.muted}; display: block; margin-bottom: 6px; font-weight: 500; }
  .tag { display: inline-flex; align-items: center; gap: 6px; background: ${C.surface}; border: 1px solid ${C.border}; border-radius: 20px; padding: 4px 12px; font-size: 12px; color: ${C.muted}; }
  .tag.active { background: rgba(61,255,143,0.1); border-color: ${C.accent}; color: ${C.accent}; }
  .spinner { width: 36px; height: 36px; border: 3px solid ${C.border}; border-top-color: ${C.accent}; border-radius: 50%; animation: spin 0.7s linear infinite; }
`;

// ─── MOCK DATA ────────────────────────────────────────────────────────────────
const CONDITIONS = ["Diabetes (Type 2)", "Iron Deficiency", "Celiac Disease", "Lactose Intolerance", "High Cholesterol", "Hypertension", "Pregnancy", "PCOS", "IBS", "None"];
const ALLERGIES = ["Shellfish", "Nuts", "Gluten", "Dairy", "Eggs", "Soy", "Fish", "None"];
const GOALS = ["Weight Loss", "Muscle Gain", "Energy Boost", "Gut Health", "Heart Health", "Blood Sugar Control", "General Wellness"];

const RECIPE_DB = [
  {
    id: 1, name: "Iron-Boosted Lentil & Spinach Soup", time: "35 min", difficulty: "Easy",
    synergies: ["Vitamin C + Iron", "Turmeric + Black Pepper"],
    nutrients: { iron: 92, vitC: 78, protein: 65, fiber: 88 },
    tags: ["High Iron", "Anti-inflammatory", "Pregnancy-safe"],
    steps: ["Sauté onions and garlic (let garlic rest 10 min before cooking to activate allicin)", "Add lentils, turmeric + black pepper", "Finish with lemon juice to boost iron absorption by 3x"],
    img: "🥣", calories: 340, suitableFor: ["Iron Deficiency", "Pregnancy"],
    bioavailabilityTip: "Squeeze lemon over bowl just before serving — Vitamin C triples non-heme iron absorption",
  },
  {
    id: 2, name: "Glycemic-Smart Chicken Rice Bowl", time: "30 min", difficulty: "Medium",
    synergies: ["Resistant Starch", "Glycemic Retrogradation"],
    nutrients: { carbs: 45, protein: 88, fiber: 72, glycemic: 38 },
    tags: ["Low GI", "Diabetic-Friendly", "High Protein"],
    steps: ["Cook rice, cool overnight (forms resistant starch)", "Reheat with vegetables", "Sequence: veggies → protein → rice last to blunt glucose spike"],
    img: "🍚", calories: 420, suitableFor: ["Diabetes (Type 2)"],
    bioavailabilityTip: "Eating vegetables and protein before rice reduces glucose spike by up to 73%",
  },
  {
    id: 3, name: "Shellfish-Free Omega Salmon Salad", time: "20 min", difficulty: "Easy",
    synergies: ["Fat-soluble Vitamins + Healthy Fats", "Quercetin + Resveratrol"],
    nutrients: { omega3: 95, vitD: 82, antioxidants: 78, protein: 91 },
    tags: ["Shellfish-Free", "Heart Health", "Anti-inflammatory"],
    steps: ["Grill salmon with olive oil", "Pair with colorful bell peppers (vit C boosts iron absorption)", "Dress with lemon-tahini (fat aids fat-soluble vitamin absorption)"],
    img: "🥗", calories: 380, suitableFor: ["High Cholesterol", "General Wellness"],
    bioavailabilityTip: "Fat-soluble vitamins A, D, E, K absorb up to 4x better with healthy dietary fats",
  },
  {
    id: 4, name: "Pregnancy Power Buddha Bowl", time: "25 min", difficulty: "Easy",
    synergies: ["Folate + B12", "Calcium + Vitamin D", "Iron + Vitamin C"],
    nutrients: { folate: 95, calcium: 85, iron: 78, protein: 72 },
    tags: ["Pregnancy-Safe", "High Folate", "Complete Protein"],
    steps: ["Layer quinoa, edamame, roasted sweet potato", "Add fortified nutritional yeast (B12)", "Top with pumpkin seeds + lemon dressing"],
    img: "🫙", calories: 460, suitableFor: ["Pregnancy", "Iron Deficiency"],
    bioavailabilityTip: "Quinoa provides all 9 essential amino acids — rare for plant proteins",
  },
];

// ─── COMPONENTS ───────────────────────────────────────────────────────────────

function Logo({ size = 28 }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <div style={{ width: size, height: size, background: `linear-gradient(135deg, ${C.accent}, ${C.sky})`, borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", fontSize: size * 0.55 }}>✦</div>
      <span style={{ fontFamily: "Syne", fontWeight: 800, fontSize: size * 0.85, color: C.text, letterSpacing: "-0.5px" }}>Synergia</span>
    </div>
  );
}

function NutrientBar({ label, value, color = C.accent }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: C.muted, marginBottom: 4 }}>
        <span>{label}</span><span style={{ color }}>{value}%</span>
      </div>
      <div style={{ height: 4, background: C.border, borderRadius: 2, overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${value}%`, background: color, borderRadius: 2, transition: "width 1s ease" }} />
      </div>
    </div>
  );
}

function SynergyBadge({ text }) {
  const colors = [C.accent, C.gold, C.sky, C.lavender, C.coral];
  const c = colors[text.length % colors.length];
  return (
    <span style={{ background: `${c}18`, border: `1px solid ${c}44`, color: c, borderRadius: 20, padding: "3px 10px", fontSize: 11, fontWeight: 500 }}>⚡ {text}</span>
  );
}

// ─── MODULE 1: LOGIN ──────────────────────────────────────────────────────────
function LoginModule({ onLogin }) {
  const [tab, setTab] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", padding: 24, position: "relative", overflow: "hidden" }}>
      {/* Background orbs */}
      <div style={{ position: "absolute", width: 500, height: 500, background: `radial-gradient(circle, ${C.accentGlow} 0%, transparent 70%)`, top: -100, left: -100, pointerEvents: "none" }} />
      <div style={{ position: "absolute", width: 400, height: 400, background: `radial-gradient(circle, rgba(96,191,255,0.08) 0%, transparent 70%)`, bottom: -50, right: -50, pointerEvents: "none" }} />

      <div className="fade-up" style={{ width: "100%", maxWidth: 420 }}>
        <div style={{ textAlign: "center", marginBottom: 40 }}>
          <Logo size={36} />
          <p style={{ color: C.muted, marginTop: 12, fontSize: 14, lineHeight: 1.6 }}>
            AI-powered family nutrition intelligence.<br />Turn complexity into nourishment.
          </p>
        </div>

        <div className="card" style={{ padding: 32 }}>
          <div style={{ display: "flex", background: C.surface, borderRadius: 10, padding: 4, marginBottom: 28 }}>
            {["login", "signup"].map(t => (
              <button key={t} onClick={() => setTab(t)} style={{ flex: 1, padding: "9px 0", border: "none", borderRadius: 8, background: tab === t ? C.card : "transparent", color: tab === t ? C.accent : C.muted, fontFamily: "DM Sans", fontSize: 14, fontWeight: tab === t ? 500 : 400, cursor: "pointer", transition: "all 0.2s" }}>
                {t === "login" ? "Sign In" : "Create Account"}
              </button>
            ))}
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            {tab === "signup" && (
              <div><label>Full Name</label><input placeholder="e.g. Sarah Johnson" value={name} onChange={e => setName(e.target.value)} /></div>
            )}
            <div><label>Email Address</label><input type="email" placeholder="you@family.com" value={email} onChange={e => setEmail(e.target.value)} /></div>
            <div><label>Password</label><input type="password" placeholder="••••••••" value={password} onChange={e => setPassword(e.target.value)} /></div>
            <button className="btn-primary" style={{ width: "100%", padding: "14px", fontSize: 15, marginTop: 4, animation: "glow 3s ease-in-out infinite" }} onClick={() => onLogin(name || "Sarah")}>
              {tab === "login" ? "Sign In to Synergia →" : "Start Your Journey →"}
            </button>
          </div>

          <div style={{ textAlign: "center", marginTop: 20, padding: "16px 0 0", borderTop: `1px solid ${C.border}` }}>
            <p style={{ fontSize: 12, color: C.dim }}>Demo: click button to enter as Sarah Johnson</p>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── MODULE 2: FAMILY PROFILE DATABASE ───────────────────────────────────────
function ProfileModule({ profiles, setProfiles, onContinue }) {
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ name: "", age: "", role: "Adult", conditions: [], allergies: [], goals: [] });

  const toggle = (arr, val) => arr.includes(val) ? arr.filter(x => x !== val) : [...arr, val];

  const addProfile = () => {
    if (!form.name) return;
    setProfiles(p => [...p, { ...form, id: Date.now() }]);
    setForm({ name: "", age: "", role: "Adult", conditions: [], allergies: [], goals: [] });
    setAdding(false);
  };

  const roleColors = { Adult: C.sky, Child: C.accent, Infant: C.gold };

  return (
    <div style={{ maxWidth: 860, margin: "0 auto", padding: "32px 20px" }} className="fade-up">
      <div style={{ marginBottom: 32 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
          <div style={{ width: 36, height: 36, background: `${C.sky}22`, border: `1px solid ${C.sky}44`, borderRadius: 10, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18 }}>👨‍👩‍👧</div>
          <h2 style={{ fontFamily: "Syne", fontWeight: 700, fontSize: 22 }}>Family Profiles</h2>
        </div>
        <p style={{ color: C.muted, fontSize: 14 }}>Build your household's nutrition map. Each profile personalizes meal recommendations.</p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 16, marginBottom: 20 }}>
        {profiles.map(p => (
          <div key={p.id} className="card" style={{ padding: 20 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 14 }}>
              <div>
                <div style={{ fontFamily: "Syne", fontWeight: 700, fontSize: 16, marginBottom: 2 }}>{p.name}</div>
                <div style={{ fontSize: 12, color: C.muted }}>{p.age ? `Age ${p.age} · ` : ""}{p.role}</div>
              </div>
              <span style={{ background: `${roleColors[p.role]}22`, color: roleColors[p.role], border: `1px solid ${roleColors[p.role]}44`, borderRadius: 6, padding: "2px 8px", fontSize: 11 }}>{p.role}</span>
            </div>
            {p.conditions.length > 0 && (
              <div style={{ marginBottom: 8 }}>
                <div style={{ fontSize: 11, color: C.dim, marginBottom: 4 }}>CONDITIONS</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                  {p.conditions.map(c => <span key={c} style={{ background: `${C.coral}18`, color: C.coral, border: `1px solid ${C.coral}33`, borderRadius: 4, padding: "2px 7px", fontSize: 11 }}>{c}</span>)}
                </div>
              </div>
            )}
            {p.allergies.length > 0 && (
              <div>
                <div style={{ fontSize: 11, color: C.dim, marginBottom: 4 }}>ALLERGIES</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                  {p.allergies.map(a => <span key={a} style={{ background: `${C.gold}18`, color: C.gold, border: `1px solid ${C.gold}33`, borderRadius: 4, padding: "2px 7px", fontSize: 11 }}>⚠ {a}</span>)}
                </div>
              </div>
            )}
          </div>
        ))}

        {!adding && (
          <button onClick={() => setAdding(true)} style={{ background: "transparent", border: `2px dashed ${C.border}`, borderRadius: 16, padding: 20, cursor: "pointer", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 8, color: C.muted, minHeight: 160, transition: "all 0.2s" }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = C.accent; e.currentTarget.style.color = C.accent; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = C.border; e.currentTarget.style.color = C.muted; }}>
            <span style={{ fontSize: 28 }}>+</span>
            <span style={{ fontSize: 13, fontWeight: 500 }}>Add Family Member</span>
          </button>
        )}
      </div>

      {adding && (
        <div className="card" style={{ padding: 28, marginBottom: 20 }}>
          <h3 style={{ fontFamily: "Syne", fontWeight: 700, marginBottom: 20 }}>New Profile</h3>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16, marginBottom: 20 }}>
            <div><label>Name</label><input placeholder="e.g. Emma" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} /></div>
            <div><label>Age</label><input type="number" placeholder="e.g. 8" value={form.age} onChange={e => setForm(f => ({ ...f, age: e.target.value }))} /></div>
            <div><label>Role</label>
              <select value={form.role} onChange={e => setForm(f => ({ ...f, role: e.target.value }))}>
                {["Adult", "Child", "Infant", "Elderly"].map(r => <option key={r}>{r}</option>)}
              </select>
            </div>
          </div>

          <div style={{ marginBottom: 16 }}>
            <label style={{ marginBottom: 10 }}>Health Conditions</label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {CONDITIONS.map(c => (
                <button key={c} onClick={() => setForm(f => ({ ...f, conditions: toggle(f.conditions, c) }))}
                  className={`tag ${form.conditions.includes(c) ? "active" : ""}`}
                  style={{ cursor: "pointer", border: form.conditions.includes(c) ? `1px solid ${C.accent}` : `1px solid ${C.border}` }}>
                  {c}
                </button>
              ))}
            </div>
          </div>

          <div style={{ marginBottom: 20 }}>
            <label style={{ marginBottom: 10 }}>Allergies / Intolerances</label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {ALLERGIES.map(a => (
                <button key={a} onClick={() => setForm(f => ({ ...f, allergies: toggle(f.allergies, a) }))}
                  className={`tag ${form.allergies.includes(a) ? "active" : ""}`}
                  style={{ cursor: "pointer", background: form.allergies.includes(a) ? `${C.gold}18` : C.surface, borderColor: form.allergies.includes(a) ? C.gold : C.border, color: form.allergies.includes(a) ? C.gold : C.muted }}>
                  {a}
                </button>
              ))}
            </div>
          </div>

          <div style={{ display: "flex", gap: 12 }}>
            <button className="btn-primary" onClick={addProfile}>Add Profile</button>
            <button className="btn-ghost" onClick={() => setAdding(false)}>Cancel</button>
          </div>
        </div>
      )}

      {profiles.length > 0 && (
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <button className="btn-primary" onClick={onContinue} style={{ fontSize: 15, padding: "14px 32px" }}>
            Generate AI Meal Plan →
          </button>
        </div>
      )}
    </div>
  );
}

// ─── MODULE 3: AI ENGINE ──────────────────────────────────────────────────────
function EngineModule({ profiles, onResults }) {
  const [stage, setStage] = useState(0);
  const stages = [
    { icon: "🔍", label: "Analyzing 847 nutrition databases...", color: C.accent },
    { icon: "⚗️", label: "Mapping food synergy combinations...", color: C.gold },
    { icon: "🧬", label: "Computing bioavailability scores...", color: C.sky },
    { icon: "👨‍👩‍👧", label: "Cross-referencing family profiles...", color: C.lavender },
    { icon: "🛡️", label: "Filtering allergens & contraindications...", color: C.coral },
    { icon: "✦", label: "Optimizing meal sequences...", color: C.accent },
  ];

  useEffect(() => {
    const t = setInterval(() => setStage(s => {
      if (s >= stages.length - 1) { clearInterval(t); setTimeout(onResults, 600); return s; }
      return s + 1;
    }), 700);
    return () => clearInterval(t);
  }, []);

  const allConditions = [...new Set(profiles.flatMap(p => p.conditions).filter(c => c !== "None"))];
  const allAllergies = [...new Set(profiles.flatMap(p => p.allergies).filter(a => a !== "None"))];

  return (
    <div style={{ minHeight: "80vh", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: 24 }} className="fade-up">
      <div style={{ textAlign: "center", maxWidth: 480 }}>
        <div style={{ marginBottom: 32 }}>
          <div style={{ fontSize: 64, marginBottom: 16, animation: "pulse 2s ease-in-out infinite" }}>✦</div>
          <h2 style={{ fontFamily: "Syne", fontWeight: 800, fontSize: 28, marginBottom: 8 }}>Synergia Engine</h2>
          <p style={{ color: C.muted, fontSize: 14 }}>Building your family's personalized nutrition blueprint</p>
        </div>

        <div className="card" style={{ padding: 28, marginBottom: 28, textAlign: "left" }}>
          {stages.map((s, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 14, padding: "10px 0", borderBottom: i < stages.length - 1 ? `1px solid ${C.border}` : "none", opacity: i <= stage ? 1 : 0.3, transition: "opacity 0.4s" }}>
              <span style={{ fontSize: 20, minWidth: 28 }}>{s.icon}</span>
              <span style={{ fontSize: 13, color: i === stage ? s.color : C.muted, fontWeight: i === stage ? 500 : 400 }}>{s.label}</span>
              {i < stage && <span style={{ marginLeft: "auto", color: C.accent, fontSize: 16 }}>✓</span>}
              {i === stage && <div className="spinner" style={{ marginLeft: "auto", width: 18, height: 18, borderWidth: 2, borderTopColor: s.color }} />}
            </div>
          ))}
        </div>

        {(allConditions.length > 0 || allAllergies.length > 0) && (
          <div className="card" style={{ padding: 18, textAlign: "left" }}>
            <div style={{ fontSize: 11, color: C.dim, marginBottom: 10 }}>OPTIMIZATION PARAMETERS</div>
            {allConditions.length > 0 && (
              <div style={{ marginBottom: 8 }}>
                <span style={{ fontSize: 12, color: C.muted }}>Conditions: </span>
                {allConditions.map(c => <span key={c} style={{ background: `${C.coral}18`, color: C.coral, borderRadius: 4, padding: "2px 8px", fontSize: 11, marginRight: 4 }}>{c}</span>)}
              </div>
            )}
            {allAllergies.length > 0 && (
              <div>
                <span style={{ fontSize: 12, color: C.muted }}>Excluded: </span>
                {allAllergies.map(a => <span key={a} style={{ background: `${C.gold}18`, color: C.gold, borderRadius: 4, padding: "2px 8px", fontSize: 11, marginRight: 4 }}>⚠ {a}</span>)}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── MODULE 4: RESULTS ────────────────────────────────────────────────────────
function ResultsModule({ profiles, onBack }) {
  const [selected, setSelected] = useState(null);
  const [activeTab, setActiveTab] = useState("recipes");
  const [saved, setSaved] = useState([]);

  const allAllergies = [...new Set(profiles.flatMap(p => p.allergies).filter(a => a !== "None"))];
  const allConditions = [...new Set(profiles.flatMap(p => p.conditions).filter(c => c !== "None"))];

  const filteredRecipes = RECIPE_DB.filter(r =>
    !allAllergies.some(a => r.tags.some(t => t.toLowerCase().includes(a.toLowerCase())))
  );

  const weekDays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const mealPlan = weekDays.map((day, i) => ({
    day, breakfast: ["Oats + berries", "Eggs & avocado toast", "Greek yogurt bowl", "Smoothie bowl", "Chia pudding", "Whole grain waffles", "Fruit & nut mix"][i],
    lunch: filteredRecipes[i % filteredRecipes.length]?.name || "Quinoa salad",
    dinner: filteredRecipes[(i + 1) % filteredRecipes.length]?.name || "Salmon bowl",
  }));

  return (
    <div style={{ maxWidth: 940, margin: "0 auto", padding: "32px 20px" }} className="fade-up">
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 28 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
            <div style={{ width: 8, height: 8, background: C.accent, borderRadius: "50%", animation: "pulse 2s ease-in-out infinite" }} />
            <span style={{ fontSize: 12, color: C.accent, fontWeight: 500 }}>MEAL INTELLIGENCE READY</span>
          </div>
          <h2 style={{ fontFamily: "Syne", fontWeight: 800, fontSize: 26 }}>Your Family's Nutrition Plan</h2>
          <p style={{ color: C.muted, fontSize: 14, marginTop: 4 }}>
            {filteredRecipes.length} optimized recipes · {profiles.length} family members · {allConditions.length} conditions managed
          </p>
        </div>
        <button className="btn-ghost" onClick={onBack}>← Edit Profiles</button>
      </div>

      {/* Summary cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 28 }}>
        {[
          { label: "Recipes Generated", val: filteredRecipes.length, icon: "🍽", color: C.accent },
          { label: "Synergy Combos", val: filteredRecipes.reduce((a, r) => a + r.synergies.length, 0), icon: "⚡", color: C.gold },
          { label: "Allergens Excluded", val: allAllergies.length, icon: "🛡", color: C.coral },
          { label: "Conditions Managed", val: allConditions.length, icon: "💊", color: C.lavender },
        ].map(s => (
          <div key={s.label} className="card" style={{ padding: 16 }}>
            <div style={{ fontSize: 22, marginBottom: 6 }}>{s.icon}</div>
            <div style={{ fontFamily: "Syne", fontWeight: 800, fontSize: 28, color: s.color }}>{s.val}</div>
            <div style={{ fontSize: 11, color: C.muted, marginTop: 2 }}>{s.label}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 4, marginBottom: 24, background: C.surface, padding: 4, borderRadius: 12, width: "fit-content" }}>
        {[["recipes", "🍽 Recipes"], ["mealplan", "📅 Weekly Plan"], ["nutrition", "📊 Nutrition Map"]].map(([id, label]) => (
          <button key={id} onClick={() => setActiveTab(id)} style={{ padding: "9px 20px", border: "none", borderRadius: 8, background: activeTab === id ? C.card : "transparent", color: activeTab === id ? C.text : C.muted, fontFamily: "DM Sans", fontSize: 13, fontWeight: activeTab === id ? 500 : 400, cursor: "pointer", transition: "all 0.2s", whiteSpace: "nowrap" }}>
            {label}
          </button>
        ))}
      </div>

      {/* RECIPES TAB */}
      {activeTab === "recipes" && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 16 }}>
          {filteredRecipes.map(r => (
            <div key={r.id} className="card" style={{ padding: 20, cursor: "pointer", transition: "all 0.2s", border: selected?.id === r.id ? `1px solid ${C.accent}` : `1px solid ${C.border}` }}
              onClick={() => setSelected(selected?.id === r.id ? null : r)}
              onMouseEnter={e => e.currentTarget.style.borderColor = C.dim}
              onMouseLeave={e => e.currentTarget.style.borderColor = selected?.id === r.id ? C.accent : C.border}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 14 }}>
                <span style={{ fontSize: 40 }}>{r.img}</span>
                <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  <span style={{ fontSize: 12, color: C.muted }}>{r.time}</span>
                  <button onClick={e => { e.stopPropagation(); setSaved(s => s.includes(r.id) ? s.filter(x => x !== r.id) : [...s, r.id]); }}
                    style={{ background: "none", border: "none", cursor: "pointer", fontSize: 18, color: saved.includes(r.id) ? C.accent : C.dim }}>
                    {saved.includes(r.id) ? "♥" : "♡"}
                  </button>
                </div>
              </div>
              <h3 style={{ fontFamily: "Syne", fontWeight: 700, fontSize: 15, marginBottom: 10, lineHeight: 1.3 }}>{r.name}</h3>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 12 }}>
                {r.synergies.map(s => <SynergyBadge key={s} text={s} />)}
              </div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
                {r.tags.slice(0, 2).map(t => <span key={t} className="tag">{t}</span>)}
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: C.muted, paddingTop: 12, borderTop: `1px solid ${C.border}` }}>
                <span>{r.calories} kcal</span>
                <span style={{ color: r.difficulty === "Easy" ? C.accent : C.gold }}>{r.difficulty}</span>
              </div>

              {selected?.id === r.id && (
                <div style={{ marginTop: 16, paddingTop: 16, borderTop: `1px solid ${C.border}` }}>
                  <div style={{ fontSize: 11, color: C.dim, marginBottom: 10 }}>NUTRIENT OPTIMIZATION</div>
                  {Object.entries(r.nutrients).map(([k, v]) => (
                    <NutrientBar key={k} label={k.replace(/([A-Z])/g, ' $1').replace(/^./, s => s.toUpperCase())} value={v} />
                  ))}
                  <div style={{ background: `${C.accentGlow}`, border: `1px solid ${C.accent}33`, borderRadius: 10, padding: 12, marginTop: 12 }}>
                    <div style={{ fontSize: 11, color: C.accent, marginBottom: 4 }}>💡 BIOAVAILABILITY TIP</div>
                    <p style={{ fontSize: 12, color: C.text, lineHeight: 1.6 }}>{r.bioavailabilityTip}</p>
                  </div>
                  <div style={{ marginTop: 14 }}>
                    <div style={{ fontSize: 11, color: C.dim, marginBottom: 8 }}>PREPARATION STEPS</div>
                    {r.steps.map((step, i) => (
                      <div key={i} style={{ display: "flex", gap: 10, marginBottom: 8 }}>
                        <span style={{ minWidth: 20, height: 20, background: C.surface, border: `1px solid ${C.border}`, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, color: C.accent, flexShrink: 0 }}>{i + 1}</span>
                        <span style={{ fontSize: 13, color: C.muted, lineHeight: 1.5 }}>{step}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* MEAL PLAN TAB */}
      {activeTab === "mealplan" && (
        <div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "separate", borderSpacing: "0 8px" }}>
              <thead>
                <tr>
                  {["Day", "Breakfast", "Lunch", "Dinner"].map(h => (
                    <th key={h} style={{ textAlign: "left", padding: "0 16px 8px", fontSize: 11, color: C.dim, fontWeight: 600, letterSpacing: 1 }}>{h.toUpperCase()}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {mealPlan.map((row, i) => (
                  <tr key={row.day}>
                    <td style={{ padding: "14px 16px", background: C.card, borderRadius: "10px 0 0 10px", border: `1px solid ${C.border}`, borderRight: "none" }}>
                      <span style={{ fontFamily: "Syne", fontWeight: 700, color: i === 0 ? C.accent : C.text }}>{row.day}</span>
                    </td>
                    {[row.breakfast, row.lunch, row.dinner].map((meal, j) => (
                      <td key={j} style={{ padding: "14px 16px", background: C.card, fontSize: 13, color: C.muted, border: `1px solid ${C.border}`, borderLeft: "none", borderRight: j < 2 ? "none" : `1px solid ${C.border}`, borderRadius: j === 2 ? "0 10px 10px 0" : 0 }}>
                        {meal}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="card" style={{ padding: 20, marginTop: 20, display: "flex", gap: 12, alignItems: "flex-start" }}>
            <span style={{ fontSize: 24 }}>💡</span>
            <div>
              <div style={{ fontFamily: "Syne", fontWeight: 700, marginBottom: 4 }}>Smart Sequencing Applied</div>
              <p style={{ fontSize: 13, color: C.muted, lineHeight: 1.6 }}>Meals are ordered to maximize nutrient absorption windows. Vitamin C-rich breakfasts prime iron absorption for iron-rich lunches. Evening meals are lower glycemic index to support overnight metabolic recovery.</p>
            </div>
          </div>
        </div>
      )}

      {/* NUTRITION MAP TAB */}
      {activeTab === "nutrition" && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
          {profiles.map(p => (
            <div key={p.id} className="card" style={{ padding: 24 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
                <div>
                  <h3 style={{ fontFamily: "Syne", fontWeight: 700, fontSize: 16 }}>{p.name}</h3>
                  <span style={{ fontSize: 12, color: C.muted }}>{p.role}{p.age ? ` · Age ${p.age}` : ""}</span>
                </div>
                <div style={{ width: 44, height: 44, background: `${C.accent}18`, border: `1px solid ${C.accent}33`, borderRadius: 22, display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "Syne", fontWeight: 800, color: C.accent, fontSize: 18 }}>
                  {p.name[0]}
                </div>
              </div>
              {[
                { label: "Iron", value: p.conditions.includes("Iron Deficiency") ? 45 : 82, color: C.coral },
                { label: "Vitamin C", value: 91, color: C.accent },
                { label: "Vitamin D", value: p.role === "Child" ? 88 : 62, color: C.gold },
                { label: "Omega-3", value: 74, color: C.sky },
                { label: "Fiber", value: p.conditions.includes("Diabetes (Type 2)") ? 55 : 79, color: C.lavender },
                { label: "Folate", value: p.conditions.includes("Pregnancy") ? 95 : 71, color: C.accent },
              ].map(n => <NutrientBar key={n.label} {...n} />)}
              {p.conditions.filter(c => c !== "None").length > 0 && (
                <div style={{ marginTop: 14, padding: 12, background: `${C.coral}10`, border: `1px solid ${C.coral}22`, borderRadius: 8 }}>
                  <div style={{ fontSize: 11, color: C.coral, marginBottom: 4 }}>CLINICAL FOCUS</div>
                  <p style={{ fontSize: 12, color: C.muted }}>Meals optimized for: {p.conditions.filter(c => c !== "None").join(", ")}</p>
                </div>
              )}
            </div>
          ))}
          <div className="card" style={{ padding: 24, gridColumn: profiles.length % 2 === 1 ? "1 / -1" : "auto" }}>
            <h3 style={{ fontFamily: "Syne", fontWeight: 700, fontSize: 16, marginBottom: 16 }}>Family Synergy Score</h3>
            <div style={{ display: "flex", alignItems: "center", gap: 20, marginBottom: 20 }}>
              <div style={{ position: "relative", width: 90, height: 90 }}>
                <svg viewBox="0 0 90 90" style={{ transform: "rotate(-90deg)" }}>
                  <circle cx="45" cy="45" r="38" fill="none" stroke={C.border} strokeWidth="8" />
                  <circle cx="45" cy="45" r="38" fill="none" stroke={C.accent} strokeWidth="8" strokeDasharray={`${2 * Math.PI * 38 * 0.87} ${2 * Math.PI * 38}`} strokeLinecap="round" />
                </svg>
                <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "Syne", fontWeight: 800, fontSize: 20, color: C.accent }}>87</div>
              </div>
              <div>
                <div style={{ fontFamily: "Syne", fontWeight: 700, marginBottom: 4 }}>Excellent Optimization</div>
                <p style={{ fontSize: 13, color: C.muted, lineHeight: 1.5 }}>Your family's meal plan achieves 87% nutrient synergy — significantly above the 52% average for unplanned family diets.</p>
              </div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              {[["Food Synergy Combos", "12 active", C.accent], ["Allergen Safety", "100%", C.sky], ["Condition Coverage", `${allConditions.length} managed`, C.gold], ["Bioavailability Boost", "+34%", C.lavender]].map(([k, v, c]) => (
                <div key={k} style={{ background: C.surface, borderRadius: 8, padding: "10px 14px" }}>
                  <div style={{ fontSize: 11, color: C.dim, marginBottom: 2 }}>{k}</div>
                  <div style={{ fontFamily: "Syne", fontWeight: 700, color: c, fontSize: 15 }}>{v}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── NAV ──────────────────────────────────────────────────────────────────────
function Nav({ user, step, setStep }) {
  const steps = ["profiles", "engine", "results"];
  const labels = ["Profiles", "Engine", "Results"];
  return (
    <div style={{ background: C.surface, borderBottom: `1px solid ${C.border}`, padding: "0 24px", display: "flex", alignItems: "center", justifyContent: "space-between", height: 60, position: "sticky", top: 0, zIndex: 100 }}>
      <Logo size={24} />
      <div style={{ display: "flex", gap: 4 }}>
        {steps.map((s, i) => (
          <button key={s} onClick={() => step !== "engine" && setStep(s)}
            style={{ padding: "6px 14px", border: "none", borderRadius: 8, background: step === s ? `${C.accent}18` : "transparent", color: step === s ? C.accent : C.dim, fontFamily: "DM Sans", fontSize: 13, cursor: "pointer", display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ width: 18, height: 18, background: step === s ? C.accent : C.border, borderRadius: "50%", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 10, color: step === s ? C.bg : C.muted, fontWeight: 700 }}>{i + 1}</span>
            {labels[i]}
          </button>
        ))}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div style={{ width: 32, height: 32, background: `${C.accent}22`, border: `1px solid ${C.accent}44`, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "Syne", fontWeight: 700, color: C.accent, fontSize: 14 }}>
          {user[0]}
        </div>
        <span style={{ fontSize: 13, color: C.muted }}>{user}</span>
      </div>
    </div>
  );
}

// ─── ROOT APP ─────────────────────────────────────────────────────────────────
export default function App() {
  const [screen, setScreen] = useState("login");
  const [user, setUser] = useState("");
  const [profiles, setProfiles] = useState([
    { id: 1, name: "Sarah", age: "35", role: "Adult", conditions: ["Pregnancy"], allergies: [], goals: ["General Wellness"] },
    { id: 2, name: "Mark", age: "38", role: "Adult", conditions: ["Diabetes (Type 2)"], allergies: [], goals: ["Blood Sugar Control", "Weight Loss"] },
    { id: 3, name: "Emma", age: "9", role: "Child", conditions: ["Iron Deficiency"], allergies: [], goals: [] },
    { id: 4, name: "Leo", age: "6", role: "Child", conditions: [], allergies: ["Shellfish"], goals: [] },
  ]);
  const [step, setStep] = useState("profiles");

  const handleLogin = (name) => { setUser(name); setScreen("app"); };

  if (screen === "login") return (
    <>
      <style>{styles}</style>
      <LoginModule onLogin={handleLogin} />
    </>
  );

  return (
    <>
      <style>{styles}</style>
      <Nav user={user} step={step} setStep={setStep} />
      {step === "profiles" && <ProfileModule profiles={profiles} setProfiles={setProfiles} onContinue={() => setStep("engine")} />}
      {step === "engine" && <EngineModule profiles={profiles} onResults={() => setStep("results")} />}
      {step === "results" && <ResultsModule profiles={profiles} onBack={() => setStep("profiles")} />}
    </>
  );
}
