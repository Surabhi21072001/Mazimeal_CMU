import { C } from "../../shared/theme/colors";
import { Card, Chip, SectionTitle, SourceTag } from "./bits";

function Row({ item }) {
  const pct = item.pct_of_target;
  const overLimit = item.nutrient === "Sodium" && pct != null && pct > 50;
  return (
    <div style={{ display: "grid", gap: 4 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <span style={{ flex: 1, fontSize: 13.5, color: C.text }}>{item.label}</span>
        <span style={{ fontSize: 14, fontWeight: 700, color: C.navy, fontVariantNumeric: "tabular-nums" }}>
          {item.value}
          <span style={{ fontSize: 11, fontWeight: 600, color: C.muted }}> {item.unit}</span>
        </span>
        <SourceTag source={item.source} confidence={item.confidence} />
      </div>
      {pct != null ? (
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ flex: 1, height: 4, borderRadius: 999, background: C.bg, overflow: "hidden" }}>
            <div
              style={{
                width: `${Math.min(pct, 100)}%`,
                height: "100%",
                borderRadius: 999,
                background: overLimit ? C.coral : item.source === "published" ? C.accent : C.gold,
              }}
            />
          </div>
          <span style={{ fontSize: 11, color: overLimit ? C.coral : C.muted, minWidth: 74, textAlign: "right" }}>
            {pct}% of {item.nutrient === "Sodium" ? "daily limit" : "daily target"}
          </span>
        </div>
      ) : null}
    </div>
  );
}

export default function NutritionPanel({ recipe, memberName = "Maya" }) {
  const rows = recipe.nutrition_per_serving || [];
  const estimated = rows.filter((r) => r.source !== "published").length;

  return (
    <Card>
      <SectionTitle right={<Chip color={C.muted} border={C.border}>per serving</Chip>}>
        Nutrition facts
      </SectionTitle>

      <div style={{ display: "grid", gap: 12 }}>
        {rows.map((item) => (
          <Row key={item.nutrient} item={item} />
        ))}
      </div>

      <p style={{ margin: "16px 0 0", fontSize: 11.5, color: C.muted, lineHeight: 1.65 }}>
        Percentages are against {memberName}&rsquo;s own targets, not a generic adult.{" "}
        {estimated > 0 ? (
          <>
            {estimated} of these {rows.length} values are estimated from ingredient weights rather than measured,
            which is why they are labelled.
          </>
        ) : null}
      </p>
    </Card>
  );
}
