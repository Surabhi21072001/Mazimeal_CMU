import { useEffect, useMemo, useState } from "react";
import { C } from "../../shared/theme/colors";
import { HEADLINE, formatGrams, loadRecipe, logMeal, nutrientLabel, qualityNote, recalcRecipe } from "./recipeData";

const NAVY = "#163F77";
const TILE = {
  Energy:             { bg: "linear-gradient(180deg, #F3F5F7, #E9EDF2)", color: "#324C71" },
  Macro_Protein:      { bg: "linear-gradient(180deg, #5A9C33, #3F7420)", color: C.white },
  Macro_Carbohydrate: { bg: "linear-gradient(180deg, #3B7EDA, #245EA7)", color: C.white },
  Macro_Fat:          { bg: "linear-gradient(180deg, #D9A11E, #B17A09)", color: C.white },
};
const CATEGORY_ORDER = ["Macro", "Fat-soluble", "Water-soluble", "Mineral", "Other"];

function SectionTitle({ children, right }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12 }}>
      <div style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 18, color: NAVY }}>{children}</div>
      {right}
    </div>
  );
}

function Pill({ children, tone = "neutral" }) {
  const tones = {
    neutral: { bg: "#EEF2F7", color: "#4A607A" },
    live:    { bg: C.accentLight, color: C.accentDark },
    warn:    { bg: C.goldLight, color: "#8A6418" },
    changed: { bg: "#FCE7E0", color: "#8E3A2A" },
  };
  const t = tones[tone] || tones.neutral;
  return (
    <span style={{ fontSize: 11, fontWeight: 700, padding: "3px 8px", borderRadius: 999, background: t.bg, color: t.color, whiteSpace: "nowrap" }}>
      {children}
    </span>
  );
}

function fmt(v, unit) {
  const n = Number(v);
  if (!Number.isFinite(n)) return "–";
  const s = n >= 100 ? Math.round(n) : n >= 10 ? n.toFixed(1) : n.toFixed(2);
  return `${String(s).replace(/\.?0+$/, "")} ${unit}`;
}

function Tile({ n }) {
  const t = TILE[n.nutrient] || TILE.Energy;
  const changed = n.original != null && Math.abs(Number(n.per_serving) - Number(n.original)) > 0.05;
  return (
    <div style={{ background: t.bg, color: t.color, padding: "12px 14px", display: "grid", gap: 2 }}>
      <div style={{ fontSize: 12, fontWeight: 700, opacity: 0.9 }}>{nutrientLabel(n.nutrient)}</div>
      <div style={{ fontWeight: 800, fontSize: 18 }}>{fmt(n.per_serving, n.unit)}</div>
      {changed && <div style={{ fontSize: 11, opacity: 0.85 }}>was {fmt(n.original, n.unit)}</div>}
    </div>
  );
}

function NutrientRow({ n }) {
  const changed = n.original != null && Math.abs(Number(n.per_serving) - Number(n.original)) > 0.05;
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr auto auto", gap: 10, alignItems: "baseline", padding: "6px 0", borderBottom: "1px solid #EEF1F5", fontSize: 14 }}>
      <span style={{ color: "#2F4A70" }}>{nutrientLabel(n.nutrient)}</span>
      <span style={{ color: "#60718B", fontSize: 12 }}>
        {changed ? `was ${fmt(n.original, n.unit)}` : n.source === "published" ? "published" : "from ingredients"}
      </span>
      <span style={{ fontWeight: 700, color: NAVY, minWidth: 72, textAlign: "right" }}>{fmt(n.per_serving, n.unit)}</span>
    </div>
  );
}

