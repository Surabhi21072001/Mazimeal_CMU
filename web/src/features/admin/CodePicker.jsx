// Choosing a code, rather than typing one.
//
// business_rules has no foreign key on trigger_code, target_code or
// action_code, so a typed code that does not exist is stored without
// complaint and the rule can never fire: nothing carries a code that is not
// in the vocabulary. The server refuses an unknown one at submission now, but
// a refusal after filling in a form is a worse experience than not being able
// to get it wrong.
//
// So this lists the real codes, filtered to the ones that belong in this
// field, ordered by what they reach. That order is the point. "ING_CRUCIFER,
// 11 ingredients, 3 rules" means a rule naming it will fire today;
// "ING_SEAWEED, nothing tagged yet" means it will not, and someone has to say
// which foods the word means first. Both are legitimate choices, and the
// difference should be visible while choosing rather than discovered later.
import { useEffect, useMemo, useRef, useState } from "react";
import { C } from "../../shared/theme/colors";
import { createCode, listCodes } from "../../shared/services/api/admin";
import { Button, Chip, Field, Notice, TextInput } from "./bits";

function reachOf(code) {
  if (code.components?.length) {
    return { label: `${code.components.join(" + ")}`, tone: C.sky, fires: true };
  }
  if (code.ingredients > 0) {
    return {
      label: `${code.ingredients} ingredient${code.ingredients === 1 ? "" : "s"}`,
      tone: C.accent,
      fires: true,
    };
  }
  return { label: "nothing tagged yet", tone: C.gold, fires: false };
}

