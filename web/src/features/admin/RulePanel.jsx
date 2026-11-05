// The rules table: how many there are, which of them the engine can reach,
// and a form that proposes a change to one.
//
// The proposal never writes to business_rules. It becomes a row in
// rule_change_requests which someone on the allowlist approves, and only then
// does the rule move. One rule applies to all 400 recipes, so an edit made
// straight from a form changes every verdict in the product at once; the queue
// is what makes that reviewable first.
import { useEffect, useMemo, useState } from "react";
import { C } from "../../shared/theme/colors";
import { getRule, listRules, submitRuleRequest } from "../../shared/services/api/admin";
import { Button, Card, Chip, Field, Notice, Select, TextInput } from "./bits";
import { AUTOMATION_STATUSES, AUTOMATION_TONE, FIELDS, RULE_CATEGORIES, reachOf, when } from "./format";

function RuleRow({ rule, selected, onSelect }) {
  const reach = reachOf(rule);
  return (
    <button
      type="button"
      onClick={() => onSelect(rule.rule_id)}
      style={{
        textAlign: "left",
        display: "grid",
        gap: 5,
        padding: "10px 12px",
        borderRadius: 10,
        border: `1px solid ${selected ? C.accent : "transparent"}`,
        background: selected ? C.accentLight : "transparent",
        cursor: "pointer",
        fontFamily: "inherit",
        width: "100%",
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: C.navy, fontVariantNumeric: "tabular-nums" }}>
          {rule.rule_id}
        </span>
        <span style={{ flex: 1, fontSize: 13, color: C.text, minWidth: 140 }}>{rule.rule_name}</span>
        {rule.pending_requests ? (
          <Chip color={C.gold} bg={C.goldLight}>{rule.pending_requests} pending</Chip>
        ) : null}
        {!rule.is_active ? <Chip color={C.muted} border={C.border}>inactive</Chip> : null}
      </div>
      <div style={{ display: "flex", gap: 7, flexWrap: "wrap", alignItems: "center" }}>
        <Chip color={C.subtext} border={C.border}>{rule.rule_category}</Chip>
        {rule.automation_status ? (
          <Chip color={AUTOMATION_TONE[rule.automation_status] || C.subtext}>
            {rule.automation_status}
          </Chip>
        ) : null}
        <span style={{ fontSize: 10.5, color: reach.tone, fontWeight: 600 }}>{reach.label}</span>
        {rule.recipes_with_trigger ? (
          <span style={{ fontSize: 10.5, color: C.muted }}>
            {rule.recipes_with_trigger} recipes contain one
          </span>
        ) : null}
      </div>
    </button>
  );
}

function Editor({ ruleId, onSubmitted }) {
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState(null);
  const [draft, setDraft] = useState({});
  const [note, setNote] = useState("");
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    let live = true;
    setDetail(null);
    setDraft({});
    setResult(null);
    setError(null);
    getRule(ruleId)
      .then((data) => live && setDetail(data))
      .catch((err) => live && setError(err.message));
    return () => {
      live = false;
    };
  }, [ruleId]);

  const rule = detail?.rule;

  // Only the fields actually touched travel in the request. Sending the whole
  // row would make every untouched field look like a deliberate re-assertion
  // of its current value, and the reviewer could not see what changed.
  const changed = useMemo(() => {
    if (!rule) return {};
    const out = {};
    for (const [key, value] of Object.entries(draft)) {
      const current = rule[key] ?? "";
      if (String(value ?? "") !== String(current)) out[key] = value === "" ? null : value;
    }
    return out;
  }, [draft, rule]);

  const changedKeys = Object.keys(changed);

  const send = async (kind) => {
    setSending(true);
    setError(null);
    setResult(null);
    try {
      const body =
        kind === "update"
          ? { kind, ruleId, proposed: changed, note }
          : { kind, ruleId, proposed: {}, note };
      const created = await submitRuleRequest(body);
      setResult(created);
      setDraft({});
      setNote("");
      onSubmitted?.();
      const fresh = await getRule(ruleId);
      setDetail(fresh);
    } catch (err) {
      setError(err.detail ? JSON.stringify(err.detail) : err.message);
    } finally {
      setSending(false);
    }
  };

  if (error && !detail) return <Notice kind="error">{error}</Notice>;
  if (!rule) return <Notice>Loading {ruleId}…</Notice>;

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <Card style={{ display: "grid", gap: 10 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
          <span style={{ fontSize: 14, fontWeight: 700, color: C.navy }}>{rule.rule_id}</span>
          <span style={{ flex: 1, fontSize: 14, color: C.text }}>{rule.rule_name}</span>
          <Chip color={rule.is_active ? C.accent : C.muted} border={C.border}>
            {rule.is_active ? "active" : "inactive"}
          </Chip>
        </div>
        <p style={{ margin: 0, fontSize: 11.5, color: C.muted, lineHeight: 1.6 }}>
          Last changed {when(rule.updated_at)}.{" "}
          {detail.tagged_ingredients.length
            ? `Fires through ${detail.tagged_ingredients.length} tagged ingredient${
                detail.tagged_ingredients.length === 1 ? "" : "s"
              }: ${detail.tagged_ingredients.slice(0, 6).map((i) => i.name).join(", ")}${
                detail.tagged_ingredients.length > 6 ? "…" : ""
              }`
            : `No ingredient carries ${rule.trigger_code || "a trigger code"}, so this rule fires on nothing yet.`}
        </p>
      </Card>

      <Card style={{ display: "grid", gap: 12 }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: C.subtext, letterSpacing: 0.3 }}>
          PROPOSE A CHANGE
        </span>
        <div style={{ display: "grid", gap: 12 }}>
          {FIELDS.map((field) => {
            const current = rule[field.key] ?? "";
            const value = field.key in draft ? draft[field.key] : current;
            const dirty = field.key in changed;
            return (
              <Field
                key={field.key}
                label={`${field.label}${dirty ? " · changed" : ""}`}
                hint={dirty ? `was: ${current || "(empty)"}` : field.hint}
              >
                {field.options ? (
                  <Select
                    value={value}
                    onChange={(next) => setDraft((d) => ({ ...d, [field.key]: next ?? "" }))}
                    options={field.options}
                    placeholder="(unset)"
                  />
                ) : (
                  <TextInput
                    value={value}
                    multiline={field.multiline}
                    onChange={(next) => setDraft((d) => ({ ...d, [field.key]: next }))}
                  />
                )}
              </Field>
            );
          })}
        </div>

        <Field label="Why" hint="Goes on the request for whoever reviews it.">
          <TextInput value={note} onChange={setNote} multiline rows={2} />
        </Field>

        {error ? <Notice kind="error">{error}</Notice> : null}
        {result ? (
          <Notice kind="ok">
            Submitted as {result.kind} on {result.rule_id}. It is pending until a reviewer approves
            it; the rule has not changed.
          </Notice>
        ) : null}

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <Button
            tone="primary"
            disabled={sending || !changedKeys.length}
            onClick={() => send("update")}
          >
            {changedKeys.length
              ? `Submit ${changedKeys.length} change${changedKeys.length === 1 ? "" : "s"}`
              : "No changes yet"}
          </Button>
          <Button
            tone="danger"
            disabled={sending}
            onClick={() => send(rule.is_active ? "deactivate" : "activate")}
          >
            Propose {rule.is_active ? "deactivating" : "activating"} this rule
          </Button>
        </div>
      </Card>

      {detail.history.length ? (
        <Card style={{ display: "grid", gap: 8 }}>
          <span style={{ fontSize: 12, fontWeight: 700, color: C.subtext, letterSpacing: 0.3 }}>
            HISTORY
          </span>
          {detail.history.map((item) => (
            <div key={item.request_id} style={{ display: "flex", gap: 8, flexWrap: "wrap", fontSize: 11.5 }}>
              <Chip
                color={
                  item.status === "approved"
                    ? C.accent
                    : item.status === "pending"
                      ? C.gold
                      : C.muted
                }
                border={C.border}
              >
                {item.status}
              </Chip>
              <span style={{ color: C.subtext }}>{item.kind}</span>
              <span style={{ color: C.muted }}>
                by {item.submitted_by} · {when(item.submitted_at)}
              </span>
              {item.note ? <span style={{ color: C.subtext }}>“{item.note}”</span> : null}
            </div>
          ))}
        </Card>
      ) : null}
    </div>
  );
}

