import { C } from "../../shared/theme/colors";
import { Chip, SourceTag } from "./bits";
import { listNames, nutrientPhrase, round } from "./focusNutrient";

// A fixed four-line template, filled from data, so it reads the same for any
// member and any nutrient:
//
//   25% of today's iron
//   6.0 mg per serving · Maya still needs 23.9 mg
//   Mostly from chickpeas, scallions and chopped tomato
//   Maya's target is 27 mg, not the standard 18 mg — iron deficiency
//
// Lines three and four disappear when the data for them is missing, so a
// recipe with no ingredient breakdown still produces a correct headline.
export default function NutrientHeadline({ focus, memberName }) {
  if (!focus) return null;

  const { row, target } = focus;
  const label = nutrientPhrase(row.label, row.nutrient);
  const pct = Math.round((100 * row.value) / target.remaining);
  const covered = pct >= 100;
  const sources = (row.top_sources || []).slice(0, 3).map((s) => s.name);
  // `baseline` is only shown when it is in the same unit as the target. Some
  // baselines are per kilogram of body weight (protein), so the contract sends
  // null rather than a number that cannot be compared.
  const showsBaseline = target.baseline != null && target.baseline !== target.target;
  const adjusted = showsBaseline || Boolean(target.adjusted_reason);

  return (
    <div style={{ display: "grid", gap: 6 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
        <span style={{ fontSize: 26, fontWeight: 700, color: C.accent, lineHeight: 1 }}>
          {covered ? "All" : `${pct}%`}
        </span>
        <span style={{ fontSize: 15, fontWeight: 600, color: C.navy }}>
          of today&rsquo;s {label}
          {covered ? " covered" : ""}
        </span>
        <SourceTag source={row.source} confidence={row.confidence} />
      </div>

      <span style={{ fontSize: 13, color: C.text, lineHeight: 1.5 }}>
        {round(row.value)} {row.unit} per serving · {memberName} still needs {round(target.remaining)}{" "}
        {target.unit}
      </span>

      {sources.length ? (
        <span style={{ fontSize: 12.5, color: C.subtext, lineHeight: 1.5 }}>
          Mostly from {listNames(sources)}
        </span>
      ) : null}

      {adjusted ? (
        <span style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
          <span style={{ fontSize: 11.5, color: C.muted, lineHeight: 1.5 }}>
            {showsBaseline ? (
              <>
                {memberName}&rsquo;s target is {round(target.target)} {target.unit}, not the standard{" "}
                {round(target.baseline)} {target.unit}
              </>
            ) : (
              <>
                {memberName}&rsquo;s target is {round(target.target)} {target.unit}, set for them
              </>
            )}
          </span>
          {target.adjusted_reason ? (
            <Chip color={C.gold} bg={C.goldLight}>
              {target.adjusted_reason}
            </Chip>
          ) : null}
        </span>
      ) : null}
    </div>
  );
}
