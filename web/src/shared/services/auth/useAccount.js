// Who is signed in, and what we know about them.
//
// Two sources, deliberately kept apart:
//
//   the session   arrives immediately from Supabase, and carries the email and
//                 whatever name was given at signup. Enough to draw a header.
//   the profile   is a request to our own API, and can be slow - the free
//                 Render instance sleeps, so a cold start is tens of seconds -
//                 or absent, because signing up writes an account and the
//                 profile only appears once the questionnaire is done.
//
// So the header never waits on the profile. It shows the name from the session
// and fills in the diet, goal, allergies and preferences when they arrive.
// `profileState` says which of those happened, because "no profile yet" and
// "the request failed" need different words on screen and look identical if
// both are just a null.
import { useEffect, useState } from "react";
import { getSession, onAuthChange } from "./authStore";
import { getMyProfile } from "../api/profile";

export function nameOf(session, profile) {
  return (
    profile?.name ||
    session?.user?.user_metadata?.full_name ||
    session?.user?.user_metadata?.username ||
    session?.user?.email?.split("@")[0] ||
    "there"
  );
}

export function useAccount() {
  const [session, setSession] = useState(null);
  const [ready, setReady] = useState(false);
  // One record per answered request, tagged with the account it answered for.
  // Keeping the account in the record is what lets "loading" be derived: a
  // record for a different account than the current one is, by definition,
  // not yet loaded. The alternative - setting a loading flag when the effect
  // starts - is a synchronous setState inside an effect, which React now
  // warns about because it renders twice for one change.
  const [fetched, setFetched] = useState(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let live = true;
    getSession().then((found) => {
      if (!live) return;
      setSession(found);
      setReady(true);
    });
    // The subscription covers sign-out and token refresh as well, so the
    // header does not need to be told about either by whoever changed it.
    const stop = onAuthChange((next) => {
      if (live) setSession(next);
    });
    return () => {
      live = false;
      stop();
    };
  }, []);

  const userId = session?.user?.id || null;

  useEffect(() => {
    if (!userId) return undefined;
    let live = true;
    getMyProfile()
      .then((data) =>
        live &&
        setFetched({
          key: userId,
          profile: data.profile,
          targets: data.targets || [],
          household: data.household || [],
          failed: false,
        }),
      )
      .catch(
        () =>
          live &&
          setFetched({ key: userId, profile: null, targets: [], household: [], failed: true }),
      );
    return () => {
      live = false;
    };
  }, [userId, attempt]);

  const current = fetched && fetched.key === userId ? fetched : null;
  const profileState = !userId
    ? "signed_out"
    : !current
      ? "loading"
      : current.failed
        ? "error"
        : current.profile
          ? "ready"
          : "none";

  return {
    session,
    ready,
    signedIn: Boolean(session),
    email: session?.user?.email || null,
    name: nameOf(session, current?.profile),
    profile: current?.profile || null,
    targets: current?.targets || [],
    household: current?.household || [],
    profileState,
    reloadProfile: () => setAttempt((n) => n + 1),
  };
}
