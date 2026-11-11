// Sign in, and who is signed in, in the top right of any screen.
//
// Login used to exist only on #/admin, which made it look like a staff-only
// feature: the app has accounts, profiles, allergies and per-person targets,
// and no way to say who you are from the page that shows them. This is that
// control, written to drop into the header each screen already has rather
// than to replace those headers.
//
// It shows the name from the session straight away and fills in the profile
// when it arrives, because the profile comes from our own API and a sleeping
// free instance takes tens of seconds to answer. A header that waits for that
// would look broken on every cold start.
import { useEffect, useRef, useState } from "react";
import { C } from "../theme/colors";
import { hasSupabaseEnv } from "../services/supabase/client";
import { signIn, signOut } from "../services/auth/authStore";
import { useAccount } from "../services/auth/useAccount";

function Row({ label, children }) {
  if (!children) return null;
  return (
    <div style={{ display: "grid", gap: 1 }}>
      <span style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: 0.5, color: C.muted, textTransform: "uppercase" }}>
        {label}
      </span>
      <span style={{ fontSize: 12, color: C.text, lineHeight: 1.5 }}>{children}</span>
    </div>
  );
}

function Link({ children, onClick, tone = C.subtext }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        textAlign: "left",
        border: "none",
        background: "transparent",
        padding: "6px 0",
        color: tone,
        fontSize: 12.5,
        fontWeight: 600,
        cursor: "pointer",
        fontFamily: "inherit",
      }}
    >
      {children}
    </button>
  );
}

const INPUT = {
  width: "100%",
  boxSizing: "border-box",
  padding: "7px 9px",
  borderRadius: 8,
  border: `1px solid ${C.border}`,
  background: C.white,
  color: C.text,
  fontSize: 12.5,
  fontFamily: "inherit",
};

function SignInForm({ onDone, onNavigate }) {
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
    onDone();
  };

  return (
    <form onSubmit={submit} style={{ display: "grid", gap: 8 }}>
      <input
        type="email"
        value={email}
        autoComplete="username"
        placeholder="you@example.com"
        onChange={(event) => setEmail(event.target.value)}
        style={INPUT}
      />
      <input
        type="password"
        value={password}
        autoComplete="current-password"
        placeholder="Password"
        onChange={(event) => setPassword(event.target.value)}
        style={INPUT}
      />
      {error ? (
        <span style={{ fontSize: 11.5, color: C.coral, lineHeight: 1.5 }}>{error}</span>
      ) : null}
      <button
        type="submit"
        disabled={busy || !email || !password}
        style={{
          padding: "7px 12px",
          borderRadius: 8,
          border: "none",
          background: busy || !email || !password ? C.dim : C.accent,
          color: C.white,
          fontSize: 12.5,
          fontWeight: 700,
          cursor: busy || !email || !password ? "default" : "pointer",
          fontFamily: "inherit",
        }}
      >
        {busy ? "Signing in…" : "Sign in"}
      </button>
      {onNavigate ? (
        <Link onClick={() => onNavigate("#/classic")}>
          No account yet? Sign up on the onboarding pages →
        </Link>
      ) : null}
    </form>
  );
}

