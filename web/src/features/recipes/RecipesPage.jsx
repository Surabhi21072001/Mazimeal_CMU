// The seed recipes, as an index you can get into the cook screen from.
//
// Grouped by cuisine because that is why these fifty were chosen - the
// spreadsheet picked them for cultural spread, not for nutrition. The grouping
// is labelled inferred, which is what the spreadsheet itself says about it:
// the association comes from the dish name, nobody verified provenance.
//
// Rule counts come from the list endpoint, which counts them in SQL. They are
// how many rule cards the cook screen will show, not how many apply - whether
// a recipe already satisfies a rule takes the engine, and that is the cook
// screen's job.
import { useEffect, useMemo, useState } from "react";
import { C } from "../../shared/theme/colors";
import { getSeedRecipes } from "../../shared/services/api/client";
import { Card, Chip, SourceBadge } from "../cook/bits";
import { matches } from "./search";

function Stat({ value, label }) {
  return (
    <div style={{ display: "grid", gap: 1 }}>
      <span style={{ fontSize: 13, fontWeight: 700, color: C.text }}>{value}</span>
      <span style={{ fontSize: 9.5, color: C.muted, letterSpacing: 0.3 }}>{label}</span>
    </div>
  );
}

function RecipeCard({ item, onOpen }) {
  const open = () => item.recipe_id && onOpen(`#/cook/${item.recipe_id}`);
  return (
    <Card
      style={{
        padding: 14,
        display: "grid",
        gap: 10,
        alignContent: "start",
        cursor: item.recipe_id ? "pointer" : "default",
        opacity: item.in_database ? 1 : 0.55,
      }}
    >
      <div
        role={item.recipe_id ? "button" : undefined}
        tabIndex={item.recipe_id ? 0 : undefined}
        onClick={open}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            open();
          }
        }}
        style={{ display: "grid", gap: 10 }}
      >
        <div style={{ display: "grid", gap: 4 }}>
          <span style={{ fontSize: 14.5, fontWeight: 700, color: C.text, lineHeight: 1.3 }}>
            {item.name}
          </span>
          <span style={{ fontSize: 11, color: C.muted }}>
            {[item.meal, item.time_min ? `${item.time_min} min` : null, item.servings ? `serves ${item.servings}` : null]
              .filter(Boolean)
              .join(" · ")}
          </span>
        </div>

        {item.in_database ? (
          <div style={{ display: "flex", gap: 16 }}>
            <Stat value={item.ingredient_count} label="INGREDIENTS" />
            <Stat value={item.step_count} label="STEPS" />
            <Stat value={item.nutrient_count} label="NUTRIENTS" />
          </div>
        ) : (
          <span style={{ fontSize: 11, color: C.coral }}>Not in the database</span>
        )}

        <div style={{ display: "flex", gap: 5, flexWrap: "wrap", alignItems: "center" }}>
          {item.rule_count > 0 ? (
            <Chip color={C.accentDark} bg={C.accentLight} border={C.accentLight}>
              {item.rule_count} {item.rule_count === 1 ? "rule" : "rules"}
            </Chip>
          ) : item.in_database ? (
            <Chip color={C.muted} border={C.border} title="No ingredient in this recipe carries a rule's trigger code yet">
              no rules matched
            </Chip>
          ) : null}
          {(item.tags || []).slice(0, 2).map((tag) => (
            <Chip key={tag} color={C.lavender} bg={C.lavLight} border={C.lavLight}>
              {tag.replace(/_/g, " ")}
            </Chip>
          ))}
        </div>
      </div>
    </Card>
  );
}

const ALL = "All";

