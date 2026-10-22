// Small shared pieces for the cook screen. Everything here is presentational;
// the rule-status table lives in ruleStatus.js so this file exports components only.
import { C } from "../../shared/theme/colors";
import { evidenceTitle, statusOf } from "./ruleStatus";

export function Card({ children, style, ...rest }) {
  return (
    <div
      style={{
        background: C.card,
        border: `1px solid ${C.border}`,
        borderRadius: 16,
        padding: 20,
        ...style,
      }}
      {...rest}
    >
      {children}
    </div>
  );
}

export function SectionTitle({ children, right }) {
  return (
    <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12, marginBottom: 14 }}>
      <h2 style={{ margin: 0, fontFamily: "Fraunces, serif", fontSize: 19, fontWeight: 600, color: C.navy }}>
        {children}
      </h2>
      {right}
    </div>
  );
}

export function Chip({ children, color = C.subtext, bg = "transparent", border, title, style }) {
  return (
    <span
      title={title}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 5,
        padding: "3px 9px",
        borderRadius: 999,
        fontSize: 11,
        fontWeight: 600,
        letterSpacing: 0.2,
        color,
        background: bg,
        border: border ? `1px solid ${border}` : "1px solid transparent",
        whiteSpace: "nowrap",
        ...style,
      }}
    >
      {children}
    </span>
  );
}

// rule id + evidence tier, the motif that repeats across the screen
export function RuleChip({ rule, showStatus = false }) {
  const status = statusOf(rule);
  return (
    <span style={{ display: "inline-flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
      <Chip color={status.color} bg={status.bg} title={rule.name}>
        {rule.rule_id}
      </Chip>
      {rule.evidence_tier ? (
        <Chip color={C.muted} border={C.border} title={evidenceTitle(rule.evidence_tier)}>
          evidence {rule.evidence_tier}
        </Chip>
      ) : null}
      {showStatus ? <Chip color={status.color}>{status.label}</Chip> : null}
    </span>
  );
}

// "measured" vs "estimated" - the distinction the whole project rests on
export function SourceTag({ source, confidence }) {
  const measured = source === "published";
  return (
    <Chip
      color={measured ? C.accent : C.gold}
      bg={measured ? C.accentLight : C.goldLight}
      title={
        measured
          ? "Measured value from the recipe dataset"
          : `Estimated from ingredient weights${confidence ? ` (confidence ${confidence})` : ""}`
      }
    >
      {measured ? "measured" : "estimated"}
    </Chip>
  );
}

export function SourceBadge({ payload, source, transport }) {
  const kind = payload?.source ?? source;
  const how = payload?.transport ?? transport;

  if (how !== "api") {
    return (
      <Chip color={C.gold} bg={C.goldLight} title="Bundled sample data. The backend is not connected.">
        Offline sample
      </Chip>
    );
  }
  if (kind === "fixture") {
    return (
      <Chip
        color={C.sky}
        bg={C.skyLight}
        title="The backend answered, and it is serving sample data until the database is connected."
      >
        Backend · sample data
      </Chip>
    );
  }
  return (
    <Chip color={C.accent} bg={C.accentLight} title="Loaded from the backend's database">
      Live
    </Chip>
  );
}

export function SourceLink({ href }) {
  if (!href) return null;
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      style={{ color: C.accent, fontSize: 11, fontWeight: 600, textDecoration: "none" }}
    >
      source ↗
    </a>
  );
}
