// Proposing a rule that does not exist yet.
//
// It goes through the same queue as a change to an existing one, and for the
// same reason: a new rule is a claim about food chemistry, and the person who
// writes it is usually not the person who should decide whether the engine
// acts on it. Nothing is written to business_rules until a reviewer approves.
//
// Two fields are required because the database requires them, and one more
// because the engine does:
//
//   rule_id        the primary key, so it cannot be generated later
//   rule_name      NOT NULL
//   rule_category  a CHECK constraint, one of four values
//
// trigger_code is not required, but a rule without one can never fire - no
// ingredient can carry it - so the form says so rather than letting someone
// write a rule that is dead on arrival and find out from a dashboard later.
import { useMemo, useState } from "react";
import { C } from "../../shared/theme/colors";
import { submitRuleRequest } from "../../shared/services/api/admin";
import { Button, Card, Chip, Field, Notice, Select, TextInput } from "./bits";
import { FIELDS, RULE_CATEGORIES } from "./format";

// The ones worth asking for up front. The rest can be filled in by an edit
// once the rule exists; a form with twenty inputs gets abandoned, and a rule
// with a name, a category and a trigger is already reviewable.
const CORE = ["rule_name", "rule_category", "trigger_code", "target_code", "action_code"];

const REFUSALS = {
  rule_exists: "A rule with that id already exists. Edit it from the Rules tab instead.",
  rule_id_required: "Give the rule an id.",
  missing_fields: "A name and a category are required.",
  bad_rule_category: "That is not one of the four categories.",
  bad_automation_status: "That is not one of the four automation statuses.",
  bad_evidence_tier: "Evidence tier is A, B or C.",
};

function message(err) {
  const detail = err?.detail;
  if (detail?.error === "missing_fields" && detail.fields?.length) {
    return `Still needed: ${detail.fields.join(", ")}.`;
  }
  if (detail?.error === "not_editable" && detail.editable) {
    return `${detail.field || "A field"} cannot be set. Allowed: ${detail.editable.join(", ")}.`;
  }
  return REFUSALS[detail?.error] || detail?.hint || err.message;
}

export default function NewRuleForm({ canPropose, onSubmitted }) {
  const [ruleId, setRuleId] = useState("");
  const [draft, setDraft] = useState({});
  const [note, setNote] = useState("");
  const [showAll, setShowAll] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(null);

  const shown = useMemo(
    () => (showAll ? FIELDS : FIELDS.filter((field) => CORE.includes(field.key))),
    [showAll],
  );

  const set = (key, value) => setDraft((old) => ({ ...old, [key]: value }));

  const proposed = useMemo(() => {
    const out = {};
    for (const [key, value] of Object.entries(draft)) {
      const trimmed = typeof value === "string" ? value.trim() : value;
      if (trimmed !== "" && trimmed != null) out[key] = trimmed;
    }
    return out;
  }, [draft]);

  const ready = ruleId.trim() && proposed.rule_name && proposed.rule_category;

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      const result = await submitRuleRequest({
        kind: "create",
        ruleId: ruleId.trim(),
        proposed,
        note: note.trim() || null,
      });
      setDone(result);
      setRuleId("");
      setDraft({});
      setNote("");
      setShowAll(false);
      onSubmitted?.();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  };

  if (!canPropose) {
    return (
      <Notice>
        Sign in to propose a new rule. It will wait in the queue until a reviewer approves it, the
        same as a change to an existing rule.
      </Notice>
    );
  }

  return (
    <Card style={{ display: "grid", gap: 14, maxWidth: 760 }}>
      <div>
        <h2
          style={{
            margin: 0,
            fontFamily: "Fraunces, serif",
            fontSize: 17,
            fontWeight: 600,
            color: C.navy,
          }}
        >
          Propose a new rule
        </h2>
        <p style={{ margin: "6px 0 0", fontSize: 12, color: C.subtext, lineHeight: 1.65 }}>
          This writes nothing to <code>business_rules</code>. It joins the same queue as an edit, and
          a reviewer decides. Only an id, a name and a category are needed to make it reviewable —
          the rest can be filled in afterwards.
        </p>
      </div>

      {done ? (
        <Notice kind="ok">
          Submitted as <strong>{done.rule_id}</strong>. It is in Pending changes now, waiting for a
          reviewer.
        </Notice>
      ) : null}
      {error ? <Notice kind="error">{error}</Notice> : null}

      <form onSubmit={submit} style={{ display: "grid", gap: 12 }}>
        <Field
          label="Rule id"
          hint="The primary key, so it cannot be changed later without orphaning every tag that points at it. The existing ones look like BIO-008 or SYN-014."
        >
          <TextInput value={ruleId} onChange={setRuleId} placeholder="BIO-055" />
        </Field>

        {shown.map((field) => (
          <Field key={field.key} label={field.label} hint={field.hint}>
            {field.options ? (
              <Select
                value={draft[field.key] ?? ""}
                onChange={(value) => set(field.key, value)}
                options={field.key === "rule_category" ? RULE_CATEGORIES : field.options}
                placeholder="Choose one"
              />
            ) : (
              <TextInput
                value={draft[field.key] ?? ""}
                onChange={(value) => set(field.key, value)}
                multiline={field.multiline}
              />
            )}
          </Field>
        ))}

        {!proposed.trigger_code ? (
          <Notice>
            Without a trigger code the rule can never fire: a rule reaches a recipe only when one of
            its ingredients is tagged with that code. It is still worth submitting if the code does
            not exist yet — just expect it under “fires on nothing” until the tagging catches up.
          </Notice>
        ) : null}

        <Button onClick={() => setShowAll((v) => !v)}>
          {showAll ? "Show fewer fields" : `Show all ${FIELDS.length} fields`}
        </Button>

        <Field label="Why this rule" hint="Shown to the reviewer with the proposal.">
          <TextInput value={note} onChange={setNote} multiline rows={2} />
        </Field>

        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <Button type="submit" tone="primary" disabled={busy || !ready}>
            {busy ? "Submitting…" : "Submit for review"}
          </Button>
          {!ready ? (
            <Chip color={C.muted} border={C.border}>
              needs an id, a name and a category
            </Chip>
          ) : null}
        </div>
      </form>
    </Card>
  );
}
