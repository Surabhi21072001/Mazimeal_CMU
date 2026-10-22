import { useState } from "react";
import { C } from "../../shared/theme/colors";
import { askQuestion } from "../../shared/services/api/client";
import { Card, Chip, RuleChip, SectionTitle, SourceLink } from "./bits";

// Where the words came from, said plainly. "from the rules" is not a lesser
// answer than a model wrote it - it is the one that cannot be wrong.
function sourceChip(payload) {
  const model = (payload?.model || "").split("/").pop();
  switch (payload?.source) {
    case "reviewed":
      return { text: payload.reviewed_by ? `reviewed by ${payload.reviewed_by}` : "reviewed", color: C.accent, bg: C.accentLight,
        title: "A person read and approved this text. It wins over anything the model would write now." };
    case "cache":
      return { text: model ? `${model} · cached` : "cached", color: C.accent, bg: C.accentLight,
        title: "Written earlier and kept, so the page does not wait for the model again" };
    case "local":
      return { text: model || "local model", color: C.accent, bg: C.accentLight,
        title: "Rewritten by a model running on this machine" };
    case "template":
      return { text: "from the rules", color: C.subtext, bg: C.bg,
        title: "The rule's own words. No model was called." };
    default:
      return { text: "sample", color: C.gold, bg: C.goldLight,
        title: "Bundled sample text. The backend is not connected." };
  }
}