export default function CodePicker({ field, label, hint, value, onChange }) {
  const [codes, setCodes] = useState(null);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState("");
  const [open, setOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState({ code: "", displayName: "", description: "" });
  const [tick, setTick] = useState(0);
  const box = useRef(null);

  useEffect(() => {
    let live = true;
    listCodes({ field })
      .then((data) => live && setCodes(data.items))
      .catch((err) => live && setError(err.message));
    return () => {
      live = false;
    };
  }, [field, tick]);

  // Clicking away closes the list; a picker that stays open over the next
  // field is worse than one extra click.
  useEffect(() => {
    if (!open) return undefined;
    const away = (event) => {
      if (box.current && !box.current.contains(event.target)) setOpen(false);
    };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [open]);

  const shown = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    const all = codes || [];
    if (!needle) return all;
    return all.filter(
      (c) =>
        c.code.toLowerCase().includes(needle) ||
        (c.display_name || "").toLowerCase().includes(needle),
    );
  }, [codes, filter]);

  const chosen = (codes || []).find((c) => c.code === value);

  const pick = (code) => {
    onChange(code);
    setOpen(false);
    setFilter("");
  };

  const add = async (event) => {
    event.preventDefault();
    setError(null);
    try {
      const made = await createCode({
        code: draft.code.trim().toUpperCase(),
        displayName: draft.displayName.trim(),
        description: draft.description.trim() || null,
      });
      setDraft({ code: "", displayName: "", description: "" });
      setAdding(false);
      setTick((n) => n + 1);
      onChange(made.code);
      setOpen(false);
    } catch (err) {
      const detail = err?.detail;
      setError(detail?.hint || detail?.error || err.message);
    }
  };

  return (
    <Field label={label} hint={hint}>
      <div ref={box} style={{ position: "relative", display: "grid", gap: 6 }}>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          style={{
            display: "flex",
            gap: 8,
            alignItems: "center",
            flexWrap: "wrap",
            padding: "8px 10px",
            borderRadius: 9,
            border: `1px solid ${C.border}`,
            background: C.white,
            color: value ? C.text : C.muted,
            fontSize: 13,
            fontFamily: "inherit",
            cursor: "pointer",
            textAlign: "left",
          }}
        >
          <span style={{ fontWeight: value ? 600 : 400 }}>{value || "Choose a code"}</span>
          {chosen ? (
            <Chip color={reachOf(chosen).tone} border={C.border}>
              {reachOf(chosen).label}
            </Chip>
          ) : null}
          <span style={{ flex: 1 }} />
          <span style={{ color: C.muted, fontSize: 11 }}>{open ? "close" : "change"}</span>
        </button>

        {chosen && !reachOf(chosen).fires ? (
          <span style={{ fontSize: 11.5, color: C.gold, lineHeight: 1.6 }}>
            No ingredient carries {chosen.code} yet, so a rule using it will not fire until someone
            says which foods it means. That is a fine thing to submit — just not a working rule yet.
          </span>
        ) : null}

        {open ? (
          // A column that is allowed to be shorter than its contents. The list
          // needs minHeight: 0 to shrink below its content height - without it
          // the row keeps all 83 rows' height, the list has nothing to scroll,
          // and the panel simply clips.
          <div
            style={{
              position: "absolute",
              top: "100%",
              left: 0,
              right: 0,
              zIndex: 20,
              marginTop: 4,
              borderRadius: 10,
              border: `1px solid ${C.border}`,
              background: C.white,
              boxShadow: "0 8px 24px rgba(0,0,0,0.12)",
              display: "flex",
              flexDirection: "column",
              maxHeight: 340,
              overflow: "hidden",
            }}
          >
            {error ? (
              <div style={{ padding: 8, flex: "0 0 auto" }}>
                <Notice kind="error">{error}</Notice>
              </div>
            ) : null}

            {adding ? (
              // Shown instead of the list, not under it: a form this tall in a
              // fixed-height panel would squeeze the list to a few pixels.
              <form onSubmit={add} style={{ display: "grid", gap: 8, padding: 10, overflowY: "auto" }}>
                <TextInput
                  value={draft.code}
                  onChange={(v) => setDraft((d) => ({ ...d, code: v }))}
                  placeholder="ING_SEAWEED"
                />
                <TextInput
                  value={draft.displayName}
                  onChange={(v) => setDraft((d) => ({ ...d, displayName: v }))}
                  placeholder="Seaweed"
                />
                <TextInput
                  value={draft.description}
                  onChange={(v) => setDraft((d) => ({ ...d, description: v }))}
                  placeholder="Which foods it means — nori, kombu, wakame…"
                />
                <div style={{ display: "flex", gap: 8 }}>
                  <Button
                    type="submit"
                    tone="primary"
                    disabled={!draft.code.trim() || !draft.displayName.trim()}
                  >
                    Add code
                  </Button>
                  <Button onClick={() => setAdding(false)}>Back to the list</Button>
                </div>
                <span style={{ fontSize: 11, color: C.muted, lineHeight: 1.6 }}>
                  A new code is safe to add without review: nothing carries it, so no rule naming
                  it can fire. Which foods it means is a separate step, written down in
                  scripts/tag_ingredients.py.
                </span>
              </form>
            ) : (
              <>
                <div style={{ padding: 8, borderBottom: `1px solid ${C.border}`, flex: "0 0 auto" }}>
                  <TextInput
                    value={filter}
                    onChange={setFilter}
                    placeholder={`Search ${(codes || []).length} codes…`}
                  />
                </div>

                <div style={{ flex: "1 1 auto", minHeight: 0, overflowY: "auto" }}>
                  {value ? (
                    <button
                      type="button"
                      onClick={() => pick("")}
                      style={{
                        display: "block",
                        width: "100%",
                        padding: "7px 10px",
                        border: "none",
                        borderBottom: `1px solid ${C.bg}`,
                        background: "transparent",
                        cursor: "pointer",
                        fontFamily: "inherit",
                        fontSize: 12,
                        color: C.muted,
                        textAlign: "left",
                      }}
                    >
                      Leave unset
                    </button>
                  ) : null}
                  {shown.map((code) => {
                    const reach = reachOf(code);
                    return (
                      <button
                        key={code.code}
                        type="button"
                        onClick={() => pick(code.code)}
                        style={{
                          display: "flex",
                          gap: 8,
                          alignItems: "baseline",
                          width: "100%",
                          padding: "7px 10px",
                          border: "none",
                          borderBottom: `1px solid ${C.bg}`,
                          background: code.code === value ? C.accentLight : "transparent",
                          cursor: "pointer",
                          fontFamily: "inherit",
                          textAlign: "left",
                        }}
                      >
                        <span style={{ fontSize: 12.5, fontWeight: 600, color: C.text, minWidth: 180 }}>
                          {code.code}
                        </span>
                        <span style={{ fontSize: 11.5, color: C.subtext, flex: 1, minWidth: 0 }}>
                          {code.display_name}
                        </span>
                        <span style={{ fontSize: 11, color: reach.tone, whiteSpace: "nowrap" }}>
                          {reach.label}
                        </span>
                      </button>
                    );
                  })}
                  {!shown.length ? (
                    <div style={{ padding: 10, fontSize: 12, color: C.muted }}>
                      {codes ? `Nothing matches “${filter}”.` : "Loading the vocabulary…"}
                    </div>
                  ) : null}
                </div>

                <div style={{ borderTop: `1px solid ${C.border}`, padding: 8, flex: "0 0 auto" }}>
                  <Button onClick={() => setAdding(true)}>Add a code that is not here</Button>
                </div>
              </>
            )}
          </div>
        ) : null}
      </div>
    </Field>
  );
}
