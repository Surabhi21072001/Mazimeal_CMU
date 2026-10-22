import { useEffect, useMemo, useState } from "react";
import { C } from "../../shared/theme/colors";
import { getRecipe, getSuggestions, RECIPE_FIXTURES } from "../../shared/services/api/client";
import { getSession, isAdmin } from "../../shared/services/auth/session";
import { Card, Chip, SectionTitle } from "../cook/bits";
import { evidenceTitle } from "../cook/ruleStatus";
import {
  addVersion,
  clearAll,
  currentVersion,
  revertToOriginal,
  EDIT_TAGS,
  fingerprint,
  getRecord,
  OUTCOME,
  seed,
  stats,
} from "./reviewStore";

// A rule's status has two different origins, and only one of them is a
// judgement about this recipe:
//   satisfied / not_satisfied  the engine decided whether THIS recipe already
//                              does what the rule asks. A reviewer checks it.
//   advisory / needs_review    the rule itself says so, through the workbook's
//                              automation_status. Nothing about the recipe can
//                              change it, so it is shown, not edited.
const FIXED_BY_RULE = {
  instruction_only: {
    status: "advisory",
    label: "advice only",
    why: "The rule is marked instruction_only in the research database: it changes what a cook is told, never the recipe. Nothing here to satisfy.",
  },
  do_not_automate: {
    status: "needs_review",
    label: "a person decides",
    why: "The rule is marked do_not_automate. It never reaches a cook; it sits here for a reviewer.",
  },
};

const RESPONSIVE = `
.rev-wrap { max-width: 980px; margin: 0 auto; padding: 20px; display: grid; gap: 18px; }
.rev-head { display: flex; gap: 12px; align-items: baseline; flex-wrap: wrap; }
.rev-actions { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
`;

function Button({ children, onClick, tone = "quiet", disabled }) {
  const tones = {
    primary: { bg: C.accent, color: C.white, border: C.accent },
    quiet: { bg: C.white, color: C.subtext, border: C.border },
    danger: { bg: C.white, color: C.coral, border: C.coralLight },
  };
  const t = tones[tone];
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: "9px 14px",
        borderRadius: 10,
        border: `1px solid ${disabled ? C.border : t.border}`,
        background: disabled ? C.bg : t.bg,
        color: disabled ? C.dim : t.color,
        fontSize: 12.5,
        fontWeight: 700,
        cursor: disabled ? "default" : "pointer",
      }}
    >
      {children}
    </button>
  );
}

function StatsBar({ figures }) {
  if (!figures.reviewed) {
    return (
      <span style={{ fontSize: 12, color: C.muted }}>
        Nothing reviewed yet. The first decision starts the count.
      </span>
    );
  }
  return (
    <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "baseline" }}>
      <span style={{ fontSize: 20, fontWeight: 700, color: C.accent }}>
        {figures.unchangedRate}%
      </span>
      <span style={{ fontSize: 12.5, color: C.text }}>
        of judged output left unchanged · {figures.confirmed} confirmed, {figures.edited} edited,{" "}
        {figures.rejected} sent back
        {figures.reverted ? `, ${figures.reverted} reverted` : ""} · {figures.reviewed} versions
      </span>
    </div>
  );
}

// When a reviewer moves a rule onto the ingredients, we have to say which
// ones. Guess from the words the rule itself uses - "crush the garlic" points
// at the garlic line - and let them correct it.
function guessLines(rule, ingredients) {
  const text = `${rule?.engine_action || ""} ${rule?.name || ""} ${rule?.body || ""}`.toLowerCase();
  return ingredients
    .filter((item) => {
      const name = item.name.toLowerCase().replace(/^of\s+/, "");
      const head = name.split(/[ ,]/)[0];
      return head.length > 3 && text.includes(head.slice(0, 6));
    })
    .map((item) => item.line_id);
}

