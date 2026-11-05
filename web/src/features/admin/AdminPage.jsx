// The admin screen: the rules table, and everything that changes it.
//
// Reading is open. The rules are published research with their sources on
// every card, and the cook screens already show them - putting the counts
// behind a login would only make the state of the data harder to see.
//
// Writing is not, and it is two levels rather than one:
//
//   any signed-in account   may propose a change, or a new rule
//   a reviewer              may approve one, and may add another reviewer
//
// Both checks are the server's. This screen asks /api/admin/me who it is and
// lays itself out accordingly, which means a browser that lies about being a
// reviewer gets a reviewer-looking page and a 403 on every action.
//
// The layout is four tabs under one line of numbers, rather than everything at
// once. The numbers are deliberately small: the only one that usually matters
// is how many rules can actually fire, and five equally-sized tiles made that
// as prominent as the count of rows in a table.
import { useCallback, useEffect, useMemo, useState } from "react";
import { C } from "../../shared/theme/colors";
import { hasSupabaseEnv } from "../../shared/services/supabase/client";
import { getSession, signIn, signOut } from "../../shared/services/auth/authStore";
import { ruleSummary, whoAmI } from "../../shared/services/api/admin";
import { Button, Card, Chip, Field, Notice, TextInput } from "./bits";
import NewRuleForm from "./NewRuleForm";
import PeoplePanel from "./PeoplePanel";
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

function Stat({ label, value, tone = C.navy, title }) {
  return (
    <span
      title={title}
      style={{ display: "inline-flex", gap: 6, alignItems: "baseline", fontSize: 12 }}
    >
      <strong style={{ fontSize: 14, color: tone, fontVariantNumeric: "tabular-nums" }}>
        {value}
      </strong>
      <span style={{ color: C.muted }}>{label}</span>
    </span>
  );
}

// One sentence and one row of numbers. The sentence carries the finding; the
// numbers are there to check it against.
function Health({ summary }) {
  if (!summary) return null;
  const t = summary.totals;
  const short = t.rules - t.reachable;
  return (
    <Card style={{ display: "grid", gap: 10 }}>
      <p style={{ margin: 0, fontSize: 13, color: C.text, lineHeight: 1.65 }}>
        <strong style={{ color: short ? C.coral : C.accent }}>
          {t.reachable} of {t.rules} rules can currently fire.
        </strong>{" "}
        The other {short} are waiting on ingredient tagging, not broken: a rule reaches a recipe only
        when one of its ingredients carries the rule&rsquo;s trigger code, and{" "}
        {t.tagged_codes} of {t.trigger_codes} codes are tagged so far.
      </p>
      <div style={{ display: "flex", gap: 18, flexWrap: "wrap", alignItems: "baseline" }}>
        <Stat label="rules" value={t.rules} title={`${t.active} of them active`} />
        <Stat label="can fire" value={t.reachable} tone={C.accent} />
        <Stat label="fire on nothing" value={t.unreachable} tone={t.unreachable ? C.coral : C.accent} />
        <Stat
          label="trigger codes tagged"
          value={`${t.tagged_codes}/${t.trigger_codes}`}
          tone={C.gold}
        />
        <Stat
          label="tagged ingredients"
          value={`${t.tagged_ingredients}/${t.ingredients}`}
          title={`${t.tags} tags in all`}
        />
        <Stat label="awaiting review" value={t.pending} tone={t.pending ? C.gold : C.navy} />
      </div>
    </Card>
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
  // decision, because the reviewer list can change under a live session - and
  // now does, from this very screen.
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

  const tabs = useMemo(
    () => [
      { id: "rules", label: "Rules", count: summary?.totals?.rules },
      { id: "new", label: "New rule" },
      { id: "queue", label: "Pending changes", count: summary?.totals?.pending },
      { id: "people", label: "Reviewers", reviewerOnly: true },
    ],
    [summary],
  );

  return (
    <div
      style={{ minHeight: "100vh", background: C.bg, fontFamily: "Plus Jakarta Sans, sans-serif" }}
    >
      <div
        style={{
          maxWidth: 1180,
          margin: "0 auto",
          padding: "24px 20px 60px",
          display: "grid",
          gap: 16,
        }}
      >
        <header style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <h1
            style={{
              margin: 0,
              fontFamily: "Fraunces, serif",
              fontSize: 23,
              fontWeight: 600,
              color: C.navy,
            }}
          >
            Rules admin
          </h1>
          {caller ? (
            <Chip
              color={caller.is_admin ? C.accent : C.gold}
              border={C.border}
              title={
                caller.is_admin
                  ? "You can approve a proposed change"
                  : "You can propose a change; approving needs a reviewer"
              }
            >
              {caller.is_admin ? "reviewer" : "can propose"}
            </Chip>
          ) : null}
          <span style={{ flex: 1 }} />
          <Button onClick={() => onNavigate("#/review/nutrition")}>Nutrition review</Button>
          <Button onClick={() => onNavigate("#/recipes")}>Recipes</Button>
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

        {summaryError ? (
          <Notice kind="error">Could not read the rule counts: {summaryError}</Notice>
        ) : null}
        <Health summary={summary} />

        {checked && !caller ? <SignIn onSignedIn={identify} /> : null}

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {tabs
            .filter((entry) => !entry.reviewerOnly || caller?.is_admin)
            .map((entry) => (
              <Button
                key={entry.id}
                tone={tab === entry.id ? "primary" : "normal"}
                onClick={() => setTab(entry.id)}
              >
                {entry.label}
                {entry.count ? ` (${entry.count})` : ""}
              </Button>
            ))}
        </div>

        {tab === "rules" ? <RulePanel refreshKey={refreshKey} onChanged={refresh} /> : null}

        {tab === "new" ? (
          <NewRuleForm
            canPropose={Boolean(caller)}
            onSubmitted={() => {
              refresh();
              setTab("queue");
            }}
          />
        ) : null}

        {tab === "queue" ? (
          caller?.is_admin ? (
            <RequestQueue refreshKey={refreshKey} onChanged={refresh} />
          ) : (
            <Notice>
              The queue is only readable by a reviewer, because a request carries who proposed it and
              what they wanted changed. Yours was submitted and is waiting there.
            </Notice>
          )
        ) : null}

        {tab === "people" && caller?.is_admin ? (
          <PeoplePanel
            onChanged={() => {
              refresh();
              identify();
            }}
          />
        ) : null}
      </div>
    </div>
  );
}
