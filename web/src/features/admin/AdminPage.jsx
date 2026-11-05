// The admin screen: how many rules there are, and the queue that changes them.
//
// Reading is open. The rules are published research with their sources on
// every card, and the cook screens already show them - putting the counts
// behind a login would only make the state of the data harder to see.
//
// Writing is not. Proposing a change needs a verified Supabase account, and
// approving one needs that account to be on the server's allowlist. Both
// checks are the server's; this screen asks /api/admin/me who it is and lays
// itself out accordingly, which means a browser that lies about being an
// admin gets an admin-looking page and a 403 on every action.
import { useCallback, useEffect, useState } from "react";
import { C } from "../../shared/theme/colors";
import { hasSupabaseEnv } from "../../shared/services/supabase/client";
import { getSession, signIn, signOut } from "../../shared/services/auth/authStore";
import { ruleSummary, whoAmI } from "../../shared/services/api/admin";
import { Button, Card, Field, Notice, TextInput, Tile } from "./bits";
import RequestQueue from "./RequestQueue";
import RulePanel from "./RulePanel";

function SignIn({ onSignedIn }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const { error: failure } = await signIn({ email, password });
    setBusy(false);
    if (failure) {
      setError(failure.message);
      return;
    }
    onSignedIn();
  };

  if (!hasSupabaseEnv) {
    return (
      <Notice kind="error">
        Sign-in needs VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY in this build. Without them the
        rule counts below still work, but nothing can be proposed or approved.
      </Notice>
    );
  }

  return (
    <Card style={{ display: "grid", gap: 12, maxWidth: 360 }}>
      <span style={{ fontSize: 12, fontWeight: 700, color: C.subtext, letterSpacing: 0.3 }}>
        SIGN IN TO PROPOSE OR APPROVE
      </span>
      <form onSubmit={submit} style={{ display: "grid", gap: 10 }}>
        <Field label="Email">
          <TextInput value={email} onChange={setEmail} type="email" autoComplete="username" />
        </Field>
        <Field label="Password">
          <TextInput
            value={password}
            onChange={setPassword}
            type="password"
            autoComplete="current-password"
          />
        </Field>
        {error ? <Notice kind="error">{error}</Notice> : null}
        <Button type="submit" tone="primary" disabled={busy || !email || !password}>
          {busy ? "Signing in…" : "Sign in"}
        </Button>
      </form>
      <span style={{ fontSize: 11, color: C.muted, lineHeight: 1.6 }}>
        The same account as the main app. Accounts are per Supabase project; this one reads the
        project this build is configured with.
      </span>
    </Card>
  );
}

function Summary({ summary }) {
  if (!summary) return null;
  const t = summary.totals;
  return (
    <div style={{ display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))" }}>
      <Tile label="Rules in the table" value={t.rules} hint={`${t.active} of them active`} />
      <Tile
        label="Rules that can fire"
        value={t.reachable}
        tone={C.accent}
        hint={`an ingredient carries their trigger code`}
      />
      <Tile
        label="Rules that fire on nothing"
        value={t.unreachable}
        tone={t.unreachable ? C.coral : C.accent}
        hint="waiting on ingredient tagging, not broken"
      />
      <Tile
        label="Trigger codes tagged"
        value={`${t.tagged_codes} / ${t.trigger_codes}`}
        tone={C.gold}
        hint={`${t.tags} tags across ${t.tagged_ingredients} of ${t.ingredients} ingredients`}
      />
      <Tile
        label="Requests awaiting review"
        value={t.pending}
        tone={t.pending ? C.gold : C.navy}
        hint="proposed changes to the rules"
      />
    </div>
  );
}

export default function AdminPage({ onNavigate }) {
  const [caller, setCaller] = useState(null);
  const [checked, setChecked] = useState(false);
  const [summary, setSummary] = useState(null);
  const [summaryError, setSummaryError] = useState(null);
  const [tab, setTab] = useState("rules");
  const [refreshKey, setRefreshKey] = useState(0);

  // Who the server says we are. Asked again after a sign-in and after any
  // decision, because the allowlist can change under a live session.
  const identify = useCallback(() => {
    let live = true;
    getSession().then((session) => {
      if (!session) {
        if (live) {
          setCaller(null);
          setChecked(true);
        }
        return;
      }
      whoAmI()
        .then((me) => live && setCaller(me))
        .catch(() => live && setCaller(null))
        .finally(() => live && setChecked(true));
    });
    return () => {
      live = false;
    };
  }, []);

  useEffect(identify, [identify]);

  useEffect(() => {
    let live = true;
    ruleSummary()
      .then((data) => live && setSummary(data))
      .catch((err) => live && setSummaryError(err.message));
    return () => {
      live = false;
    };
  }, [refreshKey]);

  const refresh = () => setRefreshKey((n) => n + 1);

  return (
    <div style={{ minHeight: "100vh", background: C.bg, fontFamily: "Plus Jakarta Sans, sans-serif" }}>
      <div style={{ maxWidth: 1180, margin: "0 auto", padding: "28px 20px 60px", display: "grid", gap: 18 }}>
        <header style={{ display: "flex", gap: 12, alignItems: "baseline", flexWrap: "wrap" }}>
          <h1 style={{ margin: 0, fontFamily: "Fraunces, serif", fontSize: 26, fontWeight: 600, color: C.navy }}>
            Rules admin
          </h1>
          <span style={{ flex: 1, fontSize: 12.5, color: C.subtext, minWidth: 200 }}>
            business_rules, what the engine can reach, and the queue that changes it.
          </span>
          <Button onClick={() => onNavigate("#/recipes")}>Recipes</Button>
          <Button onClick={() => onNavigate("#/review")}>Review</Button>
          {caller ? (
            <Button
              onClick={async () => {
                await signOut();
                setCaller(null);
              }}
            >
              Sign out {caller.email}
            </Button>
          ) : null}
        </header>

        {summaryError ? <Notice kind="error">Could not read the rule counts: {summaryError}</Notice> : null}
        <Summary summary={summary} />

        {checked && !caller ? <SignIn onSignedIn={identify} /> : null}

        {caller && !caller.is_admin ? (
          <Notice>
            Signed in as {caller.email}. You can propose a change to any rule; approving one needs an
            account on the server's reviewer allowlist.
          </Notice>
        ) : null}

        <div style={{ display: "flex", gap: 8 }}>
          <Button tone={tab === "rules" ? "primary" : "normal"} onClick={() => setTab("rules")}>
            Rules
          </Button>
          <Button tone={tab === "queue" ? "primary" : "normal"} onClick={() => setTab("queue")}>
            Pending changes
            {summary?.totals?.pending ? ` (${summary.totals.pending})` : ""}
          </Button>
        </div>

        {tab === "rules" ? (
          <RulePanel refreshKey={refreshKey} onChanged={refresh} />
        ) : caller?.is_admin ? (
          <RequestQueue refreshKey={refreshKey} onChanged={refresh} />
        ) : (
          <Notice>
            The queue is only readable by a reviewer on the allowlist, because a request carries who
            proposed it and what they wanted changed.
          </Notice>
        )}
      </div>
    </div>
  );
}
