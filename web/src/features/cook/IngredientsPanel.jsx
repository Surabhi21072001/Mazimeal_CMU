import { C } from "../../shared/theme/colors";
import { Card, Chip, SectionTitle } from "./bits";

// 1.5 -> "1.5", 2.0 -> "2", 0.3333 -> "0.33"
function num(value) {
  if (value == null) return null;
  const rounded = Math.round(value * 100) / 100;
  return String(rounded);
}

function Stepper({ servings, baseServings, onChange }) {
  const button = (label, next, disabled) => (
    <button
      type="button"
      onClick={() => onChange(next)}
      disabled={disabled}
      aria-label={label === "−" ? "Fewer servings" : "More servings"}
      style={{
        width: 28,
        height: 28,
        borderRadius: 8,
        border: `1px solid ${C.border}`,
        background: disabled ? C.bg : C.white,
        color: disabled ? C.dim : C.navy,
        fontSize: 15,
        lineHeight: 1,
        cursor: disabled ? "default" : "pointer",
      }}
    >
      {label}
    </button>
  );
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      {button("−", servings - 1, servings <= 1)}
      <span style={{ fontSize: 13, fontWeight: 600, color: C.navy, minWidth: 62, textAlign: "center" }}>
        {servings} serving{servings === 1 ? "" : "s"}
      </span>
      {button("+", servings + 1, servings >= 12)}
      {servings !== baseServings ? (
        <button
          type="button"
          onClick={() => onChange(baseServings)}
          style={{
            border: "none",
            background: "transparent",
            color: C.accent,
            fontSize: 11,
            fontWeight: 600,
            cursor: "pointer",
            padding: 0,
          }}
        >
          reset
        </button>
      ) : null}
    </div>
  );
}

export default function IngredientsPanel({ recipe, servings, onServingsChange, highlightLineIds = [] }) {
  const base = recipe.servings || 1;
  const scale = servings / base;
  const hasPlaceholderGrams = recipe.ingredients.some((i) => i.grams_source === "placeholder");

  return (
    <Card>
      <SectionTitle
        right={<Chip color={C.muted} border={C.border}>{recipe.ingredients.length} items</Chip>}
      >
        Ingredients
      </SectionTitle>

      <div style={{ marginBottom: 14 }}>
        <Stepper servings={servings} baseServings={base} onChange={onServingsChange} />
      </div>

      <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 10 }}>
        {recipe.ingredients.map((item) => {
          const required = Boolean(item.required_by_rule);
          const highlighted = highlightLineIds.includes(item.line_id);
          return (
            <li
              key={item.line_id}
              style={{
                display: "flex",
                gap: 10,
                alignItems: "baseline",
                padding: highlighted ? "6px 8px" : 0,
                margin: highlighted ? "-6px -8px" : 0,
                borderRadius: 10,
                background: highlighted ? C.accentLight : "transparent",
                transition: "background 150ms ease",
              }}
            >
              <span
                aria-hidden="true"
                style={{
                  marginTop: 6,
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  flex: "none",
                  background: item.is_optional ? "transparent" : C.accent,
                  border: item.is_optional ? `1.5px solid ${C.dim}` : "none",
                }}
              />
              <span style={{ flex: 1, fontSize: 14, color: C.text, lineHeight: 1.5 }}>
                <strong style={{ fontWeight: 600 }}>
                  {num(item.quantity * scale)} {item.unit}
                </strong>{" "}
                {item.name}
                {item.grams != null ? (
                  <span style={{ color: C.muted }}> · {num(item.grams * scale)} g</span>
                ) : null}
                {item.is_optional ? <span style={{ color: C.muted }}> (optional)</span> : null}
                {item.notes ? (
                  <span style={{ display: "block", color: C.subtext, fontSize: 12.5 }}>{item.notes}</span>
                ) : null}
              </span>
              {required ? (
                <span
                  title={`Required by rule ${item.required_by_rule}`}
                  style={{ color: C.gold, fontSize: 13, flex: "none" }}
                >
                  ★
                </span>
              ) : null}
            </li>
          );
        })}
      </ul>

      {hasPlaceholderGrams ? (
        <p style={{ margin: "14px 0 0", fontSize: 11.5, color: C.muted, lineHeight: 1.6 }}>
          Gram weights are placeholders. The data workstream replaces them with real conversions, and the
          nutrition panel changes with them.
        </p>
      ) : null}
    </Card>
  );
}
