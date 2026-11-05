// Who may approve a rule change.
//
// Two sources, shown apart because they behave differently. An address in the
// server's environment cannot be changed from here at all - it is the way back
// in if this list is ever wrong - while a row in the table can be added or
// removed by any reviewer. Collapsing them into one list would hide the fact
// that one of them is not editable, and the person clicking Remove would get a
// refusal with no reason visible on screen.
//
// The first reviewer came from a migration, which is why becoming one always
// starts outside this screen. What it allows is a reviewer adding another.
import { useCallback, useEffect, useState } from "react";
import { C } from "../../shared/theme/colors";
import { grantAdmin, listPeople, revokeAdmin } from "../../shared/services/api/admin";
import { Button, Card, Chip, Field, Notice, TextInput } from "./bits";
import { when } from "./format";

const REFUSALS = {
  cannot_revoke_self: "You cannot remove yourself. Ask another reviewer to do it.",
  last_reviewer: "This is the only reviewer left. Add another one first.",
  set_in_environment:
    "This address comes from the server's environment, not the table, so it cannot be removed here.",
  not_a_reviewer: "That address is not on the list.",
  bad_email: "That does not look like an email address.",
};

function message(err) {
  return REFUSALS[err?.detail?.error] || err?.detail?.hint || err.message;
}

function Person({ person, you, busy, onRevoke }) {
  const isYou = person.email === you;
  return (
    <div
      style={{
        display: "flex",
        gap: 10,
        alignItems: "center",
        flexWrap: "wrap",
        padding: "9px 0",
        borderTop: `1px solid ${C.border}`,
      }}
    >
      <span style={{ fontSize: 13, color: C.text, fontWeight: isYou ? 700 : 500 }}>
        {person.email}
      </span>
      {isYou ? (
        <Chip color={C.accent} border={C.border}>
          you
        </Chip>
      ) : null}
      {person.source === "environment" ? (
        <Chip color={C.sky} border={C.border} title="MAZI_ADMIN_EMAILS on the API host">
          environment
        </Chip>
      ) : null}
      <span style={{ flex: 1 }} />
      <span style={{ fontSize: 11, color: C.muted, textAlign: "right" }}>
        {person.source === "table"
          ? `added by ${person.granted_by} · ${when(person.granted_at)}`
          : "set where the API runs"}
      </span>
      {person.removable ? (
        <Button
          disabled={busy || isYou}
          onClick={() => onRevoke(person.email)}
          style={isYou ? { opacity: 0.45 } : undefined}
        >
          Remove
        </Button>
      ) : null}
    </div>
  );
}

export default function PeoplePanel({ onChanged }) {
  const [payload, setPayload] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [tick, setTick] = useState(0);
  const [email, setEmail] = useState("");
  const [note, setNote] = useState("");

  useEffect(() => {
    let live = true;
    listPeople()
      .then((data) => live && setPayload(data))
      .catch((err) => live && setError(message(err)));
    return () => {
      live = false;
    };
  }, [tick]);

  const act = useCallback(
    async (run) => {
      setBusy(true);
      setError(null);
      try {
        await run();
        setTick((n) => n + 1);
        onChanged?.();
        return true;
      } catch (err) {
        setError(message(err));
        return false;
      } finally {
        setBusy(false);
      }
    },
    [onChanged],
  );

  const add = async (event) => {
    event.preventDefault();
    const ok = await act(() => grantAdmin(email.trim(), note.trim() || null));
    if (ok) {
      setEmail("");
      setNote("");
    }
  };

  const people = payload?.items || [];

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <Card style={{ display: "grid", gap: 12 }}>
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
            Reviewers
          </h2>
          <p style={{ margin: "6px 0 0", fontSize: 12, color: C.subtext, lineHeight: 1.65 }}>
            Anyone signed in can propose a rule change. Only these accounts can approve one. A
            reviewer may add or remove another; the first one was added when the table was created,
            so nobody can make themselves a reviewer from outside.
          </p>
        </div>

        {error ? <Notice kind="error">{error}</Notice> : null}

        {payload ? (
          <div>
            {people.map((person) => (
              <Person
                key={person.email}
                person={person}
                you={payload.you}
                busy={busy}
                onRevoke={(address) => act(() => revokeAdmin(address))}
              />
            ))}
            {!people.length ? (
              <Notice kind="error">
                Nobody can approve anything. Add a row to app_admins, or set MAZI_ADMIN_EMAILS where
                the API runs.
              </Notice>
            ) : null}
          </div>
        ) : (
          <span style={{ fontSize: 12.5, color: C.muted }}>Loading…</span>
        )}
      </Card>

      <Card style={{ display: "grid", gap: 10, maxWidth: 520 }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: C.subtext, letterSpacing: 0.3 }}>
          ADD A REVIEWER
        </span>
        <form onSubmit={add} style={{ display: "grid", gap: 10 }}>
          <Field
            label="Email"
            hint="The address they sign in with. They need an account in this project already — adding a row here does not create one."
          >
            <TextInput value={email} onChange={setEmail} type="email" placeholder="name@example.com" />
          </Field>
          <Field label="Why" hint="Optional, and shown next to their name.">
            <TextInput value={note} onChange={setNote} placeholder="rules engine, data lead, …" />
          </Field>
          <Button type="submit" tone="primary" disabled={busy || !email.trim()}>
            {busy ? "Saving…" : "Add reviewer"}
          </Button>
        </form>
      </Card>
    </div>
  );
}