export default function RecipesPage({ onNavigate }) {
  const [payload, setPayload] = useState(null);
  const [error, setError] = useState(null);
  const [cuisine, setCuisine] = useState(ALL);
  const [meal, setMeal] = useState(ALL);
  const [rulesOnly, setRulesOnly] = useState(false);
  const [query, setQuery] = useState("");

  useEffect(() => {
    let live = true;
    getSeedRecipes()
      .then((data) => live && setPayload(data))
      .catch((err) => live && setError(err.message));
    return () => {
      live = false;
    };
  }, []);

  const results = useMemo(() => payload?.results || [], [payload]);

  const cuisines = useMemo(() => {
    const seen = [];
    results.forEach((item) => {
      const value = item.cuisine || "Uncategorised";
      if (!seen.includes(value)) seen.push(value);
    });
    return seen;
  }, [results]);

  const meals = useMemo(() => {
    const seen = [];
    results.forEach((item) => {
      if (item.meal && !seen.includes(item.meal)) seen.push(item.meal);
    });
    return seen.sort();
  }, [results]);

  const shown = results.filter(
    (item) =>
      (cuisine === ALL || (item.cuisine || "Uncategorised") === cuisine) &&
      (meal === ALL || item.meal === meal) &&
      (!rulesOnly || item.rule_count > 0) &&
      matches(item, query),
  );

  const grouped = useMemo(() => {
    const map = new Map();
    shown.forEach((item) => {
      const key = item.cuisine || "Uncategorised";
      map.set(key, [...(map.get(key) || []), item]);
    });
    return [...map.entries()];
  }, [shown]);

  const withRules = results.filter((item) => item.rule_count > 0).length;

  return (
    <div style={{ minHeight: "100vh", background: C.bg, color: C.text }}>
      <style>{`
        .recipes-wrap { max-width: 1100px; margin: 0 auto; padding: 20px 16px 56px; }
        .recipes-grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); }
        .recipes-filters { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
      `}</style>

      <div className="recipes-wrap">
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            gap: 12,
            flexWrap: "wrap",
            marginBottom: 6,
          }}
        >
          <div style={{ display: "grid", gap: 4 }}>
            <button
              type="button"
              onClick={() => onNavigate("#/recommend")}
              style={{
                background: "none",
                border: "none",
                padding: 0,
                cursor: "pointer",
                fontSize: 10.5,
                color: C.muted,
                textAlign: "left",
              }}
            >
              ← Recommendations
            </button>
            <h1 style={{ margin: 0, fontFamily: "Fraunces, serif", fontSize: 24, color: C.accentDark }}>
              Seed recipes
            </h1>
          </div>
          <SourceBadge payload={payload} />
        </div>

        <p style={{ margin: "0 0 16px", fontSize: 12, color: C.subtext, maxWidth: 620, lineHeight: 1.55 }}>
          {payload ? (
            <>
              {payload.in_database} of {payload.total} in the database, {withRules} with at least one rule matched.{" "}
              {payload.source === "fixture"
                ? "This is the bundled sample set, not the spreadsheet - there is no backend to ask."
                : "Cuisine is inferred from the dish name and is not verified provenance."}
            </>
          ) : error ? (
            `Could not load the list: ${error}`
          ) : (
            "Loading…"
          )}
        </p>

        <div style={{ display: "grid", gap: 8, marginBottom: 20 }}>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search by name or cuisine…"
            aria-label="Search recipes"
            style={{
              boxSizing: "border-box",
              maxWidth: 360,
              padding: "8px 12px",
              borderRadius: 10,
              border: `1px solid ${C.border}`,
              background: C.white,
              color: C.text,
              fontSize: 12.5,
              outline: "none",
            }}
          />
          <div className="recipes-filters">
            {[ALL, ...cuisines].map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setCuisine(value)}
                style={{
                  padding: "5px 11px",
                  borderRadius: 999,
                  border: `1px solid ${cuisine === value ? C.accent : C.border}`,
                  background: cuisine === value ? C.accentLight : C.white,
                  color: cuisine === value ? C.accentDark : C.subtext,
                  fontSize: 11.5,
                  fontWeight: cuisine === value ? 700 : 500,
                  cursor: "pointer",
                }}
              >
                {value}
              </button>
            ))}
          </div>
          <div className="recipes-filters">
            {[ALL, ...meals].map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setMeal(value)}
                style={{
                  padding: "4px 10px",
                  borderRadius: 8,
                  border: `1px solid ${meal === value ? C.gold : C.border}`,
                  background: meal === value ? C.goldLight : C.white,
                  color: meal === value ? C.gold : C.muted,
                  fontSize: 11,
                  fontWeight: meal === value ? 700 : 500,
                  cursor: "pointer",
                }}
              >
                {value}
              </button>
            ))}
            <label style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: C.subtext, marginLeft: 4 }}>
              <input type="checkbox" checked={rulesOnly} onChange={(event) => setRulesOnly(event.target.checked)} />
              with rules only
            </label>
          </div>
        </div>

        {grouped.length === 0 && payload ? (
          <p style={{ fontSize: 12.5, color: C.muted }}>Nothing matches those filters.</p>
        ) : null}

        <div style={{ display: "grid", gap: 26 }}>
          {grouped.map(([group, items]) => (
            <section key={group} style={{ display: "grid", gap: 10 }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                <h2 style={{ margin: 0, fontSize: 13, fontWeight: 700, color: C.accentDark }}>{group}</h2>
                <span style={{ fontSize: 10.5, color: C.dim }}>{items.length}</span>
              </div>
              <div className="recipes-grid">
                {items.map((item) => (
                  <RecipeCard key={item.external_source_id || item.recipe_id} item={item} onOpen={onNavigate} />
                ))}
              </div>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
