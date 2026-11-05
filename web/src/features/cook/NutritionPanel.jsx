import { C } from "../../shared/theme/colors";
import { Card, Chip, SectionTitle, SourceTag } from "./bits";

// Both candidates for one nutrient, when both exist.
//
// The panel above shows the value the API chose. This line shows what the
// other method produced and how far apart they are, which is the only check
// available on a computed number - so it is on the screen rather than in a
// query someone has to think to run.
function Compare({ item }) {
  const ratio = item.derived_over_published;
  if (item.published_value == null && item.derived_value == null) return null;
  const off = ratio == null ? null : Math.abs(ratio - 1);
  const tone = off == null ? C.muted : off <= 0.15 ? C.accent : off >= 1 ? C.coral : C.gold;
  return (
    <div
      style={{
        display: "flex",
        gap: 10,
        fontSize: 11,
        color: C.muted,
        fontVariantNumeric: "tabular-nums",
      }}
    >
      <span>
        published {item.published_value == null ? "—" : item.published_value}
      </span>
      <span>calculated {item.derived_value == null ? "—" : item.derived_value}</span>
      {ratio != null ? (
        <span style={{ color: tone, fontWeight: 700 }}>{ratio.toFixed(2)}x</span>
      ) : (
        <span>nothing to check it against</span>
      )}
    </div>
  );
}

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
      <Compare item={item} />
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
            which is why they are labelled. The panel below traces how those weights were arrived at.
          </>
        ) : null}
      </p>
    </Card>
  );
}
