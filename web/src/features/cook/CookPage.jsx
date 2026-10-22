import { useEffect, useMemo, useState } from "react";
import { C } from "../../shared/theme/colors";
import { getHousehold, getRecipe, getSuggestions, RECIPE_FIXTURES } from "../../shared/services/api/client";
import { isAdmin } from "../../shared/services/auth/session";
import { applyReview } from "../review/reviewStore";
import AiPanel from "./AiPanel";
import IngredientsPanel from "./IngredientsPanel";
import NutrientHeadline from "./NutrientHeadline";
import NutritionPanel from "./NutritionPanel";
import StepsPanel from "./StepsPanel";
import { Card, Chip, RuleChip, SourceBadge, SourceLink } from "./bits";
import { pickFocusNutrient } from "./focusNutrient";
import { headlineKicker, pickHeadlineRule, statusOf } from "./ruleStatus";

const RESPONSIVE = `
.cook-grid { display: grid; gap: 18px; grid-template-columns: minmax(0, 320px) minmax(0, 1fr) minmax(0, 330px); align-items: start; }
.cook-hero { display: grid; gap: 18px; grid-template-columns: minmax(0, 1fr) minmax(0, 420px); align-items: stretch; }
.cook-tabs { display: flex; gap: 8px; overflow-x: auto; }
.rule-row > summary::-webkit-details-marker { display: none; }
.rule-row > summary:hover { opacity: 0.85; }
.rule-row .chev { transition: transform 150ms ease; }
.rule-row[open] .chev { transform: rotate(90deg); }
@media (max-width: 1100px) {
  .cook-grid { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
  .cook-grid > :nth-child(3) { grid-column: 1 / -1; }
}
@media (max-width: 760px) {
  .cook-grid, .cook-hero { grid-template-columns: minmax(0, 1fr); }
  .cook-grid > :nth-child(3) { grid-column: auto; }
}
`;

function HeadlineRuleCard({ rule }) {
  if (!rule) return null;
  const status = statusOf(rule);
  return (
    <Card style={{ background: status.bg, border: "none", display: "grid", gap: 8, alignContent: "start" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: status.color, letterSpacing: 0.3 }}>
          {headlineKicker(rule)}
        </span>
        <RuleChip rule={rule} />
      </div>
      <span style={{ fontSize: 16, fontWeight: 700, color: C.navy, lineHeight: 1.3 }}>{rule.name}</span>
      <p style={{ margin: 0, fontSize: 13, color: C.text, lineHeight: 1.6 }}>{rule.why}</p>
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <span style={{ fontSize: 11.5, fontWeight: 700, color: status.color }}>{status.label}</span>
        <SourceLink href={rule.source_url} />
      </div>
    </Card>
  );
}

function SummaryCard({ summary, reviewed }) {
  // Long by design now: covering every rule is worth more than fitting in a
  // fixed box, so the box gives way instead of the content.
  const [open, setOpen] = useState(false);
  if (!summary?.text) return null;
  const long = summary.text.length > 260;
  return (
    <Card style={{ background: C.accentLight, border: "none", display: "grid", gap: 8, alignContent: "start" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: C.accentDark, letterSpacing: 0.3 }}>
          WHAT MATTERS HERE
        </span>
        {(summary.rule_ids || []).map((id) => (
          <Chip key={id} color={C.accent} bg={C.white}>
            {id}
          </Chip>
        ))}
      </div>
      <p
        style={{
          margin: 0,
          fontSize: 13.5,
          color: C.text,
          lineHeight: 1.65,
          ...(long && !open
            ? { display: "-webkit-box", WebkitLineClamp: 4, WebkitBoxOrient: "vertical", overflow: "hidden" }
            : {}),
        }}
      >
        {summary.text}
      </p>
      {long ? (
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          style={{
            justifySelf: "start",
            border: "none",
            background: "transparent",
            padding: 0,
            color: C.accentDark,
            fontSize: 11.5,
            fontWeight: 700,
            cursor: "pointer",
          }}
        >
          {open ? "Show less" : "Read all of it"}
        </button>
      ) : null}
      <span style={{ fontSize: 11, color: C.subtext }}>
        {reviewed
          ? "Approved by a reviewer."
          : summary.source === "local"
            ? "Written from every rule that applies to this recipe."
            : "Taken straight from the rules that apply to this recipe."}
      </span>
    </Card>
  );
}