function IngredientLine({ line, edit, onChange, onRemove, busy }) {
  // what the user typed wins over what the last recalculation returned
  const quantity = edit?.quantity !== undefined ? edit.quantity : line.quantity;
  const measure = edit?.measure !== undefined ? edit.measure : line.measure;
  const measures = line.measures || [];
  const hasMeasure = measure && measures.some((m) => m.measure === measure);
  return (
    <div style={{ display: "grid", gridTemplateColumns: "64px 110px minmax(0, 1fr) 72px 28px", gap: 8, alignItems: "center", opacity: busy ? 0.6 : 1 }}>
      <input
        type="number"
        min="0"
        step="0.25"
        value={quantity ?? ""}
        onChange={(e) => onChange({ quantity: e.target.value === "" ? null : Number(e.target.value) })}
        style={{ width: "100%", padding: "6px 8px", borderRadius: 8, border: `1px solid ${line.changed ? "#D9A11E" : C.border}`, font: "inherit", fontSize: 14 }}
        aria-label={`Amount of ${line.ingredient}`}
      />
      <select
        value={hasMeasure ? measure : measure || ""}
        onChange={(e) => onChange({ measure: e.target.value })}
        style={{ width: "100%", padding: "6px 6px", borderRadius: 8, border: `1px solid ${line.changed ? "#D9A11E" : C.border}`, font: "inherit", fontSize: 14, background: C.white }}
        aria-label={`Measure for ${line.ingredient}`}
      >
        {!hasMeasure && <option value={measure || ""}>{measure || "each"}</option>}
        {measures.map((m) => (
          <option key={m.measure} value={m.measure}>{m.measure}</option>
        ))}
      </select>
      <span style={{ color: "#2F4A70", fontSize: 15, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={line.ingredient}>
        {line.ingredient}
      </span>
      <span style={{ color: "#60718B", fontSize: 12, textAlign: "right" }} title={`grams: ${line.basis}`}>
        {line.grams != null ? formatGrams(line.grams) : "?"}
      </span>
      <button type="button" onClick={onRemove} aria-label={`Remove ${line.ingredient}`} title="Remove"
        style={{ border: "none", background: "transparent", color: "#8A9AB0", fontSize: 18, cursor: "pointer", padding: 0 }}>
        ×
      </button>
    </div>
  );
}

function LogMeal({ recipeId, members, mealType, overrides, live, onLogged }) {
  const [chosen, setChosen] = useState(() => Object.fromEntries((members || []).map((m) => [m.id, true])));
  const [servings, setServings] = useState(1);
  const [state, setState] = useState({ status: "idle" });   // idle | saving | done | error
  const picked = (members || []).filter((m) => chosen[m.id]);
  if (!members?.length) return null;

  const submit = async () => {
    setState({ status: "saving" });
    try {
      const result = await logMeal(recipeId, picked.map((m) => ({ member_id: m.id, servings })), { mealType, overrides });
      setState({ status: "done", result });
      onLogged?.(result);
    } catch (e) {
      setState({ status: "error", message: e.message || String(e) });
    }
  };

  return (
    <div className="card" style={{ padding: 16, border: "1px solid #DBE8BF", background: "linear-gradient(180deg, #F8FDEB, #EEF8D3)" }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 14, alignItems: "center" }}>
        <span style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 16, color: "#4E7C1F" }}>Log this meal</span>
        {members.map((m) => (
          <label key={m.id} style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 14, color: "#2F4A70" }}>
            <input type="checkbox" checked={!!chosen[m.id]} onChange={(e) => setChosen((c) => ({ ...c, [m.id]: e.target.checked }))} />
            {m.name}
          </label>
        ))}
        <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 13, color: "#5D6D83" }}>
          servings each
          <input type="number" min="0.25" step="0.25" value={servings} onChange={(e) => setServings(Math.max(0.25, Number(e.target.value) || 0.25))}
            style={{ width: 60, padding: "4px 6px", borderRadius: 8, border: `1px solid ${C.border}`, font: "inherit", fontSize: 13 }} />
        </label>
        <button type="button" className="btn-primary" disabled={!live || picked.length === 0 || state.status === "saving"}
          onClick={submit} style={{ marginLeft: "auto", minWidth: 120, background: "linear-gradient(180deg, #5AA132, #3E7A1D)", borderColor: "#3E7A1D", opacity: !live || picked.length === 0 ? 0.5 : 1 }}>
          {state.status === "saving" ? "Saving…" : "Log meal"}
        </button>
      </div>
      <div style={{ marginTop: 8, fontSize: 12, color: state.status === "error" ? "#8E3A2A" : "#5B7A2E" }}>
        {!live && "Logging needs the live database."}
        {live && state.status === "idle" && "Adds what each person ate to today's totals, with the nutrition as shown above."}
        {state.status === "done" && (state.result?.already_logged ? "Already logged." : `Logged for ${state.result?.members?.length || 0} ${state.result?.members?.length === 1 ? "person" : "people"}. Today's gaps are updated.`)}
        {state.status === "error" && `Could not log: ${state.message}`}
      </div>
    </div>
  );
}