export default function RulePanel({ refreshKey, onChanged }) {
  const [payload, setPayload] = useState(null);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState({ q: "", category: null, status: null, reach: null });
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    let live = true;
    listRules({
      q: filters.q || undefined,
      category: filters.category || undefined,
      status: filters.status || undefined,
      reach: filters.reach || undefined,
      limit: 400,
    })
      .then((data) => live && setPayload(data))
      .catch((err) => live && setError(err.message));
    return () => {
      live = false;
    };
  }, [filters, refreshKey]);

  const items = payload?.items || [];

  return (
    <div style={{ display: "grid", gap: 16, gridTemplateColumns: "minmax(300px, 420px) 1fr", alignItems: "start" }}>
      <div style={{ display: "grid", gap: 12 }}>
        <Card style={{ display: "grid", gap: 10 }}>
          <TextInput
            value={filters.q}
            onChange={(q) => setFilters((f) => ({ ...f, q }))}
            placeholder="Search id, name, trigger code…"
          />
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Select
              value={filters.category}
              onChange={(category) => setFilters((f) => ({ ...f, category }))}
              options={RULE_CATEGORIES}
              placeholder="Any category"
            />
            <Select
              value={filters.status}
              onChange={(status) => setFilters((f) => ({ ...f, status }))}
              options={AUTOMATION_STATUSES}
              placeholder="Any automation"
            />
            <Select
              value={filters.reach}
              onChange={(reach) => setFilters((f) => ({ ...f, reach }))}
              options={[
                { value: "reachable", label: "Fires on something" },
                { value: "unreachable", label: "Fires on nothing" },
              ]}
              placeholder="Any reach"
            />
          </div>
          <span style={{ fontSize: 11, color: C.muted }}>
            {error ? error : payload ? `${items.length} rules` : "Loading…"}
          </span>
        </Card>

        <Card style={{ padding: 8, display: "grid", gap: 2, maxHeight: "70vh", overflowY: "auto" }}>
          {items.map((rule) => (
            <RuleRow
              key={rule.rule_id}
              rule={rule}
              selected={selected === rule.rule_id}
              onSelect={setSelected}
            />
          ))}
          {payload && !items.length ? (
            <span style={{ padding: 10, fontSize: 12, color: C.muted }}>
              No rule matches those filters.
            </span>
          ) : null}
        </Card>
      </div>

      {selected ? (
        <Editor ruleId={selected} onSubmitted={onChanged} />
      ) : (
        <Card>
          <p style={{ margin: 0, fontSize: 13, color: C.subtext, lineHeight: 1.7 }}>
            Pick a rule to read it in full and propose a change. Nothing on this screen edits
            business_rules directly: a change becomes a request that someone on the reviewer
            allowlist approves, and the rule moves only then.
          </p>
        </Card>
      )}
    </div>
  );
}
