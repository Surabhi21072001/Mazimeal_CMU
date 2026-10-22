import { C } from "../../shared/theme/colors";
import { Chip, SourceLink } from "./bits";
import { evidenceTitle, statusOf } from "./ruleStatus";

// One rule, collapsed to the single thing the cook should notice. The name,
// the mechanism and the source are a click away, because five rules with four
// lines each is a wall nobody reads.
export default function RuleRow({ rule, defaultOpen = false }) {
  const status = statusOf(rule);

  return (
    <details
      className="rule-row"
      open={defaultOpen}
      style={{
        borderRadius: 10,
        background: status.bg,
        padding: "9px 12px",
      }}
    >
      <summary
        style={{
          cursor: "pointer",
          listStyle: "none",
          display: "flex",
          gap: 8,
          alignItems: "baseline",
        }}
      >
        <span
          aria-hidden="true"
          className="chev"
          style={{ color: status.color, fontSize: 9, flex: "none", marginTop: 4, display: "inline-block" }}
        >
          ▶
        </span>
        <span style={{ flex: 1, fontSize: 13, color: C.text, lineHeight: 1.5 }}>
          {rule.engine_action}
        </span>
        <span style={{ fontSize: 10.5, color: status.color, fontWeight: 700, whiteSpace: "nowrap" }}>
          {rule.rule_id}
        </span>
      </summary>

      <div style={{ display: "grid", gap: 6, marginTop: 8, paddingLeft: 18 }}>
        <span style={{ fontSize: 12.5, fontWeight: 700, color: C.navy }}>{rule.name}</span>
        <p style={{ margin: 0, fontSize: 12, color: C.subtext, lineHeight: 1.6 }}>{rule.why}</p>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <Chip color={status.color}>{status.label}</Chip>
          {rule.evidence_tier ? (
            <Chip color={C.muted} border={C.border} title={evidenceTitle(rule.evidence_tier)}>
              evidence {rule.evidence_tier}
            </Chip>
          ) : null}
          <SourceLink href={rule.source_url} />
        </div>
      </div>
    </details>
  );
}