export default function RecipeDetail({ recipeId, onClose, onCook, members, onLogged }) {
  const [loaded, setLoaded] = useState(null);          // { recipeId, data }
  // edits are keyed by recipe so switching recipes starts clean
  const [edits, setEdits] = useState({ recipeId, overrides: {}, servings: null });
  const [recalc, setRecalc] = useState(null);          // { key, nutrition }
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    let cancelled = false;
    loadRecipe(recipeId).then((d) => { if (!cancelled) setLoaded({ recipeId, data: d }); });
    return () => { cancelled = true; };
  }, [recipeId]);

  const data = loaded?.recipeId === recipeId ? loaded.data : null;
  const loading = !data;
  const overrides = useMemo(() => (edits.recipeId === recipeId ? edits.overrides : {}), [edits, recipeId]);
  const servings = edits.recipeId === recipeId ? edits.servings : null;
  const overrideList = useMemo(
    () => Object.entries(overrides).map(([line_id, o]) => ({ line_id, ...o })),
    [overrides]
  );
  const changed = overrideList.length > 0 || servings != null;
  const editKey = `${recipeId}|${servings ?? ""}|${JSON.stringify(overrideList)}`;

  useEffect(() => {
    if (!data || !changed) return;
    let cancelled = false;
    const t = setTimeout(() => {
      recalcRecipe(recipeId, overrideList, servings)
        .then((n) => { if (!cancelled) setRecalc({ key: editKey, nutrition: n }); })
        .catch((e) => console.warn("recalc failed", e));
    }, 250);
    return () => { cancelled = true; clearTimeout(t); };
  }, [recipeId, data, changed, overrideList, servings, editKey]);

  const nutrition = !changed ? data?.nutrition : recalc?.key === editKey ? recalc.nutrition : recalc?.nutrition || data?.nutrition;
  const busy = changed && recalc?.key !== editKey;

  const setOverrides = (fn) => setEdits((e) => {
    const cur = e.recipeId === recipeId ? e : { recipeId, overrides: {}, servings: null };
    return { ...cur, overrides: fn(cur.overrides) };
  });
  const setServings = (v) => setEdits((e) => {
    const cur = e.recipeId === recipeId ? e : { recipeId, overrides: {}, servings: null };
    return { ...cur, servings: v };
  });

  const recipe = data?.recipe;
  const lines = nutrition?.lines || [];
  const nutrients = nutrition?.nutrients || [];
  const headline = HEADLINE.map((id) => nutrients.find((n) => n.nutrient === id)).filter(Boolean);
  const rest = [...nutrients]
    .filter((n) => !HEADLINE.includes(n.nutrient))
    .sort((a, b) => CATEGORY_ORDER.indexOf(a.category) - CATEGORY_ORDER.indexOf(b.category) || a.nutrient.localeCompare(b.nutrient));
  const note = qualityNote(nutrition);
  const time = (recipe?.prep_time_min || 0) + (recipe?.cook_time_min || 0);

  const edit = (line, patch) =>
    setOverrides((o) => ({ ...o, [line.line_id]: { quantity: line.quantity, measure: line.measure, ...(o[line.line_id] || {}), ...patch } }));
  const remove = (line) => setOverrides((o) => ({ ...o, [line.line_id]: { remove: true } }));
  const reset = () => setEdits({ recipeId, overrides: {}, servings: null });

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(22, 49, 39, 0.35)", display: "grid", placeItems: "center", padding: "84px 24px 24px", zIndex: 230, backdropFilter: "blur(3px)" }}>
      <div onClick={(e) => e.stopPropagation()} className="card"
        style={{ width: "min(980px, calc(100vw - 48px))", maxHeight: "calc(100vh - 64px)", overflowY: "auto", border: "1px solid #D7DFEB", background: "linear-gradient(180deg, rgba(255,255,255,0.98), rgba(246,249,253,0.98))", boxShadow: "0 30px 80px rgba(55, 88, 138, 0.24)" }}>
        <div style={{ padding: "20px 28px 16px", borderBottom: "1px solid #E4E8F0", position: "relative" }}>
          <button type="button" onClick={onClose} aria-label="Close" style={{ position: "absolute", right: 18, top: 14, border: "none", background: "transparent", fontSize: 30, color: "#8A9AB0", cursor: "pointer" }}>×</button>
          {loading || !recipe ? (
            <div style={{ color: "#60718B", padding: "24px 0", textAlign: "center" }}>{loading ? "Loading recipe…" : "Recipe not found."}</div>
          ) : (
            <>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 12, flexWrap: "wrap" }}>
                <h2 style={{ margin: 0, fontFamily: "'Lora'", fontWeight: 700, fontSize: 30, color: "#214A86", textAlign: "center" }}>{recipe.recipe_name}</h2>
                <Pill tone={data.source === "live" ? "live" : "neutral"}>{data.source === "live" ? "Live" : "Sample data"}</Pill>
              </div>
              <div style={{ textAlign: "center", color: "#344D71", marginTop: 10, fontSize: 15 }}>
                {[recipe.meal_category, time ? `${time} min` : null, `${nutrition?.servings ?? recipe.servings} servings`].filter(Boolean).join(" · ")}
              </div>
              {recipe.dietary_tags?.length > 0 && (
                <div style={{ display: "flex", justifyContent: "center", flexWrap: "wrap", gap: 6, marginTop: 10 }}>
                  {recipe.dietary_tags.map((t) => <Pill key={t} tone="live">{String(t).replace(/_/g, " ")}</Pill>)}
                </div>
              )}
            </>
          )}
        </div>

        {recipe && (
          <div style={{ padding: 24, display: "grid", gap: 20 }}>
            {recipe.recipe_description && (
              <div style={{ color: "#4A607A", fontSize: 15, lineHeight: 1.5, textAlign: "center" }}>{recipe.recipe_description}</div>
            )}

            <div className="card" style={{ padding: 18, border: "1px solid #D7DFEB" }}>
              <SectionTitle right={
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  {changed && <Pill tone="changed">recalculated</Pill>}
                  {note && <Pill tone="warn">estimated</Pill>}
                  <span style={{ color: "#5D6D83", fontSize: 13 }}>per serving</span>
                </div>
              }>Nutrition</SectionTitle>
              <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "repeat(4, 1fr)", overflow: "hidden", borderRadius: 10, border: "1px solid #D7DFEB" }}>
                {headline.map((n) => <Tile key={n.nutrient} n={n} />)}
              </div>
              {note && <div style={{ marginTop: 10, fontSize: 13, color: "#8A6418" }}>{note}</div>}
              <button type="button" onClick={() => setShowAll((v) => !v)}
                style={{ marginTop: 12, border: "none", background: "transparent", color: C.accent, fontWeight: 700, cursor: "pointer", padding: 0, font: "inherit", fontSize: 14 }}>
                {showAll ? "Hide full panel" : `Show all ${nutrients.length} nutrients`}
              </button>
              {showAll && (
                <div style={{ marginTop: 8, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", columnGap: 28 }}>
                  {rest.map((n) => <NutrientRow key={n.nutrient} n={n} />)}
                </div>
              )}
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.05fr) minmax(0, 0.95fr)", gap: 24, alignItems: "start" }}>
              <div>
                <SectionTitle right={
                  <div style={{ display: "flex", gap: 10, alignItems: "center", fontSize: 13, color: "#5D6D83" }}>
                    <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
                      servings
                      <input type="number" min="1" step="1" value={servings ?? nutrition?.original_servings ?? recipe.servings ?? 1}
                        onChange={(e) => setServings(e.target.value === "" ? null : Math.max(1, Number(e.target.value)))}
                        style={{ width: 52, padding: "4px 6px", borderRadius: 8, border: `1px solid ${C.border}`, font: "inherit", fontSize: 13 }} />
                    </label>
                    {changed && (
                      <button type="button" onClick={reset} style={{ border: "none", background: "transparent", color: C.accent, fontWeight: 700, cursor: "pointer", padding: 0, font: "inherit", fontSize: 13 }}>
                        reset
                      </button>
                    )}
                  </div>
                }>Ingredients</SectionTitle>
                <div style={{ display: "grid", gap: 8, marginTop: 12 }}>
                  {lines.filter((line) => !overrides[line.line_id]?.remove).map((line) => (
                    <IngredientLine key={line.line_id || line.ingredient_id} line={line} edit={overrides[line.line_id]} busy={busy}
                      onChange={(patch) => edit(line, patch)} onRemove={() => remove(line)} />
                  ))}
                </div>
                <div style={{ marginTop: 10, fontSize: 12, color: "#8A9AB0" }}>
                  Change an amount or measure and the nutrition recalculates. Grams come from USDA household measures.
                </div>
              </div>

              <div>
                <SectionTitle>Instructions</SectionTitle>
                <div style={{ display: "grid", gap: 12, marginTop: 12, color: "#2F2F2F", fontSize: 15, lineHeight: 1.5 }}>
                  {(data.steps || []).length === 0 && <div style={{ color: "#8A9AB0" }}>No steps recorded for this recipe.</div>}
                  {(data.steps || []).map((s) => (
                    <div key={s.step_number} style={{ display: "flex", gap: 10 }}>
                      <strong style={{ color: NAVY, minWidth: 22 }}>{s.step_number}.</strong>
                      <span>{s.instruction}{s.duration_min ? <span style={{ color: "#60718B" }}> ({s.duration_min} min)</span> : null}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <LogMeal recipeId={recipeId} members={members} mealType={recipe.meal_category} overrides={overrideList}
              live={data.source === "live"} onLogged={onLogged} />

            <div style={{ display: "flex", justifyContent: "center", gap: 14, flexWrap: "wrap" }}>
              {onCook && (
                <button className="btn-primary" style={{ minWidth: 180, background: "linear-gradient(180deg, #5AA132, #3E7A1D)", borderColor: "#3E7A1D" }}
                  onClick={() => onCook({ recipe, nutrition, steps: data.steps })}>
                  Cook this
                </button>
              )}
              <button className="btn-ghost" style={{ minWidth: 180 }} onClick={onClose}>Keep browsing</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
