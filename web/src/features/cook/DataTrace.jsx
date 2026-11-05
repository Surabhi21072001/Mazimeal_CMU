// Where this recipe's numbers came from.
//
// This panel is for us, not for a cook. Every nutrient on the screen is either
// a figure Food.com published or one computed through a chain of guesses, and
// when a number looks wrong the only way to find out why is to see the chain:
//
//   quantity (a bare number from the source, no unit)
//     x measure (a unit our import script chose by rule)
//     = quantity_g
//     x nutrition per 100 g (USDA, per ingredient)
//     / servings
//
// Each step can fail independently, so each gets its own count rather than one
// summary verdict. The Energy row is the calibration: it is the one nutrient
// where both a published and a computed value exist, so its ratio measures the
// accuracy of every nutrient that only exists by computation.
import { C } from "../../shared/theme/colors";
import { Card, Chip, SectionTitle } from "./bits";

// Within 15% is as close as this pipeline gets on the recipes that are right;
// past 2x the quantities are not describing the same dish.
const CLOSE = 0.15;
const WAY_OFF = 2;

function verdict(ratio) {
  if (ratio == null) return { color: C.muted, text: "no published value to check against" };
  const off = Math.abs(ratio - 1);
  if (off <= CLOSE) return { color: C.accent, text: "computed and published agree" };
  if (ratio >= WAY_OFF || ratio <= 1 / WAY_OFF) {
    return { color: C.coral, text: "quantities cannot be describing this dish" };
  }
  return { color: C.gold, text: "computed and published disagree" };
}

function Line({ label, value, note, tone = C.text }) {
  return (
    <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
      <span style={{ flex: 1, fontSize: 12.5, color: C.subtext }}>{label}</span>
      <span
        style={{
          fontSize: 12.5,
          fontWeight: 700,
          color: tone,
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {value}
      </span>
      {note ? (
        <span style={{ fontSize: 11, color: C.muted, minWidth: 128, textAlign: "right" }}>{note}</span>
      ) : null}
    </div>
  );
}

export default function DataTrace({ recipe }) {
  const p = recipe.provenance;
  // The fixtures and the recommender payloads carry no provenance, and a
  // screen running on those should say nothing rather than show zeroes.
  if (!p) return null;

  const v = verdict(p.energy_ratio);
  const ratioText = p.energy_ratio == null ? "—" : `${p.energy_ratio.toFixed(2)}x`;

  return (
    <Card style={{ borderColor: v.color === C.coral ? C.coral : C.border }}>
      <SectionTitle right={<Chip color={C.muted} border={C.border}>debug</Chip>}>
        Where these numbers come from
      </SectionTitle>

      <div style={{ display: "grid", gap: 9 }}>
        <Line
          label="Published by Food.com"
          value={`${p.published_count} nutrients`}
          note="taken as given"
        />
        <Line
          label="Calculated from ingredients"
          value={`${p.derived_count} nutrients`}
          note="through the chain below"
          tone={C.gold}
        />
      </div>

      <div
        style={{
          margin: "16px 0",
          padding: "12px 14px",
          borderRadius: 12,
          background: C.bg,
          display: "grid",
          gap: 9,
        }}
      >
        <Line
          label="Energy, published"
          value={p.energy_published == null ? "—" : `${p.energy_published} kcal`}
        />
        <Line
          label="Energy, calculated"
          value={p.energy_derived == null ? "—" : `${p.energy_derived} kcal`}
          tone={C.gold}
        />
        <Line label="Calculated ÷ published" value={ratioText} tone={v.color} note={v.text} />
        <p style={{ margin: "2px 0 0", fontSize: 11, color: C.muted, lineHeight: 1.6 }}>
          Energy is the only nutrient with both. The{" "}
          {p.derived_count > 0 ? `${p.derived_count} calculated values above` : "calculated values"}{" "}
          carry the same error, and no published figure exists to catch it.
        </p>
      </div>

      <div style={{ display: "grid", gap: 9 }}>
        <Line
          label="Ingredient lines"
          value={p.lines}
          note={`${p.sequence_order_set} with a source order`}
        />
        <Line
          label="Grams from a guessed measure"
          value={`${p.grams_from_measure} of ${p.lines}`}
          note="quantity x tsp/cup/each"
          tone={p.grams_from_measure ? C.gold : C.text}
        />
        {p.grams_assumed ? (
          <Line
            label="Grams from a default weight"
            value={`${p.grams_assumed} of ${p.lines}`}
            note="no measure matched"
            tone={C.gold}
          />
        ) : null}
        {p.grams_missing ? (
          <Line
            label="No gram weight at all"
            value={`${p.grams_missing} of ${p.lines}`}
            note="excluded from every total"
            tone={C.coral}
          />
        ) : null}
        <Line
          label="Quantity possibly on the wrong ingredient"
          value={`${p.lines_misaligned} of ${p.lines}`}
          note={p.lines_misaligned ? "source lists differ in length" : "lists line up"}
          tone={p.lines_misaligned ? C.coral : C.accent}
        />
        {p.lines_without_nutrition ? (
          <Line
            label="Ingredients with no nutrition data"
            value={`${p.lines_without_nutrition} of ${p.lines}`}
            note="contribute nothing"
            tone={C.coral}
          />
        ) : null}
        {p.lines_partial_nutrition ? (
          <Line
            label="Ingredients missing some nutrients"
            value={`${p.lines_partial_nutrition} of ${p.lines}`}
            note="totals understate those"
            tone={C.gold}
          />
        ) : null}
      </div>
    </Card>
  );
}
