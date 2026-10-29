import { useMemo } from "react";
import { C } from "../../shared/theme/colors";
import { Card, Chip } from "./bits";
import RuleRow from "./RuleRow";

const TABS = ["Steps", "Variations & Enhancements", "Notes"];

// Bold the ingredients a step actually uses, the way the mockup marks
// turmeric and black pepper inside step 2.
function highlight(text, names) {
  if (!names.length) return text;
  const escaped = names
    .map((n) => n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .sort((a, b) => b.length - a.length);
  const pattern = new RegExp(`(${escaped.join("|")})`, "gi");
  return text.split(pattern).map((part, index) =>
    names.some((n) => n.toLowerCase() === part.toLowerCase()) ? (
      <strong key={index} style={{ color: C.accent, fontWeight: 700 }}>
        {part}
      </strong>
    ) : (
      <span key={index}>{part}</span>
    )
  );
}

function Step({ step, ingredientNames, rules }) {
  const names = (step.ingredient_line_ids || [])
    .map((id) => ingredientNames.get(id))
    .filter(Boolean);

  return (
    <li style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
      <span
        aria-hidden="true"
        style={{
          flex: "none",
          width: 28,
          height: 28,
          borderRadius: "50%",
          background: C.accentLight,
          color: C.accentDark,
          fontSize: 12.5,
          fontWeight: 700,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          marginTop: 2,
        }}
      >
        {step.step_number}
      </span>

      <div style={{ flex: 1 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
          {step.title ? (
            <span style={{ fontSize: 14.5, fontWeight: 700, color: C.navy }}>{step.title}</span>
          ) : null}
          {step.duration_min ? (
            <Chip color={C.muted} border={C.border}>
              {step.duration_min} min
            </Chip>
          ) : null}
          {step.is_key_step ? (
            <Chip color={C.gold} bg={C.goldLight}>
              ★ Key step
            </Chip>
          ) : null}
        </div>
        <p style={{ margin: "4px 0 0", fontSize: 13.5, color: C.text, lineHeight: 1.6 }}>
          {highlight(step.instruction, names)}
        </p>
        {rules.length ? (
          <div style={{ display: "grid", gap: 8, marginTop: 10 }}>
            {rules.map((rule) => (
              <RuleRow key={rule.rule_id} rule={rule} />
            ))}
          </div>
        ) : null}
      </div>
    </li>
  );
}

function Enhancements({ rules }) {
  if (!rules.length) {
    return (
      <p style={{ margin: 0, fontSize: 13.5, color: C.subtext, lineHeight: 1.6 }}>
        No rules matched this recipe yet. They arrive when the rules workstream links recipes to the
        research database.
      </p>
    );
  }
  return (
    <div style={{ display: "grid", gap: 8 }}>
      {rules.map((rule) => (
        <RuleRow key={rule.rule_id} rule={rule} />
      ))}
    </div>
  );
}

export default function StepsPanel({ recipe, activeTab, onTabChange }) {
  const ingredientNames = useMemo(() => {
    const map = new Map();
    (recipe.ingredients || []).forEach((item) => {
      map.set(item.line_id, item.name.replace(/^of\s+/i, ""));
    });
    return map;
  }, [recipe]);

  const rulesByStep = useMemo(() => {
    const map = new Map();
    (recipe.matched_rules || []).forEach((rule) => {
      // step_numbers is what the engine reports; step_number is the single
      // target the first fixtures were written with. A rule can mark a step
      // and an ingredient line at once, so neither depends on `type`.
      const numbers = rule.applies_to?.step_numbers
        || (rule.applies_to?.step_number ? [rule.applies_to.step_number] : []);
      numbers.forEach((n) => {
        map.set(n, [...(map.get(n) || []), rule]);
      });
    });
    return map;
  }, [recipe]);

  const enhancements = (recipe.matched_rules || []).filter((rule) => rule.status !== "satisfied");

  return (
    <Card style={{ padding: 0, overflow: "hidden" }}>
      <div style={{ display: "flex", borderBottom: `1px solid ${C.border}`, overflowX: "auto" }}>
        {TABS.map((tab) => {
          const active = tab === activeTab;
          return (
            <button
              key={tab}
              type="button"
              onClick={() => onTabChange(tab)}
              style={{
                padding: "14px 18px",
                border: "none",
                background: "transparent",
                color: active ? C.accent : C.subtext,
                fontSize: 13.5,
                fontWeight: active ? 700 : 600,
                cursor: "pointer",
                borderBottom: active ? `2px solid ${C.accent}` : "2px solid transparent",
                whiteSpace: "nowrap",
              }}
            >
              {tab}
            </button>
          );
        })}
      </div>

      <div style={{ padding: 20 }}>
        {activeTab === "Steps" ? (
          <>
            <div style={{ marginBottom: 14 }}>
              <span style={{ fontSize: 12, color: C.muted }}>{recipe.steps.length} steps</span>
            </div>
            <ol style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 18 }}>
              {recipe.steps.map((step) => (
                <Step
                  key={step.step_number}
                  step={step}
                  ingredientNames={ingredientNames}
                  rules={rulesByStep.get(step.step_number) || []}
                />
              ))}
            </ol>
          </>
        ) : null}

        {activeTab === "Variations & Enhancements" ? <Enhancements rules={enhancements} /> : null}

        {activeTab === "Notes" ? (
          <p style={{ margin: 0, fontSize: 13.5, color: C.subtext, lineHeight: 1.6 }}>
            Notes are per household and are saved on the device for now. They move to the backend when
            accounts exist.
          </p>
        ) : null}
      </div>
    </Card>
  );
}