function positionLabel(position, steps) {
  if (!position) return "Not shown on any step";
  if (position.type === "step") {
    const step = steps.find((s) => s.step_number === position.step_number);
    return `Step ${position.step_number}${step ? ` — ${step.instruction.slice(0, 70)}…` : ""}`;
  }
  if (position.type === "ingredients") return `Ingredients: ${(position.line_ids || []).join(", ")}`;
  return "Shown against the whole meal";
}

function SuggestionRow({ item, rule, status, position, steps, ingredients, onChange, onRemove, onStatus, onPosition }) {
  const fixed = FIXED_BY_RULE[rule?.automation_status];
  return (
    <Card style={{ display: "grid", gap: 8, padding: 16 }}>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <Chip color={C.accent} bg={C.accentLight}>
          {item.rule_id}
        </Chip>
        {item.evidence_tier ? (
          <Chip color={C.muted} border={C.border} title={evidenceTitle(item.evidence_tier)}>
            evidence {item.evidence_tier}
          </Chip>
        ) : null}
        {fixed ? (
          <Chip color={C.muted} border={C.border} title={fixed.why}>
            {fixed.label}
          </Chip>
        ) : (
          <span style={{ display: "inline-flex", borderRadius: 999, overflow: "hidden", border: `1px solid ${C.border}` }}>
            {[
              { value: "not_satisfied", label: "Needs a change" },
              { value: "satisfied", label: "Already true here" },
            ].map((option) => {
              const on = status === option.value;
              return (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => onStatus(option.value)}
                  title={
                    option.value === "satisfied"
                      ? "This recipe already does what the rule asks, so the cook is told why it works"
                      : "The recipe does not do it yet, so the cook is told what to change"
                  }
                  style={{
                    padding: "4px 10px",
                    border: "none",
                    background: on ? C.accent : C.white,
                    color: on ? C.white : C.subtext,
                    fontSize: 11,
                    fontWeight: on ? 700 : 600,
                    cursor: "pointer",
                  }}
                >
                  {option.label}
                </button>
              );
            })}
          </span>
        )}
        <span style={{ flex: 1 }} />
        <Button tone="danger" onClick={onRemove}>
          Doesn&rsquo;t apply here
        </Button>
      </div>

      <input
        value={item.headline}
        onChange={(event) => onChange({ ...item, headline: event.target.value })}
        style={{
          width: "100%",
          padding: "8px 10px",
          borderRadius: 8,
          border: `1px solid ${C.border}`,
          fontSize: 13.5,
          fontWeight: 700,
          color: C.navy,
          fontFamily: "inherit",
        }}
      />
      <textarea
        value={item.body}
        rows={3}
        onChange={(event) => onChange({ ...item, body: event.target.value })}
        style={{
          width: "100%",
          padding: "9px 10px",
          borderRadius: 8,
          border: `1px solid ${C.border}`,
          fontSize: 12.5,
          lineHeight: 1.6,
          color: C.text,
          fontFamily: "inherit",
          resize: "vertical",
        }}
      />
      {/* Where this rule shows up for the cook. A rule can be right and still
          be attached to the wrong step, which nothing else on this page would
          catch. */}
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", paddingTop: 4 }}>
        <span style={{ fontSize: 11, color: C.muted, whiteSpace: "nowrap" }}>Shows on</span>
        <select
          value={position?.type === "step" ? String(position.step_number) : position?.type || "meal"}
          onChange={(event) => onPosition(event.target.value)}
          style={{
            fontSize: 11.5,
            padding: "4px 7px",
            borderRadius: 8,
            border: `1px solid ${C.border}`,
            background: C.white,
            color: C.subtext,
            fontFamily: "inherit",
            maxWidth: 260,
          }}
        >
          <option value="meal">the whole meal, no step</option>
          <option value="ingredients">the ingredients it names</option>
          {steps.map((step) => (
            <option key={step.step_number} value={String(step.step_number)}>
              Step {step.step_number}: {step.instruction.slice(0, 48)}
            </option>
          ))}
        </select>
        <span style={{ fontSize: 11, color: C.subtext }}>{positionLabel(position, steps)}</span>
      </div>

      {position?.type === "ingredients" ? (
        <div style={{ display: "flex", gap: 5, flexWrap: "wrap", paddingLeft: 2 }}>
          {ingredients.map((ingredient) => {
            const on = (position.line_ids || []).includes(ingredient.line_id);
            return (
              <button
                key={ingredient.line_id}
                type="button"
                onClick={() =>
                  onPosition("ingredients", {
                    line_ids: on
                      ? (position.line_ids || []).filter((id) => id !== ingredient.line_id)
                      : [...(position.line_ids || []), ingredient.line_id],
                  })
                }
                style={{
                  padding: "3px 8px",
                  borderRadius: 999,
                  border: `1px solid ${on ? C.accent : C.border}`,
                  background: on ? C.accentLight : C.white,
                  color: on ? C.accentDark : C.muted,
                  fontSize: 11,
                  fontWeight: on ? 700 : 600,
                  cursor: "pointer",
                }}
              >
                {ingredient.name}
              </button>
            );
          })}
        </div>
      ) : null}

      {item.source_url ? (
        <a
          href={item.source_url}
          target="_blank"
          rel="noreferrer"
          style={{ fontSize: 11, color: C.accent, textDecoration: "none" }}
        >
          source ↗
        </a>
      ) : null}
    </Card>
  );
}