export default function AccountMenu({ onNavigate }) {
  const { signedIn, ready, email, name, profile, profileState, reloadProfile } = useAccount();
  const [open, setOpen] = useState(false);
  const box = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const away = (event) => {
      if (box.current && !box.current.contains(event.target)) setOpen(false);
    };
    const key = (event) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", key);
    };
  }, [open]);

  if (!hasSupabaseEnv) {
    return (
      <span style={{ fontSize: 10.5, color: C.muted }} title="VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY are missing from this build.">
        sign-in not configured
      </span>
    );
  }

  const initial = (name || "?").trim().charAt(0).toUpperCase();

  return (
    <div ref={box} style={{ position: "relative" }}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: signedIn ? "5px 11px 5px 5px" : "7px 13px",
          borderRadius: 999,
          border: `1px solid ${C.border}`,
          background: C.white,
          color: C.subtext,
          fontSize: 12.5,
          fontWeight: 600,
          cursor: "pointer",
          fontFamily: "inherit",
        }}
      >
        {signedIn ? (
          <>
            <span
              style={{
                width: 24,
                height: 24,
                borderRadius: 999,
                background: C.accent,
                color: C.white,
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 11.5,
                fontWeight: 700,
              }}
            >
              {initial}
            </span>
            {name}
          </>
        ) : (
          // `ready` is false only for the moment before Supabase answers from
          // local storage; saying "Sign in" then and switching to a name is
          // worse than one neutral word.
          <>{ready ? "Sign in" : "Account"}</>
        )}
      </button>

      {open ? (
        <div
          style={{
            position: "absolute",
            top: "100%",
            right: 0,
            zIndex: 40,
            marginTop: 6,
            width: 272,
            borderRadius: 12,
            border: `1px solid ${C.border}`,
            background: C.surface,
            boxShadow: "0 10px 30px rgba(0,0,0,0.14)",
            display: "flex",
            flexDirection: "column",
            maxHeight: "min(70vh, 440px)",
            overflow: "hidden",
            textAlign: "left",
          }}
        >
          <div style={{ flex: "1 1 auto", minHeight: 0, overflowY: "auto", padding: 12, display: "grid", gap: 10 }}>
            {!signedIn ? (
              <>
                <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.4, color: C.muted, textTransform: "uppercase" }}>
                  Sign in
                </span>
                <SignInForm onDone={() => setOpen(false)} onNavigate={onNavigate} />
              </>
            ) : (
              <>
                <div style={{ display: "grid", gap: 1 }}>
                  <span style={{ fontSize: 14, fontWeight: 700, color: C.navy }}>{name}</span>
                  <span style={{ fontSize: 11, color: C.muted }}>{email}</span>
                </div>

                {profileState === "ready" && profile ? (
                  <div style={{ display: "grid", gap: 8, paddingTop: 2 }}>
                    <Row label="Eats">
                      {[profile.diet_type, profile.goal?.replace(/_/g, " ")].filter(Boolean).join(" · ") || null}
                    </Row>
                    <Row label="Avoids">{profile.allergies?.length ? profile.allergies.join(", ") : null}</Row>
                    <Row label="Likes">{profile.preferences?.length ? profile.preferences.join(", ") : null}</Row>
                  </div>
                ) : null}

                {profileState === "loading" ? (
                  <span style={{ fontSize: 11.5, color: C.muted, lineHeight: 1.55 }}>
                    Loading your profile… the API sleeps when idle, so the first call can take a
                    while.
                  </span>
                ) : null}

                {profileState === "none" ? (
                  <span style={{ fontSize: 11.5, color: C.subtext, lineHeight: 1.55 }}>
                    This account has no profile yet. Signing up creates the account; the diet,
                    allergies and targets come from the onboarding questions.
                  </span>
                ) : null}

                {profileState === "error" ? (
                  <span style={{ fontSize: 11.5, color: C.coral, lineHeight: 1.55 }}>
                    Could not reach the profile API.{" "}
                    <button
                      type="button"
                      onClick={reloadProfile}
                      style={{ border: "none", background: "transparent", padding: 0, color: C.accent, fontWeight: 700, cursor: "pointer", fontSize: 11.5, fontFamily: "inherit" }}
                    >
                      Try again
                    </button>
                  </span>
                ) : null}
              </>
            )}
          </div>

          {signedIn ? (
            <div style={{ flex: "0 0 auto", borderTop: `1px solid ${C.border}`, padding: "6px 12px 10px", display: "grid" }}>
              {onNavigate ? (
                <>
                  <Link onClick={() => { setOpen(false); onNavigate("#/recommend"); }}>
                    Today&rsquo;s recommendations
                  </Link>
                  <Link onClick={() => { setOpen(false); onNavigate("#/admin"); }}>
                    Rules and review queue
                  </Link>
                </>
              ) : null}
              <Link
                tone={C.coral}
                onClick={async () => {
                  setOpen(false);
                  await signOut();
                }}
              >
                Sign out
              </Link>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
