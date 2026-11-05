// What other people have proposed, and the decision on it.
//
// A request shows the current value beside the proposed one for every field it
// touches, because approving is a judgement about a difference, not about a
// form. The server re-reads the rule when the decision arrives and refuses to
// apply a request whose before-snapshot no longer matches - two reviewers
// working at once cannot silently undo each other.
import { useEffect, useState } from "react";
import { C } from "../../shared/theme/colors";
import { decideRuleRequest, listRuleRequests } from "../../shared/services/api/admin";
import { Button, Card, Chip, Field, Notice, TextInput } from "./bits";
import { when } from "./format";

const STATUS_TONE = {
  pending: C.gold,
  approved: C.accent,
  rejected: C.muted,
  stale: C.coral,
};

function Diff({ request }) {
  const proposed = request.proposed || {};
  const before = request.before || {};
  const keys = Object.keys(proposed);
  if (!keys.length) {
    return (
      <span style={{ fontSize: 12, color: C.muted }}>
        No field changes — this request only {request.kind}s the rule.
      </span>
    );
  }
  return (
    <div style={{ display: "grid", gap: 8 }}>
      {keys.map((key) => (
        <div key={key} style={{ display: "grid", gap: 2 }}>
          <span style={{ fontSize: 10.5, fontWeight: 700, color: C.subtext, letterSpacing: 0.3 }}>
            {key}
          </span>
          <span style={{ fontSize: 12, color: C.muted, textDecoration: "line-through" }}>
            {String(before[key] ?? "(empty)")}
          </span>
          <span style={{ fontSize: 12.5, color: C.navy, fontWeight: 600 }}>
            {String(proposed[key] ?? "(cleared)")}
          </span>
        </div>
      ))}
    </div>
  );
}

function RequestCard({ request, onDecided }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const decide = async (approve) => {
    setBusy(true);
    setError(null);
    try {
      await decideRuleRequest(request.request_id, approve, note);
      onDecided();
    } catch (err) {
      // A stale request is the interesting failure: the reviewer was reading
      // text the database no longer holds, so say that rather than "409".
      setError(
        err.detail?.error === "rule_changed_since_request"
          ? "The rule changed after this request was made, so it was not applied. It is now marked stale; the proposer should resubmit against the current text."
          : err.detail
            ? JSON.stringify(err.detail)
            : err.message,
      );
      onDecided();
    } finally {
      setBusy(false);
    }
  };

  const pending = request.status === "pending";

  return (
    <Card style={{ display: "grid", gap: 12 }}>
      <div style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
        <Chip color={STATUS_TONE[request.status] || C.subtext} border={C.border}>
          {request.status}
        </Chip>
        <Chip color={C.subtext} border={C.border}>{request.kind}</Chip>
        <span style={{ fontSize: 13, fontWeight: 700, color: C.navy }}>{request.rule_id}</span>
        <span style={{ flex: 1, fontSize: 12.5, color: C.text, minWidth: 120 }}>
          {request.current_name || "(rule does not exist yet)"}
        </span>
      </div>

      <span style={{ fontSize: 11.5, color: C.muted }}>
        Proposed by {request.submitted_by} · {when(request.submitted_at)}
        {request.decided_by ? ` · decided by ${request.decided_by} ${when(request.decided_at)}` : ""}
      </span>

      {request.note ? (
        <span style={{ fontSize: 12.5, color: C.subtext, lineHeight: 1.6 }}>“{request.note}”</span>
      ) : null}

      <Diff request={request} />

      {error ? <Notice kind="error">{error}</Notice> : null}

      {pending ? (
        <div style={{ display: "grid", gap: 10 }}>
          <Field label="Decision note" hint="Optional. Kept with the request as the audit trail.">
            <TextInput value={note} onChange={setNote} />
          </Field>
          <div style={{ display: "flex", gap: 8 }}>
            <Button tone="primary" disabled={busy} onClick={() => decide(true)}>
              Approve and apply
            </Button>
            <Button tone="danger" disabled={busy} onClick={() => decide(false)}>
              Reject
            </Button>
          </div>
        </div>
      ) : request.decision_note ? (
        <span style={{ fontSize: 12, color: C.subtext }}>“{request.decision_note}”</span>
      ) : null}
    </Card>
  );
}

export default function RequestQueue({ refreshKey, onChanged }) {
  const [status, setStatus] = useState("pending");
  const [payload, setPayload] = useState(null);
  const [error, setError] = useState(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let live = true;
    listRuleRequests(status)
      .then((data) => live && setPayload(data))
      .catch((err) => live && setError(err.detail?.error || err.message));
    return () => {
      live = false;
    };
  }, [status, tick, refreshKey]);

  const items = payload?.items || [];
  const reload = () => {
    setTick((n) => n + 1);
    onChanged?.();
  };

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        {["pending", "approved", "rejected", "stale", "all"].map((option) => (
          <Button
            key={option}
            tone={status === option ? "primary" : "normal"}
            onClick={() => setStatus(option)}
          >
            {option}
          </Button>
        ))}
        <span style={{ fontSize: 11.5, color: C.muted, marginLeft: "auto" }}>
          {payload?.reviewer ? `signed in as ${payload.reviewer}` : null}
        </span>
      </div>

      {error ? (
        <Notice kind="error">
          {error === "not_an_admin"
            ? "This account is signed in but is not on the reviewer allowlist, so it cannot see or decide requests. MAZI_ADMIN_EMAILS on the server decides who can."
            : error}
        </Notice>
      ) : null}

      {!payload && !error ? <Notice>Loading requests…</Notice> : null}

      {payload && !items.length ? (
        <Notice>
          Nothing {status === "all" ? "submitted" : status} yet. A change proposed on the Rules tab
          lands here.
        </Notice>
      ) : null}

      {items.map((request) => (
        <RequestCard key={request.request_id} request={request} onDecided={reload} />
      ))}
    </div>
  );
}