function TagPicker({ chosen, onToggle }) {
  return (
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
      {EDIT_TAGS.map((tag) => {
        const on = chosen.includes(tag.id);
        return (
          <button
            key={tag.id}
            type="button"
            onClick={() => onToggle(tag.id)}
            style={{
              padding: "5px 10px",
              borderRadius: 999,
              border: `1px solid ${on ? C.accent : C.border}`,
              background: on ? C.accentLight : C.white,
              color: on ? C.accentDark : C.subtext,
              fontSize: 11.5,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            {tag.label}
          </button>
        );
      })}
    </div>
  );
}

function History({ record }) {
  if (!record || record.versions.length < 2) return null;
  return (
    <Card style={{ display: "grid", gap: 10 }}>
      <SectionTitle>History</SectionTitle>
      {[...record.versions].reverse().map((version) => (
        <div key={version.version} style={{ display: "grid", gap: 3, paddingBottom: 8, borderBottom: `1px solid ${C.border}` }}>
          <div style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
            <Chip color={version.version === record.current_version ? C.accent : C.muted} border={C.border}>
              v{version.version}
            </Chip>
            <span style={{ fontSize: 12, color: C.text }}>{version.author}</span>
            <span style={{ fontSize: 11, color: C.muted }}>
              {new Date(version.created_at).toLocaleString()}
            </span>
            {version.review ? (
              <Chip
                color={version.review.outcome === OUTCOME.CONFIRMED ? C.accent : C.gold}
                bg={version.review.outcome === OUTCOME.CONFIRMED ? C.accentLight : C.goldLight}
              >
                {version.review.outcome.replace(/_/g, " ")}
              </Chip>
            ) : null}
          </div>
          {version.review?.tags?.length ? (
            <span style={{ fontSize: 11.5, color: C.subtext }}>
              {version.review.tags.join(", ")}
              {version.review.note ? ` — ${version.review.note}` : ""}
            </span>
          ) : null}
          {version.rules_removed?.length ? (
            <span style={{ fontSize: 11.5, color: C.coral }}>
              removed: {version.rules_removed.join(", ")}
            </span>
          ) : null}
        </div>
      ))}
    </Card>
  );
}

export default function ReviewPage({ onNavigate }) {
  const session = getSession();
  const admin = isAdmin();

  const [recipeId, setRecipeId] = useState("falafel-001");
  const [recipe, setRecipe] = useState(null);
  const [payload, setPayload] = useState(null);
  const [draft, setDraft] = useState(null);
  const [record, setRecord] = useState(null);
  const [tags, setTags] = useState([]);
  const [note, setNote] = useState("");
  const [figures, setFigures] = useState(() => stats());
  const [saved, setSaved] = useState("");

  useEffect(() => {
    if (!admin) return undefined;
    let cancelled = false;

    Promise.all([getRecipe(recipeId), getSuggestions(recipeId, "maya", [])]).then(
      ([recipeData, suggestionData]) => {
        if (cancelled || !recipeData) return;
        const stored = seed(recipeData, suggestionData);
        const version = currentVersion(recipeId) || stored.versions[0];
        setRecipe(recipeData);
        setPayload(suggestionData);
        setRecord(stored);
        setDraft({
          summary: version.summary ? { ...version.summary } : suggestionData?.summary || null,
          position_overrides: { ...(version.position_overrides || {}) },
          suggestions: version.suggestions.map((s) => ({ ...s })),
          rules_removed: [...(version.rules_removed || [])],
          status_overrides: { ...(version.status_overrides || {}) },
          not_optimizable: Boolean(version.not_optimizable),
        });
        setTags([]);
        setNote("");
        setSaved("");
      }
    );

    return () => {
      cancelled = true;
    };
  }, [recipeId, admin]);

  const original = useMemo(() => record?.versions?.[0]?.suggestions || [], [record]);

  // Structural edits describe themselves: removing a rule, changing a status
  // or moving a tip are all visible in the diff. Only a text change needs a
  // person to say why, and that one is optional - a reviewer who has to
  // classify every edit reviews fewer recipes.
  const inferredTags = useMemo(() => {
    if (!draft || !record) return [];
    const base = currentVersion(recipeId) || record.versions[0];
    const found = [];
    if (JSON.stringify(draft.rules_removed) !== JSON.stringify(base.rules_removed || []))
      found.push("rule_not_applicable");
    if (JSON.stringify(draft.status_overrides) !== JSON.stringify(base.status_overrides || {}))
      found.push("wrong_status");
    if (JSON.stringify(draft.position_overrides) !== JSON.stringify(base.position_overrides || {}))
      found.push("wrong_position");
    return found;
  }, [draft, record, recipeId]);

  const changed = useMemo(() => {
    if (!draft || !record) return false;
    const base = currentVersion(recipeId) || record.versions[0];
    return (
      JSON.stringify(draft.summary) !== JSON.stringify(base.summary ?? null) ||
      JSON.stringify(draft.suggestions) !== JSON.stringify(base.suggestions) ||
      JSON.stringify(draft.rules_removed) !== JSON.stringify(base.rules_removed || []) ||
      JSON.stringify(draft.status_overrides) !== JSON.stringify(base.status_overrides || {}) ||
      JSON.stringify(draft.position_overrides) !== JSON.stringify(base.position_overrides || {}) ||
      draft.not_optimizable !== Boolean(base.not_optimizable)
    );
  }, [draft, record, recipeId]);

  const commit = (outcome) => {
    const updated = addVersion(recipeId, {
      summary: draft.summary,
      suggestions: draft.suggestions,
      rulesRemoved: draft.rules_removed,
      statusOverrides: draft.status_overrides,
      positionOverrides: draft.position_overrides,
      notOptimizable: draft.not_optimizable,
      outcome,
      tags: [...new Set([...inferredTags, ...tags])],
      note,
      session,
      fingerprintValue: fingerprint(recipe, payload),
    });
    setRecord(updated ? { ...updated } : getRecord(recipeId));
    setFigures(stats());
    setTags([]);
    setNote("");
    setSaved(
      outcome === OUTCOME.CONFIRMED
        ? "Marked as correct with no changes."
        : outcome === OUTCOME.REJECTED
          ? "Sent back. Nothing is published for this recipe."
          : "Saved as a new version."
    );
  };

  if (!admin) {
    return (
      <div style={{ minHeight: "100vh", background: C.bg, display: "grid", placeItems: "center" }}>
        <Card style={{ maxWidth: 420, textAlign: "center" }}>
          <p style={{ margin: 0, fontSize: 14, color: C.text }}>
            This screen is for reviewers. Ask an admin for access.
          </p>
        </Card>
      </div>
    );
  }

  const withRules = Object.values(RECIPE_FIXTURES);

  return (
    <div style={{ minHeight: "100vh", background: C.bg, paddingBottom: 48 }}>
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
          style={{ border: "none", background: "transparent", padding: 0, cursor: "pointer", display: "grid", justifyItems: "start" }}
        >
          <span style={{ fontFamily: "Fraunces, serif", fontSize: 18, fontWeight: 700, color: C.accent }}>
            MaziMeal
          </span>
          <span style={{ fontSize: 10.5, color: C.muted }}>← Review</span>
        </button>
        <span style={{ flex: 1 }} />
        <Chip color={C.gold} bg={C.goldLight} title="Login is not built yet; everyone is a reviewer for now">
          {session.name} · reviewer
        </Chip>
      </header>

      <main className="rev-wrap">
        <Card style={{ display: "grid", gap: 10 }}>
          <SectionTitle
            right={
              <Button
                tone="danger"
                onClick={() => {
                  if (!window.confirm("Delete every review decision in this browser, for every recipe? This is for clearing test data; to undo one recipe use \"Back to the model's version\" instead.")) return;
                  clearAll();
                  setFigures(stats());
                  window.location.reload();
                }}
              >
                Delete all test data
              </Button>
            }
          >
            How often the model is left alone
          </SectionTitle>
          <StatsBar figures={figures} />
          {Object.keys(figures.tagCounts).length ? (
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {Object.entries(figures.tagCounts).map(([tag, count]) => (
                <Chip key={tag} color={C.subtext} border={C.border}>
                  {EDIT_TAGS.find((t) => t.id === tag)?.label || tag}: {count}
                </Chip>
              ))}
            </div>
          ) : null}
        </Card>

        <div className="rev-head">
          <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.6, color: C.muted, textTransform: "uppercase" }}>
            Recipe
          </span>
          <select
            value={recipeId}
            onChange={(event) => setRecipeId(event.target.value)}
            style={{
              padding: "7px 10px",
              borderRadius: 8,
              border: `1px solid ${C.border}`,
              background: C.white,
              fontSize: 13,
              color: C.navy,
              fontFamily: "inherit",
            }}
          >
            {withRules.map((item) => (
              <option key={item.recipe_id} value={item.recipe_id}>
                {item.name}
              </option>
            ))}
          </select>
          {record ? (
            <Chip color={C.subtext} border={C.border}>
              version {record.current_version} of {record.versions.length}
            </Chip>
          ) : null}
          <span style={{ flex: 1 }} />
          <Button onClick={() => onNavigate(`#/cook/${recipeId}`)}>See the cook screen</Button>
        </div>

        {!draft ? (
          <Card>
            <span style={{ fontSize: 13.5, color: C.subtext }}>Loading…</span>
          </Card>
        ) : null}

        {draft && draft.suggestions.length === 0 ? (
          <Card>
            <span style={{ fontSize: 13.5, color: C.subtext }}>
              No rules matched this recipe, so there is nothing to review yet.
            </span>
          </Card>
        ) : null}

        {draft?.summary ? (
          <Card style={{ display: "grid", gap: 8, background: C.accentLight, border: "none" }}>
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <span style={{ fontSize: 11.5, fontWeight: 700, color: C.accentDark, letterSpacing: 0.4 }}>
                SUMMARY ON THE RECIPE CARD
              </span>
              {(draft.summary.rule_ids || []).map((id) => (
                <Chip key={id} color={C.accent} bg={C.white}>
                  {id}
                </Chip>
              ))}
              {draft.summary.dropped_rules?.length ? (
                <Chip color={C.coral} bg={C.white} title="The model left these out, so the plain version is being used">
                  model dropped {draft.summary.dropped_rules.join(", ")}
                </Chip>
              ) : null}
            </div>
            <textarea
              value={draft.summary.text}
              rows={3}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  summary: { ...current.summary, text: event.target.value },
                }))
              }
              style={{
                width: "100%",
                padding: "9px 10px",
                borderRadius: 8,
                border: `1px solid ${C.border}`,
                fontSize: 13,
                lineHeight: 1.6,
                color: C.text,
                fontFamily: "inherit",
                resize: "vertical",
              }}
            />
          </Card>
        ) : null}

        {draft?.suggestions.map((item, index) => (
          <SuggestionRow
            key={item.rule_id}
            item={item}
            rule={(recipe?.matched_rules || []).find((r) => r.rule_id === item.rule_id)}
            status={draft.status_overrides[item.rule_id] || item.status || "not_satisfied"}
            position={
              draft.position_overrides[item.rule_id] ||
              (recipe?.matched_rules || []).find((r) => r.rule_id === item.rule_id)?.applies_to
            }
            steps={recipe?.steps || []}
            ingredients={recipe?.ingredients || []}
            onChange={(next) =>
              setDraft((current) => ({
                ...current,
                suggestions: current.suggestions.map((s, i) => (i === index ? next : s)),
              }))
            }
            onStatus={(value) =>
              setDraft((current) => ({
                ...current,
                status_overrides: { ...current.status_overrides, [item.rule_id]: value },
              }))
            }
            onPosition={(value, extra) =>
              setDraft((current) => {
                const matched = (recipe?.matched_rules || []).find((r) => r.rule_id === item.rule_id);
                const existing = current.position_overrides[item.rule_id] || matched?.applies_to;
                let next;
                if (value === "meal") {
                  next = { type: "meal" };
                } else if (value === "ingredients") {
                  const lines =
                    extra?.line_ids ??
                    (existing?.type === "ingredients" && existing.line_ids?.length
                      ? existing.line_ids
                      : guessLines({ ...matched, ...item }, recipe?.ingredients || []));
                  next = { type: "ingredients", line_ids: lines };
                } else {
                  next = { type: "step", step_number: Number(value) };
                }
                return {
                  ...current,
                  position_overrides: { ...current.position_overrides, [item.rule_id]: next },
                };
              })
            }
            onRemove={() =>
              setDraft((current) => ({
                ...current,
                suggestions: current.suggestions.filter((_, i) => i !== index),
                rules_removed: [...current.rules_removed, item.rule_id],
              }))
            }
          />
        ))}

        {draft ? (
          <Card style={{ display: "grid", gap: 6, borderColor: draft.not_optimizable ? C.coral : C.border }}>
            <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.5, color: C.muted, textTransform: "uppercase" }}>
              About the recipe itself
            </span>
            <label style={{ display: "flex", gap: 9, alignItems: "flex-start", fontSize: 13, color: C.text }}>
              <input
                type="checkbox"
                checked={draft.not_optimizable}
                style={{ marginTop: 3 }}
                onChange={(event) =>
                  setDraft((current) => ({ ...current, not_optimizable: event.target.checked }))
                }
              />
              <span>
                This dish cannot be improved safely
                <span style={{ display: "block", fontSize: 11.5, color: C.subtext, lineHeight: 1.6, marginTop: 2 }}>
                  Tick this when the recipe is what it is - a cheese-heavy dish will never be a good
                  source of iron, and pretending otherwise is worse than saying nothing. Cooks see no
                  suggestions for it, and it stops coming back to this queue.
                </span>
              </span>
            </label>
          </Card>
        ) : null}

        {draft?.rules_removed.length ? (
          <Card style={{ display: "grid", gap: 8, background: C.coralLight, border: "none" }}>
            <span style={{ fontSize: 12.5, fontWeight: 700, color: C.coral }}>
              Marked as not applying to this recipe
            </span>
            {draft.rules_removed.map((ruleId) => (
              <div key={ruleId} style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <Chip color={C.coral} bg={C.white}>
                  {ruleId}
                </Chip>
                <Button
                  onClick={() =>
                    setDraft((current) => {
                      const restored = original.find((s) => s.rule_id === ruleId);
                      return {
                        ...current,
                        rules_removed: current.rules_removed.filter((id) => id !== ruleId),
                        suggestions: restored ? [...current.suggestions, { ...restored }] : current.suggestions,
                      };
                    })
                  }
                >
                  Put it back
                </Button>
              </div>
            ))}
            <span style={{ fontSize: 11, color: C.subtext }}>
              This only affects this recipe. The rule itself stays in the research database.
            </span>
          </Card>
        ) : null}

        {draft ? (
          <Card style={{ display: "grid", gap: 12 }}>
            {changed ? (
              <>
                <div style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
                  <span style={{ fontSize: 12, color: C.subtext }}>
                    Why, if you want to say — optional
                  </span>
                  {inferredTags.map((tag) => (
                    <Chip key={tag} color={C.accent} bg={C.accentLight} title="Recorded automatically from what you changed">
                      {EDIT_TAGS.find((t) => t.id === tag)?.label || tag}
                    </Chip>
                  ))}
                </div>
                <TagPicker
                  chosen={tags}
                  onToggle={(tag) =>
                    setTags((current) =>
                      current.includes(tag) ? current.filter((t) => t !== tag) : [...current, tag]
                    )
                  }
                />
                <input
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  placeholder="Optional note for whoever tunes the rules or the prompt"
                  style={{
                    padding: "8px 10px",
                    borderRadius: 8,
                    border: `1px solid ${C.border}`,
                    fontSize: 12.5,
                    fontFamily: "inherit",
                  }}
                />
              </>
            ) : null}

            <div className="rev-actions">
              <Button tone="primary" onClick={() => commit(OUTCOME.CONFIRMED)} disabled={changed}>
                ✓ All good, nothing to change
              </Button>
              <Button onClick={() => commit(OUTCOME.EDITED)} disabled={!changed}>
                Save edits
              </Button>
              <Button tone="danger" onClick={() => commit(OUTCOME.REJECTED)}>
                Send back
              </Button>
              <Button
                onClick={() => {
                  const updated = revertToOriginal(recipeId, session);
                  if (!updated) return;
                  const version = currentVersion(recipeId);
                  setRecord({ ...updated });
                  setDraft({
                    summary: version.summary ? { ...version.summary } : null,
                    suggestions: version.suggestions.map((item) => ({ ...item })),
                    rules_removed: [...(version.rules_removed || [])],
                    status_overrides: { ...(version.status_overrides || {}) },
                    position_overrides: { ...(version.position_overrides || {}) },
                    not_optimizable: Boolean(version.not_optimizable),
                  });
                  setTags([]);
                  setNote("");
                  setFigures(stats());
                  setSaved("Back to the model's version. The edits stay in the history.");
                }}
                disabled={!record || record.versions.length < 2}
                title="Undo every edit on this recipe by writing a new version that matches the model's original. Nothing is deleted."
              >
                Back to the model&rsquo;s version
              </Button>
              {saved ? <span style={{ fontSize: 12, color: C.accent }}>{saved}</span> : null}
            </div>

            <span style={{ fontSize: 11, color: C.muted, lineHeight: 1.6 }}>
              Stored in this browser, so Chrome and the editor&rsquo;s preview each have their own.
              Saved to this browser for now. The shape is what moves to the database later, so the
              decisions you make here are not throwaway.
            </span>
          </Card>
        ) : null}

        <History record={record} />
      </main>
    </div>
  );
}
