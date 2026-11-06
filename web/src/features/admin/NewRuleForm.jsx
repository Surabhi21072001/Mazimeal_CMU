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
import { useEffect, useMemo, useState } from "react";
import { C } from "../../shared/theme/colors";
import { nextRuleId, submitRuleRequest } from "../../shared/services/api/admin";
import { Button, Card, Chip, Field, Notice, Select, TextInput } from "./bits";
import CodePicker from "./CodePicker";
import { FIELDS, RULE_CATEGORIES } from "./format";

// Which fields are codes, and what each one is for. They are pickers rather
// than text inputs: business_rules has no foreign key on any of them, so a
// typed code that does not exist is stored and the rule is simply dead.
const CODE_FIELDS = {
  trigger_code: {
    label: "Trigger code — when the rule applies",
    hint: "A recipe matches when one of its ingredients carries this code. This is the one that "
          + "decides whether the rule ever fires.",
  },
  target_code: {
    label: "Target code — what it is about",
    hint: "The nutrient or outcome the rule aims at. Recorded, not used for matching.",
  },
  action_code: {
    label: "Action code — what to do",
    hint: "The kind of change the rule asks for.",
  },
};

// The ones worth asking for up front. The rest can be filled in by an edit
// once the rule exists; a form with twenty inputs gets abandoned, and a rule
// with a name, a category and a trigger is already reviewable.
const CORE = ["rule_name", "rule_category", "trigger_code", "target_code", "action_code"];

// The rule_id prefix follows the category - BIO is bioavailability, GLY
// glycemic, INH inhibitor, SYN food_synergy - and all 54 existing rules obey
// it. Nobody filling this form should have to know that, so the id is
// suggested from the category and stays editable.

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
  if (detail?.error === "unknown_code") {
    const near = detail.nearest?.length ? ` Closest existing: ${detail.nearest.join(", ")}.` : "";
    return `${detail.code} is not in the code vocabulary, so no ingredient can carry it and the rule could never fire.${near}`;
  }
  return REFUSALS[detail?.error] || detail?.hint || err.message;
}

export default function NewRuleForm({ canPropose, onSubmitted }) {
  const [ruleId, setRuleId] = useState("");
  const [idTouched, setIdTouched] = useState(false);
  const [suggestion, setSuggestion] = useState(null);
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

  // Ask the server for the next free id whenever the category changes, and
  // fill it in unless the person has typed their own.
  const category = draft.rule_category;
  useEffect(() => {
    if (!category) {
      setSuggestion(null);
      return undefined;
    }
    let live = true;
    nextRuleId(category)
      .then((data) => {
        if (!live) return;
        setSuggestion(data);
        if (!idTouched) setRuleId(data.rule_id);
      })
      .catch(() => live && setSuggestion(null));
    return () => {
      live = false;
    };
  }, [category, idTouched]);

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
      setIdTouched(false);
      setSuggestion(null);
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
        <Field label="Category" hint="This also decides the rule id's prefix.">
          <Select
            value={draft.rule_category ?? ""}
            onChange={(value) => set("rule_category", value)}
            options={RULE_CATEGORIES}
            placeholder="Choose one"
          />
        </Field>

        <Field
          label="Rule id"
          hint={
            suggestion
              ? `Suggested: ${suggestion.prefix} is ${suggestion.category}, and ${suggestion.existing} already exist.`
              : "Choose a category and this fills itself in."
          }
        >
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <TextInput
              value={ruleId}
              onChange={(value) => {
                setIdTouched(true);
                setRuleId(value);
              }}
              placeholder={suggestion?.rule_id || "pick a category first"}
            />
            {idTouched && suggestion && ruleId !== suggestion.rule_id ? (
              <Button
                onClick={() => {
                  setIdTouched(false);
                  setRuleId(suggestion.rule_id);
                }}
              >
                Use {suggestion.rule_id}
              </Button>
            ) : null}
          </div>
        </Field>
        {suggestion?.pending?.length ? (
          <Notice>
            Already waiting in the queue, so these ids are taken:{" "}
            {suggestion.pending.join(", ")}.
          </Notice>
        ) : null}

        {shown
          .filter((field) => field.key !== "rule_category")
          .map((field) =>
            CODE_FIELDS[field.key] ? (
              <CodePicker
                key={field.key}
                field={field.key}
                label={CODE_FIELDS[field.key].label}
                hint={CODE_FIELDS[field.key].hint}
                value={draft[field.key] ?? ""}
                onChange={(value) => set(field.key, value)}
              />
            ) : (
              <Field key={field.key} label={field.label} hint={field.hint}>
                {field.options ? (
                  <Select
                    value={draft[field.key] ?? ""}
                    onChange={(value) => set(field.key, value)}
                    options={field.options}
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
            ),
          )}

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