function Answer({ entry }) {
  const refused = entry.source === "rejected" || entry.source === "unavailable";
  return (
    <div style={{ display: "grid", gap: 6 }}>
      <div
        style={{
          justifySelf: "end",
          maxWidth: "90%",
          background: C.accentLight,
          color: C.accentDark,
          borderRadius: "12px 12px 2px 12px",
          padding: "8px 11px",
          fontSize: 12.5,
          lineHeight: 1.5,
        }}
      >
        {entry.question}
      </div>
      <div
        style={{
          maxWidth: "95%",
          background: refused ? C.coralLight : C.bg,
          borderRadius: "12px 12px 12px 2px",
          padding: "9px 12px",
          fontSize: 12.5,
          color: C.text,
          lineHeight: 1.6,
        }}
      >
        {entry.pending ? "Thinking…" : entry.answer}
        {entry.invented_numbers?.length ? (
          <div style={{ marginTop: 6 }}>
            <Chip color={C.coral} bg={C.white} title="The guard caught a figure the recipe does not have">
              guard stopped this answer
            </Chip>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export default function AiPanel({ recipeId, memberId = "maya", payload, loading, onRegenerate, regenerating }) {
  const suggestions = payload?.suggestions || [];
  const chip = sourceChip(payload);
  const connected = payload?.transport === "api";
  const canRegenerate = Boolean(onRegenerate) && connected;

  const [question, setQuestion] = useState("");
  const [thread, setThread] = useState([]);
  const [asking, setAsking] = useState(false);

  const submit = (event) => {
    event.preventDefault();
    const text = question.trim();
    if (!text || asking) return;

    const entry = { question: text, pending: true };
    setThread((current) => [...current, entry]);
    setQuestion("");
    setAsking(true);

    askQuestion(recipeId, text, memberId)
      .then((result) => {
        setThread((current) =>
          current.map((item) =>
            item === entry ? { ...item, ...result, pending: false } : item
          )
        );
      })
      .finally(() => setAsking(false));
  };

  return (
    <Card>
      <SectionTitle
        right={
          <Chip color={chip.color} bg={chip.bg} title={chip.title}>
            {chip.text}
          </Chip>
        }
      >
        Ask Mazi
      </SectionTitle>

      {loading ? (
        <p style={{ margin: 0, fontSize: 13.5, color: C.subtext }}>Reading the matched rules…</p>
      ) : null}

      {!loading && suggestions.length === 0 ? (
        <p style={{ margin: 0, fontSize: 13.5, color: C.subtext, lineHeight: 1.6 }}>
          Nothing to suggest for this recipe yet. Suggestions appear once rules are linked to it.
        </p>
      ) : null}

      {/* One line each until opened: four suggestions at full length is a wall. */}
      <div style={{ display: "grid", gap: 8 }}>
        {suggestions.map((item) => (
          <details className="rule-row" key={item.rule_id + item.headline} style={{ borderBottom: `1px solid ${C.border}`, paddingBottom: 8 }}>
            <summary style={{ cursor: "pointer", listStyle: "none", display: "flex", gap: 8, alignItems: "baseline" }}>
              <span aria-hidden="true" className="chev" style={{ color: C.accent, fontSize: 9, flex: "none", marginTop: 4, display: "inline-block" }}>
                ▶
              </span>
              <span style={{ flex: 1, fontSize: 13.5, fontWeight: 700, color: C.navy, lineHeight: 1.45 }}>
                {item.headline}
              </span>
            </summary>
            <div style={{ display: "grid", gap: 6, marginTop: 8, paddingLeft: 17 }}>
              <p style={{ margin: 0, fontSize: 12.5, color: C.text, lineHeight: 1.6 }}>{item.body}</p>
              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <RuleChip rule={{ rule_id: item.rule_id, evidence_tier: item.evidence_tier, status: item.status || "not_satisfied" }} />
                <SourceLink href={item.source_url} />
              </div>
            </div>
          </details>
        ))}
      </div>

      {thread.length ? (
        <div style={{ display: "grid", gap: 12, marginTop: 14 }}>
          {thread.map((entry, index) => (
            <Answer key={index} entry={entry} />
          ))}
        </div>
      ) : null}

      <form onSubmit={submit} style={{ marginTop: 14, display: "flex", gap: 8 }}>
        <input
          id="ask-mazi-input"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          disabled={!connected || asking}
          placeholder={connected ? "Ask anything about this recipe…" : "Connect the backend to ask questions"}
          style={{
            flex: 1,
            minWidth: 0,
            padding: "10px 12px",
            borderRadius: 10,
            border: `1px solid ${C.border}`,
            background: connected ? C.white : C.bg,
            color: connected ? C.text : C.muted,
            fontSize: 13,
            fontFamily: "inherit",
          }}
        />
        <button
          type="submit"
          disabled={!connected || asking || !question.trim()}
          style={{
            border: "none",
            borderRadius: 10,
            padding: "10px 14px",
            background: !connected || asking || !question.trim() ? C.border : C.accent,
            color: C.white,
            fontSize: 12.5,
            fontWeight: 700,
            cursor: !connected || asking ? "default" : "pointer",
          }}
        >
          {asking ? "…" : "Ask"}
        </button>
      </form>

      <div style={{ marginTop: 8, display: "flex", gap: 10, alignItems: "baseline", flexWrap: "wrap" }}>
        <p style={{ margin: 0, flex: 1, minWidth: 180, fontSize: 11.5, color: C.muted, lineHeight: 1.6 }}>
          {payload?.disclaimer ||
            "Suggestions are written from matched rules. Nutrition figures come from the database, not from a model."}
        </p>
        {canRegenerate ? (
          <button
            type="button"
            onClick={onRegenerate}
            disabled={regenerating}
            title="Run the model again and replace the text above. For testing; it does not change what other people see until a reviewer approves it."
            style={{
              border: `1px solid ${C.border}`,
              background: C.white,
              color: regenerating ? C.dim : C.subtext,
              borderRadius: 8,
              padding: "5px 10px",
              fontSize: 11.5,
              fontWeight: 600,
              cursor: regenerating ? "default" : "pointer",
              whiteSpace: "nowrap",
            }}
          >
            {regenerating ? "Rewriting…" : "Regenerate"}
          </button>
        ) : null}
      </div>
    </Card>
  );
}
