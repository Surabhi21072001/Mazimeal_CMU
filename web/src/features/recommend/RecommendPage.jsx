import { useEffect, useMemo, useState } from "react";
import { C } from "../../shared/theme/colors";
import { getHousehold, getRecommendations } from "../../shared/services/api/client";
import { Card, Chip, SourceBadge, SourceTag } from "../cook/bits";
import { listNames, nutrientPhrase, round } from "../cook/focusNutrient";

const MEALS = ["Breakfast", "Lunch", "Dinner", "Snack"];

const RESPONSIVE = `
.rec-cards { display: grid; gap: 16px; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); }
.rec-targets { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); }
.rec-controls { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
`;

function Selector({ label, options, value, onChange, render = (v) => v }) {
  return (
    <div style={{ display: "grid", gap: 6 }}>
      <span style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: 0.6, color: C.muted, textTransform: "uppercase" }}>
        {label}
      </span>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {options.map((option) => {
          const active = option === value;
          return (
            <button
              key={option}
              type="button"
              onClick={() => onChange(option)}
              style={{
                padding: "7px 13px",
                borderRadius: 999,
                border: `1px solid ${active ? C.accent : C.border}`,
                background: active ? C.accent : C.white,
                color: active ? C.white : C.subtext,
                fontSize: 12.5,
                fontWeight: active ? 700 : 600,
                cursor: "pointer",
              }}
            >
              {render(option)}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// What this member still needs today - the reason any of these recipes are here.
function TargetStrip({ member }) {
  if (!member) return null;
  return (
    <div className="rec-targets">
      {member.targets.map((target) => {
        const pct = target.target ? Math.round((100 * target.consumed) / target.target) : 0;
        return (
          <Card key={target.nutrient} style={{ padding: 14, display: "grid", gap: 6 }}>
            <span style={{ fontSize: 12, color: C.subtext }}>{target.label}</span>
            <span style={{ fontSize: 20, fontWeight: 700, color: C.navy, lineHeight: 1 }}>
              {round(target.remaining)}
              <span style={{ fontSize: 11, fontWeight: 600, color: C.muted }}> {target.unit} left</span>
            </span>
            <div style={{ height: 4, borderRadius: 999, background: C.bg, overflow: "hidden" }}>
              <div style={{ width: `${Math.min(pct, 100)}%`, height: "100%", background: C.accent }} />
            </div>
            <span style={{ fontSize: 10.5, color: C.muted }}>
              {round(target.consumed)} of {round(target.target)} {target.unit} so far
              {target.adjusted_reason ? ` · ${target.adjusted_reason}` : ""}
            </span>
          </Card>
        );
      })}
    </div>
  );
}

function RecipeCard({ item, rank, nutrientLabel, onOpen }) {
  const contribution = item.nutrient_contribution;
  return (
    <Card style={{ padding: 0, overflow: "hidden", display: "grid", gridTemplateRows: "auto 1fr" }}>
      {/* No photographs in the data yet; the band keeps the card from looking broken. */}
      <div
        style={{
          height: 92,
          background: `linear-gradient(135deg, ${C.accentLight}, ${C.skyLight})`,
          display: "flex",
          alignItems: "flex-end",
          justifyContent: "space-between",
          padding: 10,
        }}
      >
        <Chip color={C.accentDark} bg={C.white}>
          #{rank} for {nutrientLabel}
        </Chip>
        {item.score != null ? (
          <Chip color={C.subtext} bg={C.white}>
            score {item.score}
          </Chip>
        ) : null}
      </div>

      <div style={{ padding: 16, display: "grid", gap: 10, alignContent: "start" }}>
        <span style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: 0.6, color: C.muted, textTransform: "uppercase" }}>
          {item.meal}
        </span>
        <span style={{ fontSize: 16, fontWeight: 700, color: C.navy, lineHeight: 1.3 }}>{item.name}</span>

        {contribution ? (
          <div style={{ display: "grid", gap: 4 }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
              <span style={{ fontSize: 20, fontWeight: 700, color: C.accent, lineHeight: 1 }}>
                {contribution.pct_of_remaining_need}%
              </span>
              <span style={{ fontSize: 12.5, color: C.text }}>
                of the {nutrientPhrase(nutrientLabel)} still needed
              </span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <span style={{ fontSize: 12, color: C.subtext }}>
                {round(contribution.per_serving)} {contribution.unit} per serving
              </span>
              <SourceTag source={contribution.source} confidence={contribution.confidence} />
            </div>
          </div>
        ) : null}

        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <Chip color={C.subtext} border={C.border}>
            {Math.round(item.kcal_per_serving)} kcal
          </Chip>
          <Chip color={C.subtext} border={C.border}>
            {item.time_min} min
          </Chip>
          {(item.tags || []).slice(0, 2).map((tag) => (
            <Chip key={tag} color={C.subtext} bg={C.skyLight}>
              {tag.replace(/_/g, " ")}
            </Chip>
          ))}
        </div>

        {item.why ? (
          <p style={{ margin: 0, fontSize: 12.5, color: C.subtext, lineHeight: 1.55 }}>{item.why}</p>
        ) : null}

        {(item.matched_rule_ids || []).length ? (
          <div style={{ display: "flex", gap: 5, flexWrap: "wrap", alignItems: "center" }}>
            <span style={{ fontSize: 11, color: C.muted }}>rules</span>
            {item.matched_rule_ids.slice(0, 4).map((id) => (
              <Chip key={id} color={C.accent} bg={C.accentLight}>
                {id}
              </Chip>
            ))}
          </div>
        ) : null}

        <button
          type="button"
          onClick={onOpen}
          style={{
            marginTop: 2,
            padding: "10px 14px",
            borderRadius: 10,
            border: "none",
            background: C.accent,
            color: C.white,
            fontSize: 13,
            fontWeight: 700,
            cursor: "pointer",
          }}
        >
          Cook this
        </button>
      </div>
    </Card>
  );
}

function BlockedList({ blocked }) {
  if (!blocked?.length) return null;
  return (
    <Card style={{ display: "grid", gap: 10 }}>
      <span style={{ fontSize: 13, fontWeight: 700, color: C.navy }}>
        Kept out of this list ({blocked.length})
      </span>
      {blocked.map((item) => (
        <div key={item.recipe_id} style={{ display: "flex", gap: 10, alignItems: "baseline", flexWrap: "wrap" }}>
          <span style={{ fontSize: 13, color: C.subtext, textDecoration: "line-through" }}>{item.name}</span>
          <Chip color={C.coral} bg={C.coralLight}>
            {item.blocked_by?.reason}
          </Chip>
          <span style={{ fontSize: 11.5, color: C.muted }}>{item.blocked_by?.detail}</span>
        </div>
      ))}
      <span style={{ fontSize: 11, color: C.muted, lineHeight: 1.6 }}>
        Allergens and dislikes are applied before anything is scored, so these never reach the household.
      </span>
    </Card>
  );
}

export default function RecommendPage({ onNavigate }) {
  const [household, setHousehold] = useState(null);
  const [payload, setPayload] = useState(null);
  const [memberId, setMemberId] = useState("maya");
  const [meal, setMeal] = useState("Lunch");
  const [nutrient, setNutrient] = useState("Iron");

  useEffect(() => {
    let cancelled = false;
    getHousehold().then((data) => {
      if (!cancelled) setHousehold(data);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    getRecommendations({ memberId, meal, targetNutrient: nutrient }).then((data) => {
      if (!cancelled) setPayload(data);
    });
    return () => {
      cancelled = true;
    };
  }, [memberId, meal, nutrient]);

  const member = useMemo(
    () => household?.members?.find((m) => m.member_id === memberId) || household?.members?.[0],
    [household, memberId]
  );

  const nutrientOptions = useMemo(
    () => (member?.targets || []).filter((t) => t.nutrient !== "Energy").map((t) => t.nutrient),
    [member]
  );

  const nutrientLabel =
    member?.targets?.find((t) => t.nutrient === nutrient)?.label || nutrient.replace(/_/g, " ");

  const results = payload?.results || [];
  const fixture = payload?.source === "fixture";

  return (
    <div style={{ minHeight: "100vh", background: C.bg, paddingBottom: 48 }}>
      <style>{RESPONSIVE}</style>

      <header
        style={{
          background: C.surface,
          borderBottom: `1px solid ${C.border}`,
          padding: "12px 20px",
          display: "flex",
          alignItems: "center",
          gap: 16,
          flexWrap: "wrap",
        }}
      >
        <div style={{ display: "grid", flex: 1 }}>
          <span style={{ fontFamily: "Fraunces, serif", fontSize: 18, fontWeight: 700, color: C.accent }}>
            MaziMeal
          </span>
          <span style={{ fontSize: 10.5, color: C.muted }}>One meal at a time</span>
        </div>
        <SourceBadge payload={payload} />
      </header>

      <main style={{ maxWidth: 1180, margin: "0 auto", padding: "20px", display: "grid", gap: 18 }}>
        <div style={{ display: "grid", gap: 6 }}>
          <span style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: 0.6, color: C.accent, textTransform: "uppercase" }}>
            {meal} · {member?.name}
          </span>
          <h1
            style={{
              margin: 0,
              fontFamily: "Fraunces, serif",
              fontSize: 30,
              fontWeight: 600,
              color: C.navy,
              lineHeight: 1.15,
            }}
          >
            What should {member?.name || "they"} eat for {meal.toLowerCase()}?
          </h1>
          <p style={{ margin: 0, fontSize: 14, color: C.subtext, maxWidth: "62ch", lineHeight: 1.6 }}>
            Ranked by how much of today&rsquo;s {nutrientPhrase(nutrientLabel)} each one closes, after
            allergies and dislikes are removed.
          </p>
        </div>

        <Card>
          <div className="rec-controls">
            <Selector
              label="Member"
              options={(household?.members || []).map((m) => m.member_id)}
              value={memberId}
              onChange={setMemberId}
              render={(id) => household?.members?.find((m) => m.member_id === id)?.name || id}
            />
            <Selector label="Meal" options={MEALS} value={meal} onChange={setMeal} />
            <Selector
              label="Target nutrient"
              options={nutrientOptions}
              value={nutrient}
              onChange={setNutrient}
              render={(id) => member?.targets?.find((t) => t.nutrient === id)?.label || id}
            />
          </div>
        </Card>

        <TargetStrip member={member} />

        {fixture && results.length ? (
          <span style={{ fontSize: 11.5, color: C.muted, lineHeight: 1.6 }}>
            {payload.member_id !== memberId || payload.meal !== meal || payload.target_nutrient !== nutrient ? (
              <>
                The bundled sample only covers{" "}
                {household?.members?.find((m) => m.member_id === payload.member_id)?.name || payload.member_id} ·{" "}
                {payload.meal} · {payload.target_nutrient}, so these cards do not match the selection above.
                They change with it once the recommender is connected.
              </>
            ) : (
              <>Sample results. The recommender replaces them without this page changing.</>
            )}
          </span>
        ) : null}

        <div className="rec-cards">
          {results.map((item, index) => (
            <RecipeCard
              key={item.recipe_id}
              item={item}
              rank={index + 1}
              nutrientLabel={nutrientLabel}
              onOpen={() => onNavigate(`#/cook/${item.recipe_id}?n=${nutrient}`)}
            />
          ))}
        </div>

        {!results.length ? (
          <Card>
            <span style={{ fontSize: 13.5, color: C.subtext }}>
              Nothing to show for {member?.name} at {meal.toLowerCase()} yet.
            </span>
          </Card>
        ) : null}

        <BlockedList blocked={payload?.blocked} />

        {results.length ? (
          <span style={{ fontSize: 11.5, color: C.muted, lineHeight: 1.6 }}>
            Top picks use {listNames(results.slice(0, 2).map((r) => r.name))} as examples; every figure on a
            card says whether it was measured or estimated.
          </span>
        ) : null}
      </main>
    </div>
  );
}