function ReviewFlag({ rules }) {
  const flagged = rules.filter((r) => r.status === "needs_review");
  if (!flagged.length) return null;
  return (
    <Card style={{ background: C.coralLight, border: "none", display: "grid", gap: 6 }}>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: C.coral }}>FOR THE REVIEWER</span>
        {flagged.map((rule) => (
          <RuleChip key={rule.rule_id} rule={rule} />
        ))}
      </div>
      {flagged.map((rule) => (
        <p key={rule.rule_id} style={{ margin: 0, fontSize: 12.5, color: C.text, lineHeight: 1.6 }}>
          {rule.engine_action}
        </p>
      ))}
      <span style={{ fontSize: 11, color: C.subtext }}>
        Shown here for the demo. In the product this sits in the review console, not in the cook screen.
      </span>
    </Card>
  );
}

export default function CookPage({ recipeId, focusNutrient, onNavigate }) {
  const [recipe, setRecipe] = useState(null);
  const [household, setHousehold] = useState(null);
  const [suggestions, setSuggestions] = useState(null);
  const [loading, setLoading] = useState(true);
  const [servings, setServings] = useState(4);
  const [activeTab, setActiveTab] = useState("Steps");
  const [favorite, setFavorite] = useState(false);
  const [regenerating, setRegenerating] = useState(false);

  useEffect(() => {
    // The page is keyed on recipeId in App, so it remounts with fresh state
    // when the recipe changes. This effect only fetches.
    let cancelled = false;

    Promise.all([getRecipe(recipeId), getHousehold()]).then(([recipeData, householdData]) => {
      if (cancelled) return;
      const reviewed = recipeData ? applyReview(recipeData, null) : { recipe: recipeData };
      setRecipe(reviewed.recipe);
      setHousehold(householdData);
      setServings(recipeData?.servings || 4);
      setLoading(false);
    });

    return () => {
      cancelled = true;
    };
  }, [recipeId]);

  useEffect(() => {
    if (!recipe) return undefined;
    let cancelled = false;
    const ruleIds = (recipe.matched_rules || []).map((r) => r.rule_id);
    getSuggestions(recipe.recipe_id, "maya", ruleIds).then((data) => {
      if (cancelled) return;
      // A reviewer's wording wins over whatever the backend just produced.
      setSuggestions(applyReview(recipe, data).payload);
    });
    return () => {
      cancelled = true;
    };
  }, [recipe]);

  // Testers press this when they want to see what the model writes now; it
  // never changes what anyone else sees, because only reviewed text does that.
  const regenerate = () => {
    if (!recipe || regenerating) return;
    setRegenerating(true);
    const ruleIds = (recipe.matched_rules || []).map((r) => r.rule_id);
    getSuggestions(recipe.recipe_id, "maya", ruleIds, { refresh: true })
      .then(setSuggestions)
      .finally(() => setRegenerating(false));
  };

  const member = household?.members?.[0];
  const focus = useMemo(
    () => pickFocusNutrient(recipe, member, focusNutrient),
    [recipe, member, focusNutrient]
  );

  // The card at the top follows the nutrient the headline is about, so the
  // rule shown is the one that moves what this member actually needs.
  // Only used when there is no summary to show; the summary covers every rule.
  const headlineRule = useMemo(
    () => pickHeadlineRule(recipe?.matched_rules || [], focus?.row?.nutrient),
    [recipe, focus]
  );

  const highlightLineIds = useMemo(() => {
    const ids = new Set();
    (recipe?.matched_rules || []).forEach((rule) => {
      if (rule.applies_to?.type === "ingredients") {
        (rule.applies_to.line_ids || []).forEach((id) => ids.add(id));
      }
    });
    return [...ids];
  }, [recipe]);

  if (loading) {
    return (
      <div style={{ padding: 48, textAlign: "center", color: C.subtext, fontSize: 14 }}>Loading the recipe…</div>
    );
  }

  if (!recipe) {
    return (
      <div style={{ padding: 48, textAlign: "center", display: "grid", gap: 12, justifyItems: "center" }}>
        <p style={{ margin: 0, color: C.text, fontSize: 15 }}>No recipe with the id “{recipeId}”.</p>
        <button
          type="button"
          onClick={() => onNavigate(`#/cook/falafel-001`)}
          style={{
            padding: "10px 16px",
            borderRadius: 10,
            border: "none",
            background: C.accent,
            color: C.white,
            fontSize: 13,
            fontWeight: 700,
            cursor: "pointer",
          }}
        >
          Open the falafel
        </button>
      </div>
    );
  }

  const openRecipes = Object.values(RECIPE_FIXTURES).slice(0, 3);

  return (
    <div style={{ minHeight: "100vh", background: C.bg, paddingBottom: 40 }}>
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
        <button
          type="button"
          onClick={() => onNavigate("#/recommend")}
          title="Back to the recommendations"
          style={{
            display: "grid",
            justifyItems: "start",
            border: "none",
            background: "transparent",
            padding: 0,
            cursor: "pointer",
            textAlign: "left",
          }}
        >
          <span style={{ fontFamily: "Fraunces, serif", fontSize: 18, fontWeight: 700, color: C.accent }}>
            MaziMeal
          </span>
          <span style={{ fontSize: 10.5, color: C.muted }}>← Cook mode</span>
        </button>

        <div className="cook-tabs" style={{ flex: 1 }}>
          {openRecipes.map((item) => {
            const active = item.recipe_id === recipe.recipe_id;
            return (
              <button
                key={item.recipe_id}
                type="button"
                onClick={() => onNavigate(`#/cook/${item.recipe_id}`)}
                style={{
                  padding: "8px 14px",
                  borderRadius: 10,
                  border: `1px solid ${active ? C.accent : C.border}`,
                  background: active ? C.accentLight : C.white,
                  color: active ? C.accentDark : C.subtext,
                  fontSize: 12.5,
                  fontWeight: active ? 700 : 600,
                  cursor: "pointer",
                  whiteSpace: "nowrap",
                }}
              >
                {item.name}
              </button>
            );
          })}
        </div>

        {isAdmin() ? (
          <button
            type="button"
            onClick={() => onNavigate(`#/review`)}
            title="Review the AI text for this recipe"
            style={{
              border: `1px solid ${C.border}`,
              background: C.white,
              color: C.subtext,
              borderRadius: 8,
              padding: "6px 11px",
              fontSize: 11.5,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Review
          </button>
        ) : null}
        <SourceBadge payload={recipe} />
      </header>

      <main style={{ maxWidth: 1320, margin: "0 auto", padding: "18px 20px", display: "grid", gap: 18 }}>
        <div className="cook-hero">
          <Card style={{ display: "grid", gap: 10, alignContent: "start" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <h1
                style={{
                  margin: 0,
                  fontFamily: "Fraunces, serif",
                  fontSize: 28,
                  fontWeight: 600,
                  color: C.navy,
                  lineHeight: 1.15,
                }}
              >
                {recipe.name}
              </h1>
              <Chip color={C.accent} bg={C.accentLight}>
                {recipe.meal}
              </Chip>
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <Chip color={C.subtext} border={C.border}>
                {recipe.time_min} min
              </Chip>
              <Chip color={C.subtext} border={C.border}>
                {recipe.servings} servings
              </Chip>
              {(recipe.tags || []).map((tag) => (
                <Chip key={tag} color={C.subtext} bg={C.skyLight}>
                  {tag.replace(/_/g, " ")}
                </Chip>
              ))}
            </div>
            <NutrientHeadline focus={focus} memberName={member?.name || "this member"} />
          </Card>

          <div style={{ display: "grid", gap: 18, alignContent: "start" }}>
            {suggestions?.summary?.text ? (
              <SummaryCard summary={suggestions.summary} reviewed={suggestions.source === "reviewed"} />
            ) : (
              <HeadlineRuleCard rule={headlineRule} />
            )}
            <ReviewFlag rules={recipe.matched_rules || []} />
          </div>
        </div>

        <div className="cook-grid">
          <div style={{ display: "grid", gap: 18 }}>
            <IngredientsPanel
              recipe={recipe}
              servings={servings}
              onServingsChange={setServings}
              highlightLineIds={highlightLineIds}
            />
            <NutritionPanel recipe={recipe} memberName={member?.name} />
          </div>

          <StepsPanel
            recipe={recipe}
            activeTab={activeTab}
            onTabChange={setActiveTab}
          />

          <AiPanel
            recipeId={recipe.recipe_id}
            memberId={member?.member_id || "maya"}
            payload={suggestions}
            loading={!suggestions}
            onRegenerate={regenerate}
            regenerating={regenerating}
          />
        </div>

        <Card
          style={{
            display: "flex",
            alignItems: "center",
            gap: 16,
            flexWrap: "wrap",
            justifyContent: "space-between",
          }}
        >
          <span style={{ fontSize: 13, color: C.subtext }}>
            {recipe.steps.length} steps · {recipe.time_min} min · {servings} servings
          </span>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <button
              type="button"
              onClick={() => setFavorite((v) => !v)}
              style={{
                padding: "9px 14px",
                borderRadius: 10,
                border: `1px solid ${favorite ? C.coral : C.border}`,
                background: favorite ? C.coralLight : C.white,
                color: favorite ? C.coral : C.subtext,
                fontSize: 12.5,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              {favorite ? "♥ Saved" : "♡ Add to favorites"}
            </button>
          </div>
        </Card>
      </main>
    </div>
  );
}
